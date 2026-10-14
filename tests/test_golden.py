"""The refactored package must reproduce the ORIGINAL research scripts exactly.

Fixtures come from ``tools/make_golden.py`` run against epiinfer_paper_aligned.py and
epiinfer_empirical_p1.py on the bundled demo data.
"""

import numpy as np
import pytest

from epiinfer import OPENABM, PAPER
from epiinfer.calibrate import continuous_calibrate, estimate_p1, solve_p1
from epiinfer.forecast import build_model


def _sets(d):
    return {str(k): sorted(int(x) for x in v) for k, v in sorted(d.items())}


def test_dataset_matches_original(data, golden):
    g = golden["dataset"]
    assert data.population_total == g["population_total"]
    assert len(data.all_days) == g["n_days"]
    assert _sets(data.new_asymp) == g["new_asymp"]
    assert _sets(data.new_inf) == g["new_inf"]
    assert {str(k): int(v) for k, v in sorted(data.gt_total.items())} == g["gt_total"]
    for grp, m in g["gt_group"].items():
        assert {str(d): v for d, v in sorted(data.gt_group[int(grp)].items())} == m


def test_strict_transitions_match_original(data, golden):
    assert _sets(data.new_asymp_strict) == golden["dataset_strict"]["new_asymp"]
    assert _sets(data.new_inf_strict) == golden["dataset_strict"]["new_inf"]


def test_project_matches_original_stream(data, golden):
    """Same RNG stream => identical trajectory (RandomState(seed) == np.random.seed(seed))."""
    g = golden["project_paper"]
    model = build_model(data, PAPER)
    day = g["day"]
    h_a = {k: data.new_asymp[k] for k in range(day - 8, day + 1) if k in data.new_asymp}
    h_i = {k: data.new_inf[k] for k in range(day - 8, day + 1) if k in data.new_inf}
    out = model.project(np.array([0.25, 0.15, 0.08]), np.array([0.15, 0.10, 0.05]), h_a, h_i,
                        day, day + 12, data.recovered_on.get(day, set()),
                        np.random.RandomState(g["seed"]))
    assert {str(d): v.tolist() for d, v in sorted(out.items())} == g["counts"]


@pytest.mark.parametrize("method", ["unknown_both", "known_p2", "known_p1", "known_both"])
def test_calibration_matches_original(data, golden, method):
    model = build_model(data, PAPER)
    g = golden["calibrate"][method]

    def observed(day):
        return {k: {d: data.gt_group[k].get(d, 0)
                    for d in range(max(0, day - PAPER.calib_window), day + 1)}
                for k in range(model.n_groups)}

    p1, p2 = continuous_calibrate(model, method, observed(30), 30, data.new_asymp, data.new_inf,
                                  data.recovered_on, PAPER, None, None)
    assert [p1.tolist(), p2.tolist()] == g["day30"]
    q1, q2 = continuous_calibrate(model, method, observed(31), 31, data.new_asymp, data.new_inf,
                                  data.recovered_on, PAPER, p1, p2)
    assert [q1.tolist(), q2.tolist()] == g["day31"]


def test_empirical_p1_matches_original(data, golden):
    model = build_model(data, OPENABM)
    g = golden["estimate_p1"]
    a = estimate_p1(model, data, 30, OPENABM, None)
    assert a.tolist() == g["day30"]
    assert estimate_p1(model, data, 31, OPENABM, a).tolist() == g["day31"]
    half = OPENABM.with_(smoothing=0.5)
    assert estimate_p1(model, data, 31, half, a).tolist() == g["day31_smooth_half"]


def test_solve_p1_matches_original(golden):
    for case in golden["solve_p1"]["cases"]:
        kh = {int(k): v for k, v in case["k_hist"].items()}
        assert solve_p1(kh, case["observed"]) == case["p1"]


def test_empirical_projection_matches_original(data, golden):
    g = golden["project_empirical"]
    model = build_model(data, OPENABM)
    day = g["day"]
    p1 = np.array(golden["estimate_p1"]["day30"])
    lb = OPENABM.inc + OPENABM.duration + 1
    na, ni = data.transitions("strict")
    h_a = {k: na[k] for k in range(day - lb, day + 1) if k in na}
    h_i = {k: ni[k] for k in range(day - lb, day + 1) if k in ni}
    out = model.project(p1, np.ones(3), h_a, h_i, day, day + 12, data.recovered_on.get(day, set()),
                        np.random.RandomState(g["seed"]))
    assert {str(d): v.tolist() for d, v in sorted(out.items())} == g["counts"]
