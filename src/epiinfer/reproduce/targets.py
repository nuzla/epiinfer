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

#: The AUTHORS' OWN RUN of epiinfer_paper_aligned.py on the archived age-structured data,
#: ALL row (``results_paper_aligned.csv``, 13 July 2026): ``{(method, horizon): (rmse, frmse)}``.
#: It is "Simulation 2" in the authors' July compiled draft (EpiInfer_contacttracing_new.pdf);
#: the published paper reports "Simulation 3" instead. This library reproduces this run (all
#: four modes) to within 8.3% (docs/REPRODUCING.md).
AUTHORS_RUN_AGE_STRUCTURED = {
    ("known_both", 1): (8.9156, 0.0131), ("known_both", 5): (17.2452, 0.0256),
    ("known_both", 10): (30.0811, 0.0444), ("known_both", 20): (158.1382, 0.2335),
    ("known_p1", 1): (13.2419, 0.0195), ("known_p1", 5): (50.6933, 0.0753),
    ("known_p1", 10): (47.9931, 0.0709), ("known_p1", 20): (124.4041, 0.1837),
    ("known_p2", 1): (8.9215, 0.0131), ("known_p2", 5): (18.8929, 0.0281),
    ("known_p2", 10): (20.9089, 0.0309), ("known_p2", 20): (125.2740, 0.1850),
    ("unknown_both", 1): (10.2404, 0.0151), ("unknown_both", 5): (33.6882, 0.0500),
    ("unknown_both", 10): (45.9206, 0.0678), ("unknown_both", 20): (109.0364, 0.1610),
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

#: Holt-Winters columns. The authors' notebook output (baselines_standalone.ipynb) shows
#: these were computed on a DIFFERENT simulated epidemic ("abmcontact10000aprilnewage",
#: peak I 1044 age-structured / 1012 uniform) from the one EpiInfer-contact and the age-structured
#: ARIMA were scored on (peak I 915). Run these tables only on the aprilnewage data. The
#: notebook scores targets up to day 119 = last origin 99 + horizon 20 (its data runs to day 365),
#: unlike EpiInfer (<= 100); ``reproduce`` therefore loads curves up to last origin + max horizon.
HW_AGE_STRUCTURED = {("holt_winters", 1): (83.42, None), ("holt_winters", 5): (140.65, None),
                     ("holt_winters", 10): (179.05, None), ("holt_winters", 20): (260.96, None)}
HW_UNIFORM = {("holt_winters", 1): (90.51, None), ("holt_winters", 5): (139.44, None),
              ("holt_winters", 10): (177.95, None), ("holt_winters", 20): (260.39, None)}

#: Identity of the dataset each table was computed on: (people, days, peak I).
#: ``reproduce`` warns when the supplied folder does not match.
FINGERPRINT_AGE = (10000, 101, 915)          # archived age_structured (EpiInfer + ARIMA)
FINGERPRINT_OPENABM = (10000, 100, 2704)
FINGERPRINT_APRIL_AGE = (10000, 101, 1044)   # abmcontact10000aprilnewage/age_structured (HW, LSTM)
FINGERPRINT_APRIL_UNIFORM = (10000, 101, 1012)  # .../uniform (HW, LSTM and the uniform ARIMA)

TABLES = {
    "age_structured": {"targets": AGE_STRUCTURED, "group": "ALL", "fingerprint": FINGERPRINT_AGE,
                       "authors_run": AUTHORS_RUN_AGE_STRUCTURED,
                       "methods": ("known_both", "known_p1", "known_p2", "unknown_both"),
                       "default_data": "age_structured", "caption": "tab:age_structured"},
    "uniform": {"targets": UNIFORM, "group": "ALL",
                "methods": ("known_both", "known_p1", "known_p2", "unknown_both"),
                "default_data": "uniform", "caption": "tab:uniform"},
    "openabm": {"targets": OPENABM, "group": "ALL", "methods": ("empirical_p1",),
                "fingerprint": FINGERPRINT_OPENABM,
                "default_data": "openabm", "caption": "tab:openabm-forecast"},
    "arima_age_structured": {"targets": ARIMA_AGE_STRUCTURED, "group": "ALL",
                             "fingerprint": FINGERPRINT_AGE,
                             "methods": ("arima",), "baseline_window": (10, 50),
                             "default_data": "age_structured", "caption": "tab:baseline-abs"},
    "arima_uniform": {"targets": ARIMA_UNIFORM, "group": "ALL", "methods": ("arima",),
                      "baseline_window": (10, 50), "fingerprint": FINGERPRINT_APRIL_UNIFORM,
                      "default_data": "uniform", "caption": "tab:baseline-abs"},
    "hw_age_structured": {"targets": HW_AGE_STRUCTURED, "group": "ALL",
                          "methods": ("holt_winters",), "baseline_window": (25, 99),
                          "fingerprint": FINGERPRINT_APRIL_AGE, "default_data": "aprilnewage/age_structured",
                          "caption": "tab:age_specific_day*"},
    "hw_uniform": {"targets": HW_UNIFORM, "group": "ALL", "methods": ("holt_winters",),
                   "baseline_window": (25, 99), "fingerprint": FINGERPRINT_APRIL_UNIFORM,
                   "default_data": "aprilnewage/uniform", "caption": "tab:uniform_day*"},
}

# NB: the paper labels rows by the parameter that is KNOWN ("p1 known" = p1 given, p2
# estimated). In this library that is method ``known_p1``; `known_p2` = p2 given, p1 searched.
