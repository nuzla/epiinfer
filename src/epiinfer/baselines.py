"""ARIMA(1,1,1) and Holt-Winters baselines on the aggregate symptomatic curve.

Needs ``pip install epiinfer[baselines]`` (statsmodels). For each origin day the model is
refit on the observed series up to that day and forecasts ``h`` days ahead, matching the
rolling-origin protocol used for EpiInfer. The paper does not state the exact
Holt-Winters or LSTM settings, so these are the standard choices (documented below) and
LSTM is not included; compare with the published LSTM numbers in the paper.
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
        raise ImportError("baselines need statsmodels: pip install 'epiinfer[baselines]'") from exc


def _arima(series, steps):
    from statsmodels.tsa.arima.model import ARIMA
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.asarray(ARIMA(series, order=(1, 1, 1)).fit().forecast(steps))


def _holt_winters(series, steps):
    """Additive damped-trend exponential smoothing (no seasonality) on the full history."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(series, trend="add", damped_trend=True).fit()
        return np.asarray(fit.forecast(steps))


BASELINES = {"arima": _arima, "holt_winters": _holt_winters}


def rolling_baseline(data: Dataset, name: str = "arima", horizons=(1, 5, 10, 20),
                     start_eval: int = 25, max_day: int = 100) -> pd.DataFrame:
    """Rolling-origin RMSE / fRMSE of a baseline on the total symptomatic count."""
    _need_statsmodels()
    fn = BASELINES[name]
    days = sorted(data.gt_total)
    last = min(max_day, max(days) + 1)
    y = np.array([data.gt_total[d] for d in days], float)
    preds = {h: [] for h in horizons}
    acts = {h: [] for h in horizons}
    for day in range(start_eval, last):
        fc = fn(y[:day + 1], max(horizons))
        for h in horizons:
            if day + h < len(y):
                preds[h].append(fc[h - 1])
                acts[h].append(y[day + h])
    return pd.DataFrame([{"method": name, "horizon": h, "n": len(preds[h]),
                          "rmse": rmse(preds[h], acts[h]),
                          "frmse": fractional_rmse(preds[h], acts[h])}
                         for h in horizons if preds[h]])
