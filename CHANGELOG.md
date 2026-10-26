# Changelog

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
