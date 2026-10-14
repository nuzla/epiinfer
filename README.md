# epiinfer

Python implementation of **EpiInfer-CONTACT** ("Forecasting Infection Rates in Epidemics
Given Contact Tracing Information", *Algorithms*, 2025), packaged so that anyone can

1. **reproduce** the paper's tables, and
2. **forecast** with their own contact-tracing data.

Given who met whom each day and who is infected, EpiInfer rolls an S → A → I → R epidemic
forward on the recorded contact graph and averages Monte-Carlo trajectories to forecast the
number of symptomatic people, per age group and in total.

## Install

```bash
pip install "epiinfer[all]"          # numpy, pandas + matplotlib, statsmodels
# from a checkout:
pip install -e ".[dev]"
```

Docker (no Python needed):

```bash
docker build -f docker/Dockerfile -t epiinfer .
docker run --rm epiinfer --help
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/results:/work/results" \
    epiinfer reproduce --table openabm --data /data/openabm
```

## 60-second tour

```bash
epiinfer demo                                   # path to a tiny bundled dataset
epiinfer forecast --data "$(epiinfer demo)" --horizon 14 --inc 5 --duration 11
```

```python
import epiinfer
data = epiinfer.load_dataset("my_dataset/")
epiinfer.forecast(data, horizon=14, method="empirical_p1", inc=5, duration=11, seed=0)
epiinfer.run(data, "unknown_both").summary()     # rolling back-test: RMSE / fRMSE
```

Your data: three CSV files, see [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md).

## Reproduce the paper

| Paper table | Command | Data |
|---|---|---|
| `tab:openabm-forecast` | `epiinfer reproduce --table openabm --data DIR` | OpenABM run (archived) |
| `tab:age_structured` | `epiinfer reproduce --table age_structured --data DIR` | AgeMixABM, age-structured contacts |
| `tab:uniform` | `epiinfer reproduce --table uniform --data DIR` | AgeMixABM, uniform contacts |

Get the exact datasets with `epiinfer fetch-data --url … --sha256 …` (release assets), or
generate statistically equivalent ones with `epiinfer simulate`. Step-by-step, expected
runtimes and the measured agreement with the paper: [docs/REPRODUCING.md](docs/REPRODUCING.md).

**Status:** the OpenABM table reproduces to <0.2% and the age-structured *both known* row
to within 10%. The estimated-rate rows (p1 known, both unknown) do **not** match the paper;
see the report in `docs/REPRODUCING.md`.
What the paper leaves unspecified: [docs/PAPER_VS_CODE.md](docs/PAPER_VS_CODE.md).

## Methods

| `method` | What is estimated | Paper |
|---|---|---|
| `known_both` | nothing (true p1, p2 supplied via `Config`) | AgeMixABM tables |
| `known_p1` / `known_p2` | the other rate, by grid search | AgeMixABM tables |
| `unknown_both` | p1 and p2, by grid search (ContinuousCalibrate) | AgeMixABM tables |
| `empirical_p1` | p1 refit daily from observed S→A events; p2 = 1 | OpenABM table |

Baselines (`pip install epiinfer[baselines]`): `epiinfer baseline --data DIR --which arima`.

## Reproducibility

Every result is a function of `--seed`. Each (seed, origin day, trajectory) has an
independent random stream, so results are identical for any `--workers` value.

## Development

```bash
pytest -q                          # unit + golden tests against the original research scripts
python tools/mutation_check.py     # breaks 13 guards in a copy; every one must be caught
ruff check .
```

## Citation

See `CITATION.cff`. Please also cite OpenABM-Covid19 (Hinch et al.) if you use its data.
Licence: to be confirmed by the authors before release.
