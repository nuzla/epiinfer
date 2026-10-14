"""AgeMixABM: a seeded, vectorised port of the paper's age-stratified ABM notebook.

Model (per day): contacts are drawn from a persistent "core" network (a fraction
``core_frac`` of the first-day edges, kept every day) plus non-core edges redrawn each
day with probability ``C[gi, gj] * (1 - core_frac)``. Anyone in state I is isolated (no
contacts). A susceptible with k infectious (A) contacts becomes A with probability
``1 - (1 - p1_g)^k``; after ``inc`` days an A becomes I with probability ``p2_g`` (else
returns to S); I recovers after ``inf_dur`` days and R returns to S after ``rec_dur``.

Reproducibility note: this is the *same model* as the notebook but not the same random
stream, so a regenerated dataset is statistically equivalent to, not byte-identical with,
the datasets shipped with the paper. Use ``epiinfer fetch-data`` for the exact files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

S, A, I, R = 0, 1, 2, 3  # noqa: E741
AGE_LABELS = ["0-19", "20-60", "61+"]

CONTACT_MATRICES = {
    "uniform": np.full((3, 3), 0.005),
    "age_structured": np.array([[0.016054, 0.004905, 0.001925],
                                [0.004905, 0.006951, 0.003707],
                                [0.001925, 0.003707, 0.004517]]),
}

#: Group sizes the paper's notebook derives from the real population at N = 10,000.
PAPER_GROUP_SIZES = (2455, 5422, 2123)


@dataclass(frozen=True)
class AgeMixConfig:
    group_sizes: tuple[int, ...] = PAPER_GROUP_SIZES
    contact: str | tuple = "age_structured"      # a key of CONTACT_MATRICES, or a 3x3 nested tuple
    contact_scale: float = 0.2   # matrix multiplier; 0.2 matches the shipped data's edges/day
    p1: tuple[float, ...] = (0.25, 0.15, 0.08)   # per-contact transmission prob by group
    p2: tuple[float, ...] = (0.15, 0.10, 0.05)   # A -> I progression prob by group
    days: int = 100
    inc: int = 7
    inf_dur: int = 7
    rec_dur: int = 7
    core_frac: float = 0.7
    init_a: int = 8
    seed: int = 123
    extra: dict = field(default_factory=dict, compare=False)

    def matrix(self) -> np.ndarray:
        m = CONTACT_MATRICES[self.contact] if isinstance(self.contact, str) \
            else np.asarray(self.contact, float)
        return m * self.contact_scale


def _first_day_edges(group_ids, C, rng):
    """Undirected first-day network: pair (i<j) present with probability C[gi, gj]."""
    n = len(group_ids)
    ei, ej = [], []
    for i in range(n - 1):
        hit = np.nonzero(rng.random(n - i - 1) < C[group_ids[i], group_ids[i + 1:]])[0]
        if hit.size:
            ei.append(np.full(hit.size, i, dtype=np.int64))
            ej.append(hit + i + 1)
    if not ei:
        raise ValueError("no first-day contacts were generated; raise contact_scale")
    return np.concatenate(ei), np.concatenate(ej)


def simulate(cfg: AgeMixConfig | None = None) -> dict:
    """Run the ABM; returns hist (days+1 x 4 S/A/I/R), edges (day,i,j), group_ids, states."""
    cfg = cfg or AgeMixConfig()
    rng = np.random.default_rng(cfg.seed)
    C = cfg.matrix()
    sizes = np.asarray(cfg.group_sizes, int)
    p1 = np.asarray(cfg.p1, float)
    p2 = np.asarray(cfg.p2, float)
    group_ids = np.repeat(np.arange(len(sizes)), sizes)
    n = group_ids.size

    ei, ej = _first_day_edges(group_ids, C, rng)
    order = rng.permutation(ei.size)
    n_core = int(ei.size * cfg.core_frac)
    core_i, core_j = ei[order[:n_core]], ej[order[:n_core]]
    nc_i, nc_j = ei[order[n_core:]], ej[order[n_core:]]
    nc_prob = C[group_ids[nc_i], group_ids[nc_j]] * (1 - cfg.core_frac)

    states = np.full(n, S, dtype=np.int8)
    age = np.zeros(n, dtype=np.int32)
    states[rng.choice(n, size=cfg.init_a, replace=False)] = A

    hist = np.zeros((cfg.days + 1, 4), dtype=np.int64)
    hist[0] = np.bincount(states, minlength=4)
    state_log = np.empty((cfg.days + 1, n), dtype=np.int8)
    state_log[0] = states
    edge_blocks = []

    for day in range(1, cfg.days + 1):
        not_inf = states != I
        keep_core = not_inf[core_i] & not_inf[core_j]
        keep_nc = not_inf[nc_i] & not_inf[nc_j] & (rng.random(nc_i.size) < nc_prob)
        di = np.concatenate([core_i[keep_core], nc_i[keep_nc]])
        dj = np.concatenate([core_j[keep_core], nc_j[keep_nc]])
        edge_blocks.append(np.column_stack([np.full(di.size, day), di, dj]))

        is_a = states == A
        k = np.bincount(di[is_a[dj]], minlength=n) + np.bincount(dj[is_a[di]], minlength=n)
        age += 1
        cand = np.nonzero((states == S) & (k > 0))[0]
        if cand.size:
            prob = 1.0 - (1.0 - p1[group_ids[cand]]) ** k[cand]
            new_a = cand[rng.random(cand.size) < prob]
            states[new_a] = A
            age[new_a] = 0

        elig = np.nonzero((states == A) & (age >= cfg.inc))[0]
        if elig.size:
            to_i = rng.random(elig.size) < p2[group_ids[elig]]
            states[elig] = np.where(to_i, I, S)
            age[elig] = 0

        to_r = (states == I) & (age >= cfg.inf_dur)
        states[to_r] = R
        age[to_r] = 0
        to_s = (states == R) & (age >= cfg.rec_dur)
        states[to_s] = S
        age[to_s] = 0

        hist[day] = np.bincount(states, minlength=4)
        state_log[day] = states

    return {"hist": hist, "edges": np.concatenate(edge_blocks), "group_ids": group_ids,
            "states": state_log, "config": cfg}


def write_dataset(sim: dict, out: str | Path) -> Path:
    """Write the CSV files the library (and the paper's datasets) use."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cfg: AgeMixConfig = sim["config"]
    hist, edges, gid, states = sim["hist"], sim["edges"], sim["group_ids"], sim["states"]
    n_days, n = states.shape
    n_groups = len(cfg.group_sizes)

    pd.DataFrame(hist, columns=list("SAIR")).assign(day=np.arange(n_days)).to_csv(
        out / "states_total.csv", index=False)
    pd.DataFrame(edges, columns=["day", "i", "j"]).to_csv(out / "timed_edges.csv", index=False)
    pd.DataFrame({"id": np.tile(np.arange(n), n_days), "day": np.repeat(np.arange(n_days), n),
                  "state": states.reshape(-1)}).to_csv(out / "individual_day_state.csv", index=False)
    sizes = np.asarray(cfg.group_sizes)
    pd.DataFrame({"age_group": AGE_LABELS[:n_groups], "population": sizes,
                  "props": sizes / sizes.sum()}).to_csv(out / "age_group_population.csv", index=False)
    pd.DataFrame({"id": np.arange(n), "age_group": gid}).to_csv(
        out / "individual_age_group.csv", index=False)

    inf = np.stack([np.bincount(gid[states[d] == I], minlength=n_groups) for d in range(n_days)])
    pd.DataFrame({"day": np.repeat(np.arange(n_days), n_groups),
                  "age": np.tile(np.arange(n_groups), n_days),
                  "infected": inf.reshape(-1),
                  "age_group": np.tile(AGE_LABELS[:n_groups], n_days)}).to_csv(
        out / "daily_group_infected.csv", index=False)

    e = pd.DataFrame(edges, columns=["day", "i", "j"])
    ends = pd.concat([e[["day", "i"]].rename(columns={"i": "id"}),
                      e[["day", "j"]].rename(columns={"j": "id"})])
    deg = np.zeros((cfg.days + 1, n))
    cnt = ends.groupby(["day", "id"]).size()
    deg[cnt.index.get_level_values(0), cnt.index.get_level_values(1)] = cnt.to_numpy()
    rows = [(d, g, deg[d, gid == g].mean()) for d in range(1, cfg.days + 1)
            for g in range(n_groups)]
    pd.DataFrame(rows, columns=["day", "age", "c"]).to_csv(
        out / "daily_group_avg_contacts.csv", index=False)
    return out
