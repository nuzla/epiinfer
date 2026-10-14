# Changelog

## 0.1.0 (unreleased)

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
- Differences from the paper are documented in `docs/PAPER_VS_CODE.md`.
