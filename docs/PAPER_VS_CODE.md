# Paper vs. code

These notes come from porting the research scripts (`epiinfer_paper_aligned.py`,
`epiinfer_empirical_p1.py`) into this library and re-running them against the 2025
*Algorithms* proof source. Items 1–5 change how the published numbers should be read.

## 1. The original code looked ahead at future contacts

The paper says future contact data are not used. Its section "Contact Information for
Forecasting" states that observed contact values from future days were not used. The
`findprob` caption and the authors' notes also say to assume people meet the same people
as on day *d*.

The original scripts did use them. At forecast origin *d*, the projection for day *d + k*
used the **recorded contact graph of day d + k**. In the AgeMixABM data that graph also
drops anyone who is isolated (symptomatic), so it carries information about the target.

The library makes this a setting, `Config.contacts` (or `--contacts`):

| value | meaning | used by |
|---|---|---|
| `frozen` | every day after the origin reuses the origin day's graph (no look-ahead) | `run`, `forecast` (default) |
| `recorded` | each future day's recorded graph, as the original scripts did | `reproduce` (default, to match the published numbers) |

Measured effect (seed 0) is small, and it does not always go in the same direction. See
`REPRODUCING.md` for the full table.

| Data | Horizon | recorded | frozen |
|---|---|---|---|
| OpenABM, ALL | day 10 / 20 | 418.1 / 957.7 | 427.3 / 979.3 |
| age-structured, both known | day 5 / 20 | 17.9 / 158.0 | 18.2 / 126.3 |

`forecast()` never uses contacts after its origin, whatever `contacts` is set to.

## 2. The model is handed the true pre-symptomatic (A) people

Algorithm 2 needs the people who were recently exposed. The paper estimates them from the
infected set: it assumes |Infected(d)|/p2 people were exposed at day d − inc, drawn in
proportion to their contact counts.

The research code skips that step. It reads who was in **A** straight from the simulator's
per-person states. Its own docstring calls this "a known simplification". All published
EpiInfer-contact numbers, and this library, depend on that oracle input.

**Consequence for real data.** Real contact-tracing data rarely says who is infected but
not yet symptomatic. To use the library you must supply state 1 (A) in
`individual_day_state.csv`. The paper's reconstruction is not implemented here (see
"Open items").

## 3. The baselines were evaluated on a different window

The paper's ARIMA(1,1,1) column reproduces **exactly** (30.12 / 279.61 / 474.93 / 833.68).
It does so only with forecast origins **10–50**, which is what the authors' ARIMA notebook
uses. EpiInfer-contact is scored on origins **25–99**. The early growth phase is far
harder to forecast, so the two columns are not comparable.

On the same 25–99 window, ARIMA scores 20.0 / 85.4 / 97.7 / 111.8. At day 20 that beats
EpiInfer-contact's 156.9 (paper) / 158.0 (this library).

- `epiinfer reproduce --table arima_age_structured` reproduces the paper's ARIMA column.
- `epiinfer baseline --which arima` gives ARIMA on the EpiInfer window.

The Holt-Winters column was computed on a different dataset; see item 5.

## 4. The published EpiInfer-contact rows are a different run from the authors' own

In `tab:age_structured` the four knowledge modes are within about 3% of each other at
every horizon (day 20: 156.5 to 158.6), so estimating p1 and p2 apparently cost nothing.
The code does not behave like that. Three sources agree on what it produces:

| Day 5, ALL (RMSE) | both known | p1 known | p2 known | both unknown |
|---|---|---|---|---|
| **Published paper** | 17.49 | 17.28 | 18.18 | 17.79 |
| Authors' own run of the script (`results_paper_aligned.csv`, 13 July) | 17.25 | 50.69 | 18.89 | 33.69 |
| **This library** (seed 0, recorded contacts) | 17.87 | 52.23 | 17.60 | 31.29 |

- **The library matches the authors' own run in all 16 cells** (four modes × four
  horizons), within 8.3%. That is about the Monte-Carlo noise between seeds (5%). It is a
  check on the port.
- **The paper does not match either.** Only "both known" agrees with all three.
- **The July draft explains why.** `EpiInfer_contacttracing_new.pdf` (23 July) reports every
  cell as three simulations. Its **Simulation 2** is exactly the authors' run above
  (8.9156, 13.2419, 10.2404 …). Its **Simulation 3** is what the published paper later
  prints as EpiInfer-contact (8.72, 8.05, 8.50 …), and **Simulation 1** is the older
  EpiInfer (180.17 …). So the paper's EpiInfer-contact rows are a third run.
- **Simulation 3 behaves like a different dataset or code.** Its uniform-contact day-1 error
  is 74.3, against 9.2 in Simulation 2, and its estimated-rate rows barely differ from
  "both known". Which dataset and code produced it is not in the files supplied.
  Candidates are the `abmcontact10000aprilnewage` data and the damped-learning script
  `epiinfer_age_structured _1_1.py` (damping 0.005), which the paper's λ = 0.01 text
  describes. I could not run them without that data.

Simulation 2's uniform-contact data is not supplied either. Freshly simulated uniform data
gives 10.4 / 26.7 / 39.2 / 151.2 for "both known", close to Simulation 2's
9.2 / 21.2 / 37.9 / 138.0 and far from the published 74.3 / 132.1 / 84.1 / 144.4.

The authors' own July report (`EpiInfer_Implementation_Report.pptx`) lists three open
deviations: the id→age mapping fails its degree check (measured 1.4–1.9×), the
pre-symptomatic set is seeded from ground truth, and forecasts reuse future contact graphs.
These are items 1 and 2 above, found independently.

## 5. The Holt-Winters and LSTM columns use a different epidemic

The saved output of the authors' `baselines_standalone.ipynb` prints the published
Holt-Winters column (83.42 / 140.65 / 179.05 / 260.96) and the published LSTM column
(111.79 / 119.71 / 155.79 / 169.83). Both were computed on `abmcontact10000aprilnewage`,
whose age-structured epidemic peaks at **1,044** symptomatic people.

EpiInfer-contact and ARIMA were scored on the archived dataset, which peaks at **915**;
ARIMA reproduces exactly on it. So within Tables 1–8, the baseline columns and the
EpiInfer-contact column come from **two different simulated epidemics**.

The same notebook also defines "fractional RMSE" differently from the rest of the paper:

- Notebook: the RMSE of the relative errors, (pred − actual) / actual.
- Everywhere else: RMSE / mean(actual).

The library uses RMSE / mean(actual) throughout. `reproduce` checks each dataset's
identity, so this kind of mix-up now prints a warning.

## 6. Smaller differences

- **Scoring a day that does not exist.** The research code scored the day after the data
  ends against an actual of 0 (`gt.get(day, 0)`). That is OpenABM day 100, which has no
  record. The library skips such targets. This moves the OpenABM ratios from 1.000 to about
  1.008.
- **Naming.** The paper labels a mode by the parameter that is *known*:
  - `known_p1` means p1 is given and p2 is estimated.
  - `known_p2` means p2 is given and p1 is estimated.
- **Calibration settings.** The text gives a grid of [0.05, 0.30] and λ = 0.01. The code
  that produced the tables uses a 15-value grid (0.025 … 0.3), a 20-day scoring window
  and smoothing 0.5. The library follows the **code**.
- **Not stated in the paper:** random seeds, number of runs, hardware, and Python version.
  The library takes `--seed`. Every (seed, origin, trajectory) gets its own RNG stream, so
  results do not depend on `--workers` or `--jobs`.
- **Contacts reference file.** In the shipped age-structured folder,
  `daily_group_avg_contacts.csv` disagrees with `timed_edges.csv`. Day-1 contacts per
  person are 9.8 / 8.0 / 4.8 in the edges against 5.3 / 4.2 / 3.4 in the file. The loader
  warns about this, and it does not affect forecasts.
- **Group file.** `daily_group_infected.csv` omits zero counts. The loader fills them in
  as zeros.

## Inconsistencies in the paper text (not edited)

- The population is given as 2,000 in one place and 10,000 in another.
- ARIMA is shown as "--" in Tables 5–8 but is given in the absolute-RMSE table.
- The prose says EpiInfer-contact beats every baseline at every horizon. Several table
  cells contradict this, as do the like-for-like ARIMA window in item 3 and the OpenABM
  results at days 10 and 20 against the previous method.
- Table 1's day-1 value of 7.92 matches none of the summary-table rows (8.50–8.77).
- `tab:openabm-forecast` still carries the note "need to compare with ARIMA".
- The uniform-contact table (`tab:uniform`) cannot be checked because its dataset was not
  supplied. Freshly simulated uniform data gives very different day-1 errors (10.4 against
  the paper's 74.3). The paper's day-1 ARIMA error for uniform (149.5, against 30.1
  age-structured) also points to a noisier dataset than the documented settings produce.

## Open items

- Implement the paper's reconstruction of the exposed set from infections (item 2), so
  that the method runs on data without the A state.
- The authors should confirm which dataset and code produced "Simulation 3" (item 4),
  and supply the `abmcontact10000aprilnewage` data behind the Holt-Winters and LSTM columns
  (item 5).
