"""Configuration for a forecasting run.

Two engines implement the two versions of the method:

* ``engine="final"`` – the October 2026 paper (``abm_final.ipynb``, :mod:`epiinfer.final`):
  exposures rebuilt from infections (no pre-symptomatic data needed), recovered people return
  to susceptible, periodic joint-grid calibration. Preset :data:`FINAL`; the default of
  :func:`epiinfer.run` and :func:`epiinfer.forecast`.
* ``engine="contact"`` – the 2025 code behind the earlier tables (:mod:`epiinfer.core`). Presets:
  :data:`PAPER` (grid-search calibration of per-age ``p1``/``p2``) and :data:`OPENABM`
  (``p2`` fixed at 1, ``p1`` refit every day from observed S->A transitions).
* ``engine="compartmental"`` – EpiInfer, the earlier compartmental model the paper compares
  against (:mod:`epiinfer.compartmental`). It is deterministic and uses no contact list: only
  symptomatic counts and average contacts per age group. Preset :data:`COMPARTMENTAL`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

CALIBRATED_METHODS = ("unknown_both", "known_p2", "known_p1", "known_both")
EMPIRICAL_METHOD = "empirical_p1"
METHODS = CALIBRATED_METHODS + (EMPIRICAL_METHOD,)
#: "frozen": after the forecast origin, reuse the origin day's contact graph (no look-ahead;
#: what the paper describes). "recorded": use each future day's recorded graph (what the
#: original research scripts did; needed to reproduce the published numbers).
CONTACT_MODES = ("frozen", "recorded")
ENGINES = ("final", "contact", "compartmental")


@dataclass(frozen=True)
class Config:
    # --- disease timing (days) ------------------------------------------------
    inc: int = 7                      # days spent in A (infectious, pre-symptomatic)
    duration: int = 7                 # days spent in I (symptomatic, isolated)
    # --- rolling forecast -----------------------------------------------------
    horizons: tuple[int, ...] = (1, 5, 10, 20, 50)
    start_eval: int = 25              # first forecast origin
    max_day: int = 100                # origins < max_day; targets <= max_day and <= last data day
    last_origin: int | None = None    # last forecast origin (default: max_day - 1)
    num_sims: int = 10                # Monte-Carlo trajectories averaged per forecast
    seed: int = 0                     # all randomness derives from this
    mc_threads: int = 1               # threads for the Monte-Carlo trajectories
    contacts: str = "frozen"          # see CONTACT_MODES
    contact_offset: int = 0           # contact engine: 0 = day d's contacts infect on day d+1
                                      # (original scripts); 1 = day d+1's (simulator timing)
    # --- calibrated (grid) method --------------------------------------------
    candidates: tuple[float, ...] = (0.025, 0.04, 0.05, 0.06, 0.075, 0.08, 0.1, 0.125, 0.15,
                                     0.175, 0.2, 0.225, 0.25, 0.275, 0.3)
    calib_window: int = 20            # must exceed `inc` so p1's effect lands in-window
    smoothing: float = 0.5            # new = prev + smoothing * (best - prev)
    neutral_prior: float = 0.1        # first-day value for unknown rates
    p1_true: tuple[float, ...] | None = None   # only needed by known_* methods
    p2_true: tuple[float, ...] | None = None
    # --- empirical-p1 method -------------------------------------------------
    p2_fixed: float = 1.0
    p1_window: int = 5
    p1_floor: float = 1e-4
    p1_ceil: float = 0.99
    # --- engine ---------------------------------------------------------------
    engine: str = "contact"           # see ENGINES; the presets set it
    # --- final engine (October 2026 paper) ---------------------------------------
    rec_duration: int = 7             # days recovered before becoming susceptible again
    recalib_every: int = 5            # recalibrate every k forecast origins
    score_horizon: int = 7            # each calibration forecast runs this many days
    final_calib_window: int = 14      # calibration scores the origins of the last k days
    lambda_damp: float = 1.0          # Slow Learning lambda
    final_grid: tuple[float, ...] = (0.05, 0.075, 0.1, 0.125, 0.15, 0.175, 0.2, 0.225, 0.25,
                                     0.275, 0.3)
    # --- compartmental engine (the earlier EpiInfer) ----------------------------------
    group_contacts: str = "avg5"      # "avg5": mean of the previous 5 days; "same_day"

    def __post_init__(self):
        if self.engine not in ENGINES:
            raise ValueError(f"engine must be one of {ENGINES}, got {self.engine!r}")
        if self.group_contacts not in ("avg5", "same_day"):
            raise ValueError(f"group_contacts must be 'avg5' or 'same_day', got "
                             f"{self.group_contacts!r}")
        if self.contacts not in CONTACT_MODES:
            raise ValueError(f"contacts must be one of {CONTACT_MODES}, got {self.contacts!r}")
        if self.inc < 1 or self.duration < 1:
            raise ValueError("inc and duration must be >= 1 day")
        if self.num_sims < 1:
            raise ValueError("num_sims must be >= 1")
        if not self.horizons or min(self.horizons) < 1:
            raise ValueError("horizons must be positive integers")

    def with_(self, **kw) -> Config:
        return replace(self, **kw)


#: Paper experiments on the synthetic age-structured ABM (Tables 1-12).
PAPER = Config(p1_true=(0.25, 0.15, 0.08), p2_true=(0.15, 0.10, 0.05))

#: OpenABM-Covid19 experiment: p2 = 1, p1 refit daily, inc = 5, duration = 11.
OPENABM = Config(inc=5, duration=11, smoothing=1.0)

#: The final method (October 2026 paper, Tables 10-13): 30 trajectories, horizons 1-20,
#: forecast origins 25 .. max_day - max(horizons) - 1 (= 79).
FINAL = Config(engine="final", horizons=(1, 5, 10, 20), num_sims=30)

#: EpiInfer, the earlier compartmental model (the paper's "EpiInfer" columns); deterministic.
COMPARTMENTAL = Config(engine="compartmental", horizons=(1, 5, 10, 20), num_sims=1)
