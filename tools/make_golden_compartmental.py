"""Record the outputs of the authors' earlier-EpiInfer notebooks on the bundled demo data.

    uv run --all-extras --with openpyxl python tools/make_golden_compartmental.py \\
        "/path/to/epiinfer for base case.ipynb" "/path/to/Epiinfer for C_0.2.ipynb" \\
        tests/golden_compartmental_notebook.json

Both notebooks run unchanged. They read their data from ``~/Desktop/abmcontact10000april0.2``
and write Excel files there, so HOME points at a temporary folder in which the demo data is
the single scenario ``p1_0.15_p2_0.1``. (``openpyxl`` is needed only because the notebooks
write .xlsx.) The library's port (src/epiinfer/compartmental.py) must reproduce every number.

The base-case notebook's only cell, as saved, holds a truncated copy of the code (it stops
mid-statement, so the cell as a whole is a SyntaxError) followed by the complete code. Only
the complete copy, from the last ``import numpy as np``, is run.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

DEMO = Path(__file__).resolve().parents[1] / "src" / "epiinfer" / "demo_data"
P1, P2 = 0.15, 0.1


def code_of(notebook: str, last_copy: bool = False) -> str:
    nb = json.loads(Path(notebook).read_text())
    code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    return code[code.rindex("import numpy as np"):] if last_copy else code


def main(base_nb: str, calib_nb: str, out: str) -> None:
    gold: dict = {"p1": P1, "p2": P2}
    with tempfile.TemporaryDirectory() as home:
        scen = Path(home) / "Desktop" / "abmcontact10000april0.2" / f"p1_{P1}_p2_{P2}"
        shutil.copytree(DEMO, scen)
        os.environ["HOME"] = home                     # Path.home() inside the notebooks

        ns: dict = {}
        exec(code_of(base_nb, last_copy=True), ns)    # writes its .xlsx into the temp HOME
        args = ns["load_dataset"](scen)
        gold["base_sim"] = ns["sim_from_day"](P1, P2, 20, 21, *args)[0, :, 2, 0].tolist()
        table, _, _ = ns["run_one_dataset"](scen)
        gold["base_rmse"] = table["rmse"].tolist()    # horizons 1-20, origins 20-25

        ns = {}
        exec(code_of(calib_nb), ns)
        cdata, ndata, population, nmeet, days, gnum = (ns[k] for k in (
            "cdata", "ndata", "population", "nmeet", "days", "gnum"))
        gold["calib_sim"] = ns["sim_from_day"](P1, P2, 20, 21, cdata, ndata, population, nmeet,
                                               days, gnum)[0, :, 2, 0].tolist()
        gold["calib_summary"] = ns["df_summary"].to_dict(orient="list")
    for k in ("base_sim", "calib_sim"):
        assert np.isfinite(gold[k]).all()
    Path(out).write_text(json.dumps(gold, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
