"""Checks against the paper's own datasets. Skipped unless EPIINFER_PAPER_DATA points at a
folder holding ``age_structured/`` and ``openabm/`` (see docs/REPRODUCING.md)::

    EPIINFER_PAPER_DATA=/path/to/data pytest -m paper
"""

import os
from pathlib import Path

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
    assert (abs(df["rmse"] - df["paper_rmse"]) < 0.01).all(), df


def test_openabm_table_reproduces():
    """~10 s. The paper's code looked ahead at future contacts, hence contacts='recorded'."""
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("openabm", _data("openabm"), contacts="recorded")
    # 1.000 when the day-after-the-data target is scored against 0 as the original did
    assert (abs(df["rmse_ratio"] - 1) < 0.02).all(), df


def test_age_structured_known_both_reproduces():
    """~1 min. Only the both-known row reproduces; see docs/REPRODUCING.md."""
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("age_structured", _data("age_structured"), methods=("known_both",),
                         contacts="recorded")
    assert (abs(df["rmse_ratio"] - 1) < 0.15).all(), df
