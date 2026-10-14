# epiinfer

Python implementation of **EpiInfer-CONTACT** ("Forecasting Infection Rates in Epidemics
Given Contact Tracing Information", Kascelan, Yang & Shasha, *Algorithms*, 2025). It is
packaged so that anyone can:

1. **reproduce** the paper's tables, and
2. **forecast** with their own contact-tracing data.

Given who met whom each day, EpiInfer rolls an S → A → I → R epidemic forward on the
contact graph. Here A means infectious but not yet symptomatic, and I means symptomatic
and isolated. It averages Monte-Carlo trajectories to forecast the number of symptomatic
people, per age group and in total.

## Install

The package is not on PyPI yet, so install it from a checkout:

```bash
pip install -e ".[all]"        # numpy, pandas + matplotlib (plots), statsmodels (baselines)
pip install -e ".[dev]"        # + pytest, ruff, build
```

It is tested on Python 3.10–3.14, and with the minimum versions numpy 1.24 and pandas 2.0.

Docker needs no Python on the host:

```bash
docker build -f docker/Dockerfile -t epiinfer .
docker run --rm epiinfer --help
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PWD/data:/data:ro" -v "$PWD/results:/work/results" \
    epiinfer reproduce --table openabm --data /data/openabm
```

## 60-second tour

```bash
epiinfer demo                                          # path to a tiny bundled dataset
epiinfer forecast --data "$(epiinfer demo)" --horizon 14
epiinfer run --data "$(epiinfer demo)" --method unknown_both --start-eval 30 --plots
```

```python
import epiinfer
data = epiinfer.load_dataset("my_dataset/")
epiinfer.forecast(data, horizon=14, inc=7, duration=7, seed=0)   # mean + 10-90% band
epiinfer.run(data, "unknown_both", inc=7, duration=7).summary()  # back-test: RMSE, fRMSE
```

Your data must be three CSV files; see [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md). Read its
note on the **A state** first. Like the code behind the paper, the model must be told who
is pre-symptomatic, and real contact-tracing data usually do not record that.
`examples/forecast_new_data.py` is a runnable template.

## Reproduce the paper

| Paper table | Command | Agreement |
|---|---|---|
| `tab:openabm-forecast` | `epiinfer reproduce --table openabm --data DIR` | within 1% |
| `tab:age_structured`, both known | `epiinfer reproduce --table age_structured --data DIR` | within 10% |
| `tab:age_structured`, other modes | (same command) | **not reproduced** |
| ARIMA column, age-structured | `epiinfer reproduce --table arima_age_structured --data DIR` | exact |
| `tab:uniform` | `epiinfer reproduce --table uniform --data DIR` | dataset not supplied |

Exact datasets come from release assets (`epiinfer fetch-data --url … --sha256 …`).
Statistically equivalent data can be generated with `epiinfer simulate`. The steps,
runtimes and full results are in [docs/REPRODUCING.md](docs/REPRODUCING.md).

Read [docs/PAPER_VS_CODE.md](docs/PAPER_VS_CODE.md) before relying on the published
comparisons. It covers four points:

- the original code looked ahead at future contacts;
- it was given the true pre-symptomatic people;
- ARIMA was scored on a different, harder window;
- the estimated-rate rows match no version of the code.

## Methods

| `method` | What is estimated | Paper |
|---|---|---|
| `known_both` | nothing: true rates from `p1_true=…, p2_true=…` (default: the paper's AgeMixABM values, so set them for other data) | AgeMixABM tables |
| `known_p1` / `known_p2` | p1 given → p2 searched / p2 given → p1 searched | AgeMixABM tables |
| `unknown_both` (default) | p1 and p2, by grid search (ContinuousCalibrate) | AgeMixABM tables |
| `empirical_p1` | p1 refit daily from observed S→A events; p2 = 1 | OpenABM table |

The default timing (`inc`, `duration`) is 7/7 days for the grid methods and 5/11 for
`empirical_p1`. Override it for your disease.

ARIMA and Holt-Winters baselines need the `baselines` extra:
`epiinfer baseline --data DIR --which arima`.

## Reproducibility

- Every result is a function of `--seed`. Each (seed, origin day, trajectory) has an
  independent random stream, so results are identical for any `--workers` / `--jobs`.
- `run` and `forecast` never use contact data after the forecast origin. Pass
  `contacts="recorded"` to reproduce the original scripts' look-ahead.

## Development

```bash
pytest -q                                        # unit, golden and regression tests
EPIINFER_PAPER_DATA=/path/to/data pytest -m paper   # checks against the paper's datasets
python tools/mutation_check.py                   # breaks 23 guards in a copy; all must be caught
ruff check .
```

`tests/golden_original_scripts.json` holds outputs of the original research scripts on the
demo data, recorded by `tools/make_golden.py`. The package must match them exactly.

## Citation

See `CITATION.cff`. If you use its data, please also cite OpenABM-Covid19 (Hinch et al.).
The authors have not yet chosen a licence; it must be decided before public release.
