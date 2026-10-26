"""Rolling-origin forecasting and one-shot future forecasts."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .calibrate import continuous_calibrate, estimate_p1
from .config import (
    CALIBRATED_METHODS,
    COMPARTMENTAL,
    EMPIRICAL_METHOD,
    ENGINES,
    FINAL,
    METHODS,
    OPENABM,
    PAPER,
    Config,
)
from .core import EpiInferCore
from .data import Dataset, load_dataset
from .metrics import fractional_rmse, relative_rmse, rmse

log = logging.getLogger("epiinfer")

#: columns of ``ForecastResult.rows`` (also when nothing could be scored) and of ``summary()``
ROW_COLUMNS = ["group", "horizon", "current_day", "target_day", "predicted", "actual",
               "p1_used", "p2_used"]
SUMMARY_COLUMNS = ["dataset", "method", "group", "horizon", "n", "rmse", "frmse", "frmse_rel"]


def sim_rng(seed: int, day: int, sim: int) -> np.random.RandomState:
    """Independent stream per (seed, forecast day, trajectory): results do not depend
    on thread count or execution order."""
    state = np.random.SeedSequence([int(seed), int(day), int(sim)]).generate_state(1)[0]
    return np.random.RandomState(int(state))


def build_model(data: Dataset, cfg: Config) -> EpiInferCore:
    return EpiInferCore(range(data.population_total), data.daily_contacts, data.age_of,
                        cfg.inc, cfg.duration, n_groups=data.n_groups,
                        contact_offset=cfg.contact_offset)


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


def _need_presymptomatic(data: Dataset) -> None:
    """The 2025 engine seeds every forecast with who is in A. Without a single A record it
    would silently forecast that nobody new gets infected (a flat, zero-width band)."""
    if not any(data.asymp_on.get(d) for d in data.all_days):
        raise ValueError(
            "the contact engine needs the pre-symptomatic state (state 1 in "
            "individual_day_state.csv), and this dataset records none. Use the default final "
            "engine instead (--engine final): it needs only symptomatic and recovered people.")


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
        """RMSE per group and horizon, with both fRMSE definitions the paper has used:
        ``frmse`` = RMSE / mean(actual) (2025 tables) and ``frmse_rel`` = root mean squared
        relative error over targets with a non-zero actual (October 2026, Tables 10-13).
        Empty (with its columns) when no forecast could be scored."""
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
                            "frmse": fractional_rmse(p, a), "frmse_rel": relative_rmse(p, a)})
        return pd.DataFrame(out, columns=SUMMARY_COLUMNS)


def rolling_forecast(model, data: Dataset, method: str, cfg: Config, quiet: bool = False
                     ) -> ForecastResult:
    """Walk forward day by day: estimate rates, project ``cfg.num_sims`` trajectories to the
    furthest horizon, average, and record predicted-vs-actual per horizon."""
    _check_method(method)
    _need_presymptomatic(data)
    na, ni = data.transitions("strict" if method == EMPIRICAL_METHOD else "diff")
    n = model.n_groups
    labels = data.age_labels
    last_day = max(data.all_days)
    max_day = min(cfg.max_day, last_day + 1)
    start = cfg.start_eval
    if max_day <= start:
        start = max(model.inc + model.duration + 1, max_day - 10)
        log.info("data ends day %s; lowering start_eval to %s", last_day, start)

    if method in ("known_p1", "known_p2", "unknown_both") and start < model.inc + model.duration:
        # earlier, the calibration window is empty, every candidate scores inf and the "best"
        # rate would silently be the last grid value
        raise ValueError(f"method {method!r} needs start_eval >= inc + duration = "
                         f"{model.inc + model.duration} (calibration needs that much history); "
                         f"got {start}")
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
    return ForecastResult(method, data.name, cfg, pd.DataFrame(rows, columns=ROW_COLUMNS),
                          pd.DataFrame(rates), labels)


def default_config(method: str, engine: str | None = None) -> Config:
    """The preset for ``method``: OpenABM settings for ``empirical_p1``; otherwise the final
    (October 2026) engine, the 2025 contact engine with ``engine="contact"``, or the earlier
    compartmental EpiInfer with ``engine="compartmental"``."""
    _check_method(method)
    if method == EMPIRICAL_METHOD:
        return OPENABM
    engine = engine or "final"
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}, got {engine!r}")
    return {"final": FINAL, "contact": PAPER, "compartmental": COMPARTMENTAL}[engine]


def _resolve(method: str, cfg: Config | None, overrides: dict) -> Config:
    engine = overrides.pop("engine", None)
    base = cfg if cfg is not None else default_config(method, engine)
    if engine is not None:
        base = base.with_(engine=engine)
    cfg = base.with_(**overrides)
    if cfg.engine != "contact" and method == EMPIRICAL_METHOD:
        raise ValueError("empirical_p1 exists only in the contact engine (engine='contact')")
    return cfg


# ---- final engine (October 2026) --------------------------------------------------------
def final_settings(cfg: Config):
    """The :class:`epiinfer.final.FinalSettings` equivalent of a :class:`Config`."""
    from .final import FinalSettings
    return FinalSettings(inc=cfg.inc, inf_dur=cfg.duration, rec_dur=cfg.rec_duration,
                         start_day=cfg.start_eval, end_day=cfg.max_day,
                         horizons=tuple(cfg.horizons), n_mc=cfg.num_sims,
                         grid=tuple(cfg.final_grid), calib_window=cfg.final_calib_window,
                         score_h=cfg.score_horizon, recalib_every=cfg.recalib_every,
                         lam=cfg.lambda_damp, seed_offset=1_000_003 * cfg.seed)


def _scalar_truth(cfg: Config, method: str) -> tuple[float | None, float | None]:
    """The final and compartmental engines use one (p1, p2) for everyone."""
    def one(values, name):
        if values is None:
            return None
        vals = {float(v) for v in values}
        if len(vals) != 1:
            raise ValueError(f"the {cfg.engine} engine uses one {name} for the whole population; "
                             f"got {tuple(values)}. Use engine='contact' for per-group rates.")
        return vals.pop()
    need1 = method in ("known_both", "known_p1")
    need2 = method in ("known_both", "known_p2")
    p1 = one(cfg.p1_true, "p1") if need1 else None
    p2 = one(cfg.p2_true, "p2") if need2 else None
    if (need1 and p1 is None) or (need2 and p2 is None):
        raise ValueError(f"method {method!r} needs the true rate(s): pass p1_true=... / p2_true=...")
    return p1, p2


def _final_data(data, max_day: int | None):
    """``max_day``: read only the days up to it (a back-test's protocol); ``None``: all days."""
    from .final import FinalData
    if isinstance(data, FinalData):
        return data
    if isinstance(data, Dataset):
        return FinalData.from_dataset(data)
    return FinalData.from_folder(data, max_day=max_day)


def _run_final(data, method: str, cfg: Config) -> ForecastResult:
    from .final import run_final
    name = data.name if isinstance(data, Dataset) else Path(str(data)).name
    fd = _final_data(data, cfg.max_day)
    p1, p2 = _scalar_truth(cfg, method)
    settings = final_settings(cfg)
    pred, _ = run_final(fd, (method,), p1, p2, settings, last_origin=cfg.last_origin)
    rows = pd.DataFrame({"group": "ALL", "horizon": pred["horizon"], "current_day": pred["origin"],
                         "target_day": pred["target_day"], "predicted": pred["predicted"],
                         "actual": pred["actual"], "p1_used": pred["p1_used"],
                         "p2_used": pred["p2_used"]}) if len(pred) else pd.DataFrame(
        columns=ROW_COLUMNS)
    rates = (rows[["current_day", "p1_used", "p2_used"]].drop_duplicates("current_day")
             .rename(columns={"current_day": "day", "p1_used": "p1", "p2_used": "p2"})
             .reset_index(drop=True))
    return ForecastResult(method, name, cfg, rows, rates, [])


def _load_until(from_day, horizon: int) -> int | None:
    """Days a one-shot forecast reads: those up to ``from_day + horizon`` (the observed part of
    the forecast window is shown as ``actual``), or all of them when forecasting from the end.
    ``Config.max_day`` limits back-tests only; applying it here made data longer than 100 days
    be forecast from day 100."""
    return None if from_day is None else int(from_day) + int(horizon)


def _forecast_final(data, horizon: int, method: str, cfg: Config, from_day) -> pd.DataFrame:
    from .final import FinalCore, calibrate_at, first_origin
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    fd = _final_data(data, _load_until(from_day, horizon))
    p1t, p2t = _scalar_truth(cfg, method)
    settings = final_settings(cfg)
    last = fd.T - 1
    day = last if from_day is None else int(from_day)
    first = first_origin(method, settings)
    if not first <= day <= last:
        raise ValueError(f"from_day must be between {first} and the last observed day {last}; "
                         f"got {day}")
    p1, p2 = calibrate_at(fd, method, day, p1t, p2t, settings)
    trajs = FinalCore(fd, settings).trajectories(day, p1, p2, horizon, cfg.num_sims,
                                                  seed=day * 104729 + settings.seed_offset)
    out = []
    for t in range(day + 1, day + horizon + 1):
        vals = np.array([tr[t] for tr in trajs])
        out.append({"group": "ALL", "origin_day": day, "target_day": t, "horizon": t - day,
                    "mean": float(vals.mean()), "p10": float(np.percentile(vals, 10)),
                    "p90": float(np.percentile(vals, 90)),
                    "actual": float(fd.gt[t]) if t <= last else float("nan"),
                    "p1_used": float(p1), "p2_used": float(p2)})
    return pd.DataFrame(out)


# ---- compartmental engine (the earlier EpiInfer) -------------------------------------------
def _group_counts(data, max_day: int | None):
    """``max_day``: read only the days up to it (a back-test's protocol); ``None``: all days."""
    from .compartmental import GroupCounts
    if isinstance(data, GroupCounts):
        return data
    if isinstance(data, Dataset):
        raise TypeError("the compartmental engine reads the dataset folder; pass its path")
    return GroupCounts.from_folder(data, max_day=max_day)


def _run_compartmental(data, method: str, cfg: Config) -> ForecastResult:
    """Origins are the last observed day, as in the other engines: the notebooks' origin
    ``o`` (the first projected day) is ``current_day + 1``."""
    from .compartmental import min_origin, run_compartmental
    name = Path(str(data)).name
    need = min_origin(method, cfg.inc) - 1               # an origin o is current_day + 1
    if cfg.start_eval < need:
        raise ValueError(f"method {method!r}: start_eval must be {need} or later for the "
                         f"compartmental engine (inc days of history, plus a 5-day calibration "
                         f"window when a rate is searched); got {cfg.start_eval}")
    gc = _group_counts(data, cfg.max_day)
    p1, p2 = _scalar_truth(cfg, method)
    last = cfg.last_origin if cfg.last_origin is not None else cfg.max_day - max(cfg.horizons) - 1
    pred = run_compartmental(gc, (method,), p1, p2, tuple(h - 1 for h in cfg.horizons),
                             cfg.start_eval + 1, last + 1, cfg.group_contacts, cfg.inc,
                             1 / cfg.duration, freeze=cfg.contacts == "frozen")
    rows = pd.DataFrame({"group": "ALL", "horizon": pred["horizon"] + 1,
                         "current_day": pred["origin"] - 1, "target_day": pred["target_day"],
                         "predicted": pred["predicted"], "actual": pred["actual"],
                         "p1_used": pred["p1_used"], "p2_used": pred["p2_used"]}
                        )[ROW_COLUMNS] if len(pred) else pd.DataFrame(columns=ROW_COLUMNS)
    rates = (rows[["current_day", "p1_used", "p2_used"]].drop_duplicates("current_day")
             .rename(columns={"current_day": "day", "p1_used": "p1", "p2_used": "p2"})
             .reset_index(drop=True))
    return ForecastResult(method, name, cfg, rows, rates, [])


def _forecast_compartmental(data, horizon: int, method: str, cfg: Config, from_day
                            ) -> pd.DataFrame:
    from .compartmental import CALIB_WINDOW, calibrate, simulate
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    gc = _group_counts(data, _load_until(from_day, horizon))
    p1t, p2t = _scalar_truth(cfg, method)
    last = gc.days - 1
    day = last if from_day is None else int(from_day)
    first = cfg.inc + CALIB_WINDOW
    if not first <= day <= last:
        raise ValueError(f"from_day must be between {first} and the last observed day {last}; "
                         f"got {day}")
    p1, p2 = calibrate(gc, method, day + 1, p1t, p2t, cfg.group_contacts, cfg.inc,
                       1 / cfg.duration)
    sim = simulate(gc, p1, p2, day + 1, horizon, cfg.group_contacts, cfg.inc, 1 / cfg.duration,
                   freeze_after=day)
    return pd.DataFrame([{"group": "ALL", "origin_day": day, "target_day": t, "horizon": t - day,
                          "mean": float(sim[t, 0]), "p10": float(sim[t, 0]),
                          "p90": float(sim[t, 0]),
                          "actual": float(gc.I[t, 0]) if t <= last else float("nan"),
                          "p1_used": float(p1), "p2_used": float(p2)}
                         for t in range(day + 1, day + horizon + 1)])


# ---- public entry points ------------------------------------------------------------------
def run(data, method: str = "unknown_both", cfg: Config | None = None,
        **overrides) -> ForecastResult:
    """Rolling-origin back-test on a dataset (folder path, :class:`Dataset` or ``FinalData``).

    Uses the final (October 2026) engine unless ``engine="contact"`` or
    ``engine="compartmental"`` (or a config such as :data:`PAPER`) is given; ``empirical_p1``
    always uses the contact engine. ``overrides`` are applied to the config, e.g.
    ``run(path, "unknown_both", num_sims=5)``.
    """
    _check_method(method)
    cfg = _resolve(method, cfg, dict(overrides))
    if cfg.engine == "final":
        return _run_final(data, method, cfg)
    if cfg.engine == "compartmental":
        return _run_compartmental(data, method, cfg)
    if not isinstance(data, Dataset):
        data = load_dataset(data, max_day=cfg.max_day)    # nothing after max_day is ever used
    return rolling_forecast(build_model(data, cfg), data, method, cfg)


def forecast(data, horizon: int = 14, method: str = "unknown_both",
             cfg: Config | None = None, from_day: int | None = None, warmup: int = 6,
             **overrides) -> pd.DataFrame:
    """Forecast symptomatic counts for the ``horizon`` days after ``from_day``.

    ``from_day`` defaults to the last observed day of the whole dataset (``Config.max_day``
    limits back-tests, not forecasts); contacts after it are never used. Returns
    one row per (group, target day) with the Monte-Carlo ``mean`` and the 10th/90th percentile
    across trajectories, plus the ``actual`` count where the data already has it (NaN for
    genuine future days). Engine selection as in :func:`run`.

    Final engine: rates are calibrated on the data up to ``from_day`` (needs ``from_day`` >=
    2*inc + 1 + score_horizon = 22 unless both rates are known); only the total is forecast.
    Contact engine: the smoothed rate estimate is warmed up over ``warmup`` days before
    ``from_day`` and every age group is forecast.
    Compartmental engine: deterministic, so ``p10`` = ``p90`` = ``mean``; contacts after
    ``from_day`` are held at that day's.
    """
    _check_method(method)
    cfg = _resolve(method, cfg, dict(overrides))
    if cfg.engine == "final":
        return _forecast_final(data, horizon, method, cfg, from_day)
    if cfg.engine == "compartmental":
        return _forecast_compartmental(data, horizon, method, cfg, from_day)
    if not isinstance(data, Dataset):
        data = load_dataset(data)
    _need_presymptomatic(data)
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
