"""Published numbers from the paper that ``epiinfer reproduce`` compares against.

Values are the EpiInfer-contact columns of the paper's summary tables
(``tab:age_structured``, ``tab:uniform``) and the new-method ("red") values of
``tab:openabm-forecast``, transcribed from the 2025 *Algorithms* proof source.
Layout: ``{(method, horizon): (rmse, frmse)}``.

The paper reports a single Monte-Carlo run without seeds, so exact equality is not
expected; see ``docs/REPRODUCING.md`` for the measured run-to-run band.
"""

from __future__ import annotations

HORIZONS = (1, 5, 10, 20)

#: tab:age_structured, EpiInfer-contact columns. Dataset: age-structured contacts.
AGE_STRUCTURED = {
    ("known_both", 1): (8.72, 0.013), ("known_both", 5): (17.49, 0.026),
    ("known_both", 10): (29.71, 0.043), ("known_both", 20): (156.94, 0.231),
    ("known_p1", 1): (8.05, 0.012), ("known_p1", 5): (17.28, 0.026),   # paper row "p1 known"
    ("known_p1", 10): (29.35, 0.043), ("known_p1", 20): (157.82, 0.232),
    ("known_p2", 1): (8.77, 0.013), ("known_p2", 5): (18.18, 0.027),   # paper row "p2 known"
    ("known_p2", 10): (29.98, 0.044), ("known_p2", 20): (158.62, 0.233),
    ("unknown_both", 1): (8.50, 0.013), ("unknown_both", 5): (17.79, 0.027),
    ("unknown_both", 10): (29.65, 0.043), ("unknown_both", 20): (156.49, 0.230),
}

#: tab:uniform, EpiInfer-contact columns (RMSE, fRMSE). Dataset: uniform contacts.
UNIFORM = {
    ("known_both", 1): (74.32, 0.117), ("known_both", 5): (132.09, 0.190),
    ("known_both", 10): (84.07, 0.115), ("known_both", 20): (144.40, 0.195),
    ("known_p1", 1): (60.24, 0.091), ("known_p1", 5): (133.27, 0.171),
    ("known_p1", 10): (151.88, 0.200), ("known_p1", 20): (223.32, 0.300),
    ("known_p2", 1): (73.70, 0.117), ("known_p2", 5): (132.59, 0.190),
    ("known_p2", 10): (82.71, 0.113), ("known_p2", 20): (153.71, 0.209),
    ("unknown_both", 1): (60.73, 0.092), ("unknown_both", 5): (135.85, 0.174),
    ("unknown_both", 10): (154.83, 0.205), ("unknown_both", 20): (224.66, 0.303),
}

#: tab:openabm-forecast, new method ("red") ALL row. Method: empirical_p1.
OPENABM = {
    ("empirical_p1", 1): (132.72, 0.151), ("empirical_p1", 5): (177.57, 0.197),
    ("empirical_p1", 10): (414.19, 0.460), ("empirical_p1", 20): (948.33, 1.379),
}

#: ARIMA(1,1,1) columns of the age-specific/uniform tables (tab:baseline-abs). The paper's
#: ARIMA notebook refits on the full I(t) history at forecast origins 10-50, a different
#: window from the 25-99 used for EpiInfer-contact; these targets use the ARIMA window.
ARIMA_AGE_STRUCTURED = {("arima", 1): (30.12, None), ("arima", 5): (279.61, None),
                        ("arima", 10): (474.93, None), ("arima", 20): (833.68, None)}
ARIMA_UNIFORM = {("arima", 1): (149.53, None), ("arima", 5): (501.66, None),
                 ("arima", 10): (730.34, None), ("arima", 20): (984.59, None)}

TABLES = {
    "age_structured": {"targets": AGE_STRUCTURED, "group": "ALL",
                       "methods": ("known_both", "known_p1", "known_p2", "unknown_both"),
                       "default_data": "age_structured", "caption": "tab:age_structured"},
    "uniform": {"targets": UNIFORM, "group": "ALL",
                "methods": ("known_both", "known_p1", "known_p2", "unknown_both"),
                "default_data": "uniform", "caption": "tab:uniform"},
    "openabm": {"targets": OPENABM, "group": "ALL", "methods": ("empirical_p1",),
                "default_data": "openabm", "caption": "tab:openabm-forecast"},
    "arima_age_structured": {"targets": ARIMA_AGE_STRUCTURED, "group": "ALL",
                             "methods": ("arima",), "baseline_window": (10, 50),
                             "default_data": "age_structured", "caption": "tab:baseline-abs"},
    "arima_uniform": {"targets": ARIMA_UNIFORM, "group": "ALL", "methods": ("arima",),
                      "baseline_window": (10, 50), "default_data": "uniform",
                      "caption": "tab:baseline-abs"},
}

# NB: the paper labels rows by the parameter that is KNOWN ("p1 known" = p1 given, p2
# estimated). In this library that is method ``known_p1``; `known_p2` = p2 given, p1 searched.
