"""Forecast with your own contact-tracing data.

    python examples/forecast_new_data.py [/path/to/your/dataset]

The folder needs individual_day_state.csv, timed_edges.csv and an age mapping
(docs/DATA_FORMAT.md). Without an argument the tiny bundled demo is used; it was simulated
with inc = duration = 7 days, the defaults of the grid methods. For your own data set
``inc`` (days pre-symptomatic) and ``duration`` (days symptomatic) from what you observe.
"""

import sys
from pathlib import Path

import epiinfer
from epiinfer.cli import DEMO

path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEMO
data = epiinfer.load_dataset(path)
last = max(data.all_days)

# 1) Back-test: how well would the method have forecast the days you already have?
#    Uses no contact data after each forecast origin (contacts="frozen", the default).
res = epiinfer.run(data, "unknown_both", inc=7, duration=7, num_sims=10, seed=0,
                   start_eval=last - 15, horizons=(1, 5))
print(res.summary().to_string(index=False))

# 2) Forecast beyond the last observed day, with a 10-90% band over trajectories.
fc = epiinfer.forecast(data, horizon=14, method="unknown_both", inc=7, duration=7,
                       num_sims=20, seed=0)
print(fc[fc["group"] == "ALL"].to_string(index=False))
