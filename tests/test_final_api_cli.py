"""The final engine through the public API and the CLI, plus the tutorial's plotting commands."""

import numpy as np
import pandas as pd
import pytest

from epiinfer import FINAL, PAPER, forecast, load_dataset, run
from epiinfer.cli import main
from epiinfer.final import FinalData
from epiinfer.simulate import AgeMixConfig, simulate, write_dataset


def test_final_is_the_default_engine(demo_path):
    res = run(demo_path, "unknown_both", start_eval=25, max_day=46, horizons=(1, 5), num_sims=2)
    assert res.config.engine == "final" and set(res.rows["group"]) == {"ALL"}
    s = res.summary()
    assert {"rmse", "frmse", "frmse_rel"} <= set(s.columns) and (s["n"] > 0).all()
    assert set(res.rates.columns) == {"day", "p1", "p2"}


def test_contact_engine_still_available(demo_path):
    res = run(demo_path, "known_both", engine="contact", start_eval=30, max_day=34, num_sims=1,
              horizons=(1,))
    assert res.config.engine == "contact" and "0-19" in set(res.rows["group"])
    with pytest.raises(ValueError, match="only in the contact engine"):
        run(demo_path, "empirical_p1", engine="final")


def test_final_engine_needs_one_rate_pair(demo_path):
    with pytest.raises(ValueError, match="one p1 for the whole population"):
        run(demo_path, "known_both", cfg=FINAL.with_(p1_true=PAPER.p1_true, p2_true=PAPER.p2_true))
    with pytest.raises(ValueError, match="needs the true rate"):
        run(demo_path, "known_both")
    res = run(demo_path, "known_both", p1_true=(0.15,), p2_true=(0.1,), max_day=46,
              horizons=(1,), num_sims=1)
    assert (res.rows["p1_used"] == 0.15).all() and (res.rows["p2_used"] == 0.1).all()


def test_final_data_from_dataset_equals_from_folder(demo_path):
    a = FinalData.from_folder(demo_path)
    b = FinalData.from_dataset(load_dataset(demo_path))
    assert (a.is_inf == b.is_inf).all() and (a.is_rec == b.is_rec).all() and a.gt == b.gt
    assert all(np.array_equal(np.sort(a.edges[d][0]), np.sort(b.edges[d][0])) for d in a.edges)


def test_final_forecast_shape_band_and_validation(demo_path):
    df = forecast(demo_path, horizon=5, from_day=30, num_sims=4)
    assert list(df["horizon"]) == [1, 2, 3, 4, 5] and (df["group"] == "ALL").all()
    assert (df["p10"] <= df["mean"] + 1e-9).all() and (df["mean"] <= df["p90"] + 1e-9).all()
    assert df["actual"].notna().all()                       # day 31-35 are observed
    fut = forecast(demo_path, horizon=3, num_sims=2)        # from the last day: the future
    assert fut["actual"].isna().all()
    with pytest.raises(ValueError, match="from_day"):
        forecast(demo_path, horizon=3, from_day=10)          # too early to calibrate


def test_final_seed_changes_trajectories_but_zero_is_the_notebook(demo_path):
    a = forecast(demo_path, horizon=10, from_day=30, num_sims=3, seed=0)
    b = forecast(demo_path, horizon=10, from_day=30, num_sims=3, seed=0)
    c = forecast(demo_path, horizon=10, from_day=30, num_sims=3, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert not a["mean"].equals(c["mean"])


def test_cli_describe_forecast_plot_and_plot_rmse(tmp_path, demo_path, capsys):
    pytest.importorskip("matplotlib")
    assert main(["describe", "--data", str(demo_path), "--plot", str(tmp_path / "c.png")]) == 0
    out = capsys.readouterr().out
    assert "peak symptomatic" in out and "final, contact" in out and (tmp_path / "c.png").exists()
    assert main(["forecast", "--data", str(demo_path), "--from-day", "30", "--horizon", "4",
                 "--num-sims", "3", "--out", str(tmp_path / "f.csv"),
                 "--plot", str(tmp_path / "f.png")]) == 0
    assert (tmp_path / "f.png").exists() and len(pd.read_csv(tmp_path / "f.csv")) == 4
    assert main(["run", "--data", str(demo_path), "--start-eval", "25", "--max-day", "46",
                 "--horizons", "1", "5", "--num-sims", "2", "--out", str(tmp_path / "r"),
                 "--plots"]) == 0
    summ = tmp_path / "r" / "summary_demo_data_unknown_both.csv"
    assert summ.exists() and (tmp_path / "r" / "rmse_demo_data_unknown_both.png").exists()
    assert main(["plot-rmse", f"final={summ}", "--out", str(tmp_path / "cmp.png"), "--log-y"]) == 0
    assert (tmp_path / "cmp.png").exists()


def test_cli_describe_without_contacts_or_a(tmp_path, demo_path, capsys):
    d = tmp_path / "curve_only"
    d.mkdir()
    pd.read_csv(demo_path / "states_total.csv").to_csv(d / "states_total.csv", index=False)
    assert main(["describe", "--data", str(d)]) == 0
    out = capsys.readouterr().out
    assert "baselines only" in out


def test_cli_baseline_writes_csv(tmp_path, demo_path):
    pytest.importorskip("statsmodels")
    assert main(["baseline", "--data", str(demo_path), "--start-eval", "30",
                 "--out", str(tmp_path / "b.csv")]) == 0
    assert set(pd.read_csv(tmp_path / "b.csv").columns) >= {"horizon", "rmse"}


@pytest.fixture()
def mini_sweep(tmp_path):
    root = tmp_path / "base"
    sim = simulate(AgeMixConfig(group_sizes=(80, 160, 60), contact_scale=2.0, days=60, seed=4,
                                p1=(0.12,) * 3, p2=(0.05,) * 3, init_a=6))
    write_dataset(sim, root / "p1_0.12_p2_0.05")
    return root


def test_reproduce_sweep_quick(mini_sweep, tmp_path, capsys):
    from epiinfer.reproduce.sweep import reproduce_sweep
    cmp, pred, trace = reproduce_sweep(mini_sweep, cases=("known_both", "known_p2"), quick=True)
    assert set(cmp["case"]) == {"known_both", "known_p2"} and cmp["paper_RMSE"].notna().all()
    assert cmp["dataset_check"].str.startswith("MISMATCH").all()   # not the paper's Base data
    assert set(trace["case"]) == {"known_p2"}
    assert main(["reproduce", "--table", "sweep", "--data", str(mini_sweep), "--quick",
                 "--methods", "known_both", "--out", str(tmp_path / "o")]) == 0
    assert "WARNING: MISMATCH" in capsys.readouterr().out


def test_compare_tutorial_fails_on_missing_or_changed_outputs(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "compare_tutorial", Path(__file__).parents[1] / "tools" / "compare_tutorial.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    exp, got = tmp_path / "expected", tmp_path / "got"
    exp.mkdir()
    got.mkdir()
    assert mod.compare(got, exp)                       # nothing to compare is a failure
    pd.DataFrame({"horizon": [1, 5], "rmse": [1.0, 2.0]}).to_csv(exp / "a.csv", index=False)
    pd.DataFrame({"horizon": [1, 5], "rmse": [1.0, 2.0]}).to_csv(got / "a.csv", index=False)
    assert mod.compare(got, exp) == []
    pd.DataFrame({"horizon": [1, 5], "rmse": [1.0, 2.1]}).to_csv(got / "a.csv", index=False)
    assert any("rmse" in p for p in mod.compare(got, exp))
