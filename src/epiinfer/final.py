"""The final EpiInfer-contact method of the October 2026 paper (``abm_final.ipynb``).

A faithful port: same algorithm, same random-number calls and seeds, so it reproduces the
authors' notebook exactly (``tests/test_final_engine.py`` checks it against the notebook's own
code). Differences from the 2025 ("contact") engine in :mod:`epiinfer.core`:

* **No pre-symptomatic (A) data needed.** The exposure history is rebuilt from observed
  infections: people first seen infected on day e+inc were exposed on day e, plus
  ``n/p2 - n`` unobserved exposures drawn (weighted by contacts) from people free to be
  exposed that day. Only the I and R states and the contact list are read.
* **Recovered people return to susceptible** after ``rec_duration`` days (SEIRS).
* **Contacts.** Day t's contacts create day t's exposures while rolling forward over observed
  days; after the forecast origin o, every day reuses day o's contacts (no look-ahead).
* **Calibration.** Every ``recalib_every`` origins, score each candidate with 7-day forecasts
  launched from the origins of the last ``calib_window`` days (targets never after the
  training day), over a 0.05-0.30 grid, jointly for both rates when both are unknown; then
  damp: ``theta <- prev + (best - prev) * min(1, max(0, r_prev - r_best) / r_prev * lambda)``.
* **Metric.** The paper's fRMSE is the root mean squared *relative* error over targets with a
  non-zero actual count (:func:`summarize_relative`).

One (p1, p2) applies to the whole population.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import DataFormatError, _read_until

NEVER = 10**6                       # "never happens" day index
CASES = ("known_both", "known_p1", "known_p2", "unknown_both")
DEFAULT_GRID = tuple(float(x) for x in np.round(np.arange(0.05, 0.30 + 1e-9, 0.025), 4))


@dataclass(frozen=True)
class FinalSettings:
    """The notebook's configuration block (defaults are the paper's values)."""
    inc: int = 7
    inf_dur: int = 7
    rec_dur: int = 7
    start_day: int = 25
    end_day: int = 100
    horizons: tuple[int, ...] = (1, 5, 10, 20)
    n_mc: int = 30
    grid: tuple[float, ...] = DEFAULT_GRID
    calib_window: int = 14
    score_h: int = 7
    eval_stride: int = 1
    recalib_every: int = 5
    lam: float = 1.0
    recon_back: int | None = None   # default 4 * (inc + 1)
    seed_offset: int = 0            # 0 = the notebook's seeds; other values give other streams

    @property
    def last_origin(self) -> int:
        return self.end_day - max(self.horizons) - 1

    @property
    def back(self) -> int:
        return self.recon_back if self.recon_back is not None else 4 * (self.inc + 1)


class FinalData:
    """Observed data only: who is infected / recovered each day, and the daily contacts.

    Built from the daily state matrix ``S`` (days x people, int codes); only ``state_i`` and
    ``state_r`` are used, so the exposed (A) code is never read.
    """

    def __init__(self, S: np.ndarray, edges: dict, state_i: int = 2, state_r: int = 3):
        self.T, self.n = S.shape
        self.edges = edges
        self.is_inf = S == state_i
        self.is_rec = S == state_r
        prev_inf = np.zeros_like(self.is_inf)
        prev_inf[1:] = self.is_inf[:-1]
        prev_rec = np.zeros_like(self.is_rec)
        prev_rec[1:] = self.is_rec[:-1]
        self.new_inf = self.is_inf & ~prev_inf                 # onset of an infection spell that day
        self.onset_inf = np.full((self.T, self.n), NEVER, dtype=np.int64)
        self.onset_rec = np.full((self.T, self.n), NEVER, dtype=np.int64)
        for t in range(self.T):
            if t == 0:
                self.onset_inf[t][self.is_inf[t]] = 0
                self.onset_rec[t][self.is_rec[t]] = 0
                continue
            cont_i = self.is_inf[t] & prev_inf[t]
            self.onset_inf[t][cont_i] = self.onset_inf[t - 1][cont_i]
            self.onset_inf[t][self.new_inf[t]] = t
            cont_r = self.is_rec[t] & prev_rec[t]
            self.onset_rec[t][cont_r] = self.onset_rec[t - 1][cont_r]
            self.onset_rec[t][self.is_rec[t] & ~prev_rec[t]] = t
        self.gt = {t: int(self.is_inf[t].sum()) for t in range(self.T)}
        self._deg: dict[int, np.ndarray] = {}

    @classmethod
    def from_folder(cls, path: str | Path, max_day: int | None = None, n: int | None = None,
                    state_i: int = 2, state_r: int = 3) -> FinalData:
        """Read ``individual_day_state.csv`` (id, day, state) and ``timed_edges.csv`` (day, i, j).

        ``n`` (population) defaults to the sum of ``age_group_population.csv`` when present,
        otherwise the largest id + 1. People missing from a day's records count as neither
        infected nor recovered that day.
        """
        d = Path(path)
        if not d.is_dir():
            raise DataFormatError(f"dataset folder not found: {d}")
        st = _read_until(d / "individual_day_state.csv", ("id", "day", "state"), max_day)
        ed = _read_until(d / "timed_edges.csv", ("day", "i", "j"), max_day)
        if n is None:
            pop = d / "age_group_population.csv"
            n = int(pd.read_csv(pop)["population"].sum()) if pop.exists() else int(st["id"].max()) + 1
        for name, frame, cols in (("individual_day_state.csv", st, ("id",)),
                                  ("timed_edges.csv", ed, ("i", "j"))):
            for c in cols:
                if len(frame) and (frame[c].min() < 0 or frame[c].max() >= n):
                    raise DataFormatError(f"{name}: {c!r} ids must be 0..{n - 1}")
        T = int(st["day"].max()) + 1
        S = np.zeros((T, n), dtype=np.int8)
        S[st["day"].to_numpy(), st["id"].to_numpy()] = st["state"].to_numpy()
        edges = {int(day): (g["i"].to_numpy().astype(np.int32), g["j"].to_numpy().astype(np.int32))
                 for day, g in ed.groupby("day")}
        return cls(S, edges, state_i, state_r)

    @classmethod
    def from_dataset(cls, ds) -> FinalData:
        """Build from a :class:`epiinfer.data.Dataset` (uses only its I and R sets)."""
        T = max(ds.all_days) + 1
        S = np.zeros((T, ds.population_total), dtype=np.int8)
        for day in ds.all_days:
            for code, ids in ((2, ds.inf_on.get(day, ())), (3, ds.recovered_on.get(day, ()))):
                if ids:
                    S[day, np.fromiter(ids, np.int64, len(ids))] = code
        edges = {}
        for day, pairs in ds.daily_contacts.items():
            a = np.asarray(pairs, dtype=np.int32).reshape(-1, 2)
            edges[int(day)] = (a[:, 0].copy(), a[:, 1].copy())
        return cls(S, edges)

    def degree(self, day: int) -> np.ndarray:
        if day not in self._deg:
            i, j = self.edges.get(day, (np.empty(0, np.int32), np.empty(0, np.int32)))
            self._deg[day] = (np.bincount(i, minlength=self.n)
                              + np.bincount(j, minlength=self.n)).astype(float)
        return self._deg[day]

    def exposed_neighbours(self, day: int, vec: np.ndarray) -> np.ndarray:
        i, j = self.edges.get(day, (np.empty(0, np.int32), np.empty(0, np.int32)))
        return (np.bincount(i, weights=vec[j], minlength=self.n)
                + np.bincount(j, weights=vec[i], minlength=self.n))


class FinalCore:
    """EpiInfer-core with the exposure history rebuilt from infections."""

    def __init__(self, data: FinalData, settings: FinalSettings = FinalSettings()):  # noqa: B008
        self.d, self.s = data, settings
        self.inc, self.inf_dur, self.rec_dur, self.n = (settings.inc, settings.inf_dur,
                                                        settings.rec_dur, data.n)
        self._recon_cache: dict = {}

    def reconstruct(self, o: int, p2: float, sub_seed: int) -> np.ndarray:
        """Exposure day per person for the cohorts up to ``o - inc``, from infections only."""
        key = (o, round(float(p2), 6), sub_seed)
        hit = self._recon_cache.get(key)
        if hit is not None:
            return hit
        d, inc, n = self.d, self.inc, self.n
        rng = np.random.default_rng([sub_seed, o, int(round(p2 * 1e6))])
        exp_day = np.full(n, -NEVER, dtype=np.int64)
        for e in range(max(0, o - self.s.back), o - inc + 1):
            cohort = np.where(d.new_inf[e + inc])[0]
            exp_day[cohort] = e
            target = int(round(len(cohort) / p2))
            n_extra = target - len(cohort)
            if n_extra > 0:
                exposed_now = (exp_day > e - 1 - inc) & (exp_day <= e - 1)
                pending = d.new_inf[e + 1: e + inc + 1].any(axis=0)
                cand = ~d.is_inf[e] & ~d.is_rec[e] & ~pending & ~exposed_now
                w = d.degree(e) * cand
                pos = int((w > 0).sum())
                if pos == 0:                       # nobody with contacts: any free person
                    w = cand.astype(float)
                    pos = int(cand.sum())
                if pos > 0:
                    k = min(n_extra, pos)
                    chosen = rng.choice(n, size=k, replace=False, p=w / w.sum())
                    exp_day[chosen] = e
        if len(self._recon_cache) > 1500:
            self._recon_cache.clear()
        self._recon_cache[key] = exp_day
        return exp_day

    def nowcast(self, o: int, p1: float, p2: float, rng) -> np.ndarray:
        """Roll the rebuilt history forward over the last ``inc`` observed days."""
        d, inc, n = self.d, self.inc, self.n
        sub_seed = int(rng.integers(1 << 31))     # shared by every p1 at a seed: one reconstruction
        exp_day = self.reconstruct(o, p2, sub_seed).copy()
        for t in range(o - inc + 1, o + 1):
            exposed_prev = (exp_day > t - 1 - inc) & (exp_day <= t - 1)
            cnt = d.exposed_neighbours(t, exposed_prev.astype(float))
            susc = ~(d.is_inf[t] | d.is_rec[t] | exposed_prev)
            new = susc & (rng.random(n) < 1.0 - (1.0 - p1) ** cnt)
            exp_day[new] = t
        return exp_day

    def forecast(self, o: int, p1: float, p2: float, horizon: int, rng) -> dict[int, float]:
        """One trajectory: total infected on each day o+1 .. o+horizon."""
        d, inc, n, fd, rd = self.d, self.inc, self.n, self.inf_dur, self.rec_dur
        exp_day = self.nowcast(o, p1, p2, rng)
        inf_start = np.full(n, NEVER, dtype=np.int64)
        m_i = d.is_inf[o]
        inf_start[m_i] = d.onset_inf[o][m_i]
        m_r = d.is_rec[o]
        inf_start[m_r] = d.onset_rec[o][m_r] - fd
        out = {}
        for t in range(o + 1, o + horizon + 1):
            p = t - 1
            inf_f = (inf_start <= p) & (p < inf_start + fd)
            rec_f = (p >= inf_start + fd) & (p < inf_start + fd + rd)
            exposed_prev = (exp_day > p - inc) & (exp_day <= p)
            cnt = d.exposed_neighbours(o, exposed_prev.astype(float))   # contacts of day o
            susc = ~(inf_f | rec_f | exposed_prev)
            new = susc & (rng.random(n) < 1.0 - (1.0 - p1) ** cnt)
            exp_day[new] = t
            becomes = (exp_day == t - inc) & (rng.random(n) < p2)
            inf_start[becomes] = t
            out[t] = float(((inf_start <= t) & (t < inf_start + fd)).sum())
        return out

    def trajectories(self, o, p1, p2, horizon, n_runs, seed) -> list[dict[int, float]]:
        return [self.forecast(o, p1, p2, horizon, np.random.default_rng(seed + r))
                for r in range(n_runs)]

    def predict_mc(self, o, p1, p2, horizon, n_runs, seed) -> dict[int, float]:
        acc: dict[int, list[float]] = {}
        for traj in self.trajectories(o, p1, p2, horizon, n_runs, seed):
            for t, v in traj.items():
                acc.setdefault(t, []).append(v)
        return {t: float(np.mean(v)) for t, v in acc.items()}


class FinalCalibrator:
    """ContinuousCalibrate with Slow Learning, as in the notebook."""

    def __init__(self, core: FinalCore):
        self.core, self.s, self.cache = core, core.s, {}
        self.gt = core.d.gt

    def score(self, p1: float, p2: float, train_day: int) -> float:
        key = (round(float(p1), 4), round(float(p2), 4), int(train_day))
        if key in self.cache:
            return self.cache[key]
        lo = max(2 * self.core.inc + 1, train_day - self.s.calib_window)
        hi = train_day - self.s.score_h                      # every target <= train_day
        errs = []
        for o in range(lo, hi + 1, self.s.eval_stride):
            pr = self.core.predict_mc(o, p1, p2, self.s.score_h, 1, seed=o * 7919 + self.s.seed_offset)
            for t in range(o + 1, o + self.s.score_h + 1):
                if t in self.gt:
                    errs.append((pr[t] - self.gt[t]) ** 2)
        val = float(np.sqrt(np.mean(errs))) if errs else float("inf")
        self.cache[key] = val
        return val

    def best(self, case: str, train_day: int, p1_true=None, p2_true=None) -> tuple[float, float]:
        G = np.asarray(self.s.grid)
        if case == "known_p1":
            b = min(G, key=lambda x: self.score(p1_true, x, train_day))
            return p1_true, float(b)
        if case == "known_p2":
            b = min(G, key=lambda x: self.score(x, p2_true, train_day))
            return float(b), p2_true
        if case != "unknown_both":
            raise ValueError(f"no calibration for case {case!r}")
        best, bs = None, float("inf")                 # joint grid; true values never used
        for a in G:
            for b in G:
                s = self.score(a, b, train_day)
                if s < bs:
                    bs, best = s, (float(a), float(b))
        return best

    def damp(self, prev, best, train_day: int):
        if prev is None:
            return best
        r_prev = self.score(prev[0], prev[1], train_day)
        r_star = self.score(best[0], best[1], train_day)
        if not np.isfinite(r_prev) or r_prev <= 0:
            return best
        blend = min(1.0, max(0.0, r_prev - r_star) / r_prev * self.s.lam)
        return tuple(float(np.clip(p + (b - p) * blend, 0.01, 0.99))
                     for p, b in zip(prev, best, strict=True))


def _check_cases(cases, p1_true, p2_true):
    bad = [c for c in cases if c not in CASES]
    if bad:
        raise ValueError(f"unknown case(s) {bad}; choose from {CASES}")
    for c, need in (("known_both", "both"), ("known_p1", "p1"), ("known_p2", "p2")):
        if c in cases and ((need in ("both", "p1") and p1_true is None)
                           or (need in ("both", "p2") and p2_true is None)):
            raise ValueError(f"case {c!r} needs the true rate(s): pass p1_true / p2_true")


def run_final(data: FinalData, cases=CASES, p1_true: float | None = None,
              p2_true: float | None = None, settings: FinalSettings = FinalSettings(),  # noqa: B008
              last_origin: int | None = None, verbose: bool = False
              ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rolling-origin evaluation (the notebook's ``run_all_four_cases``).

    Returns ``(predictions, trace)``: one prediction row per (case, horizon, origin) and one
    trace row per (case, recalibration origin) with the grid best and the damped rates used.
    """
    cases = tuple(cases)
    _check_cases(cases, p1_true, p2_true)
    core = FinalCore(data, settings)
    cal = FinalCalibrator(core)
    rows, trace = [], []
    carry = {c: None for c in CASES}
    params = None
    last = settings.last_origin if last_origin is None else last_origin
    last = min(last, data.T - 2)
    for origin in range(settings.start_day, last + 1):
        if params is None or (origin - settings.start_day) % settings.recalib_every == 0:
            params = {}
            if "known_both" in cases:
                params["known_both"] = (p1_true, p2_true)
            for c in ("known_p1", "known_p2", "unknown_both"):
                if c not in cases:
                    continue
                best = cal.best(c, origin, p1_true, p2_true)
                carry[c] = cal.damp(carry[c], best, origin)
                params[c] = carry[c]
                trace.append(dict(p1_true=p1_true, p2_true=p2_true, case=c, origin=origin,
                                  p1_grid_best=best[0], p2_grid_best=best[1],
                                  p1_used=carry[c][0], p2_used=carry[c][1]))
        for c, (p1u, p2u) in params.items():
            pr = core.predict_mc(origin, p1u, p2u, max(settings.horizons), settings.n_mc,
                                 seed=origin * 104729 + settings.seed_offset)
            for h in settings.horizons:
                t = origin + h
                if t in pr and t in data.gt:
                    rows.append(dict(p1_true=p1_true, p2_true=p2_true, case=c, horizon=h,
                                     origin=origin, target_day=t, predicted=pr[t],
                                     actual=data.gt[t], p1_used=p1u, p2_used=p2u))
        if verbose and origin % 10 == 0:
            print(f"  origin {origin} done", flush=True)
    return pd.DataFrame(rows), pd.DataFrame(trace)


def summarize_relative(pred: pd.DataFrame, horizons=None, rounded: bool = True) -> pd.DataFrame:
    """RMSE and the paper's fRMSE (root mean squared relative error, targets with actual > 0),
    per (p1, p2, case, horizon): the notebook's ``summarize``. ``rounded`` reproduces the
    notebook's 2 / 3 decimals (``abm_summary.csv``)."""
    out = []
    keys = ["p1_true", "p2_true", "case"]
    hs = sorted(pred["horizon"].unique()) if horizons is None else horizons
    for (p1, p2, case), g in pred.groupby(keys, dropna=False):
        for h in hs:
            s = g[g.horizon == h]
            s = s[s.actual > 0]
            if s.empty:
                continue
            rel = (s.predicted - s.actual) / s.actual
            rmse = float(np.sqrt(((s.predicted - s.actual) ** 2).mean()))
            frmse = float(np.sqrt((rel ** 2).mean()))
            out.append(dict(p1=p1, p2=p2, case=case, horizon=h,
                            RMSE=round(rmse, 2) if rounded else rmse,
                            fRMSE=round(frmse, 3) if rounded else frmse))
    return pd.DataFrame(out)


def calibrate_at(data: FinalData, case: str, day: int, p1_true=None, p2_true=None,
                 settings: FinalSettings = FinalSettings()) -> tuple[float, float]:  # noqa: B008
    """The rates the method would use for a forecast made on ``day`` (first calibration, so no
    damping); for ``known_both`` the given rates."""
    _check_cases((case,), p1_true, p2_true)
    if case == "known_both":
        return p1_true, p2_true
    return FinalCalibrator(FinalCore(data, settings)).best(case, day, p1_true, p2_true)
