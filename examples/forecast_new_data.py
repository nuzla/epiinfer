"""Forecast with your own contact-tracing data.

    python examples/forecast_new_data.py [/path/to/your/dataset]

The folder needs individual_day_state.csv and timed_edges.csv (docs/DATA_FORMAT.md; only
who is symptomatic or recovered each day is read). Without an argument the tiny bundled demo
is used; it was simulated with inc = duration = 7 days, the defaults. For your own data set
``inc`` (days pre-symptomatic), ``duration`` (days symptomatic) and ``rec_duration`` (days
immune after recovery) from what you observe.
"""

import sys
from pathlib import Path

import pandas as pd

import epiinfer
from epiinfer.cli import DEMO

path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEMO
last = int(pd.read_csv(path / "individual_day_state.csv", usecols=["day"])["day"].max())

# 1) Back-test: how well would the method have forecast the days you already have?
#    Every forecast uses only the data up to its origin. The final engine needs 22 days of
#    history before its first origin, and `max_day` / `last_origin` make the back-test cover the
#    whole dataset (the default stops at day 100, the paper's protocol).
res = epiinfer.run(path, "unknown_both", inc=7, duration=7, rec_duration=7, num_sims=10,
                   seed=0, start_eval=max(22, last - 15), max_day=last + 1, last_origin=last - 1,
                   horizons=(1, 5))
print(res.summary().to_string(index=False))

# 2) Forecast beyond the last observed day, with a 10-90% band over trajectories.
fc = epiinfer.forecast(path, horizon=14, method="unknown_both", inc=7, duration=7,
                       rec_duration=7, num_sims=20, seed=0)
print(fc.to_string(index=False))
