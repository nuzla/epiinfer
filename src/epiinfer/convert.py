"""Build a dataset folder from a case list and a contact list.

Most contact-tracing systems keep one row per case (who, and the date symptoms began) and one
row per contact (date, person, person). :func:`cases_to_dataset` turns those into the files
the default (final) engine reads: see docs/DATA_FORMAT.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def cases_to_dataset(cases: pd.DataFrame | str | Path, contacts: pd.DataFrame | str | Path,
                     out: str | Path, duration: int = 7, rec_duration: int = 7) -> dict:
    """Write ``individual_day_state.csv``, ``timed_edges.csv``, ``age_group_population.csv`` and
    ``people.csv`` (id ↔ your label) into ``out``.

    ``cases`` has columns ``person, onset`` (one row per symptomatic episode) and ``contacts``
    has ``date, a, b``; either can be a DataFrame or a CSV path. Labels can be any text. Each
    case is symptomatic (state 2) for ``duration`` days from onset, then recovered (state 3)
    for ``rec_duration`` days. Day 0 is the earliest date in either list. Returns a summary.
    """
    if not isinstance(cases, pd.DataFrame):
        cases = pd.read_csv(cases)
    if not isinstance(contacts, pd.DataFrame):
        contacts = pd.read_csv(contacts)
    for name, df, cols in (("cases", cases, ("person", "onset")),
                           ("contacts", contacts, ("date", "a", "b"))):
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"{name} needs columns {cols}; missing {missing}")
    onset = pd.to_datetime(cases["onset"])
    date = pd.to_datetime(contacts["date"])
    people = sorted(set(cases["person"]) | set(contacts["a"]) | set(contacts["b"]), key=str)
    index = {p: i for i, p in enumerate(people)}
    day0 = min(onset.min(), date.min())
    n_days = (max(onset.max(), date.max()) - day0).days + 1
    n = len(people)

    state = np.zeros((n_days, n), dtype=np.int8)       # 0 = neither symptomatic nor recovered
    for person, start in zip(cases["person"], onset, strict=True):
        d, i = (start - day0).days, index[person]
        state[d:d + duration, i] = 2
        state[d + duration:d + duration + rec_duration, i] = 3

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": np.tile(np.arange(n), n_days), "day": np.repeat(np.arange(n_days), n),
                  "state": state.ravel()}).to_csv(out / "individual_day_state.csv", index=False)
    pd.DataFrame({"day": (date - day0).dt.days, "i": contacts["a"].map(index),
                  "j": contacts["b"].map(index)}).to_csv(out / "timed_edges.csv", index=False)
    pd.DataFrame({"age_group": ["all"], "population": [n]}).to_csv(
        out / "age_group_population.csv", index=False)
    pd.DataFrame({"id": range(n), "label": people}).to_csv(out / "people.csv", index=False)
    return {"folder": str(out), "people": n, "days": n_days, "day0": day0.date().isoformat()}
