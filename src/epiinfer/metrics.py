"""Error metrics used throughout the paper."""

from __future__ import annotations

import math

import numpy as np


def rmse(pred, actual) -> float:
    """Root mean squared error; NaN for empty input."""
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    return math.sqrt(np.mean((pred - actual) ** 2)) if pred.size else float("nan")


def fractional_rmse(pred, actual) -> float:
    """RMSE divided by the mean of the actual values (the paper's *fRMSE*).

    Every time point is kept, including days where ``actual == 0``. NaN when the
    input is empty or the actuals average to zero.
    """
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    if not pred.size:
        return float("nan")
    denom = actual.mean()
    if denom == 0:
        return float("nan")
    return math.sqrt(np.mean((pred - actual) ** 2)) / denom
