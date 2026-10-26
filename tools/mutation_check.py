"""Tiny mutation test: break key guards in a COPY of the package and require the suite to fail.

    uv run --all-extras python tools/mutation_check.py
A mutation that the tests do not catch means a test is a no-op.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("core.py", "probs = 1.0 - (1.0 - p1) ** counts", "probs = p1 * counts"),
    ("core.py", "rng.random_sample(cand.size) < p2", "rng.random_sample(cand.size) < 1.0"),
    ("calibrate.py", "np.random.RandomState(int(start) % (2 ** 32))", "np.random.RandomState(1)"),
    ("calibrate.py", "if r < best_rmse:", "if r <= best_rmse:"),
    ("calibrate.py", "float(np.clip(prev_val + (target - prev_val) * cfg.smoothing, 0.01, 0.99))",
     "float(target)"),
    ("calibrate.py", "if observed >= total:\n        return 1.0",
     "if observed >= total:\n        return 0.5"),
    ("forecast.py", "[int(seed), int(day), int(sim)]", "[int(seed), 0, int(sim)]"),
    ("forecast.py", '"strict" if method == EMPIRICAL_METHOD else "diff")\n    n = model.n_groups',
     '"diff")\n    n = model.n_groups'),
    ("data.py", "asymp_on[day] & susceptible_on.get(day - 1, set())",
     "asymp_on[day] - asymp_on.get(day - 1, set())"),
    ("data.py", "if lo < 0 or hi >= pop_total:", "if False:"),
    ("data.py", "if s_code != 0:", "if False:"),
    ("metrics.py", "return math.sqrt(np.mean((pred - actual) ** 2)) / denom",
     "return math.sqrt(np.mean((pred - actual) ** 2)) / actual.max()"),
    ("simulate/abm.py", "not_inf[core_i] & not_inf[core_j]", "np.ones(core_i.size, bool)"),
    # added in the full review
    ("forecast.py", 'return origin if cfg.contacts == "frozen" else None', "return None"),
    ("forecast.py", "sim_rng(cfg.seed, day, i), graph_until=day)", "sim_rng(cfg.seed, day, i))"),
    ("forecast.py", "if tgt not in avg or tgt > last_day:", "if tgt not in avg:"),
    ("forecast.py", "return max(8, model.inc + 1, model.duration + 1)", "return 8"),
    ("data.py", "codes[key] = 0", "pass"),
    ("data.py", "gt_group[g].setdefault(day, 0)", "pass"),
    ("data.py", 'next((c for c in ("c", "avg_contacts")', 'next((c for c in ("c",)'),
    ("fetch.py", ".is_relative_to(root)", ".as_posix().startswith(str(root))"),
    ("core.py", "int(n_groups) if n_groups is not None else", "int(self.age_of.max()) + 1 if True else"),
    ("baselines.py", "if day + h <= min(max_day, len(y) - 1):", "if day + h < len(y):"),
    # added with the uv migration
    ("fetch.py", "expected_sha256 = expected_sha256 or known_checksums().get(archive.name)",
     "expected_sha256 = expected_sha256"),
    ("baselines.py", "lo = 0 if window is None else max(0, day - window)", "lo = 0"),
    ("baselines.py", "return np.maximum(0.0, np.asarray(fit.forecast(steps)))",
     "return np.asarray(fit.forecast(steps))"),
    ("reproduce/run.py", 'if got == want:\n        return "ok"', 'if True:\n        return "ok"'),
    ("cli.py", 'if "install the extra" in str(exc):', "if False:"),
    # added with the appendix / max_day work
    ("data.py", 'parts = [c[c["day"] <= max_day] for c in', 'parts = [c for c in'),
    ("data.py", 'states_total = states_total[states_total["day"] <= max_day]', 'states_total = states_total'),
    ("data.py", 'curve = {k: v for k, v in curve.items() if k <= max_day}', 'curve = curve'),
    ("forecast.py", "data = load_dataset(data, max_day=cfg.max_day)", "data = load_dataset(data)"),
    ("reproduce/appendix.py", "cfg = cfg.with_(p1_true=(p1,) * g, p2_true=(p2,) * g)",
     "cfg = cfg.with_(p1_true=(p1, p1, p1), p2_true=(p2, p2, p2))"),
    ("reproduce/appendix.py", "return sorted(out, key=lambda t: (t[0], t[1]))", "return out[::-1]"),
    ("reproduce/appendix.py", 'start_eval=10, last_origin=50)', 'start_eval=25, last_origin=99)'),
    ("reproduce/run.py", "end = last + max(horizons)                       # last day a target may be",
     "end = 100"),
    # added with the final (October 2026) engine
    ("final.py", "rec_f = (p >= inf_start + fd) & (p < inf_start + fd + rd)",
     "rec_f = (p >= inf_start + fd)"),
    ("final.py", "cnt = d.exposed_neighbours(o, exposed_prev.astype(float))   # contacts of day o",
     "cnt = d.exposed_neighbours(t, exposed_prev.astype(float))"),
    ("final.py",
     "cnt = d.exposed_neighbours(t, exposed_prev.astype(float))\n            susc = ~(d.is_inf[t]",
     "cnt = d.exposed_neighbours(t - 1, exposed_prev.astype(float))\n            susc = ~(d.is_inf[t]"),
    ("final.py", "s = self.score(a, b, train_day)", "s = self.score(a, a, train_day)"),
    ("final.py", "% settings.recalib_every == 0", "% 1 == 0"),
    ("final.py", "blend = min(1.0, max(0.0, r_prev - r_star) / r_prev * self.s.lam)", "blend = 1.0"),
    ("final.py", "target = int(round(len(cohort) / p2))", "target = len(cohort)"),
    ("final.py", "rel = (s.predicted - s.actual) / s.actual",
     "rel = (s.predicted - s.actual) / s.actual.mean()"),
    ("final.py", "self.is_inf = S == state_i", "self.is_inf = (S == state_i) | (S == 1)"),
    ("metrics.py", "keep = actual > 0", "keep = actual == actual"),
    ("forecast.py", 'engine = engine or "final"', 'engine = engine or "contact"'),
    # added with the compartmental engine (the earlier EpiInfer)
    ("compartmental.py", "meet = np.mean(meet_all[lo:t], axis=0) if t > lo else meet_all[t]",
     "meet = meet_all[t]"),
    ("compartmental.py", "returning = R[t - 1] * eta", "returning = 0"),
    ("compartmental.py", "exposed_before = np.divide(inf_g, p2, out=np.zeros(G), where=p2 > 0)",
     "exposed_before = inf_g"),
    ("compartmental.py", "obs = c.I[origin - w:origin, 0]", "obs = c.I[origin - w + 1:origin + 1, 0]"),
    ("compartmental.py", "freeze_after=o - 1 if freeze else None", "freeze_after=None"),
    ("compartmental.py", "p_exp = np.divide(inf_g, p2 * free, out=np.zeros(G), where=(free > 0) & (p2 > 0))",
     "p_exp = np.sum(inf_g) / (np.mean(p2) * np.sum(free))"),
    ("forecast.py", "cfg.start_eval + 1, last + 1, cfg.group_contacts",
     "cfg.start_eval, last, cfg.group_contacts"),
]


def main() -> int:
    survivors = []
    for rel, old, new in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "pkg"
            shutil.copytree(ROOT / "src" / "epiinfer", work / "epiinfer")
            target = work / "epiinfer" / rel
            text = target.read_text()
            if old not in text:
                print(f"STALE   {rel}: pattern not found: {old[:50]!r}")
                survivors.append((rel, old))
                continue
            target.write_text(text.replace(old, new, 1))
            env = {"PYTHONPATH": str(work), "PATH": "/usr/bin:/bin"}
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                                str(ROOT / "tests")], env=env, capture_output=True, text=True)
            status = "caught " if r.returncode != 0 else "SURVIVED"
            print(f"{status} {rel}: {old[:60]!r}")
            if r.returncode == 0:
                survivors.append((rel, old))
    print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} mutations caught")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
