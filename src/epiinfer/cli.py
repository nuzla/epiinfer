"""``epiinfer`` command line."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import CONTACT_MODES, METHODS
from .reproduce.targets import TABLES

DEMO = Path(__file__).parent / "demo_data"


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=0, help="master RNG seed (default 0)")
    p.add_argument("--num-sims", type=int, default=None, help="Monte-Carlo trajectories")
    p.add_argument("--workers", type=int, default=1, help="threads for the trajectories")


def _timing(p: argparse.ArgumentParser) -> None:
    p.add_argument("--inc", type=int, default=None,
                   help="days in A before symptoms (default: 7 grid methods, 5 empirical_p1)")
    p.add_argument("--duration", type=int, default=None,
                   help="days in I (default: 7 grid methods, 11 empirical_p1)")


def _build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="epiinfer", description=__doc__)
    ap.add_argument("--version", action="version", version=f"epiinfer {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("forecast", help="forecast the days after the last observed day")
    p.add_argument("--data", required=True, help="dataset folder (see docs/DATA_FORMAT.md)")
    p.add_argument("--horizon", type=int, default=14)
    p.add_argument("--method", choices=METHODS, default="unknown_both")
    p.add_argument("--from-day", type=int, default=None)
    p.add_argument("--out", default=None, help="write CSV here (default: stdout)")
    _timing(p)
    _common(p)

    p = sub.add_parser("run", help="rolling-origin back-test on a dataset")
    p.add_argument("--data", required=True)
    p.add_argument("--method", choices=METHODS, default="unknown_both")
    p.add_argument("--start-eval", type=int, default=None)
    p.add_argument("--max-day", type=int, default=None)
    p.add_argument("--last-origin", type=int, default=None, help="last forecast origin")
    p.add_argument("--horizons", type=int, nargs="+", default=None)
    p.add_argument("--contacts", choices=CONTACT_MODES, default="frozen",
                   help="frozen (default): no future contact data; recorded: original scripts")
    p.add_argument("--out", default="results", help="output folder")
    p.add_argument("--plots", action="store_true")
    _timing(p)
    _common(p)

    p = sub.add_parser("reproduce", help="re-run a paper table and compare with published values")
    p.add_argument("--table", required=True, choices=sorted(TABLES))
    p.add_argument("--data", required=True, help="dataset folder for that table")
    p.add_argument("--quick", action="store_true", help="smoke test (not comparable to paper)")
    p.add_argument("--methods", nargs="+", default=None,
                   help="subset of the table's methods (default: all)")
    p.add_argument("--contacts", choices=CONTACT_MODES, default="recorded",
                   help="recorded (default) reproduces the published numbers; frozen removes "
                        "the original code's look-ahead at future contacts")
    p.add_argument("--jobs", type=int, default=1, help="methods run in parallel processes")
    p.add_argument("--out", default="results")
    _common(p)

    p = sub.add_parser("baseline", help="ARIMA / Holt-Winters baselines (needs [baselines])")
    p.add_argument("--data", required=True)
    p.add_argument("--which", choices=["arima", "holt_winters"], default="arima")
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 5, 10, 20])
    p.add_argument("--start-eval", type=int, default=25)
    p.add_argument("--max-day", type=int, default=100)
    p.add_argument("--last-origin", type=int, default=None,
                   help="last forecast origin (paper's ARIMA column: --start-eval 10 "
                        "--last-origin 50)")

    p = sub.add_parser("simulate", help="generate a synthetic AgeMixABM dataset")
    p.add_argument("--out", required=True)
    p.add_argument("--contact", choices=["uniform", "age_structured"], default="age_structured")
    p.add_argument("--scale", type=float, default=0.2, help="contact-matrix multiplier")
    p.add_argument("--p1", type=float, nargs="+", default=None,
                   help="per-contact transmission prob, one value or one per group")
    p.add_argument("--p2", type=float, nargs="+", default=None,
                   help="A->I progression prob, one value or one per group")
    p.add_argument("--sizes", type=int, nargs="+", default=None, help="group sizes")
    p.add_argument("--days", type=int, default=100)
    p.add_argument("--init-a", type=int, default=8)
    p.add_argument("--seed", type=int, default=123)

    p = sub.add_parser("fetch-data", help="download + verify a dataset archive")
    p.add_argument("--url", default=None)
    p.add_argument("--sha256", default=None)
    p.add_argument("--dest", default="data")

    sub.add_parser("demo", help="print the path of the tiny bundled demo dataset")
    return ap


def _per_group(values, n, name):
    if values is None:
        return None
    if len(values) == 1:
        return tuple(values) * n
    if len(values) != n:
        raise SystemExit(f"--{name} needs 1 or {n} values")
    return tuple(values)


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except ImportError as exc:                 # a missing optional extra: say which one
        if "install the extra" in str(exc):
            raise SystemExit(f"epiinfer: {exc}") from None
        raise


def _main(argv: list[str] | None = None) -> int:
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
        kw = {"contact": args.contact, "days": args.days, "seed": args.seed,
              "contact_scale": args.scale, "init_a": args.init_a}
        if args.sizes:
            kw["group_sizes"] = tuple(args.sizes)
        n = len(kw.get("group_sizes", AgeMixConfig().group_sizes))
        for name in ("p1", "p2"):
            v = _per_group(getattr(args, name), n, name)
            if v is not None:
                kw[name] = v
        print(write_dataset(simulate(AgeMixConfig(**kw)), args.out))
        return 0

    if args.cmd == "baseline":
        from .baselines import rolling_baseline
        from .data import load_dataset
        df = rolling_baseline(load_dataset(args.data), args.which, tuple(args.horizons),
                              args.start_eval, args.max_day, args.last_origin)
        print(df.to_string(index=False))
        return 0

    over = {"seed": args.seed, "mc_threads": args.workers}
    if args.num_sims:
        over["num_sims"] = args.num_sims
    for name in ("inc", "duration", "start_eval", "max_day", "last_origin"):
        if getattr(args, name, None) is not None:
            over[name] = getattr(args, name)
    if getattr(args, "horizons", None):
        over["horizons"] = tuple(args.horizons)

    if args.cmd == "forecast":
        from .forecast import forecast
        df = forecast(args.data, args.horizon, args.method, from_day=args.from_day, **over)
        if args.out:
            df.to_csv(args.out, index=False)
            print(f"wrote {args.out}")
        else:
            print(df.to_csv(index=False), end="")
        return 0

    if args.cmd == "run":
        from .forecast import run
        res = run(args.data, args.method, contacts=args.contacts, **over)
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
                             methods=tuple(args.methods) if args.methods else None,
                             contacts=args.contacts, jobs=args.jobs)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        frozen = args.contacts == "frozen" and "baseline_window" not in TABLES[args.table]
        tag = ("_quick" if args.quick else "") + ("_frozen" if frozen else "")
        path = out / f"reproduce_{args.table}{tag}.csv"
        df.to_csv(path, index=False)
        print(df.drop(columns=["dataset_check"]).to_string(
            index=False, float_format=lambda x: f"{x:.3f}"))
        checks = set(df["dataset_check"]) - {"ok", "unknown"}
        for msg in checks:
            print(f"\nWARNING: {msg}.\nNumbers will not match the paper; see docs/REPRODUCING.md.")
        if args.quick:
            print("\n--quick: reduced evaluation, numbers are not comparable with the paper.")
        if args.contacts == "recorded" and "baseline_window" not in TABLES[args.table]:
            print("\nNote: contacts=recorded uses each future day's recorded contact graph, as the "
                  "original scripts did.\nRe-run with --contacts frozen for forecasts that use "
                  "no future data (see docs/PAPER_VS_CODE.md).")
        print(f"\nwrote {path}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
