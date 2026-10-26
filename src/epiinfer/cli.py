"""``epiinfer`` command line."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import CONTACT_MODES, ENGINES, METHODS
from .data import DataFormatError
from .reproduce.targets import TABLES

DEMO = Path(__file__).parent / "demo_data"


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=0, help="master RNG seed (default 0)")
    p.add_argument("--num-sims", type=int, default=None, help="Monte-Carlo trajectories")
    p.add_argument("--workers", type=int, default=1, help="threads for the trajectories")


def _timing(p: argparse.ArgumentParser) -> None:
    p.add_argument("--inc", type=int, default=None,
                   help="days pre-symptomatic before symptoms (default 7; 5 for empirical_p1)")
    p.add_argument("--duration", type=int, default=None,
                   help="days symptomatic (default 7; 11 for empirical_p1)")
    p.add_argument("--rec-duration", type=int, default=None,
                   help="final engine: days recovered before becoming susceptible (default 7)")


def _engine(p: argparse.ArgumentParser) -> None:
    p.add_argument("--engine", choices=ENGINES, default=None,
                   help="final (default): the October 2026 method, needs no pre-symptomatic data; "
                        "contact: the 2025 code behind the earlier tables; compartmental: the "
                        "earlier EpiInfer (no contact list, deterministic)")
    p.add_argument("--p1-true", type=float, nargs="+", default=None,
                   help="known p1 for known_both / known_p1 (one value; per group for --engine "
                        "contact)")
    p.add_argument("--p2-true", type=float, nargs="+", default=None,
                   help="known p2 for known_both / known_p2")


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
    p.add_argument("--plot", default=None, help="also draw the forecast to this PNG file")
    _engine(p)
    _timing(p)
    _common(p)

    p = sub.add_parser("describe", help="summarise a dataset folder (and plot its epidemic curve)")
    p.add_argument("--data", required=True)
    p.add_argument("--plot", default=None, help="draw the epidemic curve to this PNG file")

    p = sub.add_parser("run", help="rolling-origin back-test on a dataset")
    p.add_argument("--data", required=True)
    p.add_argument("--method", choices=METHODS, default="unknown_both")
    p.add_argument("--start-eval", type=int, default=None,
                   help="first forecast origin (default 25; the final engine needs at least 22 "
                        "when it searches a rate)")
    p.add_argument("--max-day", type=int, default=None,
                   help="use only days up to this one (default 100, the paper's protocol); raise "
                        "it to back-test a longer dataset. `forecast` always uses every day")
    p.add_argument("--last-origin", type=int, default=None,
                   help="last forecast origin (default: max-day - longest horizon - 1)")
    p.add_argument("--horizons", type=int, nargs="+", default=None)
    p.add_argument("--contacts", choices=CONTACT_MODES, default="frozen",
                   help="contact and compartmental engines: frozen (default) uses no future "
                        "contact data; recorded uses each future day's contacts, as the original "
                        "scripts did")
    p.add_argument("--out", default="results", help="output folder")
    p.add_argument("--plots", action="store_true",
                   help="draw forecast-vs-truth and RMSE-by-horizon PNGs into --out")
    _engine(p)
    _timing(p)
    _common(p)

    p = sub.add_parser("reproduce", help="re-run a paper table and compare with published values")
    p.add_argument("--table", required=True, choices=[*sorted(TABLES), "appendix", "sweep"],
                   help="'appendix': Appendix A (needs --scale); 'sweep': Tables 10-13 of the "
                        "October 2026 paper. For both, --data is a folder of p1_*_p2_* folders")
    p.add_argument("--scale", choices=["0.2", "0.5", "2"], default=None,
                   help="contact scale for --table appendix")
    p.add_argument("--data", required=True, help="dataset folder for that table")
    p.add_argument("--quick", action="store_true", help="smoke test (not comparable to paper)")
    p.add_argument("--methods", nargs="+", default=None,
                   help="subset of the table's methods (default: all)")
    p.add_argument("--contacts", choices=CONTACT_MODES, default="recorded",
                   help="recorded (default) reproduces the published numbers; frozen removes "
                        "the original code's look-ahead at future contacts")
    p.add_argument("--jobs", type=int, default=1, help="methods run in parallel processes")
    p.add_argument("--offset", type=int, default=0, choices=[0, 1],
                   help="appendix: contact-day timing (0 = original scripts, 1 = simulator)")
    p.add_argument("--out", default="results")
    _common(p)

    p = sub.add_parser("baseline", help="ARIMA / Holt-Winters baselines (needs [baselines])")
    p.add_argument("--data", required=True)
    p.add_argument("--which", choices=["arima", "holt_winters"], default="arima")
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 5, 10, 20])
    p.add_argument("--start-eval", type=int, default=25, help="first forecast origin")
    p.add_argument("--max-day", type=int, default=100,
                   help="use only days up to this one (default 100, the paper's protocol)")
    p.add_argument("--last-origin", type=int, default=None,
                   help="last forecast origin (paper's ARIMA column: --start-eval 10 "
                        "--last-origin 50)")
    p.add_argument("--out", default=None, help="also write the table to this CSV file")

    p = sub.add_parser("plot-rmse", help="plot RMSE by horizon from summary CSVs (run/baseline)")
    p.add_argument("summaries", nargs="+", help="summary CSV files, optionally LABEL=FILE")
    p.add_argument("--out", required=True, help="PNG file")
    p.add_argument("--metric", default="rmse", choices=["rmse", "frmse_rel"])
    p.add_argument("--title", default="Forecast error by horizon")
    p.add_argument("--log-y", action="store_true", help="log scale for the error axis")

    p = sub.add_parser("from-cases", help="build a dataset folder from a case list and a "
                                          "contact list")
    p.add_argument("--cases", required=True, help="CSV with columns person,onset")
    p.add_argument("--contacts", required=True, help="CSV with columns date,a,b")
    p.add_argument("--out", required=True, help="dataset folder to write")
    p.add_argument("--duration", type=int, default=7, help="days symptomatic from onset (7)")
    p.add_argument("--rec-duration", type=int, default=7,
                   help="days recovered (immune) after that (7)")

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


def _reproduce_appendix(args) -> int:
    from .reproduce import reproduce_appendix
    from .reproduce.appendix import METHODS as APPENDIX_METHODS
    if not args.scale:
        raise SystemExit("--table appendix needs --scale 0.2, 0.5 or 2")
    methods = tuple(args.methods) if args.methods else APPENDIX_METHODS
    df = reproduce_appendix(args.data, args.scale, methods, seed=args.seed, num_sims=args.num_sims,
                            workers=args.workers, contacts=args.contacts, jobs=args.jobs,
                            quick=args.quick, offset=args.offset)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"reproduce_appendix_scale{args.scale}{'_quick' if args.quick else ''}.csv"
    df.to_csv(path, index=False)
    show = df[df["day"].isin([1, 5, 10, 20])]
    print(show.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    summ = df.groupby("method")["ratio"].describe()[["count", "min", "50%", "max"]]
    table = summ.to_string(float_format=lambda x: f"{x:.3f}")
    print("\nratio ours / paper over all days and pairs:\n" + table)
    if args.quick:
        print("\n--quick: reduced evaluation, numbers are not comparable with the paper.")
    print(f"\nwrote {path}")
    return 0


def _reproduce_sweep(args) -> int:
    from .final import CASES, FinalSettings
    from .reproduce.sweep import reproduce_sweep
    cases = tuple(args.methods) if args.methods else CASES
    settings = FinalSettings(n_mc=args.num_sims or 30, seed_offset=1_000_003 * args.seed)
    cmp, pred, trace = reproduce_sweep(args.data, cases, settings, jobs=args.jobs, quick=args.quick)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = "_quick" if args.quick else ""
    cmp.to_csv(out / f"reproduce_sweep{tag}.csv", index=False)
    pred.to_csv(out / f"sweep_predictions{tag}.csv", index=False)
    trace.to_csv(out / f"sweep_trace{tag}.csv", index=False)
    print(cmp.drop(columns=["dataset_check"]).to_string(index=False,
                                                         float_format=lambda x: f"{x:.3f}"))
    for msg in sorted(set(cmp["dataset_check"]) - {"ok", "unknown"}):
        print(f"\nWARNING: {msg}")
    if args.quick:
        print("\n--quick: reduced evaluation, numbers are not comparable with the paper.")
    print(f"\nwrote {out / f'reproduce_sweep{tag}.csv'}")
    return 0


def _describe(args) -> int:
    """Population, days, peak and contacts of a dataset folder; which engines can use it."""
    import pandas as pd

    d = Path(args.data)
    st_path = d / "individual_day_state.csv"
    states = pd.read_csv(st_path) if st_path.exists() else None
    if (d / "states_total.csv").exists():
        tot = pd.read_csv(d / "states_total.csv")
        if not {"day", "I"} <= set(tot.columns):
            raise SystemExit(f"{d / 'states_total.csv'}: needs the columns day and I; "
                             f"has {list(tot.columns)}")
    elif states is not None:
        tot = (states.groupby(["day", "state"]).size().unstack(fill_value=0)
               .rename(columns={0: "S", 1: "A", 2: "I", 3: "R"}).reset_index())
        for col in "SAIR":                           # a state nobody is ever in has no column
            if col not in tot.columns:
                tot[col] = 0
    else:
        raise SystemExit(f"{d}: needs states_total.csv or individual_day_state.csv")
    pop = d / "age_group_population.csv"
    n = int(pd.read_csv(pop)["population"].sum()) if pop.exists() else (
        int(states["id"].max()) + 1 if states is not None else None)
    edges = d / "timed_edges.csv"
    has_a = bool(states is not None and (states["state"] == 1).any())
    peak = tot.loc[tot["I"].idxmax()]
    print(f"dataset            {d.name}")
    print(f"people             {n}")
    print(f"days               {int(tot['day'].min())}-{int(tot['day'].max())}")
    print(f"peak symptomatic   {int(peak['I'])} on day {int(peak['day'])}")
    if edges.exists():
        per_day = pd.read_csv(edges, usecols=["day"])["day"].value_counts()
        print(f"contacts per day   {per_day.mean():.0f} (days {per_day.index.min()}-"
              f"{per_day.index.max()})")
    else:
        print("contacts per day   none (no timed_edges.csv)")
    print(f"pre-symptomatic A  {'recorded' if has_a else 'not recorded'}")
    engines = ["final"] if edges.exists() and states is not None else []
    if edges.exists() and has_a:
        engines.append("contact")
    from .compartmental import FILES
    if all((d / f).exists() for f in FILES):
        engines.append("compartmental")
    print(f"usable engines     {', '.join(engines) or 'none (baselines only)'}")
    if args.plot:
        from .plots import plot_epidemic
        print(plot_epidemic(tot, args.plot, title=f"Epidemic curve - {d.name}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")
    try:
        return _main(args)
    except ImportError as exc:                 # a missing optional extra: say which one
        if "install the extra" in str(exc):
            raise SystemExit(f"epiinfer: {exc}") from None
        raise
    except (DataFormatError, FileNotFoundError) as exc:     # the user's data, not a bug
        raise SystemExit(f"epiinfer: {exc}") from None
    except ValueError as exc:                  # an option the method cannot use: one clear line
        if args.verbose:                       # -v keeps the traceback for bug reports
            raise
        raise SystemExit(f"epiinfer: {exc}") from None


def _main(args: argparse.Namespace) -> int:
    if args.cmd == "demo":
        print(DEMO)
        return 0

    if args.cmd == "fetch-data":
        from .fetch import fetch
        print(fetch(args.url, args.dest, args.sha256))
        return 0

    if args.cmd == "from-cases":
        from .convert import cases_to_dataset
        info = cases_to_dataset(args.cases, args.contacts, args.out, args.duration,
                                args.rec_duration)
        print(f"wrote {info['folder']}: {info['people']} people, days 0-{info['days'] - 1} "
              f"(day 0 = {info['day0']})")
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
        df = rolling_baseline(args.data, args.which, tuple(args.horizons),
                              args.start_eval, args.max_day, args.last_origin)
        print(df.to_string(index=False))
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(args.out, index=False)
            print(f"wrote {args.out}")
        return 0

    if args.cmd == "plot-rmse":
        import pandas as pd

        from .plots import plot_rmse_by_horizon
        tables = {}
        for item in args.summaries:
            label, _, path = item.rpartition("=")
            df = pd.read_csv(path)
            tables[label or Path(path).stem] = df
        print(plot_rmse_by_horizon(tables, args.out, args.metric, args.title, args.log_y))
        return 0

    if args.cmd == "describe":
        return _describe(args)

    over = {"seed": args.seed, "mc_threads": args.workers}
    if args.num_sims:
        over["num_sims"] = args.num_sims
    for name, key in (("inc", "inc"), ("duration", "duration"), ("start_eval", "start_eval"),
                      ("max_day", "max_day"), ("last_origin", "last_origin"),
                      ("rec_duration", "rec_duration"), ("engine", "engine")):
        if getattr(args, name, None) is not None:
            over[key] = getattr(args, name)
    if getattr(args, "horizons", None):
        over["horizons"] = tuple(args.horizons)
    for name in ("p1_true", "p2_true"):
        if getattr(args, name, None):
            over[name] = tuple(getattr(args, name))

    if args.cmd == "forecast":
        from .forecast import forecast
        df = forecast(args.data, args.horizon, args.method, from_day=args.from_day, **over)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(args.out, index=False)
            print(f"wrote {args.out}")
        else:
            print(df.to_csv(index=False), end="")
        if args.plot:
            from .data import load_curve
            from .plots import plot_forecast_band
            print(plot_forecast_band(df, args.plot, history=load_curve(args.data)))
        return 0

    if args.cmd == "run":
        from .forecast import run
        engine = over.get("engine", "final" if args.method != "empirical_p1" else "contact")
        if engine in ("contact", "compartmental"):
            over["contacts"] = args.contacts
        res = run(args.data, args.method, **over)
        if res.rows.empty:
            raise SystemExit(
                "epiinfer: no forecast could be scored. The data is too short for these "
                "settings: a forecast origin needs history before it and its target day needs "
                "data after it. Check --start-eval, --horizons and --max-day against the number "
                f"of days in the dataset (`epiinfer describe --data {args.data}`).")
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        res.rows.to_csv(out / f"predictions_{res.dataset}_{res.method}.csv", index=False)
        res.rates.to_csv(out / f"rates_{res.dataset}_{res.method}.csv", index=False)
        summ = res.summary()
        summ.to_csv(out / f"summary_{res.dataset}_{res.method}.csv", index=False)
        print(summ.to_string(index=False))
        if args.plots:
            from .plots import plot_forecast, plot_rmse_by_horizon
            print(plot_forecast(res, out))
            label = f"{res.method} ({res.config.engine} engine)"
            print(plot_rmse_by_horizon({label: summ},
                                       out / f"rmse_{res.dataset}_{res.method}.png"))
        return 0

    if args.cmd == "reproduce" and args.table == "appendix":
        return _reproduce_appendix(args)

    if args.cmd == "reproduce" and args.table == "sweep":
        return _reproduce_sweep(args)

    if args.cmd == "reproduce":
        from .reproduce import reproduce_table
        df = reproduce_table(args.table, args.data, quick=args.quick, seed=args.seed,
                             num_sims=args.num_sims, workers=args.workers,
                             methods=tuple(args.methods) if args.methods else None,
                             contacts=args.contacts, jobs=args.jobs)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        uses_graph = not ({"baseline_window", "compartmental"} & set(TABLES[args.table]))
        frozen = args.contacts == "frozen" and uses_graph
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
        if args.contacts == "recorded" and uses_graph:
            print("\nNote: contacts=recorded uses each future day's recorded contact graph, as the "
                  "original scripts did.\nRe-run with --contacts frozen for forecasts that use "
                  "no future data (see docs/PAPER_VS_CODE.md).")
        print(f"\nwrote {path}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
