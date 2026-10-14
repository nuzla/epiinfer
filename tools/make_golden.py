"""Record golden outputs from the ORIGINAL research scripts on the bundled demo dataset.

Run once (and again only if the demo data changes):

    uv run --all-extras python tools/make_golden.py /path/to/epiinfer tests/golden_original_scripts.json \
        [/path/to/baselines_standalone.ipynb]

The library's tests then assert that the refactored package reproduces these numbers
exactly, so the refactor is provably behaviour-preserving. Needs only numpy + pandas +
matplotlib; imports ``epiinfer_paper_aligned.py`` and ``epiinfer_empirical_p1.py`` from the
given folder.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

DEMO = Path(__file__).resolve().parents[1] / "src" / "epiinfer" / "demo_data"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


def counts(d):
    return {str(k): sorted(int(x) for x in v) for k, v in sorted(d.items())}


def holt_winters_from_notebook(notebook: str, gt: dict) -> dict:
    """Run the authors' own Holt-Winters code (cell 2 of baselines_standalone.ipynb) on
    ``gt`` and return RMSE per horizon, so the library's port can be checked against it."""
    import pandas as pd
    nb = json.loads(Path(notebook).read_text())
    cell = next("".join(c["source"]) for c in nb["cells"]
                if c["cell_type"] == "code" and "def run_holt_winters" in "".join(c["source"]))
    ns = {"np": np, "pd": pd, "START_DAY": 25, "END_DAY": 100, "HORIZONS": [1, 5, 10, 20],
          "CALIB_WINDOW": 14}
    exec(cell, ns)                                   # defines _holt_forecast, run_holt_winters
    df = ns["run_holt_winters"](0, 0, gt)
    return {str(h): float(np.sqrt(((s.predicted - s.actual) ** 2).mean()))
            for h, s in df.groupby("horizon")}


def main(old_dir: str, out: str, notebook: str | None = None) -> None:
    old = Path(old_dir)
    pa = load_module(old / "epiinfer_paper_aligned.py", "old_pa")
    em = load_module(old / "epiinfer_empirical_p1.py", "old_em")
    quiet = lambda *_: None  # noqa: E731
    gold: dict = {}

    # ---- paper-aligned ---------------------------------------------------------
    pa.DATA_ROOT = str(DEMO.parent)
    data = pa.load_dataset(DEMO.name, quiet)
    model = pa.EpiInferCore(list(range(data.population_total)), data.daily_contacts,
                            data.age_of, pa.INCUBATION_PERIOD, pa.INFECTION_DURATION)
    gold["dataset"] = {
        "population_total": data.population_total,
        "n_days": len(data.all_days),
        "new_asymp": counts(data.new_asymp), "new_inf": counts(data.new_inf),
        "gt_total": {str(k): int(v) for k, v in sorted(data.gt_total.items())},
        "gt_group": {str(g): {str(d): int(v) for d, v in sorted(m.items())}
                     for g, m in data.gt_group.items()},
    }
    day = 30
    cal = {}
    for method in ["unknown_both", "known_p2", "known_p1", "known_both"]:
        observed = {g: {d: data.gt_group[g].get(d, 0)
                        for d in range(max(0, day - pa.CALIB_WINDOW), day + 1)}
                    for g in range(pa.N_GROUPS)}
        p1, p2 = pa.continuous_calibrate(model, method, observed, day, pa.CALIB_WINDOW,
                                         data.new_asymp, data.new_inf, data.recovered_on,
                                         pa.CANDIDATES, None, None, pa.SMOOTHING)
        observed2 = {g: {d: data.gt_group[g].get(d, 0)
                         for d in range(max(0, day + 1 - pa.CALIB_WINDOW), day + 2)}
                     for g in range(pa.N_GROUPS)}
        q1, q2 = pa.continuous_calibrate(model, method, observed2, day + 1, pa.CALIB_WINDOW,
                                         data.new_asymp, data.new_inf, data.recovered_on,
                                         pa.CANDIDATES, p1, p2, pa.SMOOTHING)
        cal[method] = {"day30": [p1.tolist(), p2.tolist()], "day31": [q1.tolist(), q2.tolist()]}
    gold["calibrate"] = cal

    lookback = 8
    h_a = {k: data.new_asymp[k] for k in range(day - lookback, day + 1) if k in data.new_asymp}
    h_i = {k: data.new_inf[k] for k in range(day - lookback, day + 1) if k in data.new_inf}
    np.random.seed(2024)
    proj = model.project(np.array([0.25, 0.15, 0.08]), np.array([0.15, 0.10, 0.05]), h_a, h_i,
                         day, day + 12, data.recovered_on.get(day, set()))
    gold["project_paper"] = {"seed": 2024, "day": day,
                             "counts": {str(d): v.tolist() for d, v in sorted(proj.items())}}

    # ---- empirical-p1 ----------------------------------------------------------
    em.DATA_ROOT = str(DEMO.parent)
    edata = em.load_dataset(DEMO.name, quiet)
    emodel = em.EpiInferCore(list(range(edata.population_total)), edata.daily_contacts,
                             edata.age_of, 5, 11)
    gold["dataset_strict"] = {"new_asymp": counts(edata.new_asymp),
                              "new_inf": counts(edata.new_inf)}
    p1a = em.estimate_p1(emodel, edata, 30, em.P1_WINDOW, None, em.SMOOTHING)
    p1b = em.estimate_p1(emodel, edata, 31, em.P1_WINDOW, p1a, em.SMOOTHING)
    p1c = em.estimate_p1(emodel, edata, 31, em.P1_WINDOW, p1a, 0.5)
    gold["estimate_p1"] = {"day30": p1a.tolist(), "day31": p1b.tolist(),
                           "day31_smooth_half": p1c.tolist()}
    gold["solve_p1"] = {"cases": [
        {"k_hist": {"1": 40, "2": 12, "3": 5}, "observed": 17.0,
         "p1": em._solve_p1({1: 40, 2: 12, 3: 5}, 17.0)},
        {"k_hist": {"1": 10}, "observed": 0.0, "p1": em._solve_p1({1: 10}, 0.0)},
        {"k_hist": {"1": 10}, "observed": 10.0, "p1": em._solve_p1({1: 10}, 10.0)}]}
    lb = 5 + 11 + 1
    e_a = {k: edata.new_asymp[k] for k in range(day - lb, day + 1) if k in edata.new_asymp}
    e_i = {k: edata.new_inf[k] for k in range(day - lb, day + 1) if k in edata.new_inf}
    np.random.seed(77)
    eproj = emodel.project(p1a, np.ones(3), e_a, e_i, day, day + 12,
                           edata.recovered_on.get(day, set()))
    gold["project_empirical"] = {"seed": 77, "day": day,
                                 "counts": {str(d): v.tolist() for d, v in sorted(eproj.items())}}
    if notebook:
        gold["holt_winters_notebook"] = holt_winters_from_notebook(
            notebook, {int(k): float(v) for k, v in data.gt_total.items()})
    Path(out).write_text(json.dumps(gold, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
