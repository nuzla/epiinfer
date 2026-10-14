# Reproducing the paper

## 1. Get the data

**Exact datasets** (recommended): the archived zips from the project's GitHub Release.

```bash
epiinfer fetch-data --url https://…/epiinfer-data-openabm.zip --sha256 <hash> --dest data
```

`tools/pack_datasets.py` builds these zips and `checksums.txt` from dataset folders.
The URL is deliberately not hard-coded (set `EPIINFER_DATA_URL` instead if you prefer).

**Regenerate** statistically equivalent AgeMixABM data (not byte-identical, see
`PAPER_VS_CODE.md`):

```bash
epiinfer simulate --contact age_structured --out data/age_structured
epiinfer simulate --contact uniform        --out data/uniform
```

## 2. Run a table

```bash
epiinfer reproduce --table openabm        --data data/openabm
epiinfer reproduce --table age_structured --data data/age_structured --workers 4
epiinfer reproduce --table uniform        --data data/uniform
```

Output: a CSV and a printed comparison (`paper_rmse`, `rmse`, `rmse_ratio`, `paper_frmse`,
`frmse`). `--quick` is a smoke test only. Evaluation origins are days 25–99 (the paper's
protocol); horizons 1, 5, 10, 20.

## 3. What to expect

Measured with this library (seed 0, the shipped paper datasets, 10 trajectories, origins
25-99). Ratio = ours / paper RMSE.

| Table / mode | Day 1 | Day 5 | Day 10 | Day 20 | Verdict |
|---|---|---|---|---|---|
| `tab:openabm-forecast` (`empirical_p1`, ALL) | 1.000 | 1.000 | 1.002 | 1.001 | **reproduces** (<0.2%) |
| `tab:age_structured`, both known | 1.01 | 1.02 | 1.10 | 1.01 | **reproduces** (within 10%) |
| `tab:age_structured`, p2 known (`known_p2`) | 1.00 | 0.97 | 0.68 | 0.79 | partial |
| `tab:age_structured`, p1 known (`known_p1`) | 1.69 | 3.02 | 1.64 | 0.80 | **does not reproduce** |
| `tab:age_structured`, both unknown | 1.26 | 1.76 | 1.49 | 0.69 | **does not reproduce** |

Run-to-run noise is small: three seeds (0, 1, 2) of `known_p1` and `unknown_both` agree
within about 5% of each other (e.g. `unknown_both`, day 5: 31.3 / 31.6 / 32.7 vs paper 17.8).
So the gap in the estimated-rate modes is **systematic, not Monte-Carlo noise**: those
rows of the paper were most likely produced by an earlier calibration (the superseded
`epiinfer_age_structured.py` family initialised the rates at the truth and scored one day
ahead), not by the current `epiinfer_paper_aligned.py` logic that this library ports. The
library keeps the current code because its docstring documents why the older scoring cannot
identify p1. If you need the paper's exact estimated-rate rows, treat them as unreproduced
until the authors confirm which configuration generated them. `tab:uniform` has not been
run: the uniform-contact dataset is not among the files supplied.

## 4. Your own predictions

See `README.md` and `docs/DATA_FORMAT.md`; `examples/forecast_new_data.py` is a runnable
template.
