# Paper vs. code

These notes come from porting the research scripts (`epiinfer_paper_aligned.py`,
`epiinfer_empirical_p1.py`) into this library and re-running them against the 2025
*Algorithms* proof source. Items 1–5 and 7 change how the published numbers should be read.

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
- **Simulation 3 is not the `aprilnewage` age-structured data either.** That data has since
  been supplied (item 5), and the library's "both known" run on it gives 12.5 / 27.3 / 46.5 /
  138.3, against Simulation 3's 8.7 / 17.5 / 29.7 / 156.9. On the archived 915-peak data the
  same code gives 8.8 / 17.9 / 32.6 / 158.0. So Simulation 3's "both known" row comes from the
  915-peak data (or a copy of it), and only its estimated-rate rows (which barely differ from
  "both known") remain unexplained. The code that produced them is not in the files supplied.
  The paper's λ = 0.01 text describes the damped-learning script. Both versions of it, run
  on the archived data, fail to reproduce Simulation 3 as well: the 6 July version (damping
  0.01) and the 18 August version (`_1_1`, damping 0.005) give day-10 / day-20 errors of
  191 / 547 and 190 / 547 for `unknown_both`, and 216–217 / 551 for `known_p2`. Simulation 3
  has 29.7 / 156.5 and 30.0 / 158.6.
- **Simulation 3's uniform row** (day-1 error 74.3, against 9.2 in Simulation 2) cannot be
  checked: the uniform data supplied has no contact list. Freshly simulated uniform data gives
  10.4 / 26.7 / 39.2 / 151.2 for "both known", close to Simulation 2 and far from 74.3.

The authors' own July report (`EpiInfer_Implementation_Report.pptx`) lists three open
deviations: the id→age mapping fails its degree check (measured 1.4–1.9×), the
pre-symptomatic set is seeded from ground truth, and forecasts reuse future contact graphs.
These are items 1 and 2 above, found independently.

## 5. The baseline columns come from different epidemics than EpiInfer-contact

Both datasets named in the authors' baseline notebook have now been supplied
(`abmcontact10000aprilnewage`, 365 days; `age_structured` peaks at 1,044 symptomatic people
and `uniform` at 1,012, both on day 14). Checking each published column against each dataset
shows where every column came from:

| Published column | Reproduces on | Check |
|---|---|---|
| ARIMA, age-structured | the archived **915-peak** data | exact (30.12 / 279.61 / 474.93 / 833.68); on `aprilnewage` it gives 136.8 / 328.8 / 360.5 / 408.9 |
| ARIMA, uniform | `aprilnewage/uniform` | exact (149.53 / 501.66 / 730.34 / 984.59) |
| EpiInfer-contact, age-structured | the archived 915-peak data | "both known" within 10%; on `aprilnewage` 1.4–1.6× too high at days 1–10 |
| Holt-Winters, LSTM | `aprilnewage` | Holt-Winters only approximately (below); LSTM not run |
| Appendix A: ARIMA and EpiInfer-contact | the `abmcontact10000april{0.2,0.5,2}` folders | ARIMA exact, EpiInfer-contact: item 7 |

So within the age-structured table the ARIMA and EpiInfer-contact columns come from the 915-peak
epidemic, while Holt-Winters and LSTM come from a different one (1,044 peak). The uniform table
mixes in the same way, but its EpiInfer-contact column cannot be re-run (no contact list).

**Holt-Winters is reproduced only approximately.** The notebook's own code, run unchanged on
`aprilnewage`, gives 84.0 / 130.7 / 167.5 / 211.1 (age-structured) and 89.3 / 136.8 / 174.4 /
228.8 (uniform), and so does this library, against the published 83.4 / 140.7 / 179.1 / 261.0
and 90.5 / 139.4 / 178.0 / 260.4. Day 1 agrees within 1.5%; day 20 is off by 12–19%. The fit is
sensitive to the statsmodels version, and the notebook silently falls back to a hand-written
Holt model whenever the statsmodels fit raises (that fallback gives 78 / 190 / 269 / 478, so
a mix of the two across forecast origins would be possible). I could not pin the versions.
The notebook also scores forecasts against days up to 119 (its data runs to 365), unlike
EpiInfer (days up to 100).

The same notebook defines "fractional RMSE" differently from the rest of the paper:

- Notebook: the RMSE of the relative errors, (pred − actual) / actual.
- Everywhere else: RMSE / mean(actual).

The library uses RMSE / mean(actual) throughout. `reproduce` checks each dataset's identity
(people, days, peak), so mixing datasets now prints a warning.

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
- **Contacts reference file.** In every ABM dataset supplied, `daily_group_avg_contacts.csv`
  disagrees with `timed_edges.csv` (archived age-structured data: day-1 contacts per person
  9.8 / 8.0 / 4.8 in the edges against 5.3 / 4.2 / 3.4 in the file; the 13-group appendix data
  show the same kind of gap). The ABM writes age groups as contiguous id ranges, so the
  id-to-age mapping is correct and the reference file is simply defined differently. It
  does not affect forecasts, and the loader's warning says so.
- **Group file.** `daily_group_infected.csv` omits zero counts. The loader fills them in
  as zeros.

## 7. Appendix A: the library reproduces EpiInfer-contact up to a one-day horizon offset

The `Archive.zip` data (36 simulated epidemics: 12 (p1, p2) pairs at contact scales 0.2, 0.5
and 2, 13 age groups) is the data behind Appendix A. Two checks:

- **ARIMA reproduces on every cell.** All 720 cells (36 epidemics × 20 horizons) agree with the
  paper to a relative difference below 9e-4, which is statsmodels optimiser noise. The
  authors' own `arima_baseline/arima_predictions.csv` files give the same numbers.
- **EpiInfer-contact (both rates known, recorded contacts, 10 trajectories, seed 0)** agrees
  with the paper's column in two regimes:

| Horizon | Ratio ours ÷ paper | Share within ±15% |
|---|---|---|
| days 1–8 | median 1.00–1.05 per scale (10–90%: 0.85–1.22) | 79% (91% within ±25%) |
| days 9–19, compared with **our day h + 1** | median 1.03–1.05 per scale (10–90%: 0.93–1.12) | **96%** |
| days 9–19, compared with our day h (no shift) | median 1.14–1.16 | 47% |

  Within each of the 36 epidemics the paper's curve is ours **moved one day earlier** from
  about day 9. It is clearest for p2 = 0.2, where the paper jumps from 25.9 (day 8) to 48.0
  (day 9) and ours jumps from 25.5 (day 9) to 44.5 (day 10). Incubation and illness last
  exactly 7 days in the data (every A and I run in two of the supplied epidemics, one per
  generator, is 7 days long), and a different `inc` makes the fit worse (`inc` = 6: ratios
  of 0.3 to 2.7 for p2 = 0.2).

I could not identify the code change behind the offset. Forecasting from the day before the
origin reproduces days 7–20 (ratios 0.92–1.03 for p2 = 0.2) but spoils days 1–6 (1.1–1.4), and
adding one extra day of exposures at the origin overshoots (ratio 7 at day 7). The paper's
appendix therefore comes from a version of the forecasting loop that differs from the one in
`epiinfer_paper_aligned.py` by one day in when newly predicted infections turn symptomatic.
Without the look-ahead at future contacts (`--contacts frozen`) the late-horizon values fall
by about a quarter (day 20, p2 = 0.2: ratio 0.66 instead of 0.92), so the published appendix
also used the recorded graph (item 1).

The "Base" columns (the unscaled `abmcontact10000` data) and the columns for the older EpiInfer
cannot be checked: neither the Base data nor an implementation of the older EpiInfer was
supplied.

## Inconsistencies in the paper text (not edited)

- The population is given as 2,000 in one place and 10,000 in another.
- ARIMA is shown as "--" in Tables 5–8 but is given in the absolute-RMSE table.
- The prose says EpiInfer-contact beats every baseline at every horizon. Several table
  cells contradict this, as do the like-for-like ARIMA window in item 3 and the OpenABM
  results at days 10 and 20 against the previous method.
- Table 1's day-1 value of 7.92 matches none of the summary-table rows (8.50–8.77).
- `tab:openabm-forecast` still carries the note "need to compare with ARIMA".
- The uniform-contact table's EpiInfer-contact column (`tab:uniform`) cannot be checked: the
  uniform data supplied has no contact list. Freshly simulated uniform data gives day-1 errors
  of 10.4 against the paper's 74.3. Its ARIMA column does reproduce, on the `aprilnewage` data.

## Open items

- Implement the paper's reconstruction of the exposed set from infections (item 2), so
  that the method runs on data without the A state.
- The authors should confirm which dataset and code produced "Simulation 3" (item 4) and the
  appendix's one-day horizon offset (item 7), and say which statsmodels version produced the
  Holt-Winters column (item 5).
- Still missing from the files supplied: `uniform/timed_edges.csv` (the contact list of the
  uniform data), the unscaled `abmcontact10000` folders (the "Base" columns of Appendix A and
  Tables 9–12), and `openabm_run1`.
