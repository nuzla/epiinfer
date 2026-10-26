# Changelog

## 0.2.1

Fixes from a review of 0.2.0. Each has a regression test in `tests/test_robustness.py`, which
fails on the 0.2.0 code.

- **`forecast` on a dataset longer than 100 days forecast from day 100.** The `final` and
  `compartmental` engines applied the back-test limit `max_day` (100) to the data, so they
  silently ignored everything after it, and `--from-day 110` was refused. `forecast` now reads
  every day (and the contact engine already did). `run` still stops at `--max-day`, the paper's
  protocol; the help text, README and tutorial now say so.
- **`run` with `--start-eval` below 22** crashed with `TypeError: 'NoneType' object is not
  subscriptable` (`unknown_both`) or silently used the first grid value (`known_p1`,
  `known_p2`): there is no history to calibrate on. The final engine now refuses a first
  origin without enough history (22 days when a rate is searched, `inc` for `known_both`); so
  do the 2025 engine (`inc + duration`) and the compartmental one, whose earlier origins also
  indexed days from the end of the arrays.
- **The 2025 engine on data without pre-symptomatic records** (`--engine contact`, or
  `empirical_p1`, on real-world-style data) returned a flat, zero-width "forecast" in which
  nobody new gets infected (34 people tomorrow, where the default engine says 38). It now
  refuses such data and points to the default engine; `describe` already listed `contact` as
  unusable there.
- **Nothing to score.** A run whose data is too short returned an empty table (the 2025 engine
  raised `KeyError: 'group'`). `summary()` now always has its columns and `epiinfer run` says
  why nothing was scored.
- **`from-cases` lost an episode** when one person's rows were not sorted by onset: an earlier
  episode's recovered days overwrote a later episode's first symptomatic day. It now gives the
  same result in any row order, and rejects missing values.
- **Known rates given as one number** (`p1_true=0.15`) raised `'float' object is not
  iterable` in every engine; they are now accepted. `Config` and `FinalSettings` also reject
  impossible values (`recalib_every=0`, a calibration window shorter than the score horizon,
  rates outside (0, 1], a negative seed, an empty grid) instead of failing later.
- **Clear errors.** The CLI prints data and option errors as one `epiinfer: ...` line (`-v`
  keeps the traceback). Fixed bare `IndexError`, `ValueError` and `KeyError` from a simulation
  with more age groups than its contact matrix, an `individual_age_group.csv` id outside the
  population, a header-only contact list, a state file with no rows, `describe` on data in
  which nobody is symptomatic, `plot-rmse --metric frmse_rel` on a baseline summary, and a
  missing column in the compartmental engine's four files.
- **The sdist did not contain `docker/` or `.github/`**, so `tests/test_docker_files.py` failed
  when the suite was run from it, contrary to the comment in `pyproject.toml`. Both are
  included now, and CI runs the whole suite from the built sdist.
- **Tests.** Nothing pinned ARIMA(1,1,1) in CI (only the paper-data tests did), so a changed
  model order went unnoticed; `test_arima_matches_pinned_values` pins it. The mutation check
  now breaks 78 guards.
- **Docs.** `tests/test_docs.py` checks that relative links resolve, that every version string
  and image tag agrees, and that the tutorial page shows exactly the committed outputs.
  Corrected the README's "within 8%" (8.3%) and the `frmse` note in `PAPER_VS_CODE.md`; the
  example script now back-tests a whole dataset of any length.

## 0.2.0

The October 2026 version of the paper, the earlier EpiInfer, and a Docker tutorial.

- **New default engine, `final`.** A bit-exact port of the authors' `abm_final.ipynb`, the
  method behind the new Tables 10–13 (`epiinfer.final`). It rebuilds the pre-symptomatic
  history from infections, so it needs **no A state**: only who is symptomatic or recovered,
  plus the contacts. Recovered people become susceptible again after `rec_duration` days.
  Calibration is a joint grid search every 5 days, with damping. `FINAL` preset: 30
  trajectories, origins 25–79. The 2025 code stays available as `engine="contact"`.
- **New engine, `compartmental`.** EpiInfer, the earlier model the paper compares against
  (`epiinfer.compartmental`). It is deterministic and needs only daily counts per age group.
  It reproduces exactly:
  - Appendix A's EpiInfer column (720 cells);
  - Tables 2–5 / 14 "both known" (per-group exposure);
  - the authors' own `RMSE_summary*.xlsx`.
- **New `reproduce` targets:**
  - `--table sweep` (Tables 10–13, needs the Base data; the Base curves are stored to
    recognise it);
  - `--table epiinfer_age_structured`;
  - `--table appendix --methods epiinfer_old`;
  - `--offset 0|1` for the contact engine's contact-day timing.
- **Metrics.** `relative_rmse` and a `frmse_rel` column: the October paper's fRMSE (root
  mean squared relative error). `summarize_relative` recomputes the authors'
  `abm_summary.csv` exactly from `abm_predictions.csv`.
- **CLI and plots.**
  - `describe --data D [--plot]` prints population, days, peak, contacts and the usable
    engines.
  - `from-cases` (and `epiinfer.convert.cases_to_dataset`) builds a dataset folder from a
    case list and a contact list.
  - `forecast --plot`, `run --plots` (now with an RMSE-by-horizon chart), `plot-rmse` to
    compare methods, and `baseline --out`.
  - `--engine`, `--p1-true`/`--p2-true` and `--rec-duration` on `forecast` and `run`.
- **Tutorial.** `docs/TUTORIAL.md` walks through simulate → describe → forecast → back-test
  → compare in Docker, with the exact outputs and plots. `docs/tutorial/run_tutorial.sh`
  runs it, and a CI job runs it inside the image and checks the CSVs against the committed
  ones.
- **Findings** (`docs/PAPER_VS_CODE.md`, items 7–10):
  - the October method and its Tables 10–13;
  - three code variants tested against the Appendix;
  - the earlier EpiInfer's one-day-later forecasts and contact look-ahead;
  - the uniform tables' EpiInfer-contact column comes from a notebook that seeds forecasts
    with the susceptible people.
- `docs/DATA_FORMAT.md` documents what each engine needs.

## 0.1.0

First packaged version of the EpiInfer-CONTACT research code.

- Library `epiinfer` ported from `epiinfer_paper_aligned.py` and `epiinfer_empirical_p1.py`.
  Golden tests show it matches them exactly.
- Commands: `forecast`, `run`, `reproduce`, `baseline`, `simulate`, `fetch-data`, `demo`.
- **No look-ahead by default.** The original scripts used future recorded contacts.
  `contacts="recorded"` keeps that behaviour, for reproducing the published numbers.
- **Seeds.** Seeded random streams give the same results whatever `--workers` or `--jobs`
  is set to.
- **Baselines.** ARIMA(1,1,1) and Holt-Winters follow the authors' notebooks. ARIMA
  reproduces the paper exactly. Holt-Winters matches the notebook code to within 1e-4 (the optimiser differs slightly between platforms).
- **Reproduce checks.** Each `reproduce` run checks the dataset's identity and records it
  in `dataset_check`. Downloads are verified against SHA-256 hashes, and the archives are
  built deterministically.
- **Packaging.** Managed with uv; `uv.lock` pins every dependency. Python 3.11–3.14 are
  supported, and the minimum dependency versions are tested in CI.
- **Docker.** The image installs the locked versions and runs as a non-root user. Base
  images are pinned by digest. A tag-triggered workflow publishes a multi-architecture
  image to GHCR; Apptainer/Singularity instructions are in the README (untested).
- MIT licence.
- **Validated against the authors' own run.** `reproduce --table age_structured` reports the
  authors' 13 July run of the same script (`results_paper_aligned.csv`) next to the paper;
  the library matches it in all 16 cells within 8.3%. The published paper reports a different
  run ("Simulation 3" in the authors' July draft).
- **More of the paper's data.** `load_dataset(..., max_day=)` reads only what a forecast uses (the
  365-day, 800 MB contact lists of the `aprilnewage` data load in the same time as a 100-day
  one); `load_curve` and path-based baselines run on datasets without a contact list.
- **New `reproduce` targets**: `arima_uniform`, `hw_*` on the right dataset, and
  `--table appendix --scale {0.2,0.5,2}` for Appendix A (ARIMA exact on all 720 cells;
  EpiInfer-contact matches up to a one-day offset in the paper).
- Differences from the paper are documented in `docs/PAPER_VS_CODE.md`.
