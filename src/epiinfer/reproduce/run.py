"""Run one paper table and compare it with the published values."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from ..data import load_dataset
from ..forecast import build_model, default_config, rolling_forecast
from .targets import TABLES

log = logging.getLogger("epiinfer")


def fingerprint(data) -> tuple[int, int, int]:
    """(people, days, peak symptomatic count): enough to tell the paper's datasets apart."""
    return (data.population_total, len(data.all_days), int(max(data.gt_total.values())))


def check_dataset(table: str, data) -> str:
    """'ok', 'unknown' (no reference recorded) or a description of the mismatch."""
    want = TABLES[table].get("fingerprint")
    if want is None:
        return "unknown"
    got = fingerprint(data)
    if got == want:
        return "ok"
    return (f"MISMATCH: data has {got[0]} people, {got[1]} days, peak I {got[2]}; the paper's "
            f"{table} data has {want[0]}, {want[1]}, {want[2]}")


def _run_method(table: str, data_dir: str, method: str, overrides: dict) -> list[dict]:
    spec = TABLES[table]
    data = load_dataset(data_dir)
    dataset_check = check_dataset(table, data)
    if "baseline_window" in spec:                      # statistical baseline, own window
        from ..baselines import rolling_baseline
        first, last = spec["baseline_window"]
        horizons = overrides["horizons"]
        summ = rolling_baseline(data, method, horizons, start_eval=first, last_origin=last,
                                max_day=last + max(horizons))
        summ = summ.assign(group="ALL")
        contacts = "n/a"
    else:
        cfg = default_config(method).with_(**overrides)
        horizons = cfg.horizons
        summ = rolling_forecast(build_model(data, cfg), data, method, cfg).summary()
        contacts = cfg.contacts
    summ = summ[summ["group"] == spec["group"]]
    rows = []
    for h in horizons:
        s = summ[summ["horizon"] == h]
        if s.empty:
            continue
        paper = spec["targets"].get((method, h), (float("nan"), float("nan")))
        paper = tuple(float("nan") if v is None else v for v in paper)
        authors = spec.get("authors_run", {}).get((method, h))
        rmse, frmse = float(s["rmse"].iloc[0]), float(s["frmse"].iloc[0])
        rows.append({"table": spec["caption"], "method": method, "horizon": h,
                     "contacts": contacts, "paper_rmse": paper[0], "rmse": rmse,
                     "rmse_ratio": rmse / paper[0] if paper[0] == paper[0] else float("nan"),
                     "paper_frmse": paper[1], "frmse": frmse, "n_origins": int(s["n"].iloc[0]),
                     "dataset_check": dataset_check})
        if "authors_run" in spec:
            nan = float("nan")
            rows[-1]["authors_rmse"] = authors[0] if authors else nan
            rows[-1]["authors_ratio"] = rmse / authors[0] if authors else nan
    return rows


def reproduce_table(table: str, data_dir: str | Path, quick: bool = False, seed: int = 0,
                    num_sims: int | None = None, workers: int = 1,
                    horizons: tuple[int, ...] | None = None,
                    methods: tuple[str, ...] | None = None, contacts: str = "recorded",
                    jobs: int = 1) -> pd.DataFrame:
    """Re-run ``table`` on ``data_dir`` and return paper vs. measured values.

    ``contacts="recorded"`` (default) matches the code that produced the published numbers,
    which used each future day's recorded contacts; ``"frozen"`` removes that look-ahead.
    ``quick`` shortens the evaluation (origins 30..50, 3 sims) to a smoke test; its numbers
    are NOT comparable with the paper. ``jobs`` > 1 runs the methods in parallel processes
    (results are identical to ``jobs=1``). The ``dataset_check`` column says whether
    ``data_dir`` is the dataset the paper's numbers were computed on. For ``age_structured``,
    ``authors_rmse`` / ``authors_ratio`` compare with the authors' own run of the same code
    (the published paper reports a different run; see docs/PAPER_VS_CODE.md).
    """
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}; choose from {sorted(TABLES)}")
    spec = TABLES[table]
    methods = tuple(methods or spec["methods"])
    unknown = [m for m in methods if m not in spec["methods"]]
    if unknown:
        raise ValueError(f"{table} has no published values for {unknown}; "
                         f"choose from {spec['methods']}")
    over: dict = {"seed": seed, "mc_threads": workers, "contacts": contacts,
                  "horizons": horizons or (1, 5, 10, 20)}
    if quick:
        over.update(start_eval=30, max_day=50, num_sims=3)
    if num_sims:
        over["num_sims"] = num_sims
    if jobs > 1 and len(methods) > 1:
        with ProcessPoolExecutor(max_workers=min(jobs, len(methods))) as ex:
            parts = list(ex.map(_run_method, [table] * len(methods), [str(data_dir)] * len(methods),
                                methods, [over] * len(methods)))
    else:
        parts = [_run_method(table, str(data_dir), m, over) for m in methods]
    return pd.DataFrame([row for part in parts for row in part])
