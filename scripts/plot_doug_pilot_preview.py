#!/usr/bin/env python3
"""Regenerate Doug pilot preview figures F2 and F3.

F2 includes mistralnemo (full grid) and llama31 **completed/censored only**
(failed runs excluded — budget/API stops, not scientific outcomes).

Run from the llm-convention-topology repo root:

    .venv/bin/python scripts/plot_doug_pilot_preview.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from convention_topology.analysis.common import load_run_table

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
OUT_DIR = REPO_ROOT / "outputs" / "mistralnemo" / "figures"

TOPOLOGY_ORDER = ["complete", "random_regular", "lattice"]
TOPOLOGY_LABELS = {
    "complete": "mixing",
    "random_regular": "random",
    "lattice": "lattice",
}

# Usable outcomes only — failed = infra/budget abort, excluded from denominators
USABLE = frozenset({"completed", "censored"})

ELIGIBLE_COLOR = "steelblue"
CENSORED_COLOR = "coral"
LLAMA_ELIGIBLE = "#2a9d8f"
LLAMA_MISSING = "#bdbdbd"

PREVIEW_DIR_CANDIDATES = [
    REPO_ROOT.parents[2] / "01_Orga" / "Doug_Pilot_Preview" / "figures",
    Path("/Users/jannikendress/Master Thesis/01_Orga/Doug_Pilot_Preview/figures"),
]


def _preview_dir() -> Path | None:
    for path in PREVIEW_DIR_CANDIDATES:
        if path.parent.exists() or path.exists():
            path.mkdir(parents=True, exist_ok=True)
            return path
    return None


def _usable(df: pd.DataFrame, model: str) -> pd.DataFrame:
    return df[
        (df["program"] == "emergence")
        & (df["model_shorthand"] == model)
        & (df["run_status"].isin(USABLE))
    ].copy()


def _gate_counts(emerg: pd.DataFrame, topology: str) -> dict[str, int]:
    g = emerg[emerg["topology"] == topology]
    eligible = int((g["run_status"] == "completed").sum())
    censored = int((g["run_status"] == "censored").sum())
    return {"eligible": eligible, "censored": censored, "n": int(len(g))}


def plot_f2_emergence_gate(df: pd.DataFrame, path: Path) -> dict:
    """Dual-model gate outcomes: mistral full grid + llama usable subset."""
    mistral = _usable(df, "mistralnemo")
    llama = _usable(df, "llama31")

    counts: dict[str, dict] = {"mistralnemo": {}, "llama31": {}}
    labels = [TOPOLOGY_LABELS[t] for t in TOPOLOGY_ORDER]

    m_elig, m_cens, l_elig, l_n = [], [], [], []
    for top in TOPOLOGY_ORDER:
        mc = _gate_counts(mistral, top)
        lc = _gate_counts(llama, top)
        counts["mistralnemo"][top] = mc
        counts["llama31"][top] = lc
        m_elig.append(mc["eligible"])
        m_cens.append(mc["censored"])
        l_elig.append(lc["eligible"])
        l_n.append(lc["n"])

    x = np.arange(len(labels))
    w = 0.2

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(x - 1.5 * w, m_elig, w, label="mistral eligible", color=ELIGIBLE_COLOR)
    ax.bar(x - 0.5 * w, m_cens, w, label="mistral censored", color=CENSORED_COLOR)
    ax.bar(x + 0.5 * w, l_elig, w, label="llama eligible (usable only)", color=LLAMA_ELIGIBLE)

    # Grey placeholder where llama has no usable runs
    missing = [0 if n > 0 else max(m_elig + m_cens + [1]) * 0.08 for n in l_n]
    ax.bar(
        x + 1.5 * w,
        missing,
        w,
        label="llama no usable runs",
        color=LLAMA_MISSING,
        alpha=0.7,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Number of runs")
    ax.set_xlabel("Topology")
    ax.set_title("Emergence: stability gate outcomes by topology")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ymax = max(m_elig + m_cens + l_elig + [1])
    ax.set_ylim(0, ymax + 2)

    for i, (e, c, le, n) in enumerate(zip(m_elig, m_cens, l_elig, l_n)):
        ax.text(i - 1.5 * w, e + 0.1, str(e), ha="center", va="bottom", fontsize=8)
        ax.text(i - 0.5 * w, c + 0.1, str(c), ha="center", va="bottom", fontsize=8)
        if n > 0:
            ax.text(i + 0.5 * w, le + 0.1, f"{le}/{n}", ha="center", va="bottom", fontsize=8)
        else:
            ax.text(i + 1.5 * w, missing[i] + 0.1, "n/a", ha="center", va="bottom", fontsize=8)

    fig.suptitle(
        "mistralnemo full grid · llama31 completed/censored only (failed = budget/API, excluded) · exploratory",
        fontsize=8,
        y=1.02,
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return counts


def plot_f3_cm_flip_vs_k(df: pd.DataFrame, path: Path) -> dict[int, float]:
    """Flip rate vs k on mixing — mistralnemo only (no usable llama CM)."""
    cm = df[
        (df["program"] == "cm")
        & (df["model_shorthand"] == "mistralnemo")
        & (df["topology"] == "complete")
        & (df["run_status"].isin(USABLE))
    ].copy()
    ks = list(range(1, 7))
    rates: dict[int, float] = {}
    n_per_k: dict[int, int] = {}
    y = []
    for k in ks:
        g = cm[cm["cm_k"] == k]
        n = len(g)
        n_per_k[k] = n
        rate = float(g["flip"].mean()) if n else float("nan")
        rates[k] = rate
        y.append(0.0 if pd.isna(rate) else rate)

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    ax.plot(ks, y, marker="o", color=ELIGIBLE_COLOR, linewidth=1.5)
    ax.axhline(0.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.set_xticks(ks)
    ax.set_xlabel("Committed minority size k")
    ax.set_ylabel("Flip rate")
    ax.set_ylim(0, 1)
    ax.set_title("Prepared CM pilot: flip rate vs. committed minority size (mixing)")
    n_note = n_per_k.get(1, 0)
    fig.suptitle(
        f"mistralnemo only · llama CM incomplete (failed/budget) · n≈{n_note} per k · exploratory",
        fontsize=8,
        y=1.02,
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return rates


def package_f1(preview: Path | None) -> list[Path]:
    written: list[Path] = []
    if preview is None:
        return written
    mapping = [
        (
            REPO_ROOT / "outputs" / "memory_decision_compare" / "p_M_emergence_compare.png",
            preview / "F1a_memory_emergence_compare.png",
        ),
        (
            REPO_ROOT / "outputs" / "mistralnemo" / "memory_decision" / "p_M_by_program.png",
            preview / "F1b_memory_mistral_by_program.png",
        ),
    ]
    for src, dst in mapping:
        if src.exists():
            shutil.copy2(src, dst)
            written.append(dst)
    return written


def main() -> None:
    df = load_run_table(DATA_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    f2_path = OUT_DIR / "F2_emergence_gate_by_topology.png"
    f3_path = OUT_DIR / "F3_cm_flip_vs_k_mixing.png"

    counts = plot_f2_emergence_gate(df, f2_path)
    rates = plot_f3_cm_flip_vs_k(df, f3_path)

    preview = _preview_dir()
    copied: list[Path] = []
    if preview is not None:
        for src in (f2_path, f3_path):
            dst = preview / src.name
            shutil.copy2(src, dst)
            copied.append(dst)
        copied.extend(package_f1(preview))

    print("F2 counts (usable completed/censored only; failed excluded):")
    for model in ("mistralnemo", "llama31"):
        print(f"  {model}:")
        for top in TOPOLOGY_ORDER:
            c = counts[model][top]
            print(
                f"    {TOPOLOGY_LABELS[top]}: "
                f"{c['eligible']} eligible + {c['censored']} censored (n_usable={c['n']})"
            )
    print("F3 flip rates (mistral mixing):")
    for k, rate in rates.items():
        print(f"  k={k}: flip_mean={rate}")
    print("Written:")
    for p in [f2_path, f3_path, *copied]:
        print(f"  {p}")


if __name__ == "__main__":
    main()
