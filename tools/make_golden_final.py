"""Record the outputs of the authors' final notebook (abm_final.ipynb) on the bundled demo data.

    uv run --all-extras python tools/make_golden_final.py /path/to/abm_final.ipynb \\
        tests/golden_final_notebook.json

The notebook's own code cells (config, data container, core, calibrator, runner) are executed
unchanged; only the run length is shortened (END_DAY, HORIZONS, N_MC_RUNS) because the demo
epidemic has 46 days. The library's port (src/epiinfer/final.py) must reproduce every number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DEMO = Path(__file__).resolve().parents[1] / "src" / "epiinfer" / "demo_data"

# shortened run used for the fixture (the library test uses the same FinalSettings)
END_DAY, HORIZONS, N_MC = 46, [1, 5, 10], 3
P1_TRUE, P2_TRUE = 0.15, 0.1


def notebook_namespace(path: str) -> dict:
    nb = json.loads(Path(path).read_text())
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]

    def cell_with(token):
        return next(c for c in code if token in c)

    ns: dict = {}
    exec(cell_with("import os, time, json"), ns)
    exec(cell_with("CALIB_GRID = "), ns)                  # configuration block
    ns.update(END_DAY=END_DAY, HORIZONS=HORIZONS, N_MC_RUNS=N_MC)
    for token in ("class EpiData", "class EpiInferCore", "class Calibrator",
                  "def run_all_four_cases"):
        exec(cell_with(token), ns)
    return ns


def demo_matrices(n: int):
    st = pd.read_csv(DEMO / "individual_day_state.csv")
    ed = pd.read_csv(DEMO / "timed_edges.csv")
    T = int(st["day"].max()) + 1
    S = np.zeros((T, n), dtype=np.int8)
    S[st["day"].values, st["id"].values] = st["state"].values
    edges = {int(d): (g["i"].values.astype(np.int32), g["j"].values.astype(np.int32))
             for d, g in ed.groupby("day")}
    return S, edges


def main(notebook: str, out: str) -> None:
    ns = notebook_namespace(notebook)
    n = int(pd.read_csv(DEMO / "age_group_population.csv")["population"].sum())
    S, edges = demo_matrices(n)
    data = ns["EpiData"](S, edges)
    core = ns["EpiInferCore"](data)
    gold: dict = {"settings": {"end_day": END_DAY, "horizons": HORIZONS, "n_mc": N_MC,
                               "p1_true": P1_TRUE, "p2_true": P2_TRUE, "n": n}}
    gold["reconstruct"] = core._reconstruct(30, 0.1, 12345).tolist()
    gold["nowcast"] = core._nowcast(30, 0.15, 0.1, np.random.default_rng(7)).tolist()
    gold["predict_mc"] = {str(k): v for k, v in
                          core.predict_mc(30, 0.15, 0.1, 10, 3, seed=30 * 104729).items()}
    cal = ns["Calibrator"](core)
    gold["score"] = cal.score(0.15, 0.1, 30)
    gold["best"] = {c: list(cal.best(c, 30, P1_TRUE, P2_TRUE))
                    for c in ("known_p1", "known_p2", "unknown_both")}
    gold["damp"] = list(cal.damp((0.2, 0.2), tuple(gold["best"]["unknown_both"]), 30))
    pred, trace = ns["run_all_four_cases"](P1_TRUE, P2_TRUE, n_mc=N_MC, data=data, verbose=False)
    gold["predictions"] = pred.to_dict(orient="list")
    gold["trace"] = trace.to_dict(orient="list")
    Path(out).write_text(json.dumps(gold, indent=1))
    print("wrote", out, f"({len(pred)} prediction rows, {len(trace)} trace rows)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
