"""Regression tests for defects found in the review of 0.2.0 (each one failed before its fix)."""

import shutil

import numpy as np
import pandas as pd
import pytest

from epiinfer import FINAL, Config, DataFormatError, forecast, load_dataset, run
from epiinfer.cli import main
from epiinfer.convert import cases_to_dataset
from epiinfer.forecast import ROW_COLUMNS, SUMMARY_COLUMNS
from epiinfer.simulate import AgeMixConfig, simulate, write_dataset

KNOWN = dict(p1_true=(0.15,), p2_true=(0.1,))


@pytest.fixture(scope="module")
def long_dataset(tmp_path_factory):
    """A 120-day epidemic: longer than Config.max_day (100), the back-test protocol's limit."""
    d = tmp_path_factory.mktemp("long") / "long"
    write_dataset(simulate(AgeMixConfig(group_sizes=(80, 160, 60), contact_scale=3.0, days=120,
                                        seed=5, init_a=6, p1=(0.25,) * 3, p2=(0.3,) * 3)), d)
    return d


# --- forecast() read only the first 100 days --------------------------------------------
@pytest.mark.parametrize("engine", ["final", "compartmental"])
def test_forecast_starts_from_the_last_day_of_a_long_dataset(long_dataset, engine):
    """It used to forecast from day 100 (and reject --from-day 110) on a 120-day dataset, because
    the loader applied the back-test limit Config.max_day."""
    fc = forecast(long_dataset, horizon=3, method="known_both", engine=engine, num_sims=2, **KNOWN)
    assert (fc["origin_day"] == 120).all() and list(fc["target_day"]) == [121, 122, 123]
    assert fc["actual"].isna().all()
    past = forecast(long_dataset, horizon=3, method="known_both", engine=engine, num_sims=2,
                    from_day=110, **KNOWN)
    assert (past["origin_day"] == 110).all() and past["actual"].notna().all()
    with pytest.raises(ValueError, match="last observed day 120"):
        forecast(long_dataset, horizon=3, method="known_both", engine=engine, from_day=121,
                 **KNOWN)


def test_forecast_ignores_days_beyond_its_window(long_dataset, tmp_path):
    """Reading only up to from_day + horizon must not change a forecast."""
    cut = tmp_path / "cut"
    cut.mkdir()
    for name in ("individual_day_state.csv", "timed_edges.csv"):
        df = pd.read_csv(long_dataset / name)
        df[df["day"] <= 113].to_csv(cut / name, index=False)
    shutil.copy(long_dataset / "age_group_population.csv", cut / "age_group_population.csv")
    kw = dict(horizon=3, method="known_both", from_day=110, num_sims=3, seed=2, **KNOWN)
    pd.testing.assert_frame_equal(forecast(long_dataset, **kw), forecast(cut, **kw))


# --- not enough history before the first origin ------------------------------------------
def test_run_needs_enough_history_before_the_first_origin(demo_path):
    """start_eval=15 crashed with a TypeError (unknown_both) or silently calibrated on nothing
    and picked the first grid value (known_p1)."""
    with pytest.raises(ValueError, match="start_eval.*22"):
        run(demo_path, "unknown_both", start_eval=15, num_sims=1)
    with pytest.raises(ValueError, match="start_eval.*22"):
        run(demo_path, "known_p1", start_eval=15, num_sims=1, **KNOWN)
    with pytest.raises(ValueError, match="start_eval"):
        run(demo_path, "known_both", start_eval=3, num_sims=1, **KNOWN)
    with pytest.raises(ValueError, match="start_eval.*14"):          # the 2025 engine: inc + duration
        run(demo_path, "unknown_both", engine="contact", start_eval=10, num_sims=1)
    res = run(demo_path, "known_p2", start_eval=22, max_day=28, horizons=(1,), num_sims=1,
              **KNOWN)
    assert res.rows["current_day"].min() == 22              # exactly the limit is allowed


def test_compartmental_engine_needs_history_before_its_first_origin(demo_path):
    """Earlier origins indexed the history from the end of the arrays (negative days)."""
    from epiinfer.compartmental import GroupCounts, run_compartmental
    with pytest.raises(ValueError, match="start_eval must be 11"):
        run(demo_path, "unknown_both", engine="compartmental", start_eval=5)
    with pytest.raises(ValueError, match="start_eval must be 6"):
        run(demo_path, "known_both", engine="compartmental", start_eval=3, **KNOWN)
    gc = GroupCounts.from_folder(demo_path)
    with pytest.raises(ValueError, match="first origin must be day 12"):
        run_compartmental(gc, ("unknown_both",), first_origin=5)
    ok = run_compartmental(gc, ("known_both",), 0.15, 0.1, horizons=(1,), first_origin=7,
                           last_origin=9)
    assert set(ok["origin"]) == {7, 8, 9}


def test_compartmental_loader_names_missing_columns(tmp_path, demo_path):
    """Aggregate data is the compartmental engine's audience; a missing column was a bare
    KeyError or AttributeError."""
    for name, drop, message in (
            ("daily_group_infected.csv", "infected", "daily_group_infected.csv: missing column"),
            ("states_total.csv", "R", r"states_total.csv: missing column\(s\) \['R'\]"),
            ("age_group_population.csv", "population", "age_group_population.csv: missing")):
        d = tmp_path / name
        shutil.copytree(demo_path, d)
        pd.read_csv(d / name).drop(columns=[drop]).to_csv(d / name, index=False)
        with pytest.raises(DataFormatError, match=message):
            forecast(d, horizon=2, engine="compartmental", method="known_both", **KNOWN)
    d = tmp_path / "nocontacts"
    shutil.copytree(demo_path, d)
    pd.read_csv(d / "daily_group_avg_contacts.csv").drop(columns=["c"]).to_csv(
        d / "daily_group_avg_contacts.csv", index=False)
    with pytest.raises(SystemExit, match="epiinfer: daily_group_avg_contacts.csv: needs a column c"):
        main(["forecast", "--data", str(d), "--engine", "compartmental", "--method",
              "known_both", "--p1-true", "0.15", "--p2-true", "0.1"])


def test_final_calibration_day_is_checked(demo_path):
    from epiinfer.final import FinalData, FinalSettings, calibrate_at
    fd = FinalData.from_folder(demo_path)
    with pytest.raises(ValueError, match="calibration day"):
        calibrate_at(fd, "unknown_both", 15, settings=FinalSettings())
    assert calibrate_at(fd, "known_both", 15, 0.15, 0.1) == (0.15, 0.1)


# --- the 2025 engine without pre-symptomatic records --------------------------------------
def test_contact_engine_refuses_data_without_the_presymptomatic_state(tmp_path, demo_path):
    """It used to forecast, silently, that nobody new gets infected (p10 == p90 == mean)."""
    d = tmp_path / "no_a"
    shutil.copytree(demo_path, d)
    st = pd.read_csv(d / "individual_day_state.csv")
    st.loc[st["state"] == 1, "state"] = 0
    st.to_csv(d / "individual_day_state.csv", index=False)
    rates = dict(p1_true=(0.25, 0.15, 0.08), p2_true=(0.15, 0.1, 0.05))
    with pytest.raises(ValueError, match="pre-symptomatic state"):
        run(d, "known_both", engine="contact", start_eval=30, max_day=34, num_sims=1, **rates)
    with pytest.raises(ValueError, match="pre-symptomatic state"):
        run(d, "empirical_p1", start_eval=30, max_day=34, num_sims=1)
    with pytest.raises(ValueError, match="pre-symptomatic state"):
        forecast(d, horizon=2, method="known_both", engine="contact", num_sims=1, **rates)
    with pytest.raises(SystemExit, match="epiinfer: the contact engine needs"):
        main(["forecast", "--data", str(d), "--engine", "contact", "--num-sims", "1"])
    assert len(forecast(d, horizon=2, method="known_both", num_sims=1, **KNOWN)) == 2   # final: fine


# --- configuration -----------------------------------------------------------------------
@pytest.mark.parametrize("kw, match", [
    (dict(recalib_every=0), "recalib_every"),
    (dict(final_calib_window=3), "final_calib_window"),
    (dict(rec_duration=-1), "rec_duration"),
    (dict(smoothing=0.0), "smoothing"),
    (dict(candidates=()), "candidates"),
    (dict(final_grid=(0.1, 1.5)), "final_grid"),
    (dict(mc_threads=0), "mc_threads"),
    (dict(lambda_damp=-1.0), "lambda_damp"),
    (dict(seed=-1), "seed"),
    (dict(start_eval=-5), "start_eval"),
    (dict(max_day=0), "max_day"),
    (dict(contact_offset=2), "contact_offset"),
    (dict(p2_true=(0.0,)), "p2_true"),
    (dict(p1_true=(1.5,)), "p1_true"),
])
def test_config_rejects_impossible_values(kw, match):
    with pytest.raises(ValueError, match=match):
        FINAL.with_(**kw)


def test_final_settings_reject_impossible_values():
    from epiinfer.final import FinalSettings, run_final
    with pytest.raises(ValueError, match="calib_window"):
        FinalSettings(calib_window=3)
    with pytest.raises(ValueError, match="recalib_every"):
        FinalSettings(recalib_every=0)
    with pytest.raises(ValueError, match="p2_true"):
        run_final(None, cases=("known_both",), p1_true=0.1, p2_true=0.0)


def test_one_number_is_accepted_for_a_known_rate(demo_path):
    """p1_true=0.15 raised "'float' object is not iterable" in every engine."""
    cfg = FINAL.with_(p1_true=0.15, p2_true=np.float32(0.5))
    assert cfg.p1_true == (0.15,) and cfg.p2_true == (0.5,)
    for engine in ("final", "compartmental"):
        fc = forecast(demo_path, horizon=2, method="known_both", engine=engine, p1_true=0.15,
                      p2_true=0.1, num_sims=2)
        assert (fc["p1_used"] == 0.15).all() and (fc["p2_used"] == 0.1).all()


# --- nothing could be scored -------------------------------------------------------------
@pytest.mark.parametrize("engine", ["final", "compartmental", "contact"])
def test_a_result_with_nothing_scored_still_has_columns(demo_path, engine):
    """The 2025 engine raised KeyError: 'group' from summary(); the others returned a table
    with no columns."""
    kw = dict(p1_true=(0.15,) * 3, p2_true=(0.1,) * 3) if engine == "contact" else KNOWN
    res = run(demo_path, "known_both", engine=engine, start_eval=40, horizons=(20,), num_sims=1,
              **kw)
    assert res.rows.empty and list(res.rows.columns) == ROW_COLUMNS
    s = res.summary()
    assert s.empty and list(s.columns) == SUMMARY_COLUMNS


def test_cli_run_says_when_nothing_could_be_scored(tmp_path, demo_path):
    with pytest.raises(SystemExit, match="no forecast could be scored"):
        main(["run", "--data", str(demo_path), "--method", "known_both", "--p1-true", "0.15",
              "--p2-true", "0.1", "--start-eval", "40", "--horizons", "20", "--num-sims", "1",
              "--out", str(tmp_path)])


def test_cli_reports_bad_input_in_one_line(tmp_path, demo_path):
    with pytest.raises(SystemExit, match="epiinfer: dataset folder not found"):
        main(["run", "--data", str(tmp_path / "nowhere")])
    with pytest.raises(SystemExit, match="epiinfer: case 'unknown_both'.*22"):
        main(["run", "--data", str(demo_path), "--start-eval", "15", "--num-sims", "1",
              "--out", str(tmp_path)])
    with pytest.raises(ValueError, match="22"):             # -v keeps the traceback
        main(["-v", "run", "--data", str(demo_path), "--start-eval", "15", "--num-sims", "1",
              "--out", str(tmp_path)])


# --- converting case lists ---------------------------------------------------------------
def test_cases_to_dataset_does_not_depend_on_row_order(tmp_path):
    """Two episodes of one person: with the later one listed first, the earlier episode's
    recovered days overwrote the later one's first symptomatic day."""
    contacts = pd.DataFrame({"date": ["2026-01-01"], "a": ["A"], "b": ["B"]})
    cases = pd.DataFrame({"person": ["A", "A"], "onset": ["2026-01-01", "2026-01-11"]})
    states = {}
    for name, rows in (("forward", cases), ("reversed", cases.iloc[::-1])):
        cases_to_dataset(rows, contacts, tmp_path / name)
        st = pd.read_csv(tmp_path / name / "individual_day_state.csv")
        states[name] = st[st["id"] == 0].sort_values("day")["state"].tolist()
    assert states["forward"] == states["reversed"] == [2] * 7 + [3] * 3 + [2]


def test_cases_to_dataset_rejects_missing_values_and_bad_durations(tmp_path):
    contacts = pd.DataFrame({"date": ["2026-01-01"], "a": ["A"], "b": ["B"]})
    with pytest.raises(ValueError, match="missing value"):
        cases_to_dataset(pd.DataFrame({"person": ["A"], "onset": [None]}), contacts, tmp_path / "x")
    with pytest.raises(ValueError, match="duration"):
        cases_to_dataset(pd.DataFrame({"person": ["A"], "onset": ["2026-01-01"]}), contacts,
                         tmp_path / "y", duration=0)


# --- simulator ---------------------------------------------------------------------------
def test_simulate_rejects_more_groups_than_the_contact_matrix(tmp_path):
    with pytest.raises(ValueError, match="contact matrix covers 3"):
        simulate(AgeMixConfig(group_sizes=(10, 10, 10, 10)))
    with pytest.raises(SystemExit, match="contact matrix covers 3"):
        main(["simulate", "--out", str(tmp_path / "g4"), "--sizes", "10", "10", "10", "10"])
    with pytest.raises(ValueError, match="one value per age group"):
        simulate(AgeMixConfig(group_sizes=(10, 10), p1=(0.1,)))


def test_simulate_supports_a_larger_custom_contact_matrix(tmp_path):
    cfg = AgeMixConfig(group_sizes=(20,) * 4, contact=((0.01,) * 4,) * 4, contact_scale=5.0,
                       days=5, p1=(0.2,) * 4, p2=(0.2,) * 4, seed=1)
    out = write_dataset(simulate(cfg), tmp_path / "four")
    pop = pd.read_csv(out / "age_group_population.csv")
    assert pop["age_group"].tolist() == ["group0", "group1", "group2", "group3"]
    assert load_dataset(out).n_groups == 4


# --- loaders -----------------------------------------------------------------------------
def test_age_group_file_ids_must_be_in_range(tmp_path, demo_path):
    """An id equal to the population raised a bare IndexError."""
    d = tmp_path / "ages"
    shutil.copytree(demo_path, d)
    m = pd.read_csv(d / "individual_age_group.csv")
    m.loc[0, "id"] = 600
    m.to_csv(d / "individual_age_group.csv", index=False)
    with pytest.raises(DataFormatError, match="individual_age_group.csv: ids must be 0..599"):
        load_dataset(d)


def test_a_dataset_may_have_no_contacts(tmp_path, demo_path):
    """A header-only timed_edges.csv raised "cannot convert float NaN to integer"."""
    d = tmp_path / "quiet"
    shutil.copytree(demo_path, d)
    pd.DataFrame(columns=["day", "i", "j"]).to_csv(d / "timed_edges.csv", index=False)
    for max_day in (None, 30):
        assert load_dataset(d, max_day=max_day).daily_contacts == {}


def test_an_empty_state_file_is_a_data_error(tmp_path, demo_path):
    d = tmp_path / "nostates"
    shutil.copytree(demo_path, d)
    pd.DataFrame(columns=["id", "day", "state"]).to_csv(d / "individual_day_state.csv", index=False)
    with pytest.raises(DataFormatError, match="no rows"):
        load_dataset(d)
    from epiinfer.final import FinalData
    with pytest.raises(DataFormatError, match="no rows"):
        FinalData.from_folder(d)


# --- CLI helpers -------------------------------------------------------------------------
def test_plot_rmse_names_the_missing_column(tmp_path):
    """`baseline` summaries have no frmse_rel; that was a bare KeyError."""
    pytest.importorskip("matplotlib")
    p = tmp_path / "b.csv"
    pd.DataFrame({"method": ["arima"], "horizon": [1], "n": [3], "rmse": [1.0],
                  "frmse": [0.1]}).to_csv(p, index=False)
    with pytest.raises(SystemExit, match="no column 'frmse_rel'"):
        main(["plot-rmse", str(p), "--metric", "frmse_rel", "--out", str(tmp_path / "p.png")])
    assert main(["plot-rmse", str(p), "--out", str(tmp_path / "p.png")]) == 0


def test_describe_a_folder_nobody_is_infected_in(tmp_path, capsys):
    d = tmp_path / "quiet"
    d.mkdir()
    pd.DataFrame({"id": [0, 1, 0, 1], "day": [0, 0, 1, 1], "state": [0, 0, 0, 0]}).to_csv(
        d / "individual_day_state.csv", index=False)
    assert main(["describe", "--data", str(d)]) == 0
    assert "peak symptomatic   0 on day 0" in capsys.readouterr().out


def test_config_default_still_validates_the_paper_presets():
    assert Config().num_sims == 10
    from epiinfer import COMPARTMENTAL, OPENABM, PAPER
    assert PAPER.p1_true == (0.25, 0.15, 0.08) and OPENABM.smoothing == 1.0
    assert COMPARTMENTAL.engine == "compartmental" and FINAL.engine == "final"
