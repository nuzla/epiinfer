"""Regression tests for defects found in the full review (each one failed before its fix)."""

import shutil
import zipfile

import numpy as np
import pandas as pd
import pytest

from epiinfer import Config, DataFormatError, load_dataset
from epiinfer.cli import main
from epiinfer.config import PAPER
from epiinfer.core import EpiInferCore
from epiinfer.data import detect_state_codes
from epiinfer.forecast import build_model, forecast, run


# --- look-ahead -----------------------------------------------------------------------
def _toy_model():
    n = 40
    contacts = {d: [(i, (i + 1) % n) for i in range(n)] for d in range(1, 11)}
    return EpiInferCore(range(n), contacts, np.arange(n) % 2, inc=2, duration=3), n


def test_frozen_projection_ignores_future_contacts():
    """With graph_until=origin, rewiring the graph after the origin must not change anything."""
    model, n = _toy_model()
    args = (np.full(2, 0.6), np.ones(2), {3: {0, 1, 2}}, {}, 3, 10, set())
    base = model.project(*args, np.random.RandomState(0), graph_until=3)
    for d in range(4, 11):                         # scramble every future day's contacts
        model.adj[d] = {i: {(i + 7) % n} for i in range(n)}
    again = model.project(*args, np.random.RandomState(0), graph_until=3)
    peeks = model.project(*args, np.random.RandomState(0), graph_until=None)
    assert all((base[d] == again[d]).all() for d in base)
    assert any((base[d] != peeks[d]).any() for d in base)


def test_rolling_forecast_frozen_has_no_lookahead(tmp_path, demo_path):
    """Changing contacts after day D must not change frozen forecasts made at origin <= D."""
    d = tmp_path / "edit"
    shutil.copytree(demo_path, d)
    e = pd.read_csv(d / "timed_edges.csv")
    cut = 34
    late = e["day"] > cut
    e.loc[late, "j"] = (e.loc[late, "j"] + 17) % 600     # rewire the future
    e.to_csv(d / "timed_edges.csv", index=False)
    # horizon 9 > inc (5): new exposures after the origin reach the symptomatic count
    kw = dict(start_eval=28, max_day=45, num_sims=3, horizons=(9,), seed=1)
    for contacts, same in (("frozen", True), ("recorded", False)):
        a = run(demo_path, "empirical_p1", contacts=contacts, **kw).rows
        b = run(d, "empirical_p1", contacts=contacts, **kw).rows
        a, b = a[a["current_day"] <= cut], b[b["current_day"] <= cut]
        assert len(a) > 0
        assert a["predicted"].equals(b["predicted"]) is same, contacts


def test_config_rejects_bad_values():
    with pytest.raises(ValueError, match="contacts"):
        Config(contacts="future")
    with pytest.raises(ValueError, match="num_sims"):
        PAPER.with_(num_sims=0)
    with pytest.raises(ValueError, match="horizons"):
        PAPER.with_(horizons=(0, 5))


# --- data loading ---------------------------------------------------------------------
def test_state_code_swap_keeps_codes_unique():
    """S coded as 1 used to give S and A the same code, silently emptying S."""
    st = pd.DataFrame({"id": range(10), "day": 0, "state": [1] * 9 + [0]})
    tot = pd.DataFrame({"day": [0], "S": [9]})
    codes = detect_state_codes(st, tot)
    assert codes["S"] == 1 and codes["A"] == 0
    assert len(set(codes.values())) == 4


def test_notebook_avg_contacts_column_accepted(tmp_path, demo_path):
    """The ABM notebook writes `avg_contacts`, not `c`; the check used to crash on it."""
    from epiinfer.data import validate_age_mapping
    d = tmp_path / "nb"
    shutil.copytree(demo_path, d)
    a = pd.read_csv(d / "daily_group_avg_contacts.csv").rename(columns={"c": "avg_contacts"})
    a.to_csv(d / "daily_group_avg_contacts.csv", index=False)
    data = load_dataset(d)
    assert validate_age_mapping(data.age_of, data.daily_contacts, d, data.age_labels)
    a["avg_contacts"] *= 10                         # the check must still bite
    a.to_csv(d / "daily_group_avg_contacts.csv", index=False)
    assert not validate_age_mapping(data.age_of, data.daily_contacts, d, data.age_labels)


def test_edge_ids_out_of_range_rejected(tmp_path, demo_path):
    d = tmp_path / "edges"
    shutil.copytree(demo_path, d)
    e = pd.read_csv(d / "timed_edges.csv")
    e.loc[0, "j"] = 600
    e.to_csv(d / "timed_edges.csv", index=False)
    with pytest.raises(DataFormatError, match="timed_edges.csv"):
        load_dataset(d)


def test_sparse_group_file_is_zero_filled(tmp_path, demo_path):
    """Real group files omit zero counts; forecast(from_day=...) used to crash on them."""
    d = tmp_path / "sparse"
    shutil.copytree(demo_path, d)
    gi = pd.read_csv(d / "daily_group_infected.csv")
    gi[gi["infected"] > 0].to_csv(d / "daily_group_infected.csv", index=False)
    data = load_dataset(d)
    assert all(data.gt_group[g][0] == 0 for g in range(3))
    df = forecast(data, horizon=3, method="empirical_p1", from_day=20, num_sims=2)
    assert df["actual"].notna().all()


def test_empty_last_group_keeps_group_count(tmp_path, demo_path):
    d = tmp_path / "empty"
    shutil.copytree(demo_path, d)
    pop = pd.read_csv(d / "age_group_population.csv")
    pop = pd.concat([pop, pd.DataFrame({"age_group": ["90+"], "population": [0]})])
    pop.to_csv(d / "age_group_population.csv", index=False)
    data = load_dataset(d)
    assert data.n_groups == 4 and build_model(data, PAPER).n_groups == 4
    res = run(data, "empirical_p1", start_eval=30, max_day=32, num_sims=1, horizons=(1,))
    assert set(res.rows["group"]) == {"0-19", "20-60", "61+", "90+", "ALL"}


# --- forecast -------------------------------------------------------------------------
def test_forecast_from_past_day_has_no_lookahead(tmp_path, demo_path):
    d = tmp_path / "edit"
    shutil.copytree(demo_path, d)
    e = pd.read_csv(d / "timed_edges.csv")
    late = e["day"] > 30
    e.loc[late, "j"] = (e.loc[late, "j"] + 17) % 600
    e.to_csv(d / "timed_edges.csv", index=False)
    kw = dict(horizon=12, method="empirical_p1", from_day=30, num_sims=3, seed=4)
    pd.testing.assert_frame_equal(forecast(demo_path, **kw), forecast(d, **kw))


def test_forecast_rejects_out_of_range_origin(demo_path):
    with pytest.raises(ValueError, match="from_day"):
        forecast(demo_path, horizon=2, method="empirical_p1", from_day=5)
    with pytest.raises(ValueError, match="from_day"):
        forecast(demo_path, horizon=2, method="empirical_p1", from_day=46)


def test_history_covers_long_incubation(data):
    """The fixed 8-day history dropped A cohorts when inc > 7."""
    from epiinfer.forecast import _lookback
    model = build_model(data, PAPER.with_(inc=12, duration=9))
    assert _lookback("unknown_both", model) >= 12 + 1
    assert _lookback("unknown_both", build_model(data, PAPER)) == 8      # paper value kept


# --- CLI ------------------------------------------------------------------------------
def test_cli_run_accepts_timing_and_horizons(tmp_path, demo_path):
    rc = main(["run", "--data", str(demo_path), "--method", "empirical_p1", "--inc", "6",
               "--duration", "9", "--horizons", "2", "--start-eval", "30", "--max-day", "33",
               "--num-sims", "2", "--out", str(tmp_path)])
    assert rc == 0
    summ = pd.read_csv(tmp_path / "summary_demo_data_empirical_p1.csv")
    assert set(summ["horizon"]) == {2}


def test_cli_plots(tmp_path, demo_path):
    pytest.importorskip("matplotlib")
    rc = main(["run", "--data", str(demo_path), "--method", "empirical_p1", "--start-eval", "40",
               "--num-sims", "2", "--out", str(tmp_path), "--plots"])
    assert rc == 0 and (tmp_path / "forecast_demo_data_empirical_p1.png").exists()


def test_missing_optional_extra_gives_install_hint(tmp_path, demo_path, monkeypatch):
    """A base install used to crash with a bare ModuleNotFoundError on --plots."""
    import sys
    monkeypatch.setitem(sys.modules, "matplotlib", None)       # import -> ImportError
    with pytest.raises(SystemExit, match="epiinfer\\[plots\\]"):
        main(["run", "--data", str(demo_path), "--method", "empirical_p1", "--start-eval", "44",
              "--num-sims", "1", "--out", str(tmp_path), "--plots"])
    monkeypatch.setitem(sys.modules, "statsmodels", None)
    with pytest.raises(SystemExit, match="epiinfer\\[baselines\\]"):
        main(["baseline", "--data", str(demo_path)])


def test_cli_simulate_per_group_rates(tmp_path):
    rc = main(["simulate", "--out", str(tmp_path / "s"), "--sizes", "50", "60", "40",
               "--p1", "0.3", "--p2", "0.1", "0.2", "0.3", "--days", "4", "--scale", "2"])
    assert rc == 0
    assert pd.read_csv(tmp_path / "s" / "age_group_population.csv")["population"].sum() == 150
    with pytest.raises(SystemExit):
        main(["simulate", "--out", str(tmp_path / "t"), "--p1", "0.1", "0.2"])


def test_reproduce_jobs_give_identical_results(demo_path):
    from epiinfer.reproduce import reproduce_table
    kw = dict(quick=True, methods=("known_both", "known_p1"))
    serial = reproduce_table("age_structured", demo_path, jobs=1, **kw)
    parallel = reproduce_table("age_structured", demo_path, jobs=2, **kw)
    pd.testing.assert_frame_equal(serial, parallel)
    with pytest.raises(ValueError, match="no published values"):
        reproduce_table("openabm", demo_path, quick=True, methods=("known_both",))


# --- fetch ----------------------------------------------------------------------------
def _serve(monkeypatch, archive):
    import epiinfer.fetch as f
    monkeypatch.setattr(f.urllib.request, "urlretrieve",
                        lambda url, dest: shutil.copy(archive, dest))
    return f


def test_fetch_verifies_checksum_and_unpacks(tmp_path, monkeypatch):
    src = tmp_path / "a.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("ds/x.csv", "a\n1\n")
    f = _serve(monkeypatch, src)
    out = f.fetch("https://example.org/rel/a.zip?x=1", tmp_path / "d1", f.sha256(src))
    assert (out / "ds" / "x.csv").exists()
    with pytest.raises(SystemExit, match="checksum mismatch"):
        f.fetch("https://example.org/a.zip", tmp_path / "d2", "0" * 64)
    with pytest.raises(SystemExit, match="non-HTTPS"):
        f.fetch("http://localhost.evil.example/a.zip", tmp_path / "d3")


def test_fetch_blocks_zip_slip_into_sibling_dir(tmp_path, monkeypatch):
    src = tmp_path / "bad.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("../data2/evil.txt", "x")
    f = _serve(monkeypatch, src)
    with pytest.raises(SystemExit, match="unsafe path"):
        f.fetch("https://example.org/bad.zip", tmp_path / "data", f.sha256(src))
    assert not (tmp_path / "data2").exists()


def test_targets_never_beyond_last_observed_day(data):
    """The original scored a forecast for the day after the data ends against actual = 0."""
    res = run(data, "empirical_p1", start_eval=40, num_sims=1, horizons=(1, 3))
    assert res.rows["target_day"].max() == max(data.all_days)


def test_last_origin_limits_origins_not_targets(data):
    res = run(data, "empirical_p1", start_eval=30, last_origin=33, num_sims=1, horizons=(1, 6))
    assert res.rows["current_day"].max() == 33 and res.rows["target_day"].max() == 39


def test_baseline_window_matches_epiinfer(data):
    pytest.importorskip("statsmodels")
    from epiinfer.baselines import rolling_baseline
    b = rolling_baseline(data, "arima", horizons=(1, 3), start_eval=36, max_day=42)
    e = run(data, "empirical_p1", start_eval=36, max_day=42, num_sims=1, horizons=(1, 3)).summary()
    e = e[e["group"] == "ALL"].set_index("horizon")["n"]
    assert b.set_index("horizon")["n"].to_dict() == e.to_dict()


def test_string_age_labels_in_individual_file(tmp_path, demo_path):
    d = tmp_path / "labels"
    shutil.copytree(demo_path, d)
    m = pd.read_csv(d / "individual_age_group.csv")
    labels = pd.read_csv(d / "age_group_population.csv")["age_group"].tolist()
    m["age_group"] = m["age_group"].map(dict(enumerate(labels)))
    m.to_csv(d / "individual_age_group.csv", index=False)
    assert (load_dataset(d).age_of == load_dataset(demo_path).age_of).all()
    m.loc[0, "age_group"] = "elderly"
    m.to_csv(d / "individual_age_group.csv", index=False)
    with pytest.raises(DataFormatError, match="elderly"):
        load_dataset(d)


def test_reproduce_flags_wrong_dataset(tmp_path, demo_path, capsys):
    """Running a table on the wrong data must say so instead of printing a silent mismatch."""
    from epiinfer.reproduce import reproduce_table
    from epiinfer.reproduce.run import check_dataset, fingerprint
    data = load_dataset(demo_path)
    assert fingerprint(data) == (600, 46, int(max(data.gt_total.values())))
    assert check_dataset("openabm", data).startswith("MISMATCH")
    df = reproduce_table("openabm", demo_path, quick=True)
    assert df["dataset_check"].str.startswith("MISMATCH").all()
    assert main(["reproduce", "--table", "openabm", "--data", str(demo_path), "--quick",
                 "--out", str(tmp_path)]) == 0
    assert "WARNING: MISMATCH" in capsys.readouterr().out


def test_hw_table_runs(demo_path):
    pytest.importorskip("statsmodels")
    from epiinfer.reproduce import reproduce_table
    df = reproduce_table("hw_age_structured", demo_path)
    assert list(df["horizon"]) == [1, 5, 10, 20] and df["rmse"].notna().all()


def test_holt_winters_clips_and_falls_back():
    """As in the authors' notebook: forecasts never go below 0, and with fewer than 5 points
    the last value is carried forward."""
    pytest.importorskip("statsmodels")
    import warnings

    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    from epiinfer.baselines import _holt_winters
    y = np.array([400, 330, 260, 190, 120, 60, 25, 8], float)          # collapsing epidemic
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = ExponentialSmoothing(y, trend="add", damped_trend=True,
                                   initialization_method="estimated").fit().forecast(10)
    assert (np.asarray(raw) < 0).any()                 # the clip has something to do
    fc = _holt_winters(y, 10)
    assert (fc >= 0).all() and (fc == 0).any()
    assert (_holt_winters(np.array([5.0, 7.0, 9.0]), 3) == 9.0).all()


def test_authors_run_targets_complete_and_consistent():
    """The authors' own run covers every (mode, horizon) the paper table has, and the knowledge
    modes behave as theory says: knowing more never hurts the 1-day forecast by much."""
    from epiinfer.reproduce.targets import AUTHORS_RUN_AGE_STRUCTURED, TABLES
    spec = TABLES["age_structured"]
    assert set(AUTHORS_RUN_AGE_STRUCTURED) == set(spec["targets"])
    kb = AUTHORS_RUN_AGE_STRUCTURED[("known_both", 1)][0]
    assert all(AUTHORS_RUN_AGE_STRUCTURED[(m, 1)][0] >= 0.9 * kb
               for m in spec["methods"])


def test_reproduce_adds_authors_columns_only_where_available(demo_path):
    from epiinfer.reproduce import reproduce_table
    age = reproduce_table("age_structured", demo_path, quick=True, methods=("known_both",))
    assert {"authors_rmse", "authors_ratio"} <= set(age.columns) and age["authors_rmse"].notna().all()
    oab = reproduce_table("openabm", demo_path, quick=True)
    assert "authors_rmse" not in oab.columns
