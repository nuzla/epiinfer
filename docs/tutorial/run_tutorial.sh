#!/usr/bin/env bash
# Runs every command of docs/TUTORIAL.md, in order, and collects the outputs.
#
#   docs/tutorial/run_tutorial.sh                 # inside Docker (image below)
#   IMAGE=epiinfer docs/tutorial/run_tutorial.sh  # a locally built image
#   EPI_NATIVE=1 docs/tutorial/run_tutorial.sh    # without Docker, using `epiinfer` on PATH
#
# Outputs go to $WORK/results (default ./tutorial-work/results). CI runs this inside the
# Docker image and checks the CSVs against docs/tutorial/outputs/.
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/nuzla/epiinfer:0.2.0}"
WORK="${WORK:-$PWD/tutorial-work}"
mkdir -p "$WORK/data" "$WORK/results"
WORK="$(cd "$WORK" && pwd)"

if [ "${EPI_NATIVE:-0}" = 1 ]; then
  DATA="$WORK/data"
  epi() { (cd "$WORK" && epiinfer "$@"); }
else
  DATA=/data
  epi() {
    docker run --rm --user "$(id -u):$(id -g)" \
      -v "$WORK/data:/data" -v "$WORK/results:/work/results" "$IMAGE" "$@"
  }
fi
step() { printf '\n### %s\n' "$*"; }

step "0. version"
epi --version | tee "$WORK/results/00_version.txt"

step "1. simulate a 10,000-person epidemic (100 days, age-structured contacts, seed 123)"
epi simulate --out "$DATA/my_epidemic" --contact age_structured --days 100 --seed 123

step "2. describe it and plot the epidemic curve"
epi describe --data "$DATA/my_epidemic" --plot results/01_epidemic_curve.png \
  | tee "$WORK/results/01_describe.txt"

step "3. forecast 14 days ahead from day 60 (the days after 60 are held out)"
epi forecast --data "$DATA/my_epidemic" --from-day 60 --horizon 14 \
  --out results/02_forecast_day60.csv --plot results/02_forecast_day60.png

step "4. forecast the 14 days after the last observed day (a real forecast)"
epi forecast --data "$DATA/my_epidemic" --horizon 14 \
  --out results/03_forecast_future.csv --plot results/03_forecast_future.png

step "5. back-test: forecast from every day 25-79 and score against what happened"
epi run --data "$DATA/my_epidemic" --method unknown_both \
  --out results/04_backtest_final --plots | tee "$WORK/results/04_backtest_final.txt"

step "6. the same back-test with the 2025 engine (it reads the true pre-symptomatic state)"
epi run --data "$DATA/my_epidemic" --engine contact --method unknown_both \
  --horizons 1 5 10 20 --last-origin 79 \
  --out results/05_backtest_contact | tee "$WORK/results/05_backtest_contact.txt"

step "7. the same back-test with the earlier EpiInfer (no contact list, deterministic)"
epi run --data "$DATA/my_epidemic" --engine compartmental --method unknown_both \
  --out results/06_backtest_compartmental | tee "$WORK/results/06_backtest_compartmental.txt"

step "8. statistical baselines on the same forecast origins"
epi baseline --data "$DATA/my_epidemic" --which arima --last-origin 79 \
  --out results/07_arima.csv
epi baseline --data "$DATA/my_epidemic" --which holt_winters --last-origin 79 \
  --out results/07_holt_winters.csv

step "9. one chart: error by horizon for all five"
epi plot-rmse \
  "EpiInfer-contact, final engine=results/04_backtest_final/summary_my_epidemic_unknown_both.csv" \
  "EpiInfer-contact, 2025 engine=results/05_backtest_contact/summary_my_epidemic_unknown_both.csv" \
  "EpiInfer (earlier)=results/06_backtest_compartmental/summary_my_epidemic_unknown_both.csv" \
  "ARIMA(1,1,1)=results/07_arima.csv" \
  "Holt-Winters=results/07_holt_winters.csv" \
  --out results/08_rmse_comparison.png --title "Back-test on the simulated epidemic" --log-y

step "done: outputs in $WORK/results"
