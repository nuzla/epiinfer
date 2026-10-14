"""Forecast with your own contact-tracing data.

    python examples/forecast_new_data.py /path/to/your/dataset

The folder needs individual_day_state.csv, timed_edges.csv and an age mapping
(docs/DATA_FORMAT.md). Without an argument the tiny bundled demo is used.
"""

import sys
from pathlib import Path

import epiinfer
from epiinfer.cli import DEMO

path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEMO
data = epiinfer.load_dataset(path)

# 1) How well would the method have done on the days you already have?  (back-test)
res = epiinfer.run(data, "empirical_p1", inc=5, duration=11, num_sims=10, seed=0,
                   start_eval=30, max_day=45, horizons=(1, 5))
print(res.summary().to_string(index=False))

# 2) Forecast the days after the last observation, with a 10-90% band over trajectories.
fc = epiinfer.forecast(data, horizon=14, method="empirical_p1", inc=5, duration=11,
                       num_sims=20, seed=0)
print(fc[fc["group"] == "ALL"].to_string(index=False))
