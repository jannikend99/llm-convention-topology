"""Named PNG/PDF writers for locked Results spine IDs."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HUMAN_F4 = {
    "mixing": 0.96,
    "lattice": 0.30,
    "random_regular": 0.33,
}
HUMAN_F13_CM_MIXING = 0.25
HUMAN_SOURCE = {
    "dominant_share": "Centola & Baronchelli 2015",
    "cm_mixing": "Centola et al. 2018",
}


def save_png_pdf(fig: plt.Figure, outputs_dir: Path, stem: str) -> None:
    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outputs_dir / f"{stem}.png", dpi=150, bbox_inches="tight")
    fig.savefig(outputs_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_d1(funnel: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    if funnel.empty:
        ax.set_title("D1 empty")
    else:
        labels = [f"{t}\n{m}" for t, m in zip(funnel["topology"], funnel["model_shorthand"])]
        x = range(len(funnel))
        ax.bar(x, funnel["attempted"], label="attempted")
        ax.bar(x, funnel["completed"], label="completed")
        ax.set_xticks(list(x), labels, fontsize=7)
        ax.legend()
    ax.set_ylabel("runs")
    ax.set_title("D1 funnel")
    save_png_pdf(fig, outputs_dir, "D1")


def plot_f3(mixing: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    if mixing.empty or mixing["dominant_share"].dropna().empty:
        ax.set_title("F3 empty")
    else:
        parts = []
        names = []
        for model, group in mixing.groupby("model_shorthand"):
            parts.append(group["dominant_share"].dropna().to_numpy())
            names.append(str(model))
        ax.boxplot(parts, tick_labels=names)
        ax.axhline(0.90, color="black", linestyle="--", label="tau=0.90")
        ax.legend()
    ax.set_ylabel("dominant share")
    ax.set_title("F3 mixing dominant share")
    save_png_pdf(fig, outputs_dir, "F3")


def plot_th1(table: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 3 + 0.3 * max(len(table), 1)))
    ax.axis("off")
    if table.empty:
        ax.set_title("T-H1 empty")
    else:
        show = table.copy()
        text = show.round(4).astype(str)
        ax.table(cellText=text.values, colLabels=list(text.columns), loc="center")
        ax.set_title("T-H1")
    save_png_pdf(fig, outputs_dir, "T-H1")


def plot_f4(emergence: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    if emergence.empty:
        ax.set_title("F4 empty")
    else:
        emergence.boxplot(column="dominant_share", by="topology", ax=ax)
        for topo, value in HUMAN_F4.items():
            ax.axhline(value, linestyle=":", linewidth=1, label=f"human {topo} {value}")
        ax.legend(fontsize=7)
        fig.suptitle("")
    ax.set_title("F4 dominant share by topology")
    save_png_pdf(fig, outputs_dir, "F4")


def plot_f13(empirical: pd.DataFrame, curve: list[dict] | None, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    if empirical.empty:
        ax.set_title("F13 empty")
    else:
        for topology, group in empirical.groupby("topology"):
            ax.plot(group["cm_k"], group["flip_rate"], marker="o", label=str(topology))
        if curve:
            ax.plot(
                [row["cm_k"] for row in curve],
                [row["predicted_flip_prob"] for row in curve],
                linestyle="--",
                label="GAM mixing",
            )
        ax.axhline(HUMAN_F13_CM_MIXING, color="gray", linestyle=":", label="human CM mixing ~0.25")
        ax.legend(fontsize=7)
    ax.set_xlabel("k")
    ax.set_ylabel("flip rate")
    ax.set_title("F13 flip vs k")
    save_png_pdf(fig, outputs_dir, "F13")


def plot_f18(frequencies: dict[str, float], outputs_dir: Path, pool: Sequence[str] | None = None) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = list(pool) if pool else list(frequencies)
    heights = [frequencies.get(label, 0.0) for label in labels]
    ax.bar(range(len(labels)), heights)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("winner share")
    ax.set_title("F18 mixing winners")
    save_png_pdf(fig, outputs_dir, "F18")


def plot_f1(series: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    if series.empty:
        ax.set_title("F1 empty")
    else:
        for model, group in series.groupby("model_shorthand"):
            ax.plot(group["round"], group["mean_success"], label=str(model))
            if "ci_low" in group.columns:
                ax.fill_between(group["round"], group["ci_low"], group["ci_high"], alpha=0.15)
        ax.legend()
    ax.set_xlabel("population round")
    ax.set_ylabel("mean success")
    ax.set_title("F1 mixing success")
    save_png_pdf(fig, outputs_dir, "F1")


def plot_f5(series: pd.DataFrame, outputs_dir: Path) -> None:
    models = list(series["model_shorthand"].unique()) if not series.empty else ["none"]
    n = max(len(models), 1)
    fig, axes = plt.subplots(n, 1, figsize=(7, 3 * n), squeeze=False)
    for ax, model in zip(axes.ravel(), models):
        sub = series[series["model_shorthand"] == model] if not series.empty else series
        if sub.empty:
            ax.set_title(f"{model} empty")
            continue
        for topology, group in sub.groupby("topology"):
            ax.plot(group["round"], group["mean_success"], label=str(topology))
        ax.set_title(str(model))
        ax.legend(fontsize=7)
    fig.suptitle("F5 success by topology")
    save_png_pdf(fig, outputs_dir, "F5")


def plot_f7(phase: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    if phase.empty:
        ax.set_title("F7 empty")
    else:
        for topology, group in phase.groupby("topology"):
            ax.scatter(group["window_success"], group["unique_labels"], s=8, label=str(topology), alpha=0.6)
        ax.legend()
    ax.set_xlabel("windowed success")
    ax.set_ylabel("windowed unique labels")
    ax.set_title("F7 phase plot")
    save_png_pdf(fig, outputs_dir, "F7")


def plot_f14(heat: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    if heat.empty:
        ax.set_title("F14 empty")
    else:
        pivot = heat.pivot_table(index="topology", columns="cm_k", values="flip_rate")
        im = ax.imshow(pivot.to_numpy(), aspect="auto")
        ax.set_xticks(range(len(pivot.columns)), [str(c) for c in pivot.columns])
        ax.set_yticks(range(len(pivot.index)), list(pivot.index))
        fig.colorbar(im, ax=ax)
    ax.set_title("F14 topology x k")
    save_png_pdf(fig, outputs_dir, "F14")


def plot_f24(th1: pd.DataFrame, outputs_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    if th1.empty:
        ax.set_title("F24 empty")
    else:
        mean = th1["mean_dominant_share"].to_numpy(dtype=float)
        low = th1["ci_95_low"].to_numpy(dtype=float)
        high = th1["ci_95_high"].to_numpy(dtype=float)
        y = list(range(len(th1)))
        if np.isfinite(low).all() and np.isfinite(high).all():
            ax.errorbar(mean, y, xerr=[mean - low, high - mean], fmt="o")
        else:
            ax.plot(mean, y, "o")
        ax.set_yticks(y, th1["model_shorthand"].astype(str))
        ax.axvline(0.90, linestyle="--")
    ax.set_xlabel("dominant share")
    ax.set_title("F24 H1 forest")
    save_png_pdf(fig, outputs_dir, "F24")
