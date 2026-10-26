import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_example_script_runs():
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "forecast_new_data.py")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "target_day" in r.stdout and "rmse" in r.stdout


def test_convert_case_list_builds_a_usable_dataset(tmp_path):
    """A case list + contact list becomes a folder the final engine reads: case X with onset
    on day 2 is symptomatic on days 2-8 and recovered on days 9-15."""
    import pandas as pd

    from epiinfer.final import FinalData
    days = pd.date_range("2026-01-01", periods=30)
    pd.DataFrame({"person": ["X", "Y"], "onset": [days[2], days[20]]}).to_csv(
        tmp_path / "cases.csv", index=False)
    pd.DataFrame({"date": days, "a": "X", "b": ["Y", "Z"] * 15}).to_csv(
        tmp_path / "contacts.csv", index=False)
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "convert_case_list.py"),
                        str(tmp_path / "cases.csv"), str(tmp_path / "contacts.csv"),
                        str(tmp_path / "out")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    fd = FinalData.from_folder(tmp_path / "out")
    assert (fd.T, fd.n) == (30, 3)
    x = list(pd.read_csv(tmp_path / "out" / "people.csv")["label"]).index("X")
    assert [d for d in range(30) if fd.is_inf[d, x]] == list(range(2, 9))
    assert [d for d in range(30) if fd.is_rec[d, x]] == list(range(9, 16))
    assert sum(len(e[0]) for e in fd.edges.values()) == 30
    from epiinfer.cli import main
    assert main(["from-cases", "--cases", str(tmp_path / "cases.csv"), "--contacts",
                 str(tmp_path / "contacts.csv"), "--out", str(tmp_path / "cli"),
                 "--duration", "5"]) == 0
    assert [d for d in range(30) if FinalData.from_folder(tmp_path / "cli").is_inf[d, x]] == \
        list(range(2, 7))
