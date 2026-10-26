"""EpiInfer, the earlier compartmental model, must reproduce the authors' notebooks exactly.

The fixture comes from ``tools/make_golden_compartmental.py``, which runs
``epiinfer for base case.ipynb`` and ``Epiinfer for C_0.2.ipynb`` unchanged on the demo data.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epiinfer import COMPARTMENTAL, PAPER, forecast, load_dataset, run
from epiinfer.cli import main
from epiinfer.compartmental import GroupCounts, calibrate, run_compartmental, simulate, summarize

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def gold():
    return json.loads((HERE / "golden_compartmental_notebook.json").read_text())


@pytest.fixture(scope="module")
def gc(demo_path):
    return GroupCounts.from_folder(demo_path)


def test_projection_matches_both_notebooks(gc, gold):
    a = simulate(gc, gold["p1"], gold["p2"], 20, 21, contacts="avg5")[:, 0]
    assert np.allclose(a, gold["base_sim"], rtol=1e-12, atol=0)
    b = simulate(gc, gold["p1"], gold["p2"], 20, 21, contacts="same_day")[:, 0]
    assert np.allclose(b, gold["calib_sim"], rtol=1e-12, atol=0)
    assert not np.allclose(a, b)                    # the two contact rules really differ


def test_base_case_rmse_matches_notebook(gc, gold):
    pred = run_compartmental(gc, ("known_both",), gold["p1"], gold["p2"])
    assert sorted(set(pred["origin"])) == list(range(20, 26))   # origin + 20 < 46 days
    s = summarize(pred)
    assert np.allclose(s["rmse"], gold["base_rmse"], rtol=1e-12, atol=0)


def test_knowledge_settings_match_notebook(gc, gold):
    want = pd.DataFrame(gold["calib_summary"]).set_index("Method")
    pred = run_compartmental(gc, tuple(want.index), gold["p1"], gold["p2"], horizons=(20,),
                             contacts="same_day")
    s = summarize(pred).set_index("case")
    last = pred.groupby("case").last()
    for case, row in want.iterrows():
        assert s.loc[case, "rmse"] == pytest.approx(row["RMSE_abs"], rel=1e-12), case
        assert s.loc[case, "frmse_rel"] == pytest.approx(row["RMSE_frac"], rel=1e-9), case
        assert last.loc[case, "p1_used"] == pytest.approx(row["Est_p1"], rel=1e-12), case
        assert last.loc[case, "p2_used"] == pytest.approx(row["Est_p2"], rel=1e-12), case


def test_calibration_searches_only_the_missing_rate(gc):
    assert calibrate(gc, "known_both", 30, 0.15, 0.1) == (0.15, 0.1)
    p1, p2 = calibrate(gc, "known_p1", 30, 0.15, None)
    assert p1 == 0.15 and 0.05 <= p2 <= 0.3
    p1, p2 = calibrate(gc, "known_p2", 30, None, 0.1)
    assert p2 == 0.1 and 0.05 <= p1 <= 0.3
    with pytest.raises(ValueError, match="needs the true p1"):
        calibrate(gc, "known_p1", 30)


def test_frozen_contacts_never_read_the_future(gc, demo_path, tmp_path):
    """With frozen contacts, scrambling every contact average after the origin changes nothing;
    the notebooks' recorded mode does read them."""
    d = tmp_path / "scrambled"
    shutil.copytree(demo_path, d)
    con = pd.read_csv(d / "daily_group_avg_contacts.csv")
    con.loc[con["day"] > 30, "c"] *= 3
    con.to_csv(d / "daily_group_avg_contacts.csv", index=False)
    other = GroupCounts.from_folder(d)
    frozen = [simulate(g, 0.15, 0.1, 31, 10, freeze_after=30)[:, 0] for g in (gc, other)]
    assert np.array_equal(*frozen)
    recorded = [simulate(g, 0.15, 0.1, 31, 10)[:, 0] for g in (gc, other)]
    assert not np.array_equal(*recorded)


def test_engine_through_run_and_forecast(demo_path):
    res = run(demo_path, "known_both", engine="compartmental", p1_true=(0.15,), p2_true=(0.1,),
              max_day=46, horizons=(1, 5, 10))
    assert res.config.engine == "compartmental"
    assert res.rows["current_day"].min() == 25 and res.rows["current_day"].max() == 35
    assert (res.rows["target_day"] == res.rows["current_day"] + res.rows["horizon"]).all()
    # the notebooks' origin o is the first projected day, i.e. current_day + 1
    gc = GroupCounts.from_folder(demo_path)
    sim = simulate(gc, 0.15, 0.1, 31, 5, freeze_after=30)
    row = res.rows[(res.rows["current_day"] == 30) & (res.rows["horizon"] == 5)].iloc[0]
    assert row["predicted"] == pytest.approx(sim[35, 0], rel=1e-12)

    fc = forecast(demo_path, horizon=5, method="known_both", engine="compartmental",
                  p1_true=(0.15,), p2_true=(0.1,), from_day=30)
    assert list(fc["target_day"]) == [31, 32, 33, 34, 35]
    assert np.allclose(fc["mean"], sim[31:36, 0]) and (fc["p10"] == fc["p90"]).all()
    fut = forecast(demo_path, horizon=4, engine="compartmental")       # past the data
    assert fut["actual"].isna().all() and np.isfinite(fut["mean"]).all()


def test_engine_errors(demo_path):
    with pytest.raises(ValueError, match="one p1 for the whole population"):
        run(demo_path, "known_both", cfg=COMPARTMENTAL.with_(p1_true=PAPER.p1_true,
                                                             p2_true=PAPER.p2_true))
    with pytest.raises(ValueError, match="only in the contact engine"):
        run(demo_path, "empirical_p1", engine="compartmental")
    with pytest.raises(TypeError, match="pass its path"):
        run(load_dataset(demo_path), "unknown_both", engine="compartmental")
    with pytest.raises(ValueError, match="from_day"):
        forecast(demo_path, horizon=3, engine="compartmental", from_day=5)
    with pytest.raises(ValueError, match="group_contacts"):
        COMPARTMENTAL.with_(group_contacts="weekly")


def test_cli_run_and_describe(demo_path, tmp_path, capsys):
    assert main(["describe", "--data", str(demo_path)]) == 0
    assert "final, contact, compartmental" in capsys.readouterr().out
    assert main(["run", "--data", str(demo_path), "--engine", "compartmental", "--method",
                 "unknown_both", "--max-day", "46", "--horizons", "1", "5",
                 "--out", str(tmp_path)]) == 0
    s = pd.read_csv(tmp_path / "summary_demo_data_unknown_both.csv")
    assert list(s["horizon"]) == [1, 5] and (s["n"] == 16).all()


def test_per_group_exposure_keeps_groups_independent(gc):
    """Each group's exposure chance comes from its own symptomatic people: changing one group's
    p1 leaves the other groups' projections untouched (the pooled rule couples them)."""
    a = simulate(gc, (0.25, 0.15, 0.08), (0.15, 0.1, 0.05), 20, 15, exposure="per_group")
    b = simulate(gc, (0.25, 0.30, 0.08), (0.15, 0.1, 0.05), 20, 15, exposure="per_group")
    assert not np.array_equal(a[:, 2], b[:, 2])
    assert np.array_equal(a[:, 1], b[:, 1]) and np.array_equal(a[:, 3], b[:, 3])
    assert np.allclose(a[20:35, 0], a[20:35, 1:].sum(axis=1))
    with pytest.raises(ValueError, match="exposure='per_group'"):
        simulate(gc, (0.2, 0.1, 0.1), 0.1, 20, 5)
    with pytest.raises(ValueError, match="known_both only"):
        run_compartmental(gc, ("unknown_both",), exposure="per_group")
