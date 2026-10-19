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
            # Swap codes so S takes s_code and whichever compartment had s_code takes 0;
            # plain reassignment would give two compartments the same code.
            codes = dict(default)
            for key, val in default.items():
                if val == s_code:
                    codes[key] = 0
            codes["S"] = int(s_code)
            log.warning("susceptible is state %s, not 0; using %s", s_code, codes)
            return codes
        return default
    except Exception as exc:  # noqa: BLE001 - detection is best effort
        log.info("state auto-detect failed (%r); using default", exc)
        return default


def _build_age_of(d: Path, pop_total, pop_df, df_status) -> np.ndarray:
    """id -> age group. Priority: explicit file, embedded column, contiguous id ranges."""
    explicit = d / "individual_age_group.csv"
    if explicit.exists():
        m = _require(explicit, ("id", "age_group"))
        groups = m["age_group"]
        if not pd.api.types.is_integer_dtype(groups):        # labels such as "0-19"
            labels = [str(x) for x in pop_df["age_group"]]
            index = {lab: i for i, lab in enumerate(labels)}
            unknown = sorted(set(groups.astype(str)) - set(index))
            if unknown:
                raise DataFormatError(f"{explicit.name}: age groups {unknown} are not in "
                                      f"age_group_population.csv {labels}")
            groups = groups.astype(str).map(index)
        age_of = np.full(pop_total, -1, dtype=np.int64)
        age_of[m["id"].to_numpy()] = groups.to_numpy()
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
    col = next((c for c in ("c", "avg_contacts") if c in ref.columns), None)
    if col is None or not {"day", "age"} <= set(ref.columns):
        log.warning("%s: expected columns day,age,c (or avg_contacts); skipping the check",
                    path.name)
        return True
    ref_d1 = ref[ref["day"] == 1].set_index("age")[col].to_dict()
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
        log.warning("mean day-1 contacts per group differ from %s by >15%%. If your ids are grouped "
                    "contiguously by age (as the ABM writes them) the mapping is fine and the "
                    "reference file is simply defined differently (it disagrees on every ABM "
                    "dataset supplied with the paper); otherwise provide individual_age_group.csv",
                    path.name)
    return ok


def _read_until(path: Path, columns: tuple[str, ...], max_day: int | None) -> pd.DataFrame:
    """Read a long CSV, keeping only rows with ``day <= max_day`` (all rows if None).

    The paper's ABM runs for 365 days (an 800 MB edge list) but forecasts use only the first
    100; filtering while reading keeps memory in proportion to what is used.
    """
    if max_day is None:
        return _require(path, columns)
    _require_header(path, columns)
    parts = [c[c["day"] <= max_day] for c in pd.read_csv(path, chunksize=2_000_000)]
    return pd.concat(parts, ignore_index=True)


def _require_header(path: Path, columns: tuple[str, ...]) -> None:
    if not path.exists():
        raise DataFormatError(f"required file not found: {path}")
    head = pd.read_csv(path, nrows=0)
    missing = [c for c in columns if c not in head.columns]
    if missing:
        raise DataFormatError(f"{path.name}: missing column(s) {missing}; has {list(head.columns)}")


def load_dataset(path: str | Path, name: str | None = None, max_day: int | None = None) -> Dataset:
    """Read one dataset folder (see module docstring for the file contract).

    ``max_day``: ignore everything after that day. Forecasts never use data beyond
    ``Config.max_day``, so ``run``/``forecast``/``reproduce`` pass it automatically.
    """
    d = Path(path)
    if not d.is_dir():
        raise DataFormatError(f"dataset folder not found: {d}")
    df_status = _read_until(d / "individual_day_state.csv", ("id", "day", "state"), max_day)
    df_contacts = _read_until(d / "timed_edges.csv", ("day", "i", "j"), max_day)

    pop_path = d / "age_group_population.csv"
    ages_path = d / "individual_age_group.csv"
    if pop_path.exists():
        pop_df = _require(pop_path, ("age_group", "population"))
    elif ages_path.exists():
        m = _require(ages_path, ("id", "age_group"))
        counts = m.groupby("age_group").size().sort_index()
        if pd.api.types.is_integer_dtype(m["age_group"]):     # fill empty group indices
            counts = counts.reindex(range(int(counts.index.max()) + 1), fill_value=0)
        pop_df = pd.DataFrame({"age_group": [str(g) for g in counts.index],
                               "population": counts.to_numpy()})
    else:
        raise DataFormatError(f"need {pop_path.name} or {ages_path.name} in {d}")

    st_path = d / "states_total.csv"
    states_total = pd.read_csv(st_path) if st_path.exists() else None
    if states_total is not None and max_day is not None and "day" in states_total.columns:
        states_total = states_total[states_total["day"] <= max_day].reset_index(drop=True)
    pop_total = int(pop_df["population"].sum())
    for fname, frame, cols in (("individual_day_state.csv", df_status, ("id",)),
                               ("timed_edges.csv", df_contacts, ("i", "j"))):
        for c in cols:
            lo, hi = int(frame[c].min()), int(frame[c].max())
            if lo < 0 or hi >= pop_total:
                raise DataFormatError(
                    f"{fname}: column {c!r} has ids in [{lo}, {hi}] but the population is "
                    f"{pop_total}; ids must be 0..N-1")

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
        gi = _require(gi_path, ("day", "age", "infected"))
        if max_day is not None:
            gi = gi[gi["day"] <= max_day]
        if gi["age"].min() < 0 or gi["age"].max() >= len(labels):
            raise DataFormatError(f"{gi_path.name}: age index outside 0..{len(labels) - 1}")
        for row in gi.itertuples(index=False):
            gt_group[int(row.age)][int(row.day)] = int(row.infected)
    else:
        for day in all_days:
            ids = np.fromiter(inf_on[day], np.int64, len(inf_on[day]))
            bc = np.bincount(age_of[ids], minlength=len(labels)) if ids.size else \
                np.zeros(len(labels), dtype=np.int64)
            for g in range(len(labels)):
                gt_group[g][day] = int(bc[g])
    for g in gt_group:                      # the group file may omit zero counts
        for day in all_days:
            gt_group[g].setdefault(day, 0)
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


def load_curve(path: str | Path, max_day: int | None = None) -> dict[int, float]:
    """``{day: symptomatic count}`` from ``states_total.csv`` alone (column ``I``, or
    ``individual_day_state.csv`` if that is all there is).

    The ARIMA / Holt-Winters baselines need nothing else, so they also run on datasets that
    lack a contact list (the paper's uniform-contact data has none).
    """
    d = Path(path)
    st = d / "states_total.csv"
    if st.exists():
        df = _require(st, ("day", "I"))
        curve = dict(zip(df["day"].astype(int), df["I"].astype(float), strict=False))
    else:
        df = _require(d / "individual_day_state.csv", ("id", "day", "state"))
        curve = {int(k): float(v) for k, v in (df[df["state"] == 2].groupby("day").size()).items()}
        for day in sorted(df["day"].unique()):
            curve.setdefault(int(day), 0.0)
    if max_day is not None:
        curve = {k: v for k, v in curve.items() if k <= max_day}
    return dict(sorted(curve.items()))
