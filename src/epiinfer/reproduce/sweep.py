"""Tables 10-13 of the October 2026 paper: the final method on 12 (p1, p2) epidemics.

The published numbers are the authors' ``abm_summary.csv`` (``sweep_targets.csv``), computed by
``abm_final.ipynb`` on the unscaled ("Base") AgeMixABM data, ``abmcontact10000/p1_*_p2_*``. That
data was not supplied; ``sweep_actuals.csv`` holds its symptomatic curves (days 26-99, from the
authors' predictions file) so a folder can be recognised as the Base data.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from importlib.resources import files
from pathlib import Path

import pandas as pd

from ..final import CASES, FinalData, FinalSettings, run_final, summarize_relative
from .appendix import scenarios


def load_targets() -> pd.DataFrame:
    """The paper's Tables 10-13: p1, p2, case, horizon, RMSE, fRMSE (192 rows)."""
    with files("epiinfer.reproduce").joinpath("sweep_targets.csv").open() as f:
        return pd.read_csv(f, comment="#")


def load_actuals() -> pd.DataFrame:
    """Symptomatic counts of the Base epidemics: p1, p2, day, I (days 26-99)."""
    with files("epiinfer.reproduce").joinpath("sweep_actuals.csv").open() as f:
        return pd.read_csv(f, comment="#")


def check_base_data(data: FinalData, p1: float, p2: float) -> str:
    """'ok' if the folder's symptomatic curve equals the paper's Base epidemic for (p1, p2)."""
    ref = load_actuals()
    ref = ref[(ref.p1 == p1) & (ref.p2 == p2)]
    if ref.empty:
        return "unknown"
    diff = [int(r.day) for r in ref.itertuples() if data.gt.get(int(r.day)) != int(r.I)]
    if not diff:
        return "ok"
    return (f"MISMATCH: not the paper's Base data for p1={p1}, p2={p2} "
            f"({len(diff)} of {len(ref)} days differ)")


def _one(args):
    p1, p2, folder, cases, settings = args
    data = FinalData.from_folder(folder, max_day=settings.end_day)
    pred, trace = run_final(data, cases, p1_true=p1, p2_true=p2, settings=settings)
    return pred, trace, check_base_data(data, p1, p2)


def reproduce_sweep(data_dir: str | Path, cases=CASES, settings: FinalSettings | None = None,
                    pairs=None, jobs: int = 1, quick: bool = False):
    """Re-run Tables 10-13 on ``data_dir`` (a folder of ``p1_*_p2_*`` sub-folders).

    Returns ``(comparison, predictions, trace)``; ``comparison`` has one row per
    (p1, p2, case, horizon) with ours and the paper's RMSE / fRMSE and ``dataset_check``.
    ``quick`` = 3 Monte-Carlo runs and origins 25-35 (a smoke test, not comparable).
    """
    settings = settings or FinalSettings()
    if quick:
        settings = FinalSettings(**{**settings.__dict__, "n_mc": 3, "end_day": 56})
    found = scenarios(data_dir)
    if pairs is not None:
        found = [t for t in found if (t[0], t[1]) in set(pairs)]
    if not found:
        raise FileNotFoundError(f"no p1_*_p2_* folders under {data_dir}")
    tasks = [(p1, p2, f, tuple(cases), settings) for p1, p2, f in found]
    if jobs > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=min(jobs, len(tasks))) as ex:
            parts = list(ex.map(_one, tasks))
    else:
        parts = [_one(t) for t in tasks]
    pred = pd.concat([p for p, _, _ in parts], ignore_index=True)
    trace = pd.concat([t for _, t, _ in parts], ignore_index=True)
    checks = {(p1, p2): c for (p1, p2, _), (_, _, c) in zip(found, parts, strict=True)}
    ours = summarize_relative(pred, rounded=False)
    tgt = load_targets().rename(columns={"RMSE": "paper_RMSE", "fRMSE": "paper_fRMSE"})
    cmp = ours.merge(tgt, on=["p1", "p2", "case", "horizon"], how="left")
    cmp["ratio"] = cmp["RMSE"] / cmp["paper_RMSE"]
    cmp["dataset_check"] = [checks[(a, b)] for a, b in zip(cmp["p1"], cmp["p2"], strict=True)]
    return cmp, pred, trace
