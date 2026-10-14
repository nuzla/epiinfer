# Paper vs. code: what is and is not pinned down

Honest notes from porting the research scripts into this library.

## Two methods, two experiments
| Paper experiment | Method here | Settings |
|---|---|---|
| AgeMixABM tables (age-structured and uniform contacts; knowledge modes *both known / p1 known / p2 known / both unknown*) | `known_both`, `known_p1`, `known_p2`, `unknown_both` | grid search over p1/p2, inc=7, duration=7 |
| OpenABM table | `empirical_p1` | p2=1, p1 refit daily from the last 5 days of S→A events, inc=5, duration=11 |

Naming: the paper labels a mode by the parameter that is *known*. `known_p1` = p1 given,
p2 estimated. `known_p2` = p2 given, p1 estimated.

## Things the paper does not state (this library chose, and documents, a value)
* **Random seeds** — none stated. The library takes `--seed`; every (seed, origin day,
  trajectory) uses its own RNG stream, so results do not depend on thread count.
* **Calibration grid and window** — the code uses a 15-value grid (0.025 … 0.3), a 20-day
  scoring window and smoothing 0.5; the paper text gives p ∈ [0.05, 0.30] and λ = 0.01
  "slow learning". The library follows the **code** that produced the tables.
* **Holt-Winters / LSTM settings** — only in commented-out text. `baselines.py` uses ARIMA(1,1,1)
  and additive damped Holt-Winters; LSTM is not implemented. Quote the paper's LSTM numbers.
* **Hardware, Python version** — not stated. Tested here on Python 3.13.

## Inconsistencies spotted in the source (not edited)
* population 2,000 in one place, 10,000 in another;
* ARIMA shown as "--" in Tables 5-8 but given in the absolute-RMSE table;
* the prose says EpiInfer-contact beats every baseline at every horizon; several table cells
  say otherwise (e.g. age-structured day 20, and OpenABM day 10/20 vs the previous method);
* Table 1 (age-specific, day 1: 7.92) matches none of the summary-table rows (8.50–8.77),
  so it is not used as a reproduction target;
* `tab:openabm-forecast` carries an unresolved note "need to compare with ARIMA".

## Data
* The ABM generator in this library is the same model as the paper's notebook but a
  vectorised port with a different random stream, so a regenerated dataset is statistically
  equivalent, **not** byte-identical, to the paper's. Use the archived datasets
  (`epiinfer fetch-data`) for exact reproduction.
* In the shipped age-structured folder, `daily_group_avg_contacts.csv` disagrees with the
  degrees computed from `timed_edges.csv` (day 1: 9.8/8.0/4.8 vs 5.3/4.2/3.4 contacts per
  person). The loader warns about this; it does not change the forecasts.
