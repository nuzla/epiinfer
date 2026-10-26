# Reproducing the paper

The paper's tables come from three different pieces of code. The library has an engine for
each, and `epiinfer reproduce` picks the right one for every table:

| Engine | Code it ports | Paper columns | How close |
|---|---|---|---|
| `final` (default for your own forecasts) | `abm_final.ipynb`, October 2026 | EpiInfer-contact in Tables 10–13 | the port is bit-exact against the notebook; the tables need the Base data, which was not supplied |
| `contact` | `epiinfer_paper_aligned.py`, `epiinfer_empirical_p1.py`, 2025 | EpiInfer-contact in Tables 2–9, 14–17 and Appendix A | OpenABM within 1%; the authors' own age-structured run within 8%; Appendix up to a one-day offset |
| `compartmental` | `epiinfer for base case.ipynb`, `Epiinfer for C_*.ipynb` | the "EpiInfer" columns (the earlier model) | Appendix A (720 cells) and Tables 2–5 / 14 "both known" exact |

ARIMA and Holt-Winters are separate baselines (`epiinfer baseline`). For why some published
numbers cannot be matched, see [`PAPER_VS_CODE.md`](PAPER_VS_CODE.md).

## 1. Get the data

The paper's datasets came as these archives (names as supplied; unzip each into its own empty
folder). Folder names below are the ones the commands and the paper-data tests expect:

| Archive | Contents | Folder to use |
|---|---|---|
| `EpiInfer_contacttracing_datasets-…zip` | the authors' scripts and notebooks, plus `openabm_run3.zip` | `openabm_run3` → `openabm` |
| `data-….zip` | `abmcontact10000aprilnewage/{age_structured, uniform}`: 365-day ABM runs. **`uniform/` has no `timed_edges.csv`** | `aprilnewage_age_structured`, `aprilnewage_uniform` |
| `Archive.zip` | `abmcontact10000april0.2`, `april0.5`, `april2`: 12 `p1_*_p2_*` scenarios each, 13 age groups, 100 days, contact list included; plus the authors' `RMSE_summary<scale>.xlsx` | `appendix_april0.2`, `appendix_april0.5`, `appendix_april2` |
| `abm_summary.csv`, `abm_predictions.csv` | the authors' outputs of `abm_final.ipynb` (Tables 10–13) | shipped in the package and the tests |
| (the earlier `epiinfer/` folder) | `dataset` (the 915-peak age-structured epidemic) and `new_data_set` (= `openabm_run3`) | `age_structured`, `openabm` |

Not among the files supplied: `uniform/timed_edges.csv`, the unscaled `abmcontact10000` folders
(Appendix A's "Base" columns and Tables 10–13) and `openabm_run1`.

For the paper-data tests put the folders side by side and point at them:

```bash
export EPIINFER_PAPER_DATA=/path/to/paperdata    # holds the folder names in the last column
uv run --all-extras pytest -m paper
```

**Exact datasets for others (recommended).** Archives for a GitHub Release:

```bash
uv run epiinfer fetch-data --url https://…/epiinfer-data-openabm.zip --dest data
```

- **Verification.** The download is checked against the SHA-256 recorded in
  `src/epiinfer/checksums.txt`, which ships with the package. A modified or corrupted
  archive is refused before it is unpacked.
- **Building the archives.** `tools/pack_datasets.py` builds the zips deterministically:
  re-packing the same data gives the same hash.
- **URL.** Set `EPIINFER_DATA_URL` instead of `--url` if you prefer an environment variable.
  Only the two archives listed in `checksums.txt` have recorded hashes so far.

**Regenerated data.** This is statistically equivalent but not byte-identical:

```bash
uv run epiinfer simulate --contact age_structured --out data/sim_age_structured
uv run epiinfer simulate --contact uniform        --out data/sim_uniform
```

The defaults (contact matrix × 0.2, seed 123) match the shipped age-structured dataset:

| Statistic | Regenerated | Shipped |
|---|---|---|
| Contacts per day | 34,187 | 33,976 |
| Symptomatic peak | 919 on day 19 | 915 on day 19 |
| Final S/A/I/R | 2141 / 6528 / 688 / 643 | 2069 / 6548 / 699 / 684 |

A single regenerated epidemic still gives different forecast errors. With both rates
known it gives 10.4 / 28.0 / 28.8 / 142.6, against the paper's 8.7 / 17.5 / 29.7 / 156.9.
Use the archived data to check the published numbers.

## 2. Run a table

```bash
uv sync --all-extras
uv run epiinfer reproduce --table openabm              --data data/openabm
uv run epiinfer reproduce --table age_structured       --data data/age_structured --jobs 4
uv run epiinfer reproduce --table arima_age_structured --data data/age_structured
uv run epiinfer reproduce --table arima_uniform        --data data/aprilnewage_uniform
uv run epiinfer reproduce --table hw_age_structured    --data data/aprilnewage_age_structured
uv run epiinfer reproduce --table appendix --scale 0.2 --data data/appendix_april0.2 --jobs 4
uv run epiinfer reproduce --table epiinfer_age_structured --data data/age_structured
uv run epiinfer reproduce --table sweep --data data/abmcontact10000 --jobs 12   # needs the Base data
```

Each `--table` run writes a CSV and prints a comparison. Its columns are `paper_rmse`, `rmse`,
`rmse_ratio`, `paper_frmse`, `frmse` and `n_origins`. Three tables work differently:

- **`--table appendix`** compares all 20 horizons for the 12 (p1, p2) pairs of one contact
  scale. `--methods` picks from `arima`, `contact` and `epiinfer_old` (default: all three).
- **`--table epiinfer_age_structured`** is the earlier EpiInfer's "both known" row of Tables
  2–5 and 14. It is deterministic, so it takes under a second.
- **`--table sweep`** re-runs Tables 10–13 (12 (p1, p2) pairs × 4 knowledge settings) with the
  final engine. `--data` is the folder of `p1_*_p2_*` folders.
  - It checks each folder against the paper's Base epidemics, using their symptomatic curves
    (stored in the package), and prints `MISMATCH` for anything else.
  - It writes `reproduce_sweep.csv` (paper vs ours), `sweep_predictions.csv` and
    `sweep_trace.csv` (the calibrated rates).

The CSV also has `dataset_check`, which identifies the data by population, number of days
(counting up to day 100) and peak symptomatic count:

| Data | Population | Days | Peak |
|---|---|---|---|
| Archived age-structured | 10,000 | 101 | 915 |
| `aprilnewage` age-structured | 10,000 | 101 | 1,044 |
| `aprilnewage` uniform | 10,000 | 101 | 1,012 |
| OpenABM | 10,000 | 100 | 2,704 |

A different dataset prints a **WARNING: MISMATCH** instead of quietly giving different
numbers. (Running `age_structured` on the `aprilnewage` data therefore warns, correctly.)

- **Contacts.** `--contacts recorded` is the default here. It uses each future day's
  recorded contacts, which is how the published numbers were made. `--contacts frozen`
  removes that look-ahead; see `PAPER_VS_CODE.md`, item 1.
- **Protocol.** Each table uses the protocol of the code that produced it:
  - contact engine: forecast origins 25–99;
  - final engine: origins 25–79, 30 trajectories;
  - earlier EpiInfer: origins 20–80, where an origin is the first projected day;
  - ARIMA: origins 10–50, matching the authors' ARIMA notebook.

  Horizons are 1, 5, 10 and 20 (all 20 days for the appendix).
- **Smoke test.** `--quick` runs a reduced evaluation only. Its numbers are not comparable
  with the paper.
- **Tests.** `EPIINFER_PAPER_DATA=data uv run --all-extras pytest -m paper` checks the
  reproducible rows automatically (10 tests, about 12 minutes on an Apple-silicon Mac).

Runtimes were measured on an Apple-silicon Mac, single-threaded per method:

| Table | Time |
|---|---|
| `openabm` | ~10 s |
| `arima_age_structured` | ~2 s |
| `age_structured` with `--jobs 1` | ~14 min (unknown_both ~9 min, known_p1 / known_p2 ~5 min, known_both <1 min) |
| `age_structured` with `--jobs 4` | ~7 min |

## 3. Results (seed 0, 10 trajectories)

Each cell is RMSE for the whole population, as **ours / paper (ratio)**.

### `tab:openabm-forecast`, `empirical_p1`

| Contacts | Day 1 | Day 5 | Day 10 | Day 20 |
|---|---|---|---|---|
| recorded | 133.6 / 132.7 (1.007) | 178.8 / 177.6 (1.007) | 418.1 / 414.2 (1.009) | 957.7 / 948.3 (1.010) |
| frozen | 133.6 (1.007) | 178.8 (1.007) | 427.3 (1.032) | 979.3 (1.033) |

This **reproduces**. The remaining ~1% comes from one change: the original code also
scored the day after the data ends (day 100) against an actual of 0. Including that target
gives ratios of 1.000–1.002.

### `tab:age_structured`

The table compares our RMSE with **two** references, because they disagree: the published
paper, and the authors' own 13 July run of the same script on the same data
(`results_paper_aligned.csv`, see `PAPER_VS_CODE.md`, item 4). Ratios are ours ÷ reference
(recorded contacts, seed 0):

| Mode (paper label) | Horizon | Ours | Authors' run | Ratio | Paper | Ratio |
|---|---|---|---|---|---|---|
| both known | 1 / 5 / 10 / 20 | 8.78 / 17.87 / 32.57 / 158.0 | 8.92 / 17.25 / 30.08 / 158.1 | 0.98 / 1.04 / 1.08 / 1.00 | 8.72 / 17.49 / 29.71 / 156.9 | 1.01 / 1.02 / 1.10 / 1.01 |
| p1 known (`known_p1`) | 1 / 5 / 10 / 20 | 13.61 / 52.23 / 48.24 / 125.7 | 13.24 / 50.69 / 47.99 / 124.4 | 1.03 / 1.03 / 1.01 / 1.01 | 8.05 / 17.28 / 29.35 / 157.8 | 1.69 / 3.02 / 1.64 / 0.80 |
| p2 known (`known_p2`) | 1 / 5 / 10 / 20 | 8.78 / 17.60 / 20.36 / 125.7 | 8.92 / 18.89 / 20.91 / 125.3 | 0.98 / 0.93 / 0.97 / 1.00 | 8.77 / 18.18 / 29.98 / 158.6 | 1.00 / 0.97 / 0.68 / 0.79 |
| both unknown | 1 / 5 / 10 / 20 | 10.67 / 31.29 / 44.21 / 108.1 | 10.24 / 33.69 / 45.92 / 109.0 | 1.04 / 0.93 / 0.96 / 0.99 | 8.50 / 17.79 / 29.65 / 156.5 | 1.25 / 1.76 / 1.49 / 0.69 |

- **The library reproduces the authors' own run in all 16 cells**, within 8.3%. That is
  about the seed-to-seed noise of 5% (seeds 0, 1 and 2 on `known_p1` and `unknown_both`
  agree within 5%).
- **The published paper agrees only for "both known"** (within 10%).
- **The cause is the paper, not the port.** The authors' July draft shows the published
  EpiInfer-contact numbers are a third run, "Simulation 3", which is not this script's run on
  this data. See `PAPER_VS_CODE.md`, item 4.
- **Without look-ahead (`--contacts frozen`)** the picture changes mostly at day 20. For
  example, "both known" gives 126.3 against 158.0, and "both unknown" gives 82.7 against 108.1.

`EPIINFER_PAPER_DATA=data uv run --all-extras pytest -m paper` re-checks all 16 cells against
the authors' run.

### ARIMA(1,1,1) (`tab:baseline-abs`)

| Data, window | Day 1 | Day 5 | Day 10 | Day 20 |
|---|---|---|---|---|
| 915-peak age-structured, origins 10–50: ours / paper | 30.12 / 30.12 | 279.61 / 279.61 | 474.92 / 474.93 | 833.68 / 833.68 |
| `aprilnewage` uniform, origins 10–50: ours / paper | 149.53 / 149.53 | 501.66 / 501.66 | 730.34 / 730.34 | 984.59 / 984.59 |
| 915-peak age-structured, origins 25–99 (EpiInfer's window) | 20.0 | 85.4 | 97.7 | 111.8 |

Both published ARIMA columns **reproduce exactly**, but each on a different dataset and only on
the authors' own window. On the `aprilnewage` age-structured data the age-structured ARIMA column does
not reproduce (136.8 / 328.8 / 360.5 / 408.9). See `PAPER_VS_CODE.md`, items 3 and 5.

### Holt-Winters (`hw_age_structured`, `hw_uniform`) on the `aprilnewage` data

The library's Holt-Winters is the authors' own notebook code: additive damped trend, a
14-day trailing window, origins 25–99, targets up to day 119, and forecasts clipped at 0. It
gives the same RMSE as that code on the demo data to within 1e-4 relative
(`tests/test_golden.py`).

| Data | | Day 1 | Day 5 | Day 10 | Day 20 |
|---|---|---|---|---|---|
| age-structured (peak 1,044) | ours | 84.0 | 130.7 | 167.5 | 211.1 |
| | paper | 83.4 | 140.7 | 179.1 | 261.0 |
| uniform (peak 1,012) | ours | 89.3 | 136.8 | 174.4 | 228.8 |
| | paper | 90.5 | 139.4 | 178.0 | 260.4 |

Only **approximately** reproduced: day 1 within 1.5%, day 20 off by 12–19%. The statsmodels fit
is sensitive to the version, and the notebook silently switches to a hand-written Holt model if
the fit raises; I could not pin the original versions (`PAPER_VS_CODE.md`, item 5).

### Appendix A (`--table appendix`), EpiInfer-contact and ARIMA

Run on the 36 epidemics of `Archive.zip` (contact scales 0.2, 0.5, 2; 12 (p1, p2) pairs each;
both rates known; recorded contacts; 10 trajectories, seed 0; 720 cells per method).

| | ARIMA | EpiInfer-contact days 1–8 | days 9–19, vs our day h + 1 |
|---|---|---|---|
| scale 0.2 | exact (rel. diff ≤ 8e-5) | median 1.00 | median 1.03 |
| scale 0.5 | exact (≤ 2e-5) | median 1.03 | median 1.05 |
| scale 2 | exact (≤ 9e-4) | median 1.05 | median 1.04 |
| share within ±15% | 100% | 79% | 96% (47% without the shift) |

ARIMA is exact. EpiInfer-contact matches the paper's curve once the paper's days 9 and later
are aligned with the library's day h + 1: the paper's curve runs one day ahead of the library
from about day 9 (`PAPER_VS_CODE.md`, item 7). Run time with `--jobs 4`: about 1 minute per
epidemic at scale 0.2, 2 at scale 0.5, and 4–9 at scale 2.

### The earlier EpiInfer (`compartmental` engine)

The model is deterministic, so these reproduce exactly:

| Result | Command | Agreement |
|---|---|---|
| Appendix A, EpiInfer column | `--table appendix --methods epiinfer_old` (per scale) | 720 of 720 cells to the printed 3 decimals (max difference 0.00052, two truncated cells) |
| Tables 2–5 / 14, EpiInfer "both known" | `--table epiinfer_age_structured` | 180.1720 / 408.3458 / 161.6292 / 95.9607 and fractions 0.2621 / 0.5974 / 0.2427 / 0.1432, all exact |
| the authors' `RMSE_summary<scale>.xlsx` (four settings, day 20) | paper-data test | 132 of 132 rows, including the chosen rates |

The run-time is under a second per epidemic. Table 14's calibrated rows and the uniform
column are not reproduced (`PAPER_VS_CODE.md`, item 9).

### Tables 10–13 (October 2026): the final engine

These come from `abm_final.ipynb`, which the `final` engine ports bit for bit
(`tests/test_final_engine.py` runs the notebook's own code on the demo data).

- **The authors' outputs are included.** `summarize_relative` recomputes their
  `abm_summary.csv`, which is the 192 EpiInfer-contact cells of Tables 10–13, **exactly** from
  their per-forecast `abm_predictions.csv`. That confirms the new fRMSE definition (root mean
  squared relative error over days with a non-zero count).
- **Re-running needs the Base data** (`abmcontact10000/p1_*_p2_*`), which was not supplied.
  `--table sweep` is ready for it.
- **On the scaled Appendix data the final engine is a different method.** With both rates
  known it is within 15% of the Appendix column in only 11% of cells (`PAPER_VS_CODE.md`,
  item 7), which is how we know the Appendix was made with the 2025 code.

### `tab:age_structured` on the `aprilnewage` data, for comparison

On the 1,044-peak data the library's "both known" run gives 12.5 / 27.3 / 46.5 / 138.3 against the
paper's 8.7 / 17.5 / 29.7 / 156.9, so the paper's EpiInfer-contact rows do **not** come from that
epidemic (they do come from the 915-peak one, above). The warning `MISMATCH` marks this case.

### Not checked

- **`tab:uniform`'s EpiInfer-contact column.** The uniform data supplied has no
  `timed_edges.csv`. The notebook that produced the column has been identified, and it seeds
  its forecasts with the susceptible people (`PAPER_VS_CODE.md`, item 10).
- **LSTM.** Not implemented. The authors' Keras model is trained without a seed, and it
  also used the `aprilnewage` data.
- **Appendix A "Base" columns and Tables 10–13.** They need the unscaled `abmcontact10000`
  folders, which were not supplied.

## 4. Your own predictions

Start with [`TUTORIAL.md`](TUTORIAL.md), a step-by-step Docker walk-through with the exact
outputs and plots. See also `README.md` and `docs/DATA_FORMAT.md`.
`examples/forecast_new_data.py` is a runnable template.
