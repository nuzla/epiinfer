"""Rolling-origin forecasting and one-shot future forecasts."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .calibrate import continuous_calibrate, estimate_p1
from .config import CALIBRATED_METHODS, EMPIRICAL_METHOD, METHODS, OPENABM, PAPER, Config
from .core import EpiInferCore
from .data import Dataset, load_dataset
from .metrics import fractional_rmse, rmse

log = logging.getLogger("epiinfer")


def sim_rng(seed: int, day: int, sim: int) -> np.random.RandomState:
    """Independent stream per (seed, forecast day, trajectory): results do not depend
    on thread count or execution order."""
    state = np.random.SeedSequence([int(seed), int(day), int(sim)]).generate_state(1)[0]
    return np.random.RandomState(int(state))


def build_model(data: Dataset, cfg: Config) -> EpiInferCore:
    return EpiInferCore(range(data.population_total), data.daily_contacts, data.age_of,
                        cfg.inc, cfg.duration, n_groups=data.n_groups)


def _lookback(method: str, model: EpiInferCore) -> int:
    """Days of observed history used to seed a forecast.

    The empirical method seeds ``inc + duration + 1`` days (as in the original script). The
    grid methods used a fixed 8 days, tuned for inc = duration = 7; it is widened when a
    longer ``inc`` or ``duration`` would otherwise drop A or I cohorts from the seed.
    """
    if method == EMPIRICAL_METHOD:
        return model.inc + model.duration + 1
    return max(8, model.inc + 1, model.duration + 1)


def _graph_until(cfg: Config, origin: int) -> int | None:
    return origin if cfg.contacts == "frozen" else None


def _check_method(method: str) -> None:
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {METHODS}")


def estimate_rates(method, model, data, cfg, day, prev_p1, prev_p2, na, ni):
    """One day's (p1, p2) for ``method``."""
    if method == EMPIRICAL_METHOD:
        p1 = estimate_p1(model, data, day, cfg, prev_p1)
        return p1, np.full(model.n_groups, cfg.p2_fixed)
    observed = {g: {d: data.gt_group[g].get(d, 0)
                    for d in range(max(0, day - cfg.calib_window), day + 1)}
                for g in range(model.n_groups)}
    return continuous_calibrate(model, method, observed, day, na, ni,
                                data.recovered_on, cfg, prev_p1, prev_p2)


def _history(data, na, ni, day, lookback):
    h_a = {k: na[k] for k in range(day - lookback, day + 1) if k in na}
    h_i = {k: ni[k] for k in range(day - lookback, day + 1) if k in ni}
    return h_a, h_i


def monte_carlo(model, p1, p2, h_a, h_i, day, end_day, seed_rec, cfg, pool=None):
    """Average ``cfg.num_sims`` trajectories; returns ``{day: per-group mean counts}``."""
    graph_until = _graph_until(cfg, day)

    def one(i):
        return model.project(p1, p2, h_a, h_i, day, end_day, seed_rec, sim_rng(cfg.seed, day, i),
                             graph_until)
    sims = list(pool.map(one, range(cfg.num_sims))) if pool else \
        [one(i) for i in range(cfg.num_sims)]
    agg: dict[int, np.ndarray] = {}
    for res in sims:
        for d, vec in res.items():
            agg[d] = agg.get(d, np.zeros(model.n_groups)) + vec
    return {d: v / cfg.num_sims for d, v in agg.items()}


@dataclass
class ForecastResult:
    """Output of :func:`rolling_forecast`."""
    method: str
    dataset: str
    config: Config
    rows: pd.DataFrame            # one row per (group, horizon, origin day)
    rates: pd.DataFrame           # fitted p1_g / p2_g per origin day
    age_labels: list

    def summary(self) -> pd.DataFrame:
        """RMSE and fractional RMSE per group and horizon (the paper's table cells)."""
        out = []
        for grp in [*self.age_labels, "ALL"]:
            sub = self.rows[self.rows["group"] == grp]
            for h in self.config.horizons:
                s = sub[sub["horizon"] == h]
                if s.empty:
                    continue
                p, a = s["predicted"].to_numpy(), s["actual"].to_numpy()
                out.append({"dataset": self.dataset, "method": self.method, "group": grp,
                            "horizon": h, "n": len(s), "rmse": rmse(p, a),
                            "frmse": fractional_rmse(p, a)})
        return pd.DataFrame(out)


def rolling_forecast(model, data: Dataset, method: str, cfg: Config, quiet: bool = False
                     ) -> ForecastResult:
    """Walk forward day by day: estimate rates, project ``cfg.num_sims`` trajectories to the
    furthest horizon, average, and record predicted-vs-actual per horizon."""
    _check_method(method)
    na, ni = data.transitions("strict" if method == EMPIRICAL_METHOD else "diff")
    n = model.n_groups
    labels = data.age_labels
    last_day = max(data.all_days)
    max_day = min(cfg.max_day, last_day + 1)
    start = cfg.start_eval
    if max_day <= start:
        start = max(model.inc + model.duration + 1, max_day - 10)
        log.info("data ends day %s; lowering start_eval to %s", last_day, start)

    lookback = _lookback(method, model)
    use_threads = cfg.mc_threads > 1 and cfg.num_sims > 1
    pool = ThreadPoolExecutor(max_workers=min(cfg.mc_threads, cfg.num_sims)) if use_threads else None
    rows, rates = [], []
    prev_p1 = prev_p2 = None
    stop = max_day if cfg.last_origin is None else min(max_day, cfg.last_origin + 1)
    try:
        for day in range(start, stop):
            p1, p2 = estimate_rates(method, model, data, cfg, day, prev_p1, prev_p2, na, ni)
            prev_p1, prev_p2 = p1, p2
            rates.append({"day": day, **{f"p1_{g}": float(p1[g]) for g in range(n)},
                          **{f"p2_{g}": float(p2[g]) for g in range(n)}})
            if not quiet and day % 10 == 0:
                log.info("[%s] day %3d p1=%s p2=%s", method, day,
                         np.round(p1, 4).tolist(), np.round(p2, 3).tolist())
            h_a, h_i = _history(data, na, ni, day, lookback)
            end_pred = min(day + max(cfg.horizons) + 1, max_day)
            avg = monte_carlo(model, p1, p2, h_a, h_i, day, end_pred,
                              data.recovered_on.get(day, set()), cfg, pool)
            for h in cfg.horizons:
                tgt = day + h
                if tgt not in avg or tgt > last_day:   # never score against a missing day
                    continue
                pv = avg[tgt]
                for g in range(n):
                    rows.append({"group": labels[g], "horizon": h, "current_day": day,
                                 "target_day": tgt, "predicted": float(pv[g]),
                                 "actual": data.gt_group[g].get(tgt, 0),
                                 "p1_used": float(p1[g]), "p2_used": float(p2[g])})
                rows.append({"group": "ALL", "horizon": h, "current_day": day, "target_day": tgt,
                             "predicted": float(pv.sum()), "actual": data.gt_total.get(tgt, 0),
                             "p1_used": float("nan"), "p2_used": float("nan")})
    finally:
        if pool is not None:
            pool.shutdown(wait=True)
    return ForecastResult(method, data.name, cfg, pd.DataFrame(rows), pd.DataFrame(rates), labels)


def default_config(method: str) -> Config:
    """Paper settings for grid methods, OpenABM settings for ``empirical_p1``."""
    _check_method(method)
    return OPENABM if method == EMPIRICAL_METHOD else PAPER


def run(data: Dataset | str | Path, method: str = "unknown_both", cfg: Config | None = None,
        **overrides) -> ForecastResult:
    """Rolling-origin evaluation on a dataset (object or folder path).

    ``overrides`` are applied to the config, e.g. ``run(path, "empirical_p1", num_sims=5)``.
    """
    if not isinstance(data, Dataset):
        data = load_dataset(data)
    cfg = (cfg or default_config(method)).with_(**overrides)
    return rolling_forecast(build_model(data, cfg), data, method, cfg)


def forecast(data: Dataset | str | Path, horizon: int = 14, method: str = "unknown_both",
             cfg: Config | None = None, from_day: int | None = None, warmup: int = 6,
             **overrides) -> pd.DataFrame:
    """Forecast symptomatic counts for the ``horizon`` days after ``from_day``.

    ``from_day`` defaults to the last observed day; contacts after it are never used
    (``cfg.contacts`` is ignored here). The smoothed rate estimate is warmed up
    over the ``warmup`` days before it (smoothing 0.5 forgets the neutral prior in ~5 days;
    ignored for ``empirical_p1``, which refits from scratch each day). Contacts beyond the
    recorded graph are held at the last recorded day. Returns one row per (group, target day) with the
    Monte-Carlo ``mean`` and the 10th/90th percentile across trajectories, plus the
    ``actual`` count where the data already contains it (NaN for genuine future days).
    """
    _check_method(method)
    if not isinstance(data, Dataset):
        data = load_dataset(data)
    cfg = (cfg or default_config(method)).with_(**overrides)
    model = build_model(data, cfg)
    na, ni = data.transitions("strict" if method == EMPIRICAL_METHOD else "diff")
    last = max(data.all_days)
    first = model.inc + model.duration + 1
    day = last if from_day is None else int(from_day)
    if not first <= day <= last:
        raise ValueError(f"from_day must be between {first} (inc + duration + 1) and the last "
                         f"observed day {last}; got {day}")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    n = model.n_groups
    prev_p1 = prev_p2 = None
    start = day if method == EMPIRICAL_METHOD else max(first, day - warmup)
    for d in range(start, day + 1):
        prev_p1, prev_p2 = estimate_rates(method, model, data, cfg, d, prev_p1, prev_p2, na, ni)
    p1, p2 = prev_p1, prev_p2
    h_a, h_i = _history(data, na, ni, day, _lookback(method, model))
    end = day + horizon + 1
    seed_rec = data.recovered_on.get(day, set())
    trajectories = [model.project(p1, p2, h_a, h_i, day, end, seed_rec,
                                  sim_rng(cfg.seed, day, i), graph_until=day)
                    for i in range(cfg.num_sims)]
    out = []
    for t in range(day + 1, end):
        stack = np.stack([tr[t] for tr in trajectories])          # sims x groups
        for g in range(n + 1):
            vals = stack.sum(axis=1) if g == n else stack[:, g]
            observed = t <= last
            actual = (data.gt_total.get(t, 0) if g == n else data.gt_group[g].get(t, 0)) \
                if observed else float("nan")
            out.append({"group": "ALL" if g == n else data.age_labels[g], "origin_day": day,
                        "target_day": t, "horizon": t - day, "mean": float(vals.mean()),
                        "p10": float(np.percentile(vals, 10)),
                        "p90": float(np.percentile(vals, 90)), "actual": float(actual)})
    return pd.DataFrame(out)


__all__ = ["CALIBRATED_METHODS", "ForecastResult", "build_model", "forecast", "monte_carlo",
           "rolling_forecast", "run", "sim_rng"]
