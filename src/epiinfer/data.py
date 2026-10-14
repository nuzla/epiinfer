"""Load a contact-tracing dataset folder into the structures the model needs.

Minimum input (see ``docs/DATA_FORMAT.md``)::

    individual_day_state.csv   id,day,state        state: 0=S 1=A 2=I 3=R
    timed_edges.csv            day,i,j             who met whom on which day
    age_group_population.csv   age_group,population   OR   individual_age_group.csv

Optional files (``states_total.csv``, ``daily_group_infected.csv``,
``daily_group_avg_contacts.csv``) are used when present and derived otherwise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("epiinfer")


class DataFormatError(ValueError):
    """The dataset folder is missing a file or column, or is inconsistent."""


@dataclass
class Dataset:
    name: str
    population_total: int
    age_labels: list[str]
    age_of: np.ndarray                     # age_of[id] -> group index
    daily_contacts: dict                   # {day: [(i, j), ...]}
    asymp_on: dict                         # {day: set(ids in A that day)}
    susceptible_on: dict                   # {day: set(ids in S that day)}
    inf_on: dict
    recovered_on: dict                     # {day: set(ids in R that day)}
    new_asymp: dict                        # "diff" transitions: set difference of day k vs k-1
    new_inf: dict
    new_asymp_strict: dict                 # "strict": S(k-1)&A(k) and A(k-1)&I(k)
    new_inf_strict: dict
    gt_total: dict                         # {day: total symptomatic I}
    gt_group: dict                         # {group: {day: symptomatic I}}
    states_total: pd.DataFrame
    all_days: list = field(default_factory=list)

    @property
    def n_groups(self) -> int:
        return len(self.age_labels)

    def transitions(self, kind: str):
        """(new_asymp, new_inf) under ``kind`` = 'diff' (paper grid method) or 'strict'."""
        if kind == "diff":
            return self.new_asymp, self.new_inf
        if kind == "strict":
            return self.new_asymp_strict, self.new_inf_strict
        raise ValueError(f"unknown transitions kind {kind!r}")


def _require(path: Path, columns: tuple[str, ...] = ()) -> pd.DataFrame:
    if not path.exists():
        raise DataFormatError(f"required file not found: {path}")
    df = pd.read_csv(path)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise DataFormatError(f"{path.name}: missing column(s) {missing}; has {list(df.columns)}")
    return df


def detect_state_codes(df_status: pd.DataFrame, states_total: pd.DataFrame | None) -> dict:
    """Confirm the {0:S, 1:A, 2:I, 3:R} encoding against ``states_total`` (when given)."""
    default = {"S": 0, "A": 1, "I": 2, "R": 3}
    if states_total is None:
        return default
    try:
        counts = df_status[df_status["day"] == 0]["state"].value_counts().to_dict()
        s_true = int(states_total[states_total["day"] == 0].iloc[0]["S"])
        s_code = max(counts, key=counts.get)           # most common day-0 state = S
        if counts.get(s_code, 0) != s_true:
            log.info("day-0 dominant count %s != S %s; using default encoding",
                     counts.get(s_code), s_true)
            return default
        if s_code != 0:
            log.warning("susceptible is state %s, not 0; remapping", s_code)
            return {"S": int(s_code), "A": 1, "I": 2, "R": 3}
        return default
    except Exception as exc:  # noqa: BLE001 - detection is best effort
        log.info("state auto-detect failed (%r); using default", exc)
        return default


def _build_age_of(d: Path, pop_total, pop_df, df_status) -> np.ndarray:
    """id -> age group. Priority: explicit file, embedded column, contiguous id ranges."""
    explicit = d / "individual_age_group.csv"
    if explicit.exists():
        m = pd.read_csv(explicit)
        age_of = np.full(pop_total, -1, dtype=np.int64)
        age_of[m["id"].to_numpy()] = m["age_group"].to_numpy()
        log.info("id->age: individual_age_group.csv")
        return age_of
    if "age" in df_status.columns:
        first = df_status.drop_duplicates("id")[["id", "age"]]
        age_of = np.full(pop_total, -1, dtype=np.int64)
        age_of[first["id"].to_numpy()] = first["age"].to_numpy()
        log.info("id->age: 'age' column in individual_day_state.csv")
        return age_of
    age_of = np.empty(pop_total, dtype=np.int64)
    lo = 0
    for g, n in enumerate(pop_df["population"].to_numpy()):
        age_of[lo:lo + n] = g
        lo += n
    log.info("id->age: contiguous ranges by population order %s", list(pop_df["population"]))
    return age_of


def validate_age_mapping(age_of, daily_contacts, d: Path, labels) -> bool:
    """Compare mean day-1 degree per group with ``daily_group_avg_contacts.csv``.

    Returns False (and warns) on a >15% mismatch, which usually means the
    contiguous id->age fallback is wrong and ``individual_age_group.csv`` is needed.
    """
    path = d / "daily_group_avg_contacts.csv"
    if not path.exists() or 1 not in daily_contacts:
        return True
    ref = pd.read_csv(path)
    ref_d1 = ref[ref["day"] == 1].set_index("age")["c"].to_dict()
    if not ref_d1:
        return True
    deg = np.zeros(age_of.size, dtype=np.int64)
    for u, v in daily_contacts[1]:
        if 0 <= u < deg.size:
            deg[u] += 1
        if 0 <= v < deg.size:
            deg[v] += 1
    ok = True
    for g in range(int(age_of.max()) + 1):
        measured = deg[age_of == g].mean() if (age_of == g).any() else float("nan")
        r = ref_d1.get(g, float("nan"))
        if r == r and abs(measured - r) > 0.15 * max(r, 1.0):
            ok = False
            log.warning("age mapping mismatch group %s (%s): measured %.2f vs reference %.2f",
                        g, labels[g] if g < len(labels) else g, measured, r)
    if not ok:
        log.warning("degree mismatch: contiguous id->age may be wrong; "
                    "provide individual_age_group.csv")
    return ok


def load_dataset(path: str | Path, name: str | None = None) -> Dataset:
    """Read one dataset folder (see module docstring for the file contract)."""
    d = Path(path)
    if not d.is_dir():
        raise DataFormatError(f"dataset folder not found: {d}")
    df_status = _require(d / "individual_day_state.csv", ("id", "day", "state"))
    df_contacts = _require(d / "timed_edges.csv", ("day", "i", "j"))

    pop_path = d / "age_group_population.csv"
    ages_path = d / "individual_age_group.csv"
    if pop_path.exists():
        pop_df = _require(pop_path, ("age_group", "population"))
    elif ages_path.exists():
        m = pd.read_csv(ages_path)
        counts = m.groupby("age_group").size().sort_index()
        pop_df = pd.DataFrame({"age_group": [str(g) for g in counts.index],
                               "population": counts.to_numpy()})
    else:
        raise DataFormatError(f"need {pop_path.name} or {ages_path.name} in {d}")

    st_path = d / "states_total.csv"
    states_total = pd.read_csv(st_path) if st_path.exists() else None
    pop_total = int(pop_df["population"].sum())
    if int(df_status["id"].max()) >= pop_total:
        raise DataFormatError(
            f"individual_day_state.csv has id {int(df_status['id'].max())} but the population "
            f"is {pop_total}; ids must be 0..N-1")

    codes = detect_state_codes(df_status, states_total)
    S, A, I, R = codes["S"], codes["A"], codes["I"], codes["R"]
    age_of = _build_age_of(d, pop_total, pop_df, df_status)
    labels = [str(x) for x in pop_df["age_group"]]
    if age_of.min() < 0 or age_of.max() >= len(labels):
        raise DataFormatError("age mapping leaves some ids unassigned or out of range")

    daily_contacts = {int(day): list(zip(g["i"].tolist(), g["j"].tolist()))
                      for day, g in df_contacts.groupby("day")}
    validate_age_mapping(age_of, daily_contacts, d, labels)

    all_days = sorted(int(x) for x in df_status["day"].unique())
    sets = {k: {} for k in "SAIR"}
    code_to_key = {S: "S", A: "A", I: "I", R: "R"}
    for (day, state), grp in df_status.groupby(["day", "state"]):
        key = code_to_key.get(int(state))
        if key is not None:
            sets[key][int(day)] = set(grp["id"].tolist())
    for key in "SAIR":
        for day in all_days:
            sets[key].setdefault(day, set())
    susceptible_on, asymp_on, inf_on, rec_on = sets["S"], sets["A"], sets["I"], sets["R"]

    new_asymp, new_inf, new_asymp_s, new_inf_s = {}, {}, {}, {}
    for day in all_days:
        if day == 0:
            new_asymp[0], new_inf[0] = asymp_on[0], inf_on[0]
            new_asymp_s[0], new_inf_s[0] = set(asymp_on[0]), set(inf_on[0])
        else:
            new_asymp[day] = asymp_on[day] - asymp_on.get(day - 1, set())
            new_inf[day] = inf_on[day] - inf_on.get(day - 1, set())
            new_asymp_s[day] = asymp_on[day] & susceptible_on.get(day - 1, set())
            new_inf_s[day] = inf_on[day] & asymp_on.get(day - 1, set())

    # Ground truth: symptomatic counts per group (file if present, else derived).
    gt_group = {g: {} for g in range(len(labels))}
    gi_path = d / "daily_group_infected.csv"
    if gi_path.exists():
        for row in _require(gi_path, ("day", "age", "infected")).itertuples(index=False):
            gt_group[int(row.age)][int(row.day)] = int(row.infected)
    else:
        for day in all_days:
            ids = np.fromiter(inf_on[day], np.int64, len(inf_on[day]))
            bc = np.bincount(age_of[ids], minlength=len(labels)) if ids.size else \
                np.zeros(len(labels), dtype=np.int64)
            for g in range(len(labels)):
                gt_group[g][day] = int(bc[g])
    if states_total is not None and {"day", "I"} <= set(states_total.columns):
        gt_total = dict(zip(states_total["day"], states_total["I"], strict=False))
    else:
        gt_total = {day: sum(gt_group[g].get(day, 0) for g in gt_group) for day in all_days}
        states_total = pd.DataFrame({
            "day": all_days,
            "S": [len(susceptible_on[x]) for x in all_days],
            "A": [len(asymp_on[x]) for x in all_days],
            "I": [len(inf_on[x]) for x in all_days],
            "R": [len(rec_on[x]) for x in all_days]})

    return Dataset(name or d.name, pop_total, labels, age_of, daily_contacts, asymp_on,
                   susceptible_on, inf_on, rec_on, new_asymp, new_inf, new_asymp_s, new_inf_s,
                   gt_total, gt_group, states_total, all_days)
