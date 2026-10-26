"""Optional figures (needs ``epiinfer[plots]``)."""

from __future__ import annotations

from pathlib import Path

from .forecast import ForecastResult


def plot_forecast(result: ForecastResult, out_dir: str | Path) -> Path:
    try:
        import matplotlib
    except ImportError as exc:
        raise ImportError("plots need matplotlib: install the extra, e.g. "
                          "`uv sync --extra plots` or `pip install 'epiinfer[plots]'`") from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = [*result.age_labels, "ALL"]
    hs = list(result.config.horizons)
    df = result.rows
    fig, axes = plt.subplots(len(groups), len(hs), figsize=(3.6 * len(hs), 2.8 * len(groups)),
                             squeeze=False)
    for r, grp in enumerate(groups):
        for c, h in enumerate(hs):
            ax = axes[r][c]
            s = df[(df["group"] == grp) & (df["horizon"] == h)]
            if s.empty:
                ax.set_visible(False)
                continue
            ax.plot(s["target_day"], s["actual"], "k", alpha=0.6, label="actual")
            ax.plot(s["target_day"], s["predicted"], "b--", label="forecast")
            ax.set_title(f"{grp} | h={h}d", fontsize=9)
            ax.grid(alpha=0.3)
    axes[0][0].legend(fontsize=7)
    fig.suptitle(f"{result.dataset} - {result.method} ({result.config.engine} engine)")
    fig.tight_layout()
    return _save(fig, out_dir / f"forecast_{result.dataset}_{result.method}.png")


def _plt():
    try:
        import matplotlib
    except ImportError as exc:
        raise ImportError("plots need matplotlib: install the extra, e.g. "
                          "`uv sync --extra plots` or `pip install 'epiinfer[plots]'`") from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _save(fig, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, metadata={"Software": None})     # byte-stable across runs
    import matplotlib.pyplot as plt
    plt.close(fig)
    return path


def plot_epidemic(states_total, path, title: str = "Epidemic curve") -> Path:
    """S / A / I / R counts per day (columns that are missing are skipped)."""
    plt = _plt()
    df = states_total.sort_values("day")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    styles = {"S": ("Susceptible", "tab:blue", "-"), "A": ("Pre-symptomatic (A)", "tab:orange", "--"),
              "I": ("Symptomatic (I)", "tab:red", "-"), "R": ("Recovered (R)", "tab:green", "--")}
    for col, (lab, color, ls) in styles.items():
        if col in df.columns:
            ax.plot(df["day"], df[col], ls, color=color, lw=2 if col == "I" else 1.4, label=lab)
    ax.set_xlabel("Day")
    ax.set_ylabel("People")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, path)


def plot_forecast_band(fc, path, history=None, title: str | None = None) -> Path:
    """A one-shot forecast (``epiinfer.forecast`` output, group ALL): mean and 10-90% band,
    the actual counts where known, and the observed history before the origin."""
    plt = _plt()
    df = fc[fc["group"] == "ALL"].sort_values("target_day")
    origin = int(df["origin_day"].iloc[0])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if history is not None:
        hd = sorted(d for d in history if d <= origin)
        ax.plot(hd, [history[d] for d in hd], "k-", lw=1.5, label="observed (up to the origin)")
    ax.fill_between(df["target_day"], df["p10"], df["p90"], color="tab:blue", alpha=0.25,
                    label="forecast 10-90%")
    ax.plot(df["target_day"], df["mean"], "o-", color="tab:blue", ms=3, label="forecast mean")
    known = df[df["actual"].notna()]
    if len(known):
        ax.plot(known["target_day"], known["actual"], "s", color="black", ms=3, mfc="white",
                label="actual (held out)")
    ax.axvline(origin, color="grey", ls=":", lw=1)
    ax.set_xlabel("Day")
    ax.set_ylabel("Symptomatic (I)")
    ax.set_title(title or f"Forecast from day {origin}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, path)


def plot_rmse_by_horizon(summaries: dict, path, metric: str = "rmse",
                         title: str = "Forecast error by horizon", log_y: bool = False) -> Path:
    """One line per method: ``summaries`` maps a label to a summary table with columns
    ``horizon`` and ``metric`` (only the ALL group is used when a ``group`` column exists).
    ``log_y`` draws the error axis on a log scale, for methods of very different accuracy."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ticks: set = set()
    for label, df in summaries.items():
        if metric not in df.columns or "horizon" not in df.columns:
            raise ValueError(f"{label!r}: the summary has no column {metric!r} (it has "
                             f"{list(df.columns)}); frmse_rel is only in the summaries of "
                             f"`epiinfer run`, not of `epiinfer baseline`")
        d = df[df["group"] == "ALL"] if "group" in df.columns else df
        d = d.sort_values("horizon")
        ax.plot(d["horizon"], d[metric], "o-", label=label)
        ticks |= set(int(h) for h in d["horizon"])
    ax.set_xticks(sorted(ticks))
    if log_y:
        ax.set_yscale("log")
    ax.set_xlabel("Forecast horizon (days)")
    ax.set_ylabel({"rmse": "RMSE", "frmse_rel": "fRMSE (relative)"}.get(metric, metric))
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, path)


def plot_paper_vs_ours(days, ours, paper, path, title: str = "Ours vs the paper",
                       ylabel: str = "RMSE") -> Path:
    """Two curves over the forecast horizon."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(days, paper, "s-", color="black", label="paper")
    ax.plot(days, ours, "o--", color="tab:blue", label="this library")
    ax.set_xlabel("Forecast horizon (days)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, path)
