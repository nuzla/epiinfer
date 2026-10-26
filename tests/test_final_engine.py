"""The final (October 2026) engine must reproduce the authors' notebook exactly.

The fixture comes from ``tools/make_golden_final.py``, which executes abm_final.ipynb's own code
cells, unchanged, on the bundled demo data.
"""

import gzip
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epiinfer.final import (
    FinalCalibrator,
    FinalCore,
    FinalData,
    FinalSettings,
    run_final,
    summarize_relative,
)

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def gold():
    return json.loads((HERE / "golden_final_notebook.json").read_text())


@pytest.fixture(scope="module")
def settings(gold):
    s = gold["settings"]
    return FinalSettings(end_day=s["end_day"], horizons=tuple(s["horizons"]), n_mc=s["n_mc"])


@pytest.fixture(scope="module")
def fdata(demo_path):
    return FinalData.from_folder(demo_path)


def test_reconstruct_nowcast_predict_match_notebook(fdata, settings, gold):
    core = FinalCore(fdata, settings)
    assert core.reconstruct(30, 0.1, 12345).tolist() == gold["reconstruct"]
    assert core.nowcast(30, 0.15, 0.1, np.random.default_rng(7)).tolist() == gold["nowcast"]
    pr = core.predict_mc(30, 0.15, 0.1, 10, 3, seed=30 * 104729)
    assert {str(k): v for k, v in pr.items()} == pytest.approx(gold["predict_mc"], rel=1e-12)


def test_calibration_matches_notebook(fdata, settings, gold):
    s = gold["settings"]
    cal = FinalCalibrator(FinalCore(fdata, settings))
    assert cal.score(0.15, 0.1, 30) == pytest.approx(gold["score"], rel=1e-12)
    for case, want in gold["best"].items():
        assert list(cal.best(case, 30, s["p1_true"], s["p2_true"])) == pytest.approx(want), case
    damped = cal.damp((0.2, 0.2), tuple(gold["best"]["unknown_both"]), 30)
    assert list(damped) == pytest.approx(gold["damp"], rel=1e-12)


def test_rolling_run_matches_notebook(fdata, settings, gold):
    s = gold["settings"]
    pred, trace = run_final(fdata, p1_true=s["p1_true"], p2_true=s["p2_true"], settings=settings)
    want = pd.DataFrame(gold["predictions"])
    assert len(pred) == len(want) == 11 * 4 * 3
    for col in ("case", "horizon", "origin", "target_day", "actual"):
        assert pred[col].tolist() == want[col].tolist(), col
    for col in ("predicted", "p1_used", "p2_used"):
        assert np.allclose(pred[col].to_numpy(float), want[col].to_numpy(float), rtol=1e-12, atol=0)
    wt = pd.DataFrame(gold["trace"])
    assert trace[["case", "origin"]].values.tolist() == wt[["case", "origin"]].values.tolist()
    assert np.allclose(trace[["p1_used", "p2_used"]].to_numpy(float),
                       wt[["p1_used", "p2_used"]].to_numpy(float), rtol=1e-12, atol=0)


def test_only_infected_and_recovered_states_are_read(tmp_path, demo_path, fdata, settings):
    """Erasing every pre-symptomatic (A) record must not change anything."""
    d = tmp_path / "no_a"
    shutil.copytree(demo_path, d)
    st = pd.read_csv(d / "individual_day_state.csv")
    st.loc[st["state"] == 1, "state"] = 0
    st.to_csv(d / "individual_day_state.csv", index=False)
    a = FinalCore(fdata, settings).predict_mc(30, 0.15, 0.1, 10, 3, seed=1)
    b = FinalCore(FinalData.from_folder(d), settings).predict_mc(30, 0.15, 0.1, 10, 3, seed=1)
    assert a == b


def test_no_lookahead(fdata, settings):
    """The notebook's leak test: scrambling every observation after the origin leaves the
    forecast unchanged."""
    origin = 30
    rng = np.random.default_rng(0)
    S2 = np.zeros((fdata.T, fdata.n), dtype=np.int8)
    S2[:origin + 1][fdata.is_inf[:origin + 1]] = 2
    S2[:origin + 1][fdata.is_rec[:origin + 1]] = 3
    S2[origin + 1:] = rng.choice([1, 2, 3], size=(fdata.T - origin - 1, fdata.n))
    edges2 = dict(fdata.edges)
    for day in list(edges2):
        if day > origin:
            m = len(edges2[day][0])
            edges2[day] = (rng.integers(0, fdata.n, m).astype(np.int32),
                           rng.integers(0, fdata.n, m).astype(np.int32))
    a = FinalCore(fdata, settings).predict_mc(origin, 0.15, 0.1, 10, 3, 123)
    b = FinalCore(FinalData(S2, edges2), settings).predict_mc(origin, 0.15, 0.1, 10, 3, 123)
    assert a == b


def test_recovered_people_become_susceptible_again(fdata, settings):
    """rec_duration matters: with permanent immunity (a huge rec_dur) forecasts change."""
    a = FinalCore(fdata, settings).predict_mc(25, 0.2, 0.2, 10, 3, 5)
    b = FinalCore(fdata, FinalSettings(end_day=46, horizons=(1, 5, 10), n_mc=3,
                                       rec_dur=10**5)).predict_mc(25, 0.2, 0.2, 10, 3, 5)
    assert any(abs(a[t] - b[t]) > 0 for t in a)


def test_summarize_reproduces_the_authors_summary():
    """abm_summary.csv (the paper's Tables 10-13) is exactly summarize(abm_predictions.csv)."""
    with gzip.open(HERE / "data" / "abm_predictions.csv.gz", "rt") as f:
        pred = pd.read_csv(f)
    from epiinfer.reproduce.sweep import load_targets
    want = load_targets()
    got = summarize_relative(pred)
    m = got.merge(want, on=["p1", "p2", "case", "horizon"], suffixes=("", "_paper"))
    assert len(m) == len(want) == 192
    assert (m["RMSE"] == m["RMSE_paper"]).all() and (m["fRMSE"] == m["fRMSE_paper"]).all()


def test_known_rates_required():
    s = FinalSettings(end_day=46, horizons=(1,), n_mc=1)
    with pytest.raises(ValueError, match="true rate"):
        run_final(None, cases=("known_both",), settings=s)
    with pytest.raises(ValueError, match="unknown case"):
        run_final(None, cases=("guess",), settings=s)


def test_relative_rmse_skips_zero_actuals():
    from epiinfer.metrics import relative_rmse
    assert relative_rmse([1, 2, 3], [0, 1, 2]) == pytest.approx(np.sqrt((1 + 0.25) / 2))
    assert np.isnan(relative_rmse([1.0], [0.0]))
