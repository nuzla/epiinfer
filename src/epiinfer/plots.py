"""Optional figures (needs ``epiinfer[plots]``)."""

from __future__ import annotations

from pathlib import Path

from .forecast import ForecastResult


def plot_forecast(result: ForecastResult, out_dir: str | Path) -> Path:
    import matplotlib
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
    fig.suptitle(f"{result.dataset} - {result.method}")
    fig.tight_layout()
    path = out_dir / f"forecast_{result.dataset}_{result.method}.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
