"""The documentation must agree with the code and with the committed tutorial outputs."""

import re
import tomllib
from pathlib import Path

import pandas as pd

import epiinfer

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]
OUTPUTS = ROOT / "docs" / "tutorial" / "outputs"


def _prose(path: Path) -> str:
    """The markdown without fenced code blocks (their brackets are not links)."""
    return re.sub(r"```.*?```", "", path.read_text(), flags=re.S)


def test_relative_links_and_images_resolve():
    """Links must work on GitHub and on the published site (nuzla.github.io/epiinfer, built from
    docs/ alone): from a page in docs/ they must name a file inside docs/. A folder or a file
    outside docs/ (../examples/...) opens on GitHub but is a 404 on the site; use a full URL."""
    docs_dir = ROOT / "docs"
    broken = []
    for doc in DOCS:
        for m in re.finditer(r"\]\(([^)\s]+)\)", _prose(doc)):
            target = m.group(1).split("#")[0]
            if not target or re.match(r"[a-z]+:", target):
                continue
            path = (doc.parent / target).resolve()
            if not path.exists():
                broken.append(f"{doc.name}: {m.group(1)}")
            elif doc.parent == docs_dir and (not path.is_file() or docs_dir not in path.parents):
                broken.append(f"{doc.name}: {m.group(1)} (the published site serves files in "
                              f"docs/ only)")
    assert not broken, broken


def test_every_version_string_agrees():
    """A release changes the version in five places; forgetting one ships a tutorial whose
    commands pull another image or whose expected output names another version."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert epiinfer.__version__ == version
    assert re.search(rf"^version: {re.escape(version)}$", (ROOT / "CITATION.cff").read_text(), re.M)
    assert (OUTPUTS / "00_version.txt").read_text().strip() == f"epiinfer {version}"
    tutorial = (ROOT / "docs" / "TUTORIAL.md").read_text()
    assert f"epiinfer {version}" in tutorial and f"`epi --version` says {version}" in tutorial
    tags = set()
    for path in [*DOCS, ROOT / "docs" / "tutorial" / "run_tutorial.sh"]:
        tags |= set(re.findall(r"ghcr\.io/nuzla/epiinfer:([0-9][\w.\-]*)", path.read_text()))
    assert tags == {version}, tags


def test_tutorial_shows_exactly_what_its_committed_outputs_contain():
    """CI compares the tutorial's outputs with docs/tutorial/outputs; this compares the page
    with those files, so a regenerated output cannot leave stale numbers in the text."""
    text = (ROOT / "docs" / "TUTORIAL.md").read_text()
    missing = []
    for name in ("01_describe.txt", "04_backtest_final.txt", "06_backtest_compartmental.txt"):
        for line in (OUTPUTS / name).read_text().splitlines():
            if line.strip() and not line.startswith("epiinfer ") and line not in text:
                missing.append(f"{name}: {line}")
    # the 2025 engine prints a row per age group; the tutorial shows only the totals
    for line in (OUTPUTS / "05_backtest_contact.txt").read_text().splitlines():
        if (" ALL " in line or "frmse_rel" in line) and line not in text:
            missing.append(f"05_backtest_contact.txt: {line}")
    forecast = (OUTPUTS / "02_forecast_day60.csv").read_text().splitlines()
    future = (OUTPUTS / "03_forecast_future.csv").read_text().splitlines()
    for line in [*forecast, *future[:2], future[-1]]:
        if line not in text:
            missing.append(f"forecast csv: {line}")
    for name in ("07_arima.csv", "07_holt_winters.csv"):             # printed with 6 decimals
        for rmse in pd.read_csv(OUTPUTS / name)["rmse"]:
            if f"{rmse:.6f}" not in text:
                missing.append(f"{name}: rmse {rmse:.6f}")
    assert not missing, missing
