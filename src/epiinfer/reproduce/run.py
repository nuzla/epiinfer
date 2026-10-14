"""Run one paper table and compare it with the published values."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..data import load_dataset
from ..forecast import build_model, default_config, rolling_forecast
from .targets import TABLES

log = logging.getLogger("epiinfer")


def reproduce_table(table: str, data_dir: str | Path, quick: bool = False, seed: int = 0,
                    num_sims: int | None = None, workers: int = 1,
                    horizons: tuple[int, ...] | None = None,
                    methods: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Re-run ``table`` on ``data_dir`` and return paper vs. measured values.

    ``quick`` shortens the evaluation (origins 30..50, 3 sims) to a smoke test; its numbers
    are NOT comparable with the paper. Columns: method, horizon, paper_rmse, rmse,
    rmse_ratio (ours / paper), paper_frmse, frmse.
    """
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}; choose from {sorted(TABLES)}")
    spec = TABLES[table]
    data = load_dataset(data_dir)
    rows = []
    for method in (methods or spec["methods"]):
        cfg = default_config(method).with_(seed=seed, mc_threads=workers)
        cfg = cfg.with_(horizons=horizons or (1, 5, 10, 20))
        if quick:
            cfg = cfg.with_(start_eval=30, max_day=50, num_sims=3)
        if num_sims:
            cfg = cfg.with_(num_sims=num_sims)
        res = rolling_forecast(build_model(data, cfg), data, method, cfg)
        summ = res.summary()
        summ = summ[summ["group"] == spec["group"]]
        for h in cfg.horizons:
            s = summ[summ["horizon"] == h]
            if s.empty:
                continue
            paper = spec["targets"].get((method, h), (float("nan"), float("nan")))
            rmse, frmse = float(s["rmse"].iloc[0]), float(s["frmse"].iloc[0])
            rows.append({"table": spec["caption"], "method": method, "horizon": h,
                         "paper_rmse": paper[0], "rmse": rmse,
                         "rmse_ratio": rmse / paper[0] if paper[0] == paper[0] else float("nan"),
                         "paper_frmse": paper[1], "frmse": frmse,
                         "n_origins": int(s["n"].iloc[0])})
    return pd.DataFrame(rows)
