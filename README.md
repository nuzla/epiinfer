# epiinfer

Python implementation of **EpiInfer-CONTACT** ("Forecasting Infection Rates in Epidemics
Given Contact Tracing Information", Kascelan, Yang & Shasha, *Algorithms*, 2025). It is
packaged so that anyone can:

1. **reproduce** the paper's tables, and
2. **forecast** with their own contact-tracing data.

Given who met whom each day, EpiInfer-contact rolls an S → A → I → R epidemic forward on the
contact graph. Here A means infectious but not yet symptomatic, and I means symptomatic
and isolated. It averages Monte-Carlo trajectories to forecast the number of symptomatic
people.

**New here? Start with the [tutorial](docs/TUTORIAL.md).** It walks through a forecast in
Docker step by step, with the exact output and plots you should get.

The paper's numbers come from three versions of the code, and the library has an engine
for each:

| Engine | What it is | Needs |
|---|---|---|
| `final` (default) | the October 2026 method (`abm_final.ipynb`): rebuilds the pre-symptomatic history from infections, recovered people become susceptible again, periodic joint calibration | who is symptomatic or recovered each day, plus the contacts |
| `contact` | the 2025 code behind most published tables | the above **plus** who is pre-symptomatic (state A), which real data rarely record |
| `compartmental` | EpiInfer, the earlier model the paper compares against: deterministic, no contact list | daily counts per age group (symptomatic, average contacts) |

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

No Python on the host? Use [Docker](#docker) instead.

## 60-second tour

```bash
uv run epiinfer demo                                   # path to a tiny bundled dataset
uv run epiinfer describe --data "$(uv run epiinfer demo)"
uv run epiinfer forecast --data "$(uv run epiinfer demo)" --horizon 14 --plot forecast.png
uv run epiinfer run --data "$(uv run epiinfer demo)" --method unknown_both --max-day 46 \
    --horizons 1 5 10 --plots
```

```python
import epiinfer
epiinfer.forecast("my_dataset/", horizon=14, seed=0)           # mean + 10-90% band
epiinfer.run("my_dataset/", "unknown_both").summary()           # back-test: RMSE, fRMSE
epiinfer.run("my_dataset/", "unknown_both", engine="contact")   # the 2025 code instead
```

Your data is a folder of CSV files; see [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md). For the
default engine that is two files: who is symptomatic or recovered each day, and who met
whom. `epiinfer from-cases` builds the folder from a case list and a contact list.
`examples/forecast_new_data.py` is a runnable template.

## Reproduce the paper

| Paper table | Command | Agreement |
|---|---|---|
| Tables 10–13 (October 2026), EpiInfer-contact | `uv run epiinfer reproduce --table sweep --data DIR` | the authors' summary is recomputed **exactly** from their predictions (192 cells); the engine is bit-exact against their notebook; re-running needs the Base data, which was not supplied |
| Tables 2–5 / 14, EpiInfer "both known" | `uv run epiinfer reproduce --table epiinfer_age_structured --data DIR` | **exact** |
| Appendix A: EpiInfer | `uv run epiinfer reproduce --table appendix --scale 0.2 --methods epiinfer_old --data DIR` | **exact**, all 720 cells |
| `tab:openabm-forecast` | `uv run epiinfer reproduce --table openabm --data DIR` | within 1% |
| `tab:age_structured`, vs the authors' own run of the same code | `uv run epiinfer reproduce --table age_structured --data DIR` | all 16 cells within 8.3% |
| `tab:age_structured`, vs the published paper | (same command) | "both known" within 10%; the other modes differ (the paper reports a different run) |
| ARIMA columns (age-structured, uniform) | `uv run epiinfer reproduce --table arima_age_structured` / `arima_uniform --data DIR` | exact, each on its own dataset |
| Holt-Winters columns | `uv run epiinfer reproduce --table hw_age_structured` / `hw_uniform --data DIR` | day 1 within 1.5%, day 20 off by 12–19% |
| Appendix A: ARIMA | `uv run epiinfer reproduce --table appendix --scale 0.2 --methods arima --data DIR` | exact, all 720 cells |
| Appendix A: EpiInfer-contact | `uv run epiinfer reproduce --table appendix --scale 0.2 --data DIR --jobs 4` | 79% of days 1–8 within 15%; days 9–19 match after a one-day shift (96%) |
| `tab:uniform`'s EpiInfer-contact column | | cannot run: the uniform data has no contact list (the notebook behind it is identified) |

**Getting the data.** The exact datasets are release assets: `epiinfer fetch-data --url …`
downloads one and checks it against the SHA-256 hashes shipped in the package.
`epiinfer simulate` generates statistically equivalent data instead.

**Wrong-data check.** Every `reproduce` run checks that it was given the dataset the paper
used, by population, number of days and peak. It warns if not.

The steps, runtimes and full results are in [docs/REPRODUCING.md](docs/REPRODUCING.md).

Read [docs/PAPER_VS_CODE.md](docs/PAPER_VS_CODE.md) before relying on the published
comparisons. Its main points:

- the 2025 code looked ahead at future contacts, and was given the true pre-symptomatic
  people (the October 2026 method fixes the second);
- ARIMA was scored on a different, harder window;
- the Holt-Winters and LSTM columns came from a different simulated epidemic;
- the paper's Appendix A runs one day ahead of the library from about day 9;
- the paper's estimated-rate rows are a different run from the authors' own, which the
  library does reproduce;
- Tables 10–13 use a new method and a new fRMSE definition, and their ARIMA column mixes two
  datasets;
- the earlier EpiInfer's forecasts are made one day further from the data than
  EpiInfer-contact's;
- the uniform tables' EpiInfer-contact column came from a notebook that treats susceptible
  people as the infectious ones.

## Docker

The image bundles Python, the locked dependencies and every `epiinfer` command, so the only
thing you need on the host is Docker. Released versions are published to the GitHub container
registry. CI also builds the image on every push, runs `demo`, `forecast` and `run --plots` in
it as an arbitrary non-root user, and runs the whole [tutorial](docs/TUTORIAL.md) in it.

### 1. Get the image

**Pull a released image** (Intel/AMD and ARM, including Apple silicon). Each version tag
publishes one; see the repository's Packages page for the list.

```bash
docker pull ghcr.io/nuzla/epiinfer:0.2.1
docker tag  ghcr.io/nuzla/epiinfer:0.2.1 epiinfer      # the commands below call it "epiinfer"
```

For a paper or a script, pin the exact image by digest, which is printed in each release's
workflow summary: `ghcr.io/nuzla/epiinfer@sha256:…`. Version tags can be re-pointed; digests
cannot.

**Or build it from this repository:**

```bash
docker build -f docker/Dockerfile -t epiinfer .
docker run --rm epiinfer --version
```

### 2. How the container is wired

| Host | In the container | Used for |
|---|---|---|
| `./data` | `/data` | datasets you read, and ones `simulate` / `fetch-data` write |
| `./results` | `/work/results` | everything the commands write (the default `--out`) |

The container runs as a non-root user. Pass `--user "$(id -u):$(id -g)"` so that the files
it writes into `./results` belong to you. Commands below use the shell function

```bash
epi() { docker run --rm --user "$(id -u):$(id -g)" \
          -v "$PWD/data:/data" -v "$PWD/results:/work/results" epiinfer "$@"; }
```

Paths in the arguments are paths **inside the container**: datasets are under `/data/...`
and outputs go under `results/...`.

### 3. Try it on the bundled demo data (nothing to download)

```bash
mkdir -p data results
DEMO="$(epi demo)"                       # path of the demo dataset inside the image
epi forecast --data "$DEMO" --horizon 14 --out results/demo_forecast.csv
epi run --data "$DEMO" --method unknown_both --start-eval 30 --plots --out results/demo_backtest
epi baseline --data "$DEMO" --which arima --start-eval 30
```

Open `results/demo_backtest/forecast_demo_data_unknown_both.png` to see the back-test.

### 4. Your own data

Put the dataset folder (see [docs/DATA_FORMAT.md](docs/DATA_FORMAT.md)) in `./data`, or
build it from a case list and a contact list with
`epi from-cases --cases /data/cases.csv --contacts /data/contacts.csv --out /data/my_dataset`:

```bash
epi describe --data /data/my_dataset                     # which engines can use it
epi forecast --data /data/my_dataset --horizon 14 --inc 7 --duration 7 \
    --out results/my_forecast.csv --plot results/my_forecast.png
epi run      --data /data/my_dataset --method unknown_both --inc 7 --duration 7 \
    --out results/my_backtest --plots
```

The [tutorial](docs/TUTORIAL.md) explains each output.

### 5. Reproduce the paper

```bash
epi reproduce --table openabm              --data /data/openabm        --out results/paper
epi reproduce --table age_structured       --data /data/age_structured --jobs 4 --out results/paper
epi reproduce --table arima_age_structured --data /data/age_structured --out results/paper
```

The paper's datasets are not in the image or the repository. Put them in `./data/openabm`
and `./data/age_structured`. `epi fetch-data --url <release asset URL> --dest /data`
downloads and verifies an archive, but no release assets are published yet. You can also
generate similar data with `epi simulate --contact age_structured --out /data/sim_age_structured`
(similar, not identical; see [docs/REPRODUCING.md](docs/REPRODUCING.md)). A run on the wrong
dataset prints a **WARNING: MISMATCH**. Expect about 7 minutes for the age-structured table
with `--jobs 4`.

### 6. Run everything with one command

```bash
docker/run_all.sh                                  # data in ./data, output in ./results
DATA=/path/to/data OUT=/path/to/out JOBS=8 docker/run_all.sh
```

The script builds the image, runs the demo commands above, and then runs each paper table
whose dataset folder it finds under the data directory. It skips the others with a message
and never fakes a result. Everything is written to the results directory.

### Docker Compose

`docker/docker-compose.yml` records the same mounts and user:

```bash
LOCAL_USER="$(id -u):$(id -g)" docker compose -f docker/docker-compose.yml run --rm epiinfer \
    reproduce --table openabm --data /data/openabm --out results/paper
```

### Apptainer / Singularity (clusters without Docker)

Most HPC systems run [Apptainer](https://apptainer.org/) (formerly Singularity) instead of
Docker. It converts the same image, with nothing extra to install:

```bash
apptainer pull epiinfer.sif docker://ghcr.io/nuzla/epiinfer:0.2.1     # once; makes epiinfer.sif
mkdir -p data results
apptainer run epiinfer.sif --version
apptainer run --bind "$PWD/data:/data" epiinfer.sif forecast --data /data/my_dataset --out results/forecast.csv
apptainer run --bind "$PWD/data:/data" epiinfer.sif reproduce --table openabm --data /data/openabm --out results/paper
```

Everything after `epiinfer.sif` is passed straight to `epiinfer`, as with `docker run`.
Differences from Docker:

- It runs as **you**, so there is no `--user` flag and output files are yours.
- The image itself is read-only. Results go to `results/` in the **current directory**
  (Apptainer mounts it), so run from a folder you can write to.
- Datasets must be bound in with `--bind host_dir:/data`, as above.
- `--containall` or `--no-home` stops the current directory from being mounted; if you use
  them, bind `results/` explicitly too: `--bind "$PWD/results:/work/results"`.
- On SingularityCE, replace `apptainer` with `singularity`; the commands are the same.
- To pin the exact image: `apptainer pull epiinfer.sif docker://ghcr.io/nuzla/epiinfer@sha256:…`.
- Pulling a big image can fill your home quota. Point the cache elsewhere with
  `export APPTAINER_CACHEDIR=/scratch/$USER/apptainer`.

This route has **not been tested** by the maintainers (no Apptainer is available to them).
Please open an issue if a command here does not work.

### Troubleshooting

- **`Permission denied` writing to `results/`.** Add `--user "$(id -u):$(id -g)"`
  (or set `LOCAL_USER` for Compose), and make sure `./results` exists before the first run.
- **`no such file` for a dataset.** The path in `--data` must be the container path
  (`/data/...`), not the host path.
- **A table warns `MISMATCH`.** The folder is not the dataset the paper used. See the
  table in [docs/REPRODUCING.md](docs/REPRODUCING.md).
- **Slow age-structured table.** It is CPU-bound: give Docker Desktop more CPUs and raise
  `--jobs` (one process per method, up to 4).

## Methods

`--method` says which rates are known; the engine says how the rest are found.

| `method` | What is estimated | Engines |
|---|---|---|
| `known_both` | nothing: true rates from `--p1-true` / `--p2-true` | all |
| `known_p1` / `known_p2` | p1 given → p2 searched / p2 given → p1 searched | all |
| `unknown_both` (default) | p1 and p2 | all |
| `empirical_p1` | p1 refit daily from observed S→A events; p2 = 1 (the OpenABM table) | `contact` only |

How the search works:

- **final**: every 5 days, a joint grid search (0.05–0.30) scored by 7-day forecasts over
  the last 14 days, with one (p1, p2) for everyone.
- **contact**: a daily grid search per age group, smoothed (ContinuousCalibrate).
- **compartmental**: a 15 × 10 grid fitted to the last 5 days.

`final` and `compartmental` take one known rate for everyone. `contact` takes one per age
group; its default is the paper's AgeMixABM values, so set them for other data.

The default timing (`inc`, `duration`) is 7/7 days, and 5/11 for `empirical_p1`. The final
engine also has `--rec-duration` (7), the days a recovered person stays immune. Override
them for your disease.

ARIMA and Holt-Winters baselines follow the authors' notebooks and need the `baselines`
extra: `uv run epiinfer baseline --data DIR --which arima`.

## Reproducibility

- Every result is a function of `--seed`. Each (seed, origin day, trajectory) has an
  independent random stream, so results are identical for any `--workers` / `--jobs`.
- `run` and `forecast` never use contact data after the forecast origin. Pass
  `contacts="recorded"` to reproduce the original scripts' look-ahead (contact and
  compartmental engines; the final engine has none).
- `forecast` uses every day of the dataset and starts from its last day. `run` is a back-test
  and uses the days up to `--max-day` (default 100, the paper's protocol, with origins 25–79);
  raise `--max-day` (and `--last-origin`) to back-test a longer dataset.

## Development

```bash
uv run --all-extras pytest -q                        # unit, golden and regression tests
EPIINFER_PAPER_DATA=/path/to/data uv run --all-extras pytest -m paper  # vs the paper's data
uv run --all-extras python tools/mutation_check.py   # breaks key guards one at a time; all must be caught
uv run ruff check .
uv lock --check                                      # uv.lock matches pyproject.toml
uv build                                             # sdist + wheel
```

`uv run` keeps `.venv` in sync with `uv.lock`. Pass the same `--all-extras` every time,
otherwise it removes the extras. To upgrade the locked versions, run
`uv lock --upgrade && uv run --all-extras pytest`.

Three fixtures hold the outputs of the authors' own code on the demo data, and the package
must match each exactly:

- `tests/golden_original_scripts.json`: the 2025 scripts and the Holt-Winters notebook code,
  recorded by `tools/make_golden.py`;
- `tests/golden_final_notebook.json`: `abm_final.ipynb`, recorded by
  `tools/make_golden_final.py`;
- `tests/golden_compartmental_notebook.json`: the earlier EpiInfer notebooks, recorded by
  `tools/make_golden_compartmental.py`.

## Citation

See `CITATION.cff`. If you use its data, please also cite OpenABM-Covid19 (Hinch et al.).
Released under the [MIT licence](LICENSE).
