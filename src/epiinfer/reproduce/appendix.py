"""Appendix A of the paper: ARIMA, EpiInfer and EpiInfer-contact RMSE for 12 (p1, p2) pairs per
contact scale.

The paper's simulated populations have 13 age groups with ONE (p1, p2) per dataset. The data
folder for a scale holds one sub-folder per pair, named ``p1_<p1>_p2_<p2>``, e.g.
``abmcontact10000april0.2/p1_0.12_p2_0.05``.
"""

from __future__ import annotations

import re
from concurrent.futures import ProcessPoolExecutor
from importlib.resources import files
from pathlib import Path

import pandas as pd

from ..baselines import rolling_baseline
from ..compartmental import GroupCounts, run_compartmental, summarize
from ..config import PAPER
from ..data import load_dataset
from ..forecast import build_model, rolling_forecast

SCALES = ("0.2", "0.5", "2")          # "Base" (the unscaled data) is not among the supplied files
#: "epiinfer_old" is EpiInfer, the earlier compartmental model (epiinfer.compartmental)
METHODS = ("arima", "contact", "epiinfer_old")
HORIZONS = tuple(range(1, 21))
_PAIR = re.compile(r"p1_([\d.]+)_p2_([\d.]+)$")


def load_targets() -> pd.DataFrame:
    """The paper's appendix numbers: columns p1, p2, scale, day, method, rmse."""
    with files("epiinfer.reproduce").joinpath("appendix_targets.csv").open() as f:
        df = pd.read_csv(f, comment="#", dtype={"scale": str})
    return df


def scenarios(data_dir: str | Path) -> list[tuple[float, float, Path]]:
    """``(p1, p2, folder)`` for every ``p1_*_p2_*`` sub-folder of ``data_dir``, sorted."""
    out = []
    for sub in sorted(Path(data_dir).glob("p1_*_p2_*")):
        m = _PAIR.match(sub.name)
        if m and sub.is_dir():
            out.append((float(m.group(1)), float(m.group(2)), sub))
    return sorted(out, key=lambda t: (t[0], t[1]))


def _one(args) -> list[dict]:
    (p1, p2, folder, methods, scale, seed, num_sims, workers, contacts, quick, offset) = args
    rows = []
    if "arima" in methods:
        r = rolling_baseline(folder, "arima", HORIZONS, start_eval=10, last_origin=50)
        rows += [{"p1": p1, "p2": p2, "scale": scale, "day": int(d), "method": "arima", "rmse": v}
                 for d, v in zip(r["horizon"], r["rmse"], strict=True)]
    if "epiinfer_old" in methods:
        # epiinfer for base case.ipynb: both rates known, 5-day mean contacts, origins 20-80
        pred = run_compartmental(GroupCounts.from_folder(folder), ("known_both",), p1, p2, HORIZONS)
        s = summarize(pred)
        rows += [{"p1": p1, "p2": p2, "scale": scale, "day": int(h), "method": "epiinfer_old",
                  "rmse": v} for h, v in zip(s["horizon"], s["rmse"], strict=True)]
    if "contact" in methods:
        over = dict(horizons=HORIZONS, seed=seed, mc_threads=workers, contacts=contacts,
                    contact_offset=offset)
        if quick:
            over.update(start_eval=30, max_day=50, num_sims=3)
        if num_sims:
            over["num_sims"] = num_sims
        cfg = PAPER.with_(**over)
        data = load_dataset(folder, max_day=cfg.max_day)
        g = data.n_groups
        cfg = cfg.with_(p1_true=(p1,) * g, p2_true=(p2,) * g)       # one (p1, p2) for every group
        s = rolling_forecast(build_model(data, cfg), data, "known_both", cfg, quiet=True).summary()
        s = s[s["group"] == "ALL"]
        rows += [{"p1": p1, "p2": p2, "scale": scale, "day": int(h), "method": "contact", "rmse": v}
                 for h, v in zip(s["horizon"], s["rmse"], strict=True)]
    return rows


def reproduce_appendix(data_dir: str | Path, scale: str, methods: tuple[str, ...] = METHODS,
                       seed: int = 0, num_sims: int | None = None, workers: int = 1,
                       contacts: str = "recorded", jobs: int = 1, quick: bool = False,
                       pairs: list[tuple[float, float]] | None = None, offset: int = 0
                       ) -> pd.DataFrame:
    """Re-run Appendix A for one contact ``scale`` on ``data_dir``; returns paper vs. measured.

    ``contact`` is EpiInfer-contact with both rates known (``known_both``) and all 20 horizons,
    on the contact engine with ``contact_offset=offset`` (0, the original scripts' timing, is the
    default; the published curve runs one day ahead of it from about day 9, and 1 (the
    simulator's timing) fits scale 0.2 better but scales 0.5 and 2 worse, docs/PAPER_VS_CODE.md);
    ``arima`` uses forecast origins 10-50 like the authors' ARIMA notebook. ``epiinfer_old`` is
    the earlier compartmental EpiInfer as in ``epiinfer for base case.ipynb`` (deterministic;
    origins 20-80, where an origin is the first projected day). ``pairs`` limits
    the (p1, p2) combinations. Columns: scale, p1, p2, method, day, paper_rmse, rmse, ratio.
    """
    scale = str(scale)
    if scale not in SCALES:
        raise ValueError(f"scale must be one of {SCALES} (the unscaled 'Base' data was not supplied)")
    bad = [m for m in methods if m not in METHODS]
    if bad:
        raise ValueError(f"unknown method(s) {bad}; choose from {METHODS}")
    found = scenarios(data_dir)
    if pairs is not None:
        found = [t for t in found if (t[0], t[1]) in set(pairs)]
    if not found:
        raise FileNotFoundError(f"no p1_*_p2_* folders under {data_dir}")
    tasks = [(p1, p2, f, tuple(methods), scale, seed, num_sims, workers, contacts, quick, offset)
             for p1, p2, f in found]
    if jobs > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=min(jobs, len(tasks))) as ex:
            parts = list(ex.map(_one, tasks))
    else:
        parts = [_one(t) for t in tasks]
    ours = pd.DataFrame([r for part in parts for r in part])
    tgt = load_targets()
    tgt = tgt[tgt["scale"] == scale].rename(columns={"rmse": "paper_rmse"})
    out = ours.merge(tgt, on=["p1", "p2", "scale", "day", "method"], how="left")
    out["ratio"] = out["rmse"] / out["paper_rmse"]
    out["contacts"] = [contacts if m == "contact" else "n/a" for m in out["method"]]
    return out[["scale", "p1", "p2", "method", "day", "paper_rmse", "rmse", "ratio", "contacts"]]
