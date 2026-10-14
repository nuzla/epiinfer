import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_example_script_runs():
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "forecast_new_data.py")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "target_day" in r.stdout and "rmse" in r.stdout
