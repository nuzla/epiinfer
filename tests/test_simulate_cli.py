import numpy as np
import pytest

from epiinfer import load_dataset
from epiinfer.cli import main
from epiinfer.simulate import AgeMixConfig, simulate, write_dataset


def small(**kw):
    return AgeMixConfig(group_sizes=(60, 120, 40), contact_scale=2.0, days=25, seed=5,
                        init_a=5, **kw)


def test_simulation_deterministic_and_conserves_population():
    a, b = simulate(small()), simulate(small())
    assert (a["hist"] == b["hist"]).all() and (a["edges"] == b["edges"]).all()
    assert (a["hist"].sum(axis=1) == 220).all()
    other = simulate(AgeMixConfig(**{**small().__dict__, "seed": 6}))
    assert not (a["hist"] == other["hist"]).all()


def test_infected_people_are_isolated():
    sim = simulate(small())
    st, e = sim["states"], sim["edges"]
    for day in range(1, 25):
        inf_yesterday = st[day - 1] == 2           # isolation is decided on start-of-day state
        d = e[e[:, 0] == day]
        assert not inf_yesterday[d[:, 1]].any() and not inf_yesterday[d[:, 2]].any()


def test_written_dataset_loads_and_matches_hist(tmp_path):
    sim = simulate(small())
    write_dataset(sim, tmp_path)
    d = load_dataset(tmp_path)
    assert d.population_total == 220
    for day in (0, 10, 24):
        assert len(d.asymp_on[day]) == sim["hist"][day, 1]
        assert d.gt_total[day] == sim["hist"][day, 2]
    assert sum(d.gt_group[g][24] for g in range(3)) == sim["hist"][24, 2]


def test_invalid_contact_scale():
    with pytest.raises(ValueError, match="no first-day contacts"):
        simulate(AgeMixConfig(group_sizes=(5, 5, 5), contact_scale=0.0, days=2))


def test_cli_demo_and_forecast(capsys, demo_path):
    assert main(["demo"]) == 0
    assert str(demo_path) in capsys.readouterr().out
    assert main(["forecast", "--data", str(demo_path), "--horizon", "2", "--num-sims", "3"]) == 0
    out = capsys.readouterr().out.splitlines()                 # final engine: the total only
    assert out[0].startswith("group,origin_day") and len(out) == 1 + 2
    assert main(["forecast", "--data", str(demo_path), "--horizon", "2", "--num-sims", "3",
                 "--engine", "contact"]) == 0
    out = capsys.readouterr().out.splitlines()                 # contact engine: 3 groups + ALL
    assert len(out) == 1 + 2 * 4


def test_cli_run_writes_outputs(tmp_path, demo_path):
    rc = main(["run", "--data", str(demo_path), "--method", "empirical_p1", "--start-eval", "30",
               "--max-day", "34", "--num-sims", "2", "--out", str(tmp_path)])
    assert rc == 0
    names = {p.name for p in tmp_path.iterdir()}
    assert any(n.startswith("summary_") for n in names) and any(n.startswith("rates_") for n in names)


def test_cli_reproduce_quick(tmp_path, demo_path, capsys):
    rc = main(["reproduce", "--table", "openabm", "--data", str(demo_path), "--quick",
               "--out", str(tmp_path)])
    assert rc == 0
    assert "not comparable" in capsys.readouterr().out
    assert (tmp_path / "reproduce_openabm_quick.csv").exists()


def test_cli_simulate(tmp_path):
    rc = main(["simulate", "--out", str(tmp_path / "s"), "--days", "3", "--scale", "0.2"])
    assert rc == 0 and (tmp_path / "s" / "timed_edges.csv").exists()


def test_fetch_rejects_plain_http_and_no_url(monkeypatch):
    from epiinfer.fetch import fetch
    monkeypatch.delenv("EPIINFER_DATA_URL", raising=False)
    with pytest.raises(SystemExit, match="no data URL"):
        fetch(None, "x")
    with pytest.raises(SystemExit, match="non-HTTPS"):
        fetch("http://example.com/a.zip", "x")


def test_baselines_arima_runs(demo_path):
    pytest.importorskip("statsmodels")
    from epiinfer.baselines import rolling_baseline
    df = rolling_baseline(load_dataset(demo_path), "arima", horizons=(1, 5), start_eval=25, max_day=44)
    assert set(df["horizon"]) == {1, 5} and np.isfinite(df["rmse"]).all()
