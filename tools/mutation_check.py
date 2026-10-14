"""Tiny mutation test: break key guards in a COPY of the package and require the suite to fail.

    python tools/mutation_check.py
A mutation that the tests do not catch means a test is a no-op.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("core.py", "probs = 1.0 - (1.0 - p1) ** counts", "probs = p1 * counts"),
    ("core.py", "rng.random_sample(cand.size) < p2", "rng.random_sample(cand.size) < 1.0"),
    ("calibrate.py", "np.random.RandomState(int(start) % (2 ** 32))", "np.random.RandomState(1)"),
    ("calibrate.py", "if r < best_rmse:", "if r <= best_rmse:"),
    ("calibrate.py", "float(np.clip(prev_val + (target - prev_val) * cfg.smoothing, 0.01, 0.99))",
     "float(target)"),
    ("calibrate.py", "if observed >= total:\n        return 1.0",
     "if observed >= total:\n        return 0.5"),
    ("forecast.py", "[int(seed), int(day), int(sim)]", "[int(seed), 0, int(sim)]"),
    ("forecast.py", '"strict" if method == EMPIRICAL_METHOD else "diff")\n    n = model.n_groups',
     '"diff")\n    n = model.n_groups'),
    ("data.py", "asymp_on[day] & susceptible_on.get(day - 1, set())",
     "asymp_on[day] - asymp_on.get(day - 1, set())"),
    ("data.py", "if int(df_status[\"id\"].max()) >= pop_total:", "if False:"),
    ("data.py", "if s_code != 0:", "if False:"),
    ("metrics.py", "return math.sqrt(np.mean((pred - actual) ** 2)) / denom",
     "return math.sqrt(np.mean((pred - actual) ** 2)) / actual.max()"),
    ("simulate/abm.py", "not_inf[core_i] & not_inf[core_j]", "np.ones(core_i.size, bool)"),
]


def main() -> int:
    survivors = []
    for rel, old, new in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "pkg"
            shutil.copytree(ROOT / "src" / "epiinfer", work / "epiinfer")
            target = work / "epiinfer" / rel
            text = target.read_text()
            if old not in text:
                print(f"STALE   {rel}: pattern not found: {old[:50]!r}")
                survivors.append((rel, old))
                continue
            target.write_text(text.replace(old, new, 1))
            env = {"PYTHONPATH": str(work), "PATH": "/usr/bin:/bin"}
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                                str(ROOT / "tests")], env=env, capture_output=True, text=True)
            status = "caught " if r.returncode != 0 else "SURVIVED"
            print(f"{status} {rel}: {old[:60]!r}")
            if r.returncode == 0:
                survivors.append((rel, old))
    print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} mutations caught")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
