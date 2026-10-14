# Reproducing the paper

## 1. Get the data

**Exact datasets (recommended).** Download the archived zips from the project's GitHub
Release:

```bash
epiinfer fetch-data --url https://…/epiinfer-data-openabm.zip --sha256 <hash> --dest data
```

`tools/pack_datasets.py` builds these zips and their `checksums.txt` from the dataset
folders. The URL is not hard-coded; set `EPIINFER_DATA_URL` if you prefer an environment
variable. The folders used below are:

- `age_structured`: AgeMixABM with age-structured contacts, 10,000 people, days 0–100.
- `openabm`: OpenABM-Covid19, 10,000 people, days 0–99.

**Regenerated data.** This is statistically equivalent but not byte-identical:

```bash
epiinfer simulate --contact age_structured --out data/sim_age_structured
epiinfer simulate --contact uniform        --out data/sim_uniform
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
epiinfer reproduce --table openabm              --data data/openabm
epiinfer reproduce --table age_structured       --data data/age_structured --jobs 4
epiinfer reproduce --table arima_age_structured --data data/age_structured
```

Each run writes a CSV and prints a comparison. Its columns are `paper_rmse`, `rmse`,
`rmse_ratio`, `paper_frmse`, `frmse` and `n_origins`.

- **Contacts.** `--contacts recorded` is the default here. It uses each future day's
  recorded contacts, which is how the published numbers were made. `--contacts frozen`
  removes that look-ahead; see `PAPER_VS_CODE.md`, item 1.
- **Protocol.** Forecast origins are days 25–99 and horizons are 1, 5, 10 and 20. The
  ARIMA table uses origins 10–50, matching the authors' ARIMA notebook.
- **Smoke test.** `--quick` runs a reduced evaluation only. Its numbers are not comparable
  with the paper.
- **Tests.** `EPIINFER_PAPER_DATA=data pytest -m paper` checks the reproducible rows
  automatically, in about one minute.

Runtimes were measured on an Apple-silicon Mac, single-threaded per method:

| Table | Time |
|---|---|
| `openabm` | ~10 s |
| `arima_age_structured` | ~2 s |
| `age_structured` with `--jobs 1` | ~14 min (unknown_both ~9 min, known_p1 / known_p2 ~5 min, known_both <1 min) |
| `age_structured` with `--jobs 4` | ~7 min |

## 3. Results (seed 0, 10 trajectories, archived data)

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

| Mode (paper label) | Contacts | Day 1 | Day 5 | Day 10 | Day 20 |
|---|---|---|---|---|---|
| both known | recorded | 8.78 / 8.72 (1.01) | 17.87 / 17.49 (1.02) | 32.57 / 29.71 (1.10) | 158.0 / 156.9 (1.01) |
| both known | frozen | 8.78 (1.01) | 18.18 (1.04) | 30.40 (1.02) | 126.3 (0.80) |
| p1 known (`known_p1`) | recorded | 13.61 / 8.05 (1.69) | 52.23 / 17.28 (3.02) | 48.24 / 29.35 (1.64) | 125.7 / 157.8 (0.80) |
| p2 known (`known_p2`) | recorded | 8.78 / 8.77 (1.00) | 17.60 / 18.18 (0.97) | 20.36 / 29.98 (0.68) | 125.7 / 158.6 (0.79) |
| both unknown | recorded | 10.67 / 8.50 (1.25) | 31.29 / 17.79 (1.76) | 44.21 / 29.65 (1.49) | 108.1 / 156.5 (0.69) |
| both unknown | frozen | 10.67 (1.25) | 32.48 (1.83) | 47.13 (1.59) | 82.7 (0.53) |

- **Both known reproduces.** Every other mode differs systematically.
- **Not noise.** Seeds 0, 1 and 2 agree within about 5%; for `unknown_both` at day 5 they
  give 31.3 / 31.6 / 32.7.
- **Not the older script.** The July 2026 version of the research script does not
  reproduce these rows either.

See `PAPER_VS_CODE.md`, item 4.

### ARIMA(1,1,1), age-structured (`tab:baseline-abs`)

| Window | Day 1 | Day 5 | Day 10 | Day 20 |
|---|---|---|---|---|
| origins 10–50 (paper's) | 30.12 / 30.12 | 279.61 / 279.61 | 474.92 / 474.93 | 833.68 / 833.68 |
| origins 25–99 (EpiInfer's) | 20.0 | 85.4 | 97.7 | 111.8 |

The paper's column **reproduces exactly**, but only on its own window. See
`PAPER_VS_CODE.md`, item 3.

### Not checked

- **`tab:uniform`.** The uniform-contact dataset was not supplied.
- **Holt-Winters.** The settings are unknown, and the standard damped-trend model gives
  different numbers.
- **LSTM.** Not implemented.
- **Parameter-sweep tables 9–12 and Appendix A.** Their datasets were not supplied.
  `epiinfer simulate --p1 … --p2 …` can generate equivalents.

## 4. Your own predictions

See `README.md` and `docs/DATA_FORMAT.md`. `examples/forecast_new_data.py` is a runnable
template.
