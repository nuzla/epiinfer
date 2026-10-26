"""Check that a tutorial run reproduced the committed outputs.

    uv run python tools/compare_tutorial.py RESULTS_DIR docs/tutorial/outputs

Every CSV under the expected folder must exist in the results with the same columns, the same
non-numeric values and numbers equal to a relative 1e-9; .txt files must match line by line.
Two tables are compared more loosely, because statsmodels' optimiser differs between
platforms: ARIMA to a relative 1e-4 (tests/test_golden.py allows the same; measured 1e-9) and
Holt-Winters to 5e-3 (the Docker image on linux/amd64 and a native Apple-silicon run differ by
up to 0.2%, at day 20).
Exit status 1 lists every difference.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


def compare(results: Path, expected: Path) -> list[str]:
    if not any(expected.rglob("*.csv")):
        return [f"no expected CSV files under {expected}: nothing would be checked"]
    problems = []
    for exp in sorted(expected.rglob("*")):
        if exp.is_dir():
            continue
        got = results / exp.relative_to(expected)
        if not got.exists():
            problems.append(f"missing: {got}")
            continue
        if exp.suffix == ".csv":
            a, b = pd.read_csv(got), pd.read_csv(exp)
            if list(a.columns) != list(b.columns) or len(a) != len(b):
                problems.append(f"{exp.name}: shape/columns differ {a.shape} vs {b.shape}")
                continue
            rtol = 5e-3 if "holt_winters" in exp.name else 1e-4 if "arima" in exp.name else 1e-9
            for c in b.columns:
                if pd.api.types.is_numeric_dtype(b[c]):
                    x, y = a[c].to_numpy(float), b[c].to_numpy(float)
                    if not np.allclose(x, y, rtol=rtol, atol=1e-12, equal_nan=True):
                        i = int(np.argmax(~np.isclose(x, y, rtol=rtol, atol=1e-12, equal_nan=True)))
                        problems.append(f"{exp.name}: column {c!r} row {i}: {x[i]} vs {y[i]}")
                elif not a[c].astype(str).equals(b[c].astype(str)):
                    problems.append(f"{exp.name}: column {c!r} differs")
        elif exp.suffix == ".txt":
            la = [ln for ln in got.read_text().splitlines() if not ln.startswith("epiinfer ")]
            lb = [ln for ln in exp.read_text().splitlines() if not ln.startswith("epiinfer ")]
            if la != lb:
                problems.append(f"{exp.name}: text differs")
    return problems


if __name__ == "__main__":
    probs = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    for p in probs:
        print("DIFF", p)
    print("tutorial outputs reproduced exactly" if not probs else f"{len(probs)} difference(s)")
    sys.exit(1 if probs else 0)
