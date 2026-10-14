"""ARIMA(1,1,1) and Holt-Winters baselines on the aggregate symptomatic curve.

Needs the ``baselines`` extra (statsmodels). At each forecast origin the model is refit
and forecasts ``h`` days ahead. Both follow the authors' notebooks:

* ARIMA(1,1,1) is fit on the whole history up to the origin (``arima age structure.ipynb``).
* Holt-Winters is additive damped-trend exponential smoothing, no seasonality, fit on the
  trailing 14 days (``window=14``), forecasts clipped at 0, and the last value carried
  forward when fewer than 5 points exist (``baselines_standalone.ipynb``).

LSTM is not included: the authors' Keras model is trained without a seed, so its column
cannot be reproduced exactly.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .data import Dataset
from .metrics import fractional_rmse, rmse


def _need_statsmodels():
    try:
        import statsmodels  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError("baselines need statsmodels: install the extra, e.g. "
                          "`uv sync --extra baselines` or `pip install 'epiinfer[baselines]'`") from exc


def _arima(series, steps):
    from statsmodels.tsa.arima.model import ARIMA
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.asarray(ARIMA(series, order=(1, 1, 1)).fit().forecast(steps))


def _holt_winters(series, steps):
    """Additive damped-trend exponential smoothing, as in the authors' notebook."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    y = np.asarray(series, float)
    if len(y) < 5:
        return np.full(steps, max(0.0, y[-1] if len(y) else 0.0))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(y, trend="add", damped_trend=True, seasonal=None,
                                   initialization_method="estimated").fit(optimized=True)
        return np.maximum(0.0, np.asarray(fit.forecast(steps)))


BASELINES = {"arima": _arima, "holt_winters": _holt_winters}
#: trailing window (days) each baseline is refit on; None = the whole history
DEFAULT_WINDOW = {"arima": None, "holt_winters": 14}


def rolling_baseline(data: Dataset, name: str = "arima", horizons=(1, 5, 10, 20),
                     start_eval: int = 25, max_day: int = 100,
                     last_origin: int | None = None, window: int | None | str = "default"
                     ) -> pd.DataFrame:
    """Rolling-origin RMSE / fRMSE of a baseline on the total symptomatic count.

    The defaults match the EpiInfer evaluation (origins 25-99). The paper's ARIMA column
    used origins 10-50 instead (``start_eval=10, last_origin=50``), which reproduces its
    published ARIMA numbers exactly on the age-structured dataset. ``window`` is the number
    of trailing days each fit sees (``"default"``: whole history for ARIMA, 14 for HW).
    """
    _need_statsmodels()
    if name not in BASELINES:
        raise ValueError(f"unknown baseline {name!r}; choose from {sorted(BASELINES)}")
    fn = BASELINES[name]
    if window == "default":
        window = DEFAULT_WINDOW[name]
    days = sorted(data.gt_total)
    if days != list(range(days[0], days[-1] + 1)) or days[0] != 0:
        raise ValueError("baselines need a contiguous daily series starting at day 0")
    last = min(max_day, max(days) + 1)
    y = np.array([data.gt_total[d] for d in days], float)
    preds = {h: [] for h in horizons}
    acts = {h: [] for h in horizons}
    stop = last if last_origin is None else min(last, last_origin + 1)
    for day in range(start_eval, stop):
        lo = 0 if window is None else max(0, day - window)
        fc = fn(y[lo:day + 1], max(horizons))
        for h in horizons:
            if day + h <= min(max_day, len(y) - 1):      # same targets as EpiInfer
                preds[h].append(fc[h - 1])
                acts[h].append(y[day + h])
    return pd.DataFrame([{"method": name, "horizon": h, "n": len(preds[h]),
                          "rmse": rmse(preds[h], acts[h]),
                          "frmse": fractional_rmse(preds[h], acts[h])}
                         for h in horizons if preds[h]])
