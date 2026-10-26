"""EpiInfer, the earlier compartmental model: the paper's "EpiInfer" columns.

A port of two of the authors' notebooks:

* ``epiinfer for base case.ipynb``: both rates known, contacts averaged over the previous five
  days, horizons 1-20. It produced the EpiInfer column of Appendix A, which this port
  reproduces in all 720 cells (``reproduce --table appendix``).
* ``Epiinfer for C_<scale>.ipynb``: the knowledge settings. A missing rate is found by grid
  search over the last five days (``GRID_P1`` x ``GRID_P2``); these notebooks use the same
  day's contacts. They wrote the ``RMSE_summary<scale>.xlsx`` files inside ``Archive.zip``.

The model is deterministic and needs no contact list. It reads only the symptomatic count per
age group and each group's average number of contacts per day (``daily_group_infected.csv``,
``daily_group_avg_contacts.csv``), plus ``states_total.csv`` and ``age_group_population.csv``.

Each day t:

* The symptomatic people of the last ``inc`` days, each standing for ``1/p2`` exposures, give
  the chance ``p_exp`` that a contact is with someone exposed.
* A group member not yet exposed is infected with probability
  ``1 - (1 - p1)^(contacts * p_exp)``.
* A fraction ``p2`` of the new exposures become symptomatic.
* Symptomatic people recover at rate ``gamma = 1/duration``, and recovered people return to
  susceptible at rate ``eta``.

As in the notebooks, the observed history enters through ``daily_group_infected.csv``. That
file holds the number of people symptomatic each day, not newly symptomatic, and the model
uses it for both.

``exposure="per_group"`` computes ``p_exp`` for each age group from that group's own
symptomatic people and takes one ``(p1, p2)`` per group. With the paper's age-specific rates,
same-day contacts and origins 20-80 it reproduces the EpiInfer "both known" column of the
age-specific tables (Tables 2-5 and 14) exactly; the code for it was not supplied, so only
``known_both`` is offered.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import DataFormatError
from .metrics import fractional_rmse, relative_rmse, rmse

INC, DURATION, ETA = 7, 7, 1 / 10
#: calibration grids of ``Epiinfer for C_*.ipynb``
GRID_P1 = np.linspace(0.05, 0.3, 15)
GRID_P2 = np.linspace(0.05, 0.3, 10)
CALIB_WINDOW = 5
CASES = ("known_both", "known_p1", "known_p2", "unknown_both")
#: "avg5": mean of the previous five days' contacts (Appendix A); "same_day": that day's
CONTACTS = ("avg5", "same_day")
#: "pooled": one exposure chance from the whole population (the notebooks); "per_group"
EXPOSURES = ("pooled", "per_group")
FILES = ("states_total.csv", "age_group_population.csv", "daily_group_infected.csv",
         "daily_group_avg_contacts.csv")


@dataclass
class GroupCounts:
    """Daily counts as the notebooks hold them. Column 0 of ``I``/``R``/``new`` is the total,
    columns 1.. the age groups."""
    I: np.ndarray            # (days, G+1) symptomatic: total from states_total, groups from file
    R: np.ndarray            # (days, G+1) recovered: total from states_total, groups zero
    new: np.ndarray          # (days, G+1) symptomatic per group; total = their sum
    meet: np.ndarray         # (days, G) average contacts per person
    population: np.ndarray   # (G,)

    @property
    def days(self) -> int:
        return len(self.I)

    @property
    def n_groups(self) -> int:
        return len(self.population)

    @classmethod
    def from_folder(cls, path: str | Path, max_day: int | None = None) -> GroupCounts:
        """Load a dataset folder (the loader of ``epiinfer for base case.ipynb``)."""
        d = Path(path)
        missing = [f for f in FILES if not (d / f).exists()]
        if missing:
            raise FileNotFoundError(f"{d}: the compartmental model needs {', '.join(missing)}")

        def read(name, *columns):
            df = pd.read_csv(d / name)
            lacking = [c for c in columns if c not in df.columns]
            if lacking:
                raise DataFormatError(f"{name}: missing column(s) {lacking}; has "
                                      f"{list(df.columns)}")
            return df

        pop = read("age_group_population.csv", "population")
        st = read("states_total.csv", "day", "I", "R")
        if max_day is not None:
            st = st[st["day"] <= max_day]
        if st.empty:
            raise ValueError(f"{d / 'states_total.csv'} has no rows"
                             + (f" up to day {max_day}" if max_day is not None else ""))
        G = len(pop)
        days = int(st["day"].max()) + 1
        I = np.zeros((days, G + 1))
        R = np.zeros((days, G + 1))
        new = np.zeros((days, G + 1))
        for row in st.itertuples(index=False):
            I[int(row.day), 0] = float(row.I)
            R[int(row.day), 0] = float(row.R)
        labels = pop["age_group"].astype(str).tolist() if "age_group" in pop.columns else None

        def group_index(df, name):
            if "age" in df.columns:
                g = pd.to_numeric(df["age"], errors="raise").astype(int)
                if ((g < 0) | (g >= G)).any():
                    raise ValueError(f"{name}: 'age' has group indices outside 0..{G - 1}")
                return g
            if "age_group" in df.columns and labels is not None:
                m = {lab: i for i, lab in enumerate(labels)}
                vals = df["age_group"].astype(str)
                bad = sorted(set(vals) - set(m))
                if bad:
                    raise ValueError(f"{name}: age groups not in age_group_population.csv: {bad}")
                return vals.map(m).astype(int)
            raise ValueError(f"{name} needs an 'age' or 'age_group' column")

        inf = read("daily_group_infected.csv", "day", "infected")
        inf = (inf.assign(grp=group_index(inf, "daily_group_infected.csv"))
               .groupby(["day", "grp"], as_index=False)["infected"].sum())
        for row in inf.itertuples(index=False):
            day, g = int(row.day), int(row.grp)
            if 0 <= day < days:
                I[day, g + 1] = float(row.infected)
                new[day, g + 1] = float(row.infected)
                new[day, 0] += float(row.infected)
        con = read("daily_group_avg_contacts.csv", "day")
        col = "c" if "c" in con.columns else "avg_contacts"
        if col not in con.columns:
            raise DataFormatError(f"daily_group_avg_contacts.csv: needs a column c (or "
                                  f"avg_contacts); has {list(con.columns)}")
        con = (con.assign(grp=group_index(con, "daily_group_avg_contacts.csv"),
                          cval=pd.to_numeric(con[col], errors="raise"))
               .groupby(["day", "grp"], as_index=False)["cval"].mean())
        meet = np.zeros((days, G))
        seen = np.zeros((days, G), dtype=bool)
        for row in con.itertuples(index=False):
            day, g = int(row.day), int(row.grp)
            if 0 <= day < days:
                meet[day, g] = float(row.cval)
                seen[day, g] = True
        for g in range(G):                       # a missing day repeats the previous one
            for day in range(1, days):
                if not seen[day, g]:
                    meet[day, g] = meet[day - 1, g]
        return cls(I, R, new, meet, pop["population"].to_numpy(float))


def simulate(c: GroupCounts, p1, p2, start: int, horizon: int,
             contacts: str = "avg5", inc: int = INC, gamma: float = 1 / DURATION,
             eta: float = ETA, freeze_after: int | None = None,
             exposure: str = "pooled") -> np.ndarray:
    """Project the days ``start .. start + horizon - 1`` from the observations before
    ``start`` (``sim_from_day`` in the notebooks). Returns symptomatic counts (days, G+1),
    filled for ``start - inc .. start + horizon - 1``.

    The notebooks read each projected day's recorded average contacts, which lie after the
    last observation. ``freeze_after=d`` instead repeats day ``d``'s contacts for every later
    day, so nothing after ``d`` is used, and lets the projection run past the end of the data.

    ``p1`` and ``p2`` are numbers, or one value per age group with ``exposure="per_group"``.
    """
    if contacts not in CONTACTS:
        raise ValueError(f"contacts must be one of {CONTACTS}")
    if exposure not in EXPOSURES:
        raise ValueError(f"exposure must be one of {EXPOSURES}")
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    if exposure == "pooled" and (p1.ndim or p2.ndim):
        raise ValueError("per-group rates need exposure='per_group'")
    days, G = c.meet.shape
    meet_all = c.meet
    if freeze_after is not None:
        last = min(freeze_after, days - 1)
        days = max(days, start + horizon)
        meet_all = np.vstack([c.meet[:last + 1],
                              np.repeat(c.meet[last:last + 1], days - last - 1, axis=0)])
    I = np.zeros((days, G + 1))
    R = np.zeros((days, G + 1))
    new = np.zeros((days, G + 1))
    for j in range(start - inc, start):
        if j >= 0:
            I[j], R[j], new[j] = c.I[j], c.R[j], c.new[j]
    N = np.sum(c.population)
    for t in range(start, min(start + horizon, days)):
        if contacts == "avg5":
            lo = max(0, t - 5)
            meet = np.mean(meet_all[lo:t], axis=0) if t > lo else meet_all[t]
        else:
            meet = meet_all[t]
        inf_total = 0
        inf_g = np.zeros(G)
        for j in range(1, inc + 1):
            if t - j >= 0:
                inf_total += new[t - j, 0]
                inf_g += new[t - j, 1:]
        if exposure == "pooled":
            asymp_total = N - I[t - inc, 0]
            p_exp = inf_total / (p2 * asymp_total) if asymp_total > 0 and p2 > 0 else 0
        else:
            free = c.population - I[t - inc, 1:]
            p_exp = np.divide(inf_g, p2 * free, out=np.zeros(G), where=(free > 0) & (p2 > 0))
        ptran = 1 - (1 - p1) ** (meet * p_exp)
        exposed_before = np.divide(inf_g, p2, out=np.zeros(G), where=p2 > 0)
        not_exposed = np.maximum(0, c.population - I[t - inc, 1:] - exposed_before - R[t - inc, 1:])
        newexp = not_exposed * ptran
        new[t, 1:] = newexp * p2
        new[t, 0] = np.sum(newexp) * p2 if exposure == "pooled" else np.sum(new[t, 1:])
        recovering = I[t - 1] * gamma
        returning = R[t - 1] * eta
        R[t] = R[t - 1] - returning + recovering
        I[t] = I[t - 1] + new[t] - recovering
    return I


def min_origin(case: str, inc: int = INC) -> int:
    """The earliest origin (first projected day) the model can run from: ``known_both`` reads the
    ``inc`` days before it, and a calibration also projects from ``CALIB_WINDOW`` days earlier.
    Before that the history would be indexed from the end of the arrays (negative days)."""
    return inc if case == "known_both" else inc + CALIB_WINDOW


def calibrate(c: GroupCounts, case: str, origin: int, p1_true: float | None = None,
              p2_true: float | None = None, contacts: str = "avg5", inc: int = INC,
              gamma: float = 1 / DURATION) -> tuple[float, float]:
    """The rates used at ``origin``: a missing one is the grid value whose projection from
    ``origin - 5`` best fits the last five observed totals (first best wins on ties)."""
    if case not in CASES:
        raise ValueError(f"unknown case {case!r}; choose from {CASES}")
    if case in ("known_both", "known_p1") and p1_true is None:
        raise ValueError(f"{case} needs the true p1")
    if case in ("known_both", "known_p2") and p2_true is None:
        raise ValueError(f"{case} needs the true p2")
    if case == "known_both":
        return p1_true, p2_true
    w = CALIB_WINDOW
    obs = c.I[origin - w:origin, 0]

    def err(p1, p2):
        sim = simulate(c, p1, p2, origin - w, w, contacts, inc, gamma)
        return np.sqrt(np.mean((obs - sim[origin - w:origin, 0]) ** 2))

    p1s = GRID_P1 if case in ("known_p2", "unknown_both") else [p1_true]
    p2s = GRID_P2 if case in ("known_p1", "unknown_both") else [p2_true]
    best = 1e9
    b1 = p1_true if case == "known_p1" else 0.05
    b2 = p2_true if case == "known_p2" else 0.05
    for p1 in p1s:
        for p2 in p2s:
            e = err(p1, p2)
            if e < best:
                best, b1, b2 = e, p1, p2
    return float(b1), float(b2)


def run_compartmental(c: GroupCounts, cases=("known_both",), p1_true: float | None = None,
                      p2_true: float | None = None, horizons=tuple(range(1, 21)),
                      first_origin: int = 20, last_origin: int = 80, contacts: str = "avg5",
                      inc: int = INC, gamma: float = 1 / DURATION,
                      freeze: bool = False, exposure: str = "pooled") -> pd.DataFrame:
    """Rolling forecasts of the total symptomatic count from every origin
    ``first_origin..last_origin`` whose furthest target lies inside the data (the notebooks'
    protocol: origins 20-80, horizons 1-20). One row per (case, origin, horizon).

    In the notebooks the origin ``o`` is the first projected day: only days before ``o`` are
    observed, so horizon ``h`` is ``h + 1`` days after the last observation. ``freeze=True``
    stops the projection reading recorded contacts after day ``o - 1``."""
    if exposure != "pooled" and set(cases) != {"known_both"}:
        raise ValueError("per-group exposure is available for known_both only")
    for case in cases:
        if case in CASES and first_origin < min_origin(case, inc):
            raise ValueError(f"case {case!r}: the first origin must be day "
                             f"{min_origin(case, inc)} or later (it needs that much history); "
                             f"got {first_origin}")
    H = max(horizons)
    rows = []
    for case in cases:
        for o in range(first_origin, last_origin + 1):
            if o + H >= c.days:
                continue
            p1, p2 = calibrate(c, case, o, p1_true, p2_true, contacts, inc, gamma)
            sim = simulate(c, p1, p2, o, H + 1, contacts, inc, gamma,
                           freeze_after=o - 1 if freeze else None, exposure=exposure)
            rows += [{"case": case, "origin": o, "horizon": h, "target_day": o + h,
                      "predicted": float(sim[o + h, 0]), "actual": float(c.I[o + h, 0]),
                      "p1_used": p1, "p2_used": p2} for h in horizons]
    return pd.DataFrame(rows)


def summarize(pred: pd.DataFrame) -> pd.DataFrame:
    """RMSE and both fRMSE definitions per case and horizon."""
    out = []
    for (case, h), s in pred.groupby(["case", "horizon"], sort=False):
        p, a = s["predicted"].to_numpy(), s["actual"].to_numpy()
        out.append({"case": case, "horizon": int(h), "n": len(s), "rmse": rmse(p, a),
                    "frmse": fractional_rmse(p, a), "frmse_rel": relative_rmse(p, a)})
    return pd.DataFrame(out)
