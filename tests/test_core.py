import numpy as np
import pandas as pd
import pytest

import epiinfer
from epiinfer import DataFormatError, fractional_rmse, load_dataset, rmse
from epiinfer.calibrate import solve_p1
from epiinfer.config import PAPER
from epiinfer.core import EpiInferCore
from epiinfer.forecast import forecast, run, sim_rng


def test_metrics():
    assert rmse([1, 2], [1, 4]) == pytest.approx(np.sqrt(2))
    assert fractional_rmse([1, 2], [1, 4]) == pytest.approx(np.sqrt(2) / 2.5)
    assert np.isnan(rmse([], [])) and np.isnan(fractional_rmse([1], [0]))


def test_solve_p1_inverts_expectation():
    kh = {1: 100, 2: 50, 4: 10}
    p = 0.07
    expected = sum(n * (1 - (1 - p) ** k) for k, n in kh.items())
    assert solve_p1(kh, expected) == pytest.approx(p, abs=1e-9)
    assert solve_p1({}, 3) == 0.0


def test_project_is_seeded_and_isolated():
    """Same seed -> same trajectory; different seed -> different; caller's history untouched."""
    n = 60
    contacts = {d: [(i, (i + d) % n) for i in range(n)] for d in range(1, 30)}
    age = np.arange(n) % 3
    model = EpiInferCore(range(n), contacts, age, inc=3, duration=4)
    h_a = {0: set(range(6))}
    h_i = {}
    args = (np.full(3, 0.4), np.ones(3), h_a, h_i, 0, 15, set())
    a = model.project(*args, np.random.RandomState(1))
    b = model.project(*args, np.random.RandomState(1))
    c = model.project(*args, np.random.RandomState(2))
    assert all((a[d] == b[d]).all() for d in a)
    assert any((a[d] != c[d]).any() for d in a)
    assert h_a == {0: set(range(6))} and h_i == {}


def test_sim_rng_streams_independent_of_order():
    a = sim_rng(0, 30, 2).random_sample(3)
    sim_rng(0, 30, 0).random_sample(100)
    assert (sim_rng(0, 30, 2).random_sample(3) == a).all()
    assert (sim_rng(0, 31, 2).random_sample(3) != a).any()


def test_workers_do_not_change_results(data):
    kw = dict(start_eval=30, max_day=36, num_sims=4, horizons=(1, 5), seed=3)
    one = run(data, "empirical_p1", mc_threads=1, **kw).rows
    four = run(data, "empirical_p1", mc_threads=4, **kw).rows
    pd.testing.assert_frame_equal(one, four)


def test_seed_changes_stochastic_forecast(data):
    # horizon must exceed `inc` (5): new exposures only turn symptomatic after inc days
    kw = dict(start_eval=30, max_day=48, num_sims=4, horizons=(12,))
    a = run(data, "empirical_p1", seed=1, **kw).rows["predicted"].to_numpy()
    b = run(data, "empirical_p1", seed=1, **kw).rows["predicted"].to_numpy()
    c = run(data, "empirical_p1", seed=2, **kw).rows["predicted"].to_numpy()
    assert (a == b).all() and (a != c).any()


def test_forecast_shape_and_future_actual_is_nan(demo_path):
    df = forecast(demo_path, horizon=4, method="empirical_p1", num_sims=4)
    assert set(df["group"]) == {"0-19", "20-60", "61+", "ALL"}
    assert df["horizon"].max() == 4 and len(df) == 4 * 4
    assert df["actual"].isna().all()               # beyond the last observed day
    assert (df["p10"] <= df["mean"] + 1e-9).all() and (df["mean"] <= df["p90"] + 1e-9).all()
    allrow = df[df["group"] == "ALL"].set_index("target_day")["mean"]
    parts = df[df["group"] != "ALL"].groupby("target_day")["mean"].sum()
    assert np.allclose(allrow.sort_index(), parts.sort_index())


def test_forecast_from_past_day_reports_actuals(demo_path):
    df = forecast(demo_path, horizon=3, method="empirical_p1", from_day=30, num_sims=3)
    assert df["actual"].notna().all()


def test_known_methods_need_truth(data):
    with pytest.raises(ValueError, match="p1_true"):
        run(data, "known_both", cfg=PAPER.with_(p1_true=None, p2_true=None),
            start_eval=30, max_day=31, num_sims=1)


def test_unknown_method_rejected(data):
    with pytest.raises(ValueError, match="unknown method"):
        run(data, "nope")


def test_missing_file_and_column(tmp_path, demo_path):
    with pytest.raises(DataFormatError, match="not found"):
        load_dataset(tmp_path / "missing")
    d = tmp_path / "bad"
    d.mkdir()
    pd.DataFrame({"id": [0], "day": [0]}).to_csv(d / "individual_day_state.csv", index=False)
    with pytest.raises(DataFormatError, match="missing column"):
        load_dataset(d)


def test_minimal_dataset_derives_everything(tmp_path, demo_path):
    """Only 3 files needed: states_total / group counts are derived."""
    import shutil
    d = tmp_path / "min"
    d.mkdir()
    for f in ("individual_day_state.csv", "timed_edges.csv", "individual_age_group.csv"):
        shutil.copy(demo_path / f, d / f)
    m = load_dataset(d)
    ref = load_dataset(demo_path)
    assert m.gt_total == {int(k): int(v) for k, v in ref.gt_total.items()}
    assert m.gt_group == ref.gt_group


def test_state_code_remap(tmp_path, demo_path):
    """Susceptible encoded as another code is detected via states_total."""
    import shutil
    d = tmp_path / "remap"
    shutil.copytree(demo_path, d)
    st = pd.read_csv(d / "individual_day_state.csv")
    assert (st["state"] == 0).any()
    st["state"] = st["state"].replace({0: 9})
    st.to_csv(d / "individual_day_state.csv", index=False)
    from epiinfer.data import detect_state_codes
    codes = detect_state_codes(st, pd.read_csv(d / "states_total.csv"))
    assert codes["S"] == 9


def test_id_out_of_range_rejected(tmp_path, demo_path):
    import shutil
    d = tmp_path / "oob"
    shutil.copytree(demo_path, d)
    st = pd.read_csv(d / "individual_day_state.csv")
    st.loc[0, "id"] = 10_000
    st.to_csv(d / "individual_day_state.csv", index=False)
    with pytest.raises(DataFormatError, match="ids must be"):
        load_dataset(d)


def test_public_api():
    for name in ("run", "forecast", "load_dataset", "Config", "PAPER", "OPENABM"):
        assert hasattr(epiinfer, name)


def test_strict_vs_diff_transitions_on_sparse_records(tmp_path, demo_path):
    """A person missing from the record on day k-1 is a record gap, not a new infection under
    the 'strict' definition (S on k-1 and A on k) used by the empirical-p1 method."""
    import shutil
    d = tmp_path / "gap"
    shutil.copytree(demo_path, d)
    st = pd.read_csv(d / "individual_day_state.csv")
    ref = load_dataset(demo_path)
    day = 20
    pid = sorted(ref.asymp_on[day - 1] & ref.asymp_on[day])[0]   # in A on both days
    st = st[~((st["id"] == pid) & (st["day"] == day - 1))]       # delete day k-1's record
    st.to_csv(d / "individual_day_state.csv", index=False)
    gap = load_dataset(d)
    assert pid in gap.new_asymp[day]            # diff: looks newly infected (artefact)
    assert pid not in gap.new_asymp_strict[day]  # strict: robust to the gap


def test_each_method_uses_its_transition_definition(data, monkeypatch):
    seen = []
    orig = type(data).transitions

    def spy(self, kind):
        seen.append(kind)
        return orig(self, kind)

    monkeypatch.setattr(type(data), "transitions", spy)
    run(data, "empirical_p1", start_eval=30, max_day=32, num_sims=1, horizons=(1,))
    run(data, "known_both", start_eval=30, max_day=32, num_sims=1, horizons=(1,), engine="contact")
    assert seen == ["strict", "diff"]
