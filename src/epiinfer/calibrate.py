"""Rate estimation: paper Algorithm 5 (ContinuousCalibrate) and the empirical-p1 variant."""

from __future__ import annotations

import numpy as np

from .config import Config
from .core import EpiInferCore
from .data import Dataset
from .metrics import rmse


def score_rates(model: EpiInferCore, p1_vec, p2_vec, eval_days, new_asymp, new_inf,
                recovered_on, observed_group, g) -> float:
    """RMSE of group ``g``'s symptomatic curve under ONE multi-day projection.

    The recent history is seeded once at the window start and projected across the
    whole window. A one-day-ahead score cannot identify ``p1``: it only creates
    pre-symptomatic people, who become the symptomatic people scored ``inc`` days
    later. The window must therefore be longer than ``inc``.

    The RNG is seeded from the window start so candidates are compared on common
    random numbers and the outer forecast stream is untouched.
    """
    days = list(eval_days)
    if not days:
        return float("inf")
    start, end = days[0], days[-1]
    rng = np.random.RandomState(int(start) % (2 ** 32))
    lookback = model.inc + model.duration + 1
    h_a = {k: new_asymp[k] for k in range(start - lookback, start) if k in new_asymp}
    h_i = {k: new_inf[k] for k in range(start - lookback, start) if k in new_inf}
    proj = model.project(p1_vec, p2_vec, h_a, h_i, start - 1, end + 1,
                         recovered_on.get(start - 1, set()), rng)
    keep = [d for d in days if d in proj and d in observed_group]
    pred = np.array([proj[d][g] for d in keep])
    obs = np.array([observed_group[d] for d in keep])
    return rmse(pred, obs)


def _truth(cfg: Config, n_groups: int, method: str):
    if cfg.p1_true is None or cfg.p2_true is None:
        raise ValueError(f"method {method!r} needs Config(p1_true=..., p2_true=...) "
                         "(the known rates)")
    if len(cfg.p1_true) != n_groups or len(cfg.p2_true) != n_groups:
        raise ValueError(f"p1_true/p2_true need {n_groups} entries (one per age group)")
    return np.array(cfg.p1_true, float), np.array(cfg.p2_true, float)


def continuous_calibrate(model: EpiInferCore, method: str, observed_group_map, current_day,
                         new_asymp, new_inf, recovered_on, cfg: Config, prev_p1, prev_p2):
    """CONTINUOUSCALIBRATE (Alg. 5) generalised to per-group rates by coordinate descent.

    Each group's unknown rate is grid-searched (others held fixed) to minimise
    :func:`score_rates` over the trailing window, then exponentially smoothed
    towards the grid-best. On the first day unknown rates start from
    ``cfg.neutral_prior`` rather than the truth.

    ``method``: ``known_both`` (both fixed at truth), ``known_p2`` (search p1),
    ``known_p1`` (search p2), ``unknown_both`` (search both). Returns ``(p1, p2)``.
    """
    n = model.n_groups
    if method == "known_both":
        return _truth(cfg, n, method)
    truth_p1 = truth_p2 = None
    if method in ("known_p1", "known_p2"):
        truth_p1, truth_p2 = _truth(cfg, n, method)

    window_start = max(model.inc + model.duration, current_day - cfg.calib_window)
    eval_days = range(window_start, current_day + 1)

    p1_vec = prev_p1.copy() if prev_p1 is not None else np.full(n, cfg.neutral_prior)
    p2_vec = prev_p2.copy() if prev_p2 is not None else np.full(n, cfg.neutral_prior)
    if method == "known_p1":
        p1_vec = truth_p1.copy()
    if method == "known_p2":
        p2_vec = truth_p2.copy()

    def smooth(prev_val, target):
        if prev_val is None:
            return target
        return float(np.clip(prev_val + (target - prev_val) * cfg.smoothing, 0.01, 0.99))

    def best_candidate(vary_p1: bool, g: int) -> float:
        best_rmse, best = float("inf"), cfg.candidates[-1]
        trial = (p1_vec if vary_p1 else p2_vec).copy()
        for c in cfg.candidates:
            trial[g] = c
            a, b = (trial, p2_vec) if vary_p1 else (p1_vec, trial)
            r = score_rates(model, a, b, eval_days, new_asymp, new_inf, recovered_on,
                            observed_group_map.get(g, {}), g)
            if r < best_rmse:
                best_rmse, best = r, c
        return best

    for g in range(n):
        if method in ("unknown_both", "known_p2"):
            pv = None if prev_p1 is None else float(prev_p1[g])
            p1_vec[g] = smooth(pv, best_candidate(True, g))
        if method in ("unknown_both", "known_p1"):
            pv = None if prev_p2 is None else float(prev_p2[g])
            p2_vec[g] = smooth(pv, best_candidate(False, g))
    return p1_vec, p2_vec


def solve_p1(k_hist: dict, observed: float) -> float:
    """Solve ``sum_k n_k * (1 - (1 - p)^k) = observed`` for ``p`` in [0, 1] by bisection.

    ``k_hist`` maps k (infectious contacts) to the number of at-risk susceptibles
    who met k. Returns 0.0 if nothing was observed, 1.0 if everyone at risk converted.
    """
    if not k_hist:
        return 0.0
    ks = np.fromiter(k_hist.keys(), np.int64, len(k_hist))
    nk = np.fromiter(k_hist.values(), np.float64, len(k_hist))
    total = nk.sum()
    if observed <= 0 or total == 0:
        return 0.0
    if observed >= total:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        p = 0.5 * (lo + hi)
        expected = float((nk * (1.0 - (1.0 - p) ** ks)).sum())
        if expected < observed:
            lo = p
        else:
            hi = p
    return 0.5 * (lo + hi)


def estimate_p1(model: EpiInferCore, data: Dataset, current_day: int, cfg: Config, prev_p1):
    """Recompute per-group ``p1`` from the last ``cfg.p1_window`` days of observed S->A events.

    For each transition day d in [current_day - window, current_day - 1], count each
    susceptible's infectious-contact degree k from the day-d graph, accumulate a
    per-group k-histogram and the number who were actually in A on day d+1, then
    invert the FINDPROB expectation by :func:`solve_p1`.
    """
    n = model.n_groups
    k_hist = [dict() for _ in range(n)]
    observed = np.zeros(n)
    lo = max(1, current_day - cfg.p1_window)
    for d in range(lo, current_day):
        infectious = data.asymp_on.get(d)
        susceptible = data.susceptible_on.get(d)
        if not infectious or not susceptible:
            continue
        next_asymp = data.asymp_on.get(d + 1, set())
        for s, k in model.infectious_encounters(infectious, susceptible, d).items():
            g = int(model.age_of[s])
            if not 0 <= g < n:
                continue
            k_hist[g][k] = k_hist[g].get(k, 0) + 1
            if s in next_asymp:
                observed[g] += 1.0
    p1 = np.empty(n)
    for g in range(n):
        fit = solve_p1(k_hist[g], observed[g])
        if not k_hist[g] and prev_p1 is not None:
            fit = float(prev_p1[g])                      # no signal -> hold last value
        if prev_p1 is not None and cfg.smoothing < 1.0:
            fit = float(prev_p1[g]) + cfg.smoothing * (fit - float(prev_p1[g]))
        p1[g] = float(np.clip(fit, cfg.p1_floor, cfg.p1_ceil))
    return p1
