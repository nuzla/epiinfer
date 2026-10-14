"""EpiInfer-CONTACT: forecast infections from contact-tracing data."""

from .config import OPENABM, PAPER, Config
from .data import DataFormatError, Dataset, load_dataset
from .forecast import ForecastResult, forecast, run
from .metrics import fractional_rmse, rmse

__version__ = "0.1.0"
__all__ = ["Config", "DataFormatError", "Dataset", "ForecastResult", "OPENABM", "PAPER",
           "forecast", "fractional_rmse", "load_dataset", "rmse", "run"]
