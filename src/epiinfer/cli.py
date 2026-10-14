"""``epiinfer`` command line."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import METHODS

DEMO = Path(__file__).parent / "demo_data"


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=0, help="master RNG seed (default 0)")
    p.add_argument("--num-sims", type=int, default=None, help="Monte-Carlo trajectories")
    p.add_argument("--workers", type=int, default=1, help="threads for the trajectories")


def _build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="epiinfer", description=__doc__)
    ap.add_argument("--version", action="version", version=f"epiinfer {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("forecast", help="forecast the days after the last observed day")
    p.add_argument("--data", required=True, help="dataset folder (see docs/DATA_FORMAT.md)")
    p.add_argument("--horizon", type=int, default=14)
    p.add_argument("--method", choices=METHODS, default="empirical_p1")
    p.add_argument("--from-day", type=int, default=None)
    p.add_argument("--out", default=None, help="write CSV here (default: stdout)")
    p.add_argument("--inc", type=int, default=None, help="days in A (incubation)")
    p.add_argument("--duration", type=int, default=None, help="days in I")
    _common(p)

    p = sub.add_parser("run", help="rolling-origin evaluation on a dataset")
    p.add_argument("--data", required=True)
    p.add_argument("--method", choices=METHODS, default="unknown_both")
    p.add_argument("--start-eval", type=int, default=None)
    p.add_argument("--max-day", type=int, default=None)
    p.add_argument("--out", default="results", help="output folder")
    p.add_argument("--plots", action="store_true")
    _common(p)

    p = sub.add_parser("reproduce", help="re-run a paper table and compare with published values")
    p.add_argument("--table", required=True, choices=["age_structured", "uniform", "openabm"])
    p.add_argument("--data", required=True, help="dataset folder for that table")
    p.add_argument("--quick", action="store_true", help="smoke test (not comparable to paper)")
    p.add_argument("--methods", nargs="+", choices=METHODS, default=None,
                   help="subset of the table's methods (default: all)")
    p.add_argument("--out", default="results")
    _common(p)

    p = sub.add_parser("baseline", help="ARIMA / Holt-Winters baselines (needs [baselines])")
    p.add_argument("--data", required=True)
    p.add_argument("--which", choices=["arima", "holt_winters"], default="arima")

    p = sub.add_parser("simulate", help="generate a synthetic AgeMixABM dataset")
    p.add_argument("--out", required=True)
    p.add_argument("--contact", choices=["uniform", "age_structured"], default="age_structured")
    p.add_argument("--days", type=int, default=100)
    p.add_argument("--seed", type=int, default=123)
    p.add_argument("--scale", type=float, default=0.2, help="contact-matrix multiplier")

    p = sub.add_parser("fetch-data", help="download + verify a dataset archive")
    p.add_argument("--url", default=None)
    p.add_argument("--sha256", default=None)
    p.add_argument("--dest", default="data")

    sub.add_parser("demo", help="print the path of the tiny bundled demo dataset")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")

    if args.cmd == "demo":
        print(DEMO)
        return 0

    if args.cmd == "fetch-data":
        from .fetch import fetch
        print(fetch(args.url, args.dest, args.sha256))
        return 0

    if args.cmd == "simulate":
        from .simulate import AgeMixConfig, simulate, write_dataset
        sim = simulate(AgeMixConfig(contact=args.contact, days=args.days, seed=args.seed,
                                    contact_scale=args.scale))
        print(write_dataset(sim, args.out))
        return 0

    if args.cmd == "baseline":
        from .baselines import rolling_baseline
        from .data import load_dataset
        print(rolling_baseline(load_dataset(args.data), args.which).to_string(index=False))
        return 0

    over = {"seed": args.seed, "mc_threads": args.workers}
    if args.num_sims:
        over["num_sims"] = args.num_sims

    if args.cmd == "forecast":
        from .forecast import forecast
        if args.inc is not None:
            over["inc"] = args.inc
        if args.duration is not None:
            over["duration"] = args.duration
        df = forecast(args.data, args.horizon, args.method, from_day=args.from_day, **over)
        if args.out:
            df.to_csv(args.out, index=False)
            print(f"wrote {args.out}")
        else:
            print(df.to_csv(index=False), end="")
        return 0

    if args.cmd == "run":
        from .forecast import run
        if args.start_eval is not None:
            over["start_eval"] = args.start_eval
        if args.max_day is not None:
            over["max_day"] = args.max_day
        res = run(args.data, args.method, **over)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        res.rows.to_csv(out / f"predictions_{res.dataset}_{res.method}.csv", index=False)
        res.rates.to_csv(out / f"rates_{res.dataset}_{res.method}.csv", index=False)
        summ = res.summary()
        summ.to_csv(out / f"summary_{res.dataset}_{res.method}.csv", index=False)
        print(summ.to_string(index=False))
        if args.plots:
            from .plots import plot_forecast
            print(plot_forecast(res, out))
        return 0

    if args.cmd == "reproduce":
        from .reproduce import reproduce_table
        df = reproduce_table(args.table, args.data, quick=args.quick, seed=args.seed,
                             num_sims=args.num_sims, workers=args.workers,
                             methods=tuple(args.methods) if args.methods else None)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"reproduce_{args.table}{'_quick' if args.quick else ''}.csv"
        df.to_csv(path, index=False)
        print(df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        if args.quick:
            print("\n--quick: reduced evaluation, numbers are not comparable with the paper.")
        print(f"\nwrote {path}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
