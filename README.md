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

The project is managed with [uv](https://docs.astral.sh/uv/). `uv.lock` pins every
dependency, so everyone gets the same numerical stack. The package is not on PyPI yet;
from a checkout:

```bash
uv sync --all-extras                   # .venv with the locked versions + plots + baselines
uv run epiinfer --help                 # run any command inside that environment
```

Other routes:

- **Base install.** `uv sync` gives numpy and pandas only. Add `--extra plots` or
  `--extra baselines` for the extras.
- **Command on your PATH.** `uv tool install ".[all]"` installs the `epiinfer` command.
- **pip.** `pip install ".[all]"` works too, but it resolves fresh versions instead of the
  locked ones.

It is tested on Python 3.11–3.14 (`.python-version` picks 3.13 by default). The oldest
supported dependencies are also tested: numpy 1.26, pandas 2.0, statsmodels 0.14 and
scipy 1.16. Python 3.10 is not supported: it reaches end of life in October 2026, and no
scipy build for it loads on current macOS.

Docker needs no Python on the host. The image installs the exact locked versions through uv:

```bash
docker build -f docker/Dockerfile -t epiinfer .
docker run --rm epiinfer --help
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$PWD/data:/data:ro" -v "$PWD/results:/work/results" \
    epiinfer reproduce --table openabm --data /data/openabm
```

## 60-second tour

```bash
uv run epiinfer demo                                   # path to a tiny bundled dataset
uv run epiinfer forecast --data "$(uv run epiinfer demo)" --horizon 14
uv run epiinfer run --data "$(uv run epiinfer demo)" --method unknown_both --start-eval 30 --plots
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
| `tab:openabm-forecast` | `uv run epiinfer reproduce --table openabm --data DIR` | within 1% |
| `tab:age_structured`, both known | `uv run epiinfer reproduce --table age_structured --data DIR` | within 10% |
| `tab:age_structured`, other modes | (same command) | **not reproduced** |
| ARIMA column, age-structured | `uv run epiinfer reproduce --table arima_age_structured --data DIR` | exact |
| Holt-Winters columns | `uv run epiinfer reproduce --table hw_age_structured --data DIR` | dataset not supplied |
| `tab:uniform` | `uv run epiinfer reproduce --table uniform --data DIR` | dataset not supplied |

**Getting the data.** The exact datasets are release assets: `epiinfer fetch-data --url …`
downloads one and checks it against the SHA-256 hashes shipped in the package.
`epiinfer simulate` generates statistically equivalent data instead.

**Wrong-data check.** Every `reproduce` run checks that it was given the dataset the paper
used, by population, number of days and peak. It warns if not.

The steps, runtimes and full results are in [docs/REPRODUCING.md](docs/REPRODUCING.md).

Read [docs/PAPER_VS_CODE.md](docs/PAPER_VS_CODE.md) before relying on the published
comparisons. It covers five points:

- the original code looked ahead at future contacts;
- it was given the true pre-symptomatic people;
- ARIMA was scored on a different, harder window;
- the Holt-Winters and LSTM columns came from a different simulated epidemic;
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

ARIMA and Holt-Winters baselines follow the authors' notebooks and need the `baselines`
extra: `uv run epiinfer baseline --data DIR --which arima`.

## Reproducibility

- Every result is a function of `--seed`. Each (seed, origin day, trajectory) has an
  independent random stream, so results are identical for any `--workers` / `--jobs`.
- `run` and `forecast` never use contact data after the forecast origin. Pass
  `contacts="recorded"` to reproduce the original scripts' look-ahead.

## Development

```bash
uv run --all-extras pytest -q                        # unit, golden and regression tests
EPIINFER_PAPER_DATA=/path/to/data uv run --all-extras pytest -m paper  # vs the paper's data
uv run --all-extras python tools/mutation_check.py   # breaks 28 guards; all must be caught
uv run ruff check .
uv lock --check                                      # uv.lock matches pyproject.toml
uv build                                             # sdist + wheel
```

`uv run` keeps `.venv` in sync with `uv.lock`. Pass the same `--all-extras` every time,
otherwise it removes the extras. To upgrade the locked versions, run
`uv lock --upgrade && uv run --all-extras pytest`.

`tests/golden_original_scripts.json` holds the outputs of the original research scripts on
the demo data, plus the authors' own Holt-Winters notebook code. It was recorded by
`tools/make_golden.py`, and the package must match it exactly.

## Citation

See `CITATION.cff`. If you use its data, please also cite OpenABM-Covid19 (Hinch et al.).
Released under the [MIT licence](LICENSE).
