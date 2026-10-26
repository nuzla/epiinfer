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


def relative_rmse(pred, actual) -> float:
    """Root mean squared relative error, ``sqrt(mean(((pred - actual) / actual)**2))``, over the
    points with a non-zero actual: the October 2026 paper's fRMSE. NaN if there are none."""
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    keep = actual > 0
    if not keep.any():
        return float("nan")
    rel = (pred[keep] - actual[keep]) / actual[keep]
    return math.sqrt(np.mean(rel ** 2))
