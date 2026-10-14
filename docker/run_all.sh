#!/usr/bin/env bash
# Build the image and run everything inside Docker.
#
#   docker/run_all.sh                     # data in ./data, output in ./results
#   DATA=/path/to/data OUT=/path/to/out JOBS=8 docker/run_all.sh
#
# Always runs: version, demo forecast, demo back-test, demo baseline.
# Runs when the dataset folder exists under $DATA:
#   $DATA/openabm          -> reproduce openabm
#   $DATA/age_structured   -> reproduce age_structured, arima_age_structured
# Missing datasets are skipped with a message, never faked.
set -euo pipefail
cd "$(dirname "$0")/.."

DATA="${DATA:-$PWD/data}"
OUT="${OUT:-$PWD/results}"
IMAGE="${IMAGE:-epiinfer}"
JOBS="${JOBS:-4}"
mkdir -p "$DATA" "$OUT"
DATA="$(cd "$DATA" && pwd)"; OUT="$(cd "$OUT" && pwd)"

# One place that knows how to call the container: your uid (so you own the output),
# datasets at /data, results at /work/results.
epi() {
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$DATA:/data" -v "$OUT:/work/results" "$IMAGE" "$@"
}
step() { printf '\n==> %s\n' "$*"; }

step "Building image '$IMAGE'"
docker build -f docker/Dockerfile -t "$IMAGE" .
epi --version

DEMO="$(epi demo)"
step "Demo: forecast the 14 days after the last observed day"
epi forecast --data "$DEMO" --horizon 14 --method unknown_both --out results/demo_forecast.csv
step "Demo: rolling back-test, with a plot"
epi run --data "$DEMO" --method unknown_both --start-eval 30 --num-sims 5 --plots --out results/demo_backtest
step "Demo: ARIMA baseline"
epi baseline --data "$DEMO" --which arima --start-eval 30

ran=0
if [ -d "$DATA/openabm" ]; then
  step "Reproduce: OpenABM table"
  epi reproduce --table openabm --data /data/openabm --out results/paper
  ran=1
else
  echo "skip: $DATA/openabm not found"
fi
if [ -d "$DATA/age_structured" ]; then
  step "Reproduce: age-structured table (takes ~7 min with JOBS=4)"
  epi reproduce --table age_structured --data /data/age_structured --jobs "$JOBS" --out results/paper
  step "Reproduce: ARIMA column"
  epi reproduce --table arima_age_structured --data /data/age_structured --out results/paper
  ran=1
else
  echo "skip: $DATA/age_structured not found"
fi
[ "$ran" = 1 ] || echo "No paper datasets in $DATA: see 'Getting the data' in docs/REPRODUCING.md."

step "Done. Output is in $OUT"
