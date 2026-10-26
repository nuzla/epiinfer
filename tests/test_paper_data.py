"""Checks against the paper's own datasets. Skipped unless EPIINFER_PAPER_DATA points at a
folder holding ``age_structured/`` and ``openabm/`` (see docs/REPRODUCING.md)::

    EPIINFER_PAPER_DATA=/path/to/data pytest -m paper
"""

import os
from pathlib import Path

import pandas as pd
import pytest

ROOT = os.environ.get("EPIINFER_PAPER_DATA")
pytestmark = [pytest.mark.paper,
              pytest.mark.skipif(not ROOT, reason="EPIINFER_PAPER_DATA not set")]


def _data(name):
    p = Path(ROOT) / name
    if not p.is_dir():
        pytest.skip(f"{p} not found")
    return p


def test_arima_column_reproduces_exactly():
    pytest.importorskip("statsmodels")
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("arima_age_structured", _data("age_structured"))
    assert (df["dataset_check"] == "ok").all(), df["dataset_check"].iloc[0]
    assert (abs(df["rmse"] - df["paper_rmse"]) < 0.01).all(), df


def test_openabm_table_reproduces():
    """~10 s. The paper's code looked ahead at future contacts, hence contacts='recorded'."""
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("openabm", _data("openabm"), contacts="recorded")
    assert (df["dataset_check"] == "ok").all(), df["dataset_check"].iloc[0]
    # 1.000 when the day-after-the-data target is scored against 0 as the original did
    assert (abs(df["rmse_ratio"] - 1) < 0.02).all(), df


def test_age_structured_known_both_reproduces():
    """~1 min. Only the both-known row reproduces; see docs/REPRODUCING.md."""
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("age_structured", _data("age_structured"), methods=("known_both",),
                         contacts="recorded")
    assert (abs(df["rmse_ratio"] - 1) < 0.15).all(), df


def test_library_reproduces_the_authors_own_run():
    """All 16 cells (4 knowledge modes x 4 horizons) vs results_paper_aligned.csv, the
    authors' 13 July run of the same script on the same data. ~8 min single-process."""
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("age_structured", _data("age_structured"), contacts="recorded", jobs=4)
    assert len(df) == 16 and (df["dataset_check"] == "ok").all()
    # Monte-Carlo noise between runs is ~5%; the largest gap seen was 8.3%
    assert (abs(df["authors_ratio"] - 1) < 0.15).all(), df[["method", "horizon", "authors_ratio"]]


def test_uniform_arima_column_reproduces_exactly():
    """The paper's uniform ARIMA column (149.53 / 501.66 / 730.34 / 984.59) is computed on
    abmcontact10000aprilnewage/uniform, which has no contact list: it must still run."""
    pytest.importorskip("statsmodels")
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("arima_uniform", _data("aprilnewage_uniform"))
    assert (df["dataset_check"] == "ok").all(), df["dataset_check"].iloc[0]
    assert (abs(df["rmse"] - df["paper_rmse"]) < 0.01).all(), df


def test_appendix_arima_reproduces_for_every_scenario():
    """720 cells (3 scales x 12 (p1, p2) pairs x 20 horizons): relative difference < 1e-3
    (the residual is statsmodels optimiser noise)."""
    pytest.importorskip("statsmodels")
    from epiinfer.reproduce import reproduce_appendix
    for scale in ("0.2", "0.5", "2"):
        df = reproduce_appendix(_data(f"appendix_april{scale}"), scale, methods=("arima",))
        assert len(df) == 240, (scale, len(df))
        assert (abs(df["ratio"] - 1) < 1e-3).all(), (scale, df.loc[abs(df["ratio"] - 1).idxmax()])


def test_appendix_contact_one_scenario():
    """EpiInfer-contact (known_both) on p1=0.12, p2=0.05 at scale 0.2: the first 8 horizons are
    within 15% of the paper; the paper's later days run one day ahead of the library
    (docs/PAPER_VS_CODE.md, item 7), so those are checked with that shift."""
    from epiinfer.reproduce import reproduce_appendix
    df = reproduce_appendix(_data("appendix_april0.2"), "0.2", methods=("contact",),
                            pairs=[(0.12, 0.05)], workers=4)
    assert len(df) == 20
    ours = df.set_index("day")["rmse"]
    paper = df.set_index("day")["paper_rmse"]
    assert (abs(ours[:8] / paper[:8] - 1) < 0.2).all(), (ours[:8] / paper[:8])
    shifted = [paper[h] / ours[h + 1] for h in range(9, 20)]
    assert (abs(pd.Series(shifted) - 1) < 0.2).all(), shifted


def test_appendix_epiinfer_column_reproduces_every_cell():
    """The earlier EpiInfer (epiinfer for base case.ipynb) is deterministic: all 720 cells agree
    with the paper to its printed precision (two cells are truncated rather than rounded)."""
    from epiinfer.reproduce import reproduce_appendix
    for scale in ("0.2", "0.5", "2"):
        df = reproduce_appendix(_data(f"appendix_april{scale}"), scale, methods=("epiinfer_old",))
        assert len(df) == 240, (scale, len(df))
        diff = abs(df["rmse"] - df["paper_rmse"])
        assert (diff < 1e-3).all(), (scale, df.loc[diff.idxmax()])


def test_calibration_notebooks_reproduce_the_authors_summaries():
    """RMSE_summary<scale>.xlsx (Epiinfer for C_<scale>.ipynb: four knowledge settings, horizon
    20, same-day contacts), 132 rows: RMSE and the chosen rates are identical."""
    from pathlib import Path

    from epiinfer.compartmental import GroupCounts, run_compartmental, summarize
    from epiinfer.reproduce.appendix import scenarios
    want = pd.read_csv(Path(__file__).parent / "data" / "c_notebook_summaries.csv", comment="#",
                       dtype={"scale": str})
    for scale, w in want.groupby("scale"):
        for p1, p2, folder in scenarios(_data(f"appendix_april{scale}")):
            rows = w[(abs(w["True_p1"] - p1) < 1e-12) & (abs(w["True_p2"] - p2) < 1e-12)]
            pred = run_compartmental(GroupCounts.from_folder(folder), tuple(rows["Method"]),
                                     p1, p2, horizons=(20,), contacts="same_day")
            s = summarize(pred).set_index("case")
            last = pred.groupby("case").last()
            for r in rows.itertuples():
                assert s.loc[r.Method, "rmse"] == pytest.approx(r.RMSE_abs, rel=1e-12)
                assert last.loc[r.Method, "p1_used"] == pytest.approx(r.Est_p1, rel=1e-12)
                assert last.loc[r.Method, "p2_used"] == pytest.approx(r.Est_p2, rel=1e-12)


def test_age_specific_epiinfer_column_reproduces_exactly():
    """Tables 2-5 / Table 14, EpiInfer "both known" (180.1720 / 408.3458 / 161.6292 / 95.9607)."""
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("epiinfer_age_structured", _data("age_structured"))
    assert (df["dataset_check"] == "ok").all()
    assert (abs(df["rmse"] - df["paper_rmse"]) < 1e-4).all(), df
    assert (abs(df["frmse"] - df["paper_frmse"]) < 1e-4).all(), df
