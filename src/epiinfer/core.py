"""Contact-network SAIR projector: paper Algorithms 2 (EpiInferContact), 3 (predict), 4 (findprob).

Compartment flow (the paper's S-E-I-R with E called A, "asymptomatic/pre-symptomatic")::

    S --(exposure from infectious contacts, rate p1)--> A
    A --(after `inc` days, with prob p2)--> I          (otherwise back to S)
    I --(after `duration` days)--> R

All randomness is drawn from an explicit ``numpy.random.RandomState`` so that a
run is reproducible from its seed regardless of thread or process count.

Contacts after the forecast origin: the paper (section "Contact Information for
Forecasting") states that future contact data are not used. Pass ``graph_until=origin``
to :meth:`EpiInferCore.project` to enforce that: every day after ``graph_until`` reuses the
origin day's graph ("assume the people whom P meets are the same as on day d"). With
``graph_until=None`` the recorded graph of each future day is used, which is what the
original research scripts did (they therefore looked ahead at future contacts).
"""

from __future__ import annotations

import numpy as np


class EpiInferCore:
    """Projects the epidemic forward on a recorded daily contact graph.

    Tracks *sets of ids* per compartment, so transitions are set algebra.
    ``adj[day][id]`` is the set of neighbours ``id`` met on ``day``. Beyond the
    last recorded day the final graph is reused (paper: "assume the people whom P
    meets are the same as on day d").
    """

    def __init__(self, population_ids, daily_contacts, age_of, inc: int, duration: int,
                 n_groups: int | None = None, contact_offset: int = 0):
        self.population = set(population_ids)
        self.age_of = np.asarray(age_of, dtype=np.int64)
        # n_groups comes from the dataset's labels: a group with no members still counts.
        self.n_groups = int(n_groups) if n_groups is not None else int(self.age_of.max()) + 1
        # 0: day d's contacts create day d+1's exposures (the original scripts); 1: day d+1's
        # contacts do, as in the simulator and the final notebook
        self.contact_offset = int(contact_offset)
        self.inc = inc
        self.duration = duration
        self.adj: dict[int, dict[int, set]] = {}
        for day, meets in daily_contacts.items():
            day_adj: dict[int, set] = {}
            for u, v in meets:
                if u in self.population:
                    day_adj.setdefault(u, set()).add(v)
                if v in self.population:
                    day_adj.setdefault(v, set()).add(u)
            self.adj[day] = day_adj
        self.max_contact_day = max(self.adj) if self.adj else -1

    def contact_day(self, day: int, graph_until: int | None = None) -> int:
        """Which recorded day's graph stands in for ``day``."""
        last = self.max_contact_day if graph_until is None else min(graph_until,
                                                                     self.max_contact_day)
        return min(day, last)

    def infectious_encounters(self, infectious, susceptible, day,
                              graph_until: int | None = None) -> dict:
        """FINDPROB counts: ``{susceptible id: number of infectious contacts on day}``."""
        adj_d = self.adj.get(self.contact_day(day, graph_until), {})
        encounters: dict[int, int] = {}
        for a in infectious:
            for nb in adj_d.get(a, ()):
                if nb in susceptible:
                    encounters[nb] = encounters.get(nb, 0) + 1
        return encounters

    def predict(self, infectious, susceptible, p1_vec, day, rng,
                graph_until: int | None = None) -> set:
        """Alg. 3: susceptibles newly exposed on ``day``.

        A susceptible with k infectious contacts is exposed with probability
        ``1 - (1 - p1)^k`` (Alg. 4), one draw each.
        """
        if not infectious or not susceptible:
            return set()
        encounters = self.infectious_encounters(infectious, susceptible, day, graph_until)
        if not encounters:
            return set()
        at_risk = np.fromiter(encounters.keys(), np.int64, len(encounters))
        counts = np.fromiter(encounters.values(), np.int64, len(encounters))
        p1 = p1_vec[self.age_of[at_risk]]
        probs = 1.0 - (1.0 - p1) ** counts
        drawn = rng.random_sample(at_risk.size) < probs
        return set(at_risk[drawn].tolist())

    def group_counts(self, idset) -> np.ndarray:
        out = np.zeros(self.n_groups, dtype=np.int64)
        if idset:
            arr = np.fromiter(idset, np.int64, len(idset))
            bc = np.bincount(self.age_of[arr], minlength=self.n_groups)
            out[:bc.size] = bc
        return out

    def project(self, p1_vec, p2_vec, new_asymp_hist, new_inf_hist, start_day, end_day,
                immune, rng, graph_until: int | None = None):
        """Roll the dynamics from ``start_day`` to ``end_day`` (exclusive).

        Returns ``{day: array([I_g0, I_g1, ...])}``: symptomatic count per group at
        the end of each simulated day.

        ``new_asymp_hist``/``new_inf_hist`` are ``{day: set(ids)}`` of who newly
        entered A / I on recent days; ``immune`` are ids recovered before ``start_day``.
        ``graph_until``: last day whose recorded contacts may be used (see module docstring).
        """
        p1_vec = np.asarray(p1_vec, float)
        p2_vec = np.asarray(p2_vec, float)
        new_asymp = dict(new_asymp_hist)       # local copies: never clobber the caller's
        new_inf = dict(new_inf_hist)

        asymp = set()
        for k in range(start_day - self.inc + 1, start_day + 1):
            asymp |= new_asymp.get(k, set())
        infected = set()
        for k in range(start_day - self.duration + 1, start_day + 1):
            infected |= new_inf.get(k, set())
        recovered = set(immune) if immune else set()
        for k, ids in new_inf.items():
            if k + self.duration <= start_day:
                recovered |= ids

        results = {}
        for day in range(start_day, end_day):
            susceptible = self.population - (asymp | infected | recovered)

            newly_asymp = self.predict(asymp, susceptible, p1_vec, day + self.contact_offset, rng,
                                       graph_until)                               # S -> A
            new_asymp[day + 1] = newly_asymp

            cohort = new_asymp.get((day + 1) - self.inc)                            # A -> I
            newly_inf = set()
            if cohort:
                cand = np.fromiter(cohort, np.int64, len(cohort))
                p2 = p2_vec[self.age_of[cand]]
                newly_inf = set(cand[rng.random_sample(cand.size) < p2].tolist())
            new_inf[day + 1] = newly_inf

            asymp |= newly_asymp
            asymp -= new_asymp.get(day - self.inc + 1, set())

            infected |= newly_inf
            expired = new_inf.get(day - self.duration + 1, set())
            if expired:
                infected -= expired
                recovered |= expired

            results[day + 1] = self.group_counts(infected)
        return results
