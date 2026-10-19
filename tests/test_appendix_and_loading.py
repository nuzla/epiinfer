"""max_day loading, contact-free baselines, and the Appendix A reproduction."""

import shutil

import numpy as np
import pandas as pd
import pytest

from epiinfer import load_dataset, run
from epiinfer.cli import main
from epiinfer.data import load_curve
from epiinfer.reproduce.appendix import SCALES, load_targets, reproduce_appendix, scenarios
from epiinfer.simulate import AgeMixConfig, simulate, write_dataset


# ---- max_day --------------------------------------------------------------------------
def test_max_day_drops_later_rows_everywhere(demo_path):
    d = load_dataset(demo_path, max_day=30)
    assert max(d.all_days) == 30 and max(d.daily_contacts) == 30
    assert max(d.gt_total) == 30 and all(max(m) <= 30 for m in d.gt_group.values())
    assert d.states_total["day"].max() == 30
    full = load_dataset(demo_path)
    assert d.population_total == full.population_total
    assert d.new_asymp[30] == full.new_asymp[30]            # earlier days are untouched


def test_run_loads_only_what_it_uses(demo_path, monkeypatch):
    """run() must pass cfg.max_day to the loader, and the forecasts must be identical to
    loading everything: nothing after max_day is ever read by the model."""
    import sys

    F = sys.modules["epiinfer.forecast"]       # `epiinfer.forecast` the attribute is the function
    seen = []
    orig = F.load_dataset
    monkeypatch.setattr(F, "load_dataset", lambda p, **kw: seen.append(kw) or orig(p, **kw))
    kw = dict(start_eval=28, num_sims=3, horizons=(1, 5), seed=2, max_day=38)
    a = run(demo_path, "empirical_p1", **kw)
    assert seen == [{"max_day": 38}]
    b = run(load_dataset(demo_path), "empirical_p1", **kw)
    pd.testing.assert_frame_equal(a.rows, b.rows)


# ---- load_curve / contact-free baselines ----------------------------------------------
def test_load_curve_from_states_total_and_from_states(tmp_path, demo_path):
    ref = load_dataset(demo_path).gt_total
    d = tmp_path / "curve"
    d.mkdir()
    shutil.copy(demo_path / "states_total.csv", d / "states_total.csv")
    assert load_curve(d) == {int(k): float(v) for k, v in ref.items()}
    assert max(load_curve(d, max_day=20)) == 20
    only_states = tmp_path / "states"
    only_states.mkdir()
    shutil.copy(demo_path / "individual_day_state.csv", only_states / "individual_day_state.csv")
    assert load_curve(only_states) == load_curve(d)


def test_baseline_runs_without_any_contact_file(tmp_path, demo_path):
    """The paper's uniform-contact data has states_total.csv but no timed_edges.csv."""
    pytest.importorskip("statsmodels")
    from epiinfer.baselines import rolling_baseline
    d = tmp_path / "curve_only"
    d.mkdir()
    shutil.copy(demo_path / "states_total.csv", d / "states_total.csv")
    a = rolling_baseline(d, "arima", (1, 5), start_eval=10, last_origin=30)
    b = rolling_baseline(load_dataset(demo_path), "arima", (1, 5), start_eval=10, last_origin=30)
    pd.testing.assert_frame_equal(a, b)


# ---- Appendix A targets and runner ----------------------------------------------------
def test_appendix_targets_are_complete():
    t = load_targets()
    assert len(t) == 12 * 4 * 3 * 20                      # pairs x scales x methods x days
    assert set(t["scale"]) == {"Base", "0.2", "0.5", "2"} and set(t["method"]) == {
        "arima", "contact", "epiinfer_old"}
    assert t["day"].min() == 1 and t["day"].max() == 20 and t["rmse"].gt(0).all()
    row = t[(t.p1 == 0.12) & (t.p2 == 0.05) & (t.scale == "0.2") & (t.day == 1)].set_index("method")
    assert row.loc["arima", "rmse"] == 15.103 and row.loc["contact", "rmse"] == 5.845
    assert SCALES == ("0.2", "0.5", "2")


def test_scenarios_parse_and_sort(tmp_path):
    for name in ("p1_0.25_p2_0.1", "p1_0.12_p2_0.05", "p1_0.2_p2_0.2", "p1_0.12_p2_0.1", "notes"):
        (tmp_path / name).mkdir()
    (tmp_path / "p1_0.9_p2_0.9").write_text("a file, not a folder")
    assert [(p1, p2) for p1, p2, _ in scenarios(tmp_path)] == [
        (0.12, 0.05), (0.12, 0.1), (0.2, 0.2), (0.25, 0.1)]


@pytest.fixture()
def mini_appendix(tmp_path):
    """One tiny scenario folder named like the paper's, simulated from the library's ABM."""
    root = tmp_path / "abmcontact_mini"
    sim = simulate(AgeMixConfig(group_sizes=(80, 160, 60), contact_scale=2.0, days=70, seed=3,
                                p1=(0.12,) * 3, p2=(0.05,) * 3, init_a=6))
    write_dataset(sim, root / "p1_0.12_p2_0.05")
    return root


def test_reproduce_appendix_runs_and_compares(mini_appendix):
    pytest.importorskip("statsmodels")
    df = reproduce_appendix(mini_appendix, "0.2", quick=True, num_sims=2)
    assert set(df["method"]) == {"arima", "contact"} and set(df["day"]) == set(range(1, 21))
    assert df["paper_rmse"].notna().all() and np.isfinite(df["ratio"]).all()
    assert (df["p1"] == 0.12).all() and (df["p2"] == 0.05).all()
    only = reproduce_appendix(mini_appendix, "0.2", methods=("arima",))
    assert set(only["method"]) == {"arima"}


def test_reproduce_appendix_uses_one_rate_pair_for_every_group(mini_appendix, monkeypatch):
    """Appendix datasets have ONE (p1, p2) and many age groups; known_both must be given it for
    every group (the paper-default 3-element tuple would crash or mis-size)."""
    import epiinfer.reproduce.appendix as A
    seen = {}
    orig = A.rolling_forecast

    def spy(model, data, method, cfg, quiet=False):
        seen.update(p1=cfg.p1_true, p2=cfg.p2_true, groups=data.n_groups, method=method)
        return orig(model, data, method, cfg, quiet=quiet)

    monkeypatch.setattr(A, "rolling_forecast", spy)
    reproduce_appendix(mini_appendix, "0.2", methods=("contact",), quick=True, num_sims=1)
    assert seen == {"p1": (0.12,) * 3, "p2": (0.05,) * 3, "groups": 3, "method": "known_both"}


def test_reproduce_appendix_input_errors(tmp_path, mini_appendix):
    with pytest.raises(ValueError, match="scale"):
        reproduce_appendix(mini_appendix, "1")
    with pytest.raises(ValueError, match="unknown method"):
        reproduce_appendix(mini_appendix, "0.2", methods=("lstm",))
    with pytest.raises(FileNotFoundError):
        reproduce_appendix(tmp_path, "0.2")


def test_cli_reproduce_appendix(tmp_path, mini_appendix, capsys):
    pytest.importorskip("statsmodels")
    rc = main(["reproduce", "--table", "appendix", "--scale", "0.2", "--data", str(mini_appendix),
               "--methods", "arima", "--out", str(tmp_path / "o")])
    assert rc == 0
    assert (tmp_path / "o" / "reproduce_appendix_scale0.2.csv").exists()
    assert "arima" in capsys.readouterr().out


@pytest.fixture()
def five_group_appendix(tmp_path, demo_path):
    """The paper's appendix data have 13 age groups; build a folder with 5 (ids spread over the
    groups, so the mapping comes from individual_age_group.csv) to prove nothing assumes 3."""
    root = tmp_path / "five"
    sub = root / "p1_0.12_p2_0.05"
    shutil.copytree(demo_path, sub)
    ages = pd.read_csv(sub / "individual_age_group.csv")
    ages["age_group"] = ages["id"] % 5
    ages.to_csv(sub / "individual_age_group.csv", index=False)
    pd.DataFrame({"age_group": list("abcde"), "population": [120] * 5}).to_csv(
        sub / "age_group_population.csv", index=False)
    (sub / "daily_group_infected.csv").unlink()              # derive the per-group truth instead
    (sub / "daily_group_avg_contacts.csv").unlink()
    return root


def test_appendix_contact_handles_a_different_number_of_age_groups(five_group_appendix):
    df = reproduce_appendix(five_group_appendix, "0.2", methods=("contact",), quick=True, num_sims=2)
    assert len(df) >= 10 and np.isfinite(df["rmse"]).all()     # demo data end limits the horizons


def test_appendix_arima_uses_the_authors_origin_window(mini_appendix):
    """ARIMA is scored on forecast origins 10-50 (the authors' notebook), not EpiInfer's 25-99."""
    pytest.importorskip("statsmodels")
    from epiinfer.baselines import rolling_baseline
    df = reproduce_appendix(mini_appendix, "0.2", methods=("arima",))
    direct = rolling_baseline(mini_appendix / "p1_0.12_p2_0.05", "arima", tuple(range(1, 21)),
                              start_eval=10, last_origin=50)
    assert np.allclose(df.sort_values("day")["rmse"].to_numpy(), direct["rmse"].to_numpy())


def test_holt_winters_table_scores_targets_beyond_day_100(tmp_path):
    """The notebook scores origins 25-99 against targets up to day 119 on its 365-day curve;
    reproduce must load that far (it used to stop at the origin limit)."""
    pytest.importorskip("statsmodels")
    from epiinfer.baselines import rolling_baseline
    from epiinfer.reproduce import reproduce_table
    rng = np.random.default_rng(0)
    days = np.arange(0, 140)
    curve = 500 * np.exp(-((days - 40) / 25.0) ** 2) + rng.normal(0, 5, days.size)
    d = tmp_path / "long"
    d.mkdir()
    pd.DataFrame({"day": days, "S": 0, "A": 0, "I": curve.round().astype(int), "R": 0}).to_csv(
        d / "states_total.csv", index=False)
    pd.DataFrame({"age_group": ["all"], "population": [10000]}).to_csv(
        d / "age_group_population.csv", index=False)
    df = reproduce_table("hw_uniform", d)
    full = {int(k): float(v) for k, v in zip(days, curve.round(), strict=True)}
    want = rolling_baseline(full, "holt_winters", (1, 5, 10, 20), start_eval=25, last_origin=99,
                            max_day=119)
    assert np.allclose(df["rmse"].to_numpy(), want["rmse"].to_numpy())
    assert df["n_origins"].tolist() == [75, 75, 75, 75]       # every origin reaches every horizon
