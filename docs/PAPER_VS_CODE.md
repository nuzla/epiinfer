# Paper vs. code

These notes come from porting the research code into this library and re-running it against
the paper. Three code versions are covered:

- **The 2025 scripts** (`epiinfer_paper_aligned.py`, `epiinfer_empirical_p1.py`), which are
  the library's `contact` engine. They produced most EpiInfer-contact tables.
- **The October 2026 notebook** (`abm_final.ipynb`), the library's `final` engine and its
  default. It produced the new Tables 10–13.
- **The earlier EpiInfer notebooks** (`epiinfer for base case.ipynb`,
  `Epiinfer for C_<scale>.ipynb`), the library's `compartmental` engine. They produced the
  "EpiInfer" columns the paper compares against (item 9).

The paper versions compared are the 2025 *Algorithms* proof source and the 25 October 2026
PDF. Items 1–5 and 7–10 change how the published numbers should be read.

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

**Consequence for real data.** Real contact-tracing data rarely say who is infected but
not yet symptomatic, so the contact engine needs state 1 (A) in `individual_day_state.csv`.

**Addressed by the October 2026 method (item 8).** `abm_final.ipynb` implements the paper's
reconstruction and never reads A. The library's `final` engine is a bit-exact port of it and
is the default, so forecasting now needs only who is symptomatic or recovered each day, plus
the contacts.

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
  EpiInfer (180.17 …, reproduced exactly in item 9). So the paper's EpiInfer-contact rows
  are a third run.
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
  has 29.7 / 156.5 and 30.0 / 158.6. The 18 August script's own default data is the
  `aprilnewage` data; run there (after renaming its `avg_contacts` column to `c`, which the
  script requires, so it cannot have read this file as supplied) it gives 11.8 / 26.7 / 47.9 /
  139.0 for `known_both` and 12.7 / 39.8 / 116 / 241 for `unknown_both`: not Simulation 3 either.
- **Nor is it either newer variant tested here.** On the archived 915-peak data:
  - The October 2026 method (`final` engine, `unknown_both`) gives 20.8 / 31.8 / 23.9 / 62.4,
    against Simulation 3's 8.50 / 17.79 / 29.65 / 156.49.
  - The 2025 code with contacts aligned to the infection day (`contact_offset=1`, see item 7)
    gives 13.6 / 73.6 / 65.6 / 128.8 for "p1 known".
- **Nor is it the `AgeBased (1).ipynb` forecaster** that produced the uniform column
  (item 10). Its code, run unchanged on the archived 915-peak data, gives 14.35 / 31.03 /
  35.22 / 157.82 for "both known". (On the `aprilnewage` data it reproduces its own saved
  output within Monte-Carlo noise: 67.75 against 69.61 at day 1.)
- **Simulation 3's uniform row** (day-1 error 74.3) is item 10's notebook run.

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

The library reports RMSE / mean(actual) as `frmse` and, in the engines' summaries, the notebook's
definition as `frmse_rel` (the October 2026 paper adopts it for Tables 10–13; the baselines
report `frmse` only). `reproduce` checks each dataset's identity (people, days, peak), so mixing
datasets now prints a warning.

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
| days 1–8 | median 1.00–1.05 per scale (10–90%: 0.89–1.19) | 79% (91% within ±25%) |
| days 9–19, compared with **our day h + 1** | median 0.95–0.97 per scale (10–90%: 0.91–1.06) | **96%** |
| days 9–19, compared with our day h (no shift) | median 0.86–0.88 (10–90%: 0.76–0.97) | 61% |

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

**Three code variants tested against all 720 cells** (36 epidemics × 20 horizons, both rates
known, 10–30 trajectories):

| Variant | Share within ±15% | Median ratio ours ÷ paper per scale, days 1–8 / 13–20 |
|---|---|---|
| 2025 code as written (`contact_offset=0`, the library's default) | 70%; 96% of days 9–19 after the one-day shift | 1.00–1.05 / 0.87–0.89 |
| 2025 code with day-t contacts infecting on day t (`contact_offset=1`, the simulator's timing) | 61%: 85% at scale 0.2, 55% at 0.5, 42% at 2 | 1.00–1.04 / 1.05–1.28 |
| The October 2026 method (`final` engine) | 11% (10–13% per scale) | 1.5–1.9 / 0.35–0.51 |

Adding "recovered people become susceptible again", one of the October method's changes,
to the 2025 code makes the fit much worse. On the clearest epidemic (p1 = 0.12, p2 = 0.2,
scale 0.2) the ratios fall to 0.19–0.29 from day 10, against 0.54–0.92 without it.

The appendix was therefore made with the 2025 code family, not the October method. Its
remaining one-day offset is best described by the shift; aligning contacts to the infection
day fixes it only at the smallest contact scale.

`reproduce --table appendix --offset 0|1` runs either timing. The appendix's EpiInfer
column reproduces exactly (item 9). The "Base" columns cannot be checked: they need the
unscaled `abmcontact10000` data, which was not supplied.

## 8. The October 2026 version: a new method and new Tables 10–13

The 25 October 2026 PDF keeps every earlier table and the Appendix unchanged (Tables 2–9,
14–17 and A1–A20). It regenerates the EpiInfer and EpiInfer-contact columns of the
parameter-sweep Tables 10–13 with a new method, `abm_final.ipynb`.

**Tables 10–13 equal the authors' `abm_summary.csv` in all 192 cells.** That is 12 (p1, p2)
pairs × 4 knowledge cases × days 1/5/10/20, RMSE and fRMSE. The library's
`summarize_relative` recomputes that file **exactly** from the authors' `abm_predictions.csv`
(`tests/test_final_engine.py`).

**The method changed in seven ways** (`epiinfer.final`):

| | 2025 code (`contact` engine) | October 2026 (`final` engine) |
|---|---|---|
| Pre-symptomatic history | read from the simulator (oracle) | rebuilt from infections: cohort e = people first symptomatic on e + 7, plus n/p2 − n unseen exposures drawn by contacts from people free that day |
| Recovered people | immune for the rest of the run | susceptible again after 7 days (SEIRS, as in the simulator) |
| Contacts used | day d's for exposures on d + 1; future days' recorded graphs | day t's for exposures on t while rolling over observed days; day o's for every day after origin o |
| Calibration | every day; per age group; 20-day projection; smoothing 0.5 from a 0.1 prior | every 5 origins; one (p1, p2) for everyone; 7-day forecasts from the last 14 days' origins; joint 11 × 11 grid for "both unknown"; λ = 1 damping from the grid best |
| Trajectories | 10 | 30 |
| Forecast origins | 25–99 | 25–79 |
| fRMSE | RMSE / mean(actual) | root mean squared **relative** error over targets with actual > 0 |

The joint grid usually finds the true p2, so "p2 known" and "both unknown" are identical in
almost every cell. "p1 known" also equals "both known" except at p2 = 0.2. This is the same
pattern as the earlier "Simulation 3" rows (item 4), but running the new method on that data
does not reproduce them.

**Checks possible with the files supplied:**

- **The port is exact.** The library's `final` engine reproduces the notebook's own code bit
  for bit: reconstruction, nowcast, Monte-Carlo, calibration, damping and the whole rolling
  run (`tools/make_golden_final.py`, run on the demo data).
- **The tables themselves need the Base data.** They were computed on the unscaled "Base"
  data (`abmcontact10000/p1_*_p2_*`), which was not supplied.
  - `reproduce --table sweep` re-runs them when given that folder. It recognises the Base
    data by its symptomatic curves, which the package stores from the authors' predictions
    file, and warns `MISMATCH` otherwise.
  - On the Appendix's scaled epidemics the new method runs (item 7) but is a different
    method from the one in the Appendix.

**Other observations on the October version:**

- **ARIMA column of Tables 10–13.** For p1 = 0.15 it is copied from the appendix's
  contact-scale-0.2 column; for every other p1, from the scale-2 column. The columns are
  not from one dataset, and the "40 of 48" claim in the introduction depends on it.
- **Overclaims.** The introduction and conclusions now say EpiInfer-contact beats EpiInfer
  "in every setting at every horizon". Tables 5, 9 and 16 at day 20 still show EpiInfer
  ahead.
- **Two fRMSE definitions in one paper.** Tables 2–9 and 14–16 keep the old definition,
  while Tables 10–13 use the new one. Section 6.5.1 still defines the old one and quotes 10
  trajectories, not 30.
- **Three forecast windows stated.** Table 10's caption says origins 25–79, section 6.5
  says 25–100, and the notes give other days.
- **Calibration text vs notebook.** λ = 1 matches the notebook. The new text drops the
  earlier λ-sensitivity claim (0.005–0.05).



## 9. The "EpiInfer" columns: the earlier compartmental model

The paper compares EpiInfer-contact with EpiInfer, the authors' earlier compartmental model.
Its code is in the datasets archive: `epiinfer for base case.ipynb` and the three identical
`Epiinfer for C_<scale>.ipynb`. The library's `compartmental` engine is a port of it.

**It is deterministic, and three published or saved results reproduce exactly:**

| Result | Code | Agreement |
|---|---|---|
| Appendix A, EpiInfer column (both known, 36 epidemics × 20 horizons) | base case: contacts averaged over the previous 5 days, origins 20–80 | **all 720 cells** to the printed 3 decimals; two cells are truncated rather than rounded (difference ≤ 0.00052) |
| `RMSE_summary<scale>.xlsx` in `Archive.zip` (four knowledge settings, day 20) | C notebooks: same-day contacts, 15 × 10 grid fitted to the last 5 days | **all 132 rows**, including the chosen rates |
| Tables 2–5 and 14, EpiInfer "both known" (180.1720 / 408.3458 / 161.6292 / 95.9607) | a per-group variant (below), same-day contacts, origins 20–80, archived 915-peak data | **exact** to the printed 4 decimals, RMSE and fraction |

The commands are `reproduce --table appendix --methods epiinfer_old` and
`reproduce --table epiinfer_age_structured`.

**The per-group variant was identified by matching, not from code.** The notebooks pool all
groups into one exposure chance and take one (p1, p2). The age-specific tables use one rate
pair per group, so a different version was used. Computing each group's exposure chance from
that group's own symptomatic people reproduces the "both known" row exactly. The library
offers it as `exposure="per_group"`, for "both known" only.

**Not reproduced:**

- **Table 14's calibrated rows** ("p1 known", "p2 known", "both unknown"). The supplied grid
  search does not give them. The closest variant tried (each group's rate fitted to that
  group's counts) is within 1% for "p2 known", 0.003% at day 1 for "both unknown", and far
  off elsewhere.
- **The uniform tables' EpiInfer column** (Tables 6–9 and 15: 230.142 / 453.189 / 108.053 /
  131.096 for "both known"). Day 1 is reproduced exactly on the `aprilnewage` uniform data,
  which identifies the dataset. Day 5 is within 0.01% (453.161), but days 10 and 20 are 4% and
  24% off (103.5, 162.8), so the variant is unknown.
- **Tables 10–13's EpiInfer columns** need the Base data, which was not supplied.

**How the code differs from what the paper describes:**

- **One day less information.** A notebook "origin" o is the first projected day, so its
  "day h" forecast is made h + 1 days after the last observation. EpiInfer-contact's day-h
  forecast is h days after. The EpiInfer columns therefore face a harder task by one day. The
  library's `run`/`forecast` use the same convention as the other engines (origin = last
  observed day); `reproduce` keeps the notebooks' convention.
- **Different forecast origins.** EpiInfer uses origins 20–80; EpiInfer-contact uses 25–99
  (2025) or 25–79 (October 2026).
- **Look-ahead at contacts.** Each projected day uses that day's recorded average contacts,
  which lie after the forecast origin. The library's `run` and `forecast` hold them at the
  last observed day instead (`--contacts frozen`, the default).
- **Current cases used as new cases.** The observed history comes from
  `daily_group_infected.csv`, which holds the number of people symptomatic each day. The
  model treats it as the number newly symptomatic.

**Housekeeping in the notebooks:**

- The base-case notebook's only cell is not runnable as saved. It holds a truncated copy of
  the code (a SyntaxError) followed by the complete code. Only the complete copy runs.
- The C notebooks always save to `RMSE_summary0.5.xlsx`, so the scale-2 file was renamed by
  hand.
- The scale-0.2 file comes from an older version: three settings, no fraction.

## 10. The uniform tables' EpiInfer-contact column comes from another notebook

Tables 6–9 (uniform contacts) print 74.32 / 132.09 / 84.07 / 144.40 for "both known", and so
on for all 16 cells. These are **exactly** the saved output of cell 18 of
`AgeBased (1).ipynb`, run on `abmcontact10000aprilnewage/uniform`. That notebook is a
different contact-network forecaster from the 2025 script:

- 5 Monte-Carlo runs;
- recalibration every 5 days over a 14-day window;
- grids of 0.01–0.30 in steps of 0.01;
- the recorded contacts of every future day;
- no seed for the trajectories.

**It seeds its forecasts with the wrong compartment.** Its loader takes state 0 as the
"exposed" (pre-symptomatic) set:

```python
'exposed': set(d[d['state'] == 0]['id'])
```

In every dataset supplied, state 0 is **susceptible** and state 1 is pre-symptomatic (A). The
published uniform EpiInfer-contact column was therefore produced by a model that treats the
people who have not been infected as the infectious ones.

The run cannot be repeated, because the uniform data supplied has no contact list. Its
age-structured run (cell 20) is not "Simulation 3" (item 4).

## Inconsistencies in the paper text (not edited)

- The population is given as 2,000 in one place and 10,000 in another.
- ARIMA is shown as "--" in Tables 5–8 but is given in the absolute-RMSE table.
- The prose says EpiInfer-contact beats every baseline at every horizon. Several table
  cells contradict this, as do the like-for-like ARIMA window in item 3 and the OpenABM
  results at days 10 and 20 against the previous method.
- Table 1's day-1 value of 7.92 matches none of the summary-table rows (8.50–8.77).
- `tab:openabm-forecast` still carries the note "need to compare with ARIMA".
- **October 2026 PDF:**
  - Meeting notes and red review comments are still in the text.
  - Cross-references are broken ("Table ??", stale table and figure numbers).
  - A2's caption says p2 = 0.15 (it is 0.10); A12's EpiInfer "Base" column duplicates A11.
  - A13–A20 captions give no contact scale.
  - Duplicate references (Munday [24]/[30], two [43]) and a duplicated Conflicts of
    Interest section.
  - Table 2 (age-specific, day 1: 7.92) still disagrees with Table 14 (8.72).
- The uniform-contact table's EpiInfer-contact column (`tab:uniform`) cannot be re-run: the
  uniform data supplied has no contact list. Item 10 identifies the notebook that produced it.
  Its ARIMA column does reproduce, on the `aprilnewage` data.

## Open items

- The authors should confirm five things:
  - which dataset and code produced "Simulation 3" (item 4);
  - the appendix's one-day horizon offset (item 7);
  - which statsmodels version produced the Holt-Winters column (item 5);
  - the code behind the EpiInfer columns not reproduced in item 9;
  - whether the uniform column (item 10) should be re-run with state 1 as the exposed set.
- Still missing from the files supplied:
  - `uniform/timed_edges.csv`, the contact list of the uniform data;
  - the unscaled `abmcontact10000` folders, needed for Tables 10–13 and Appendix A's "Base"
    columns;
  - `openabm_run1`.
