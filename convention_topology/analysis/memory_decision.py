"""Memory decision-function analysis (Doug ask / TODO #4b).

For each non-committed agent decision at index ``t``, take the previous
``M`` partner (or pooled) labels, compute the modal label, and score whether
the agent's choice at ``t`` matches that mode. Ties are excluded from the
hit rate denominator.

Exploratory only — not confirmatory H1–H3b evidence.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import matplotlib.pyplot as plt
import pandas as pd

from convention_topology.analysis.common import scan_meta_paths
from convention_topology.persistence import (
    PersistenceError,
    load_run_pickle,
    read_meta,
    write_analysis_csv,
    write_analysis_json,
)

MEMORY_SIZES = (1, 2, 3, 4, 5)
VALID_STATUSES = frozenset({"completed", "censored"})


def modal_label(items: Sequence[str]) -> tuple[str | None, bool]:
    """Return ``(mode, is_tie)``. Empty input → ``(None, True)``."""
    if not items:
        return None, True
    counts = Counter(items)
    top = counts.most_common()
    if len(top) >= 2 and top[0][1] == top[1][1]:
        return None, True
    return top[0][0], False


def decision_rows_for_agent(
    *,
    run_id: str,
    program: str | None,
    topology: str | None,
    model_shorthand: str | None,
    agent_id: int,
    my_history: Sequence[str],
    partner_history: Sequence[str],
    memory_sizes: Sequence[int] = MEMORY_SIZES,
) -> list[dict[str, Any]]:
    """Emit one row per (t, M) for a non-committed agent."""
    n = len(my_history)
    if n != len(partner_history) or n == 0:
        return []

    rows: list[dict[str, Any]] = []
    for t in range(1, n):  # t=0 has empty pre-decision memory
        choice = my_history[t]
        for m in memory_sizes:
            start = max(0, t - m)
            partner_window = list(partner_history[start:t])
            pooled_window = list(my_history[start:t]) + list(partner_history[start:t])

            mode_partner, tie_partner = modal_label(partner_window)
            mode_pooled, tie_pooled = modal_label(pooled_window)

            hit_partner = None if tie_partner else int(choice == mode_partner)
            hit_pooled = None if tie_pooled else int(choice == mode_pooled)

            rows.append(
                {
                    "run_id": run_id,
                    "program": program,
                    "topology": topology,
                    "model_shorthand": model_shorthand,
                    "agent_id": agent_id,
                    "t": t,
                    "M": m,
                    "choice": choice,
                    "mode_partner": mode_partner,
                    "tie_partner": tie_partner,
                    "hit_partner": hit_partner,
                    "mode_pooled": mode_pooled,
                    "tie_pooled": tie_pooled,
                    "hit_pooled": hit_pooled,
                    "window_len": len(partner_window),
                }
            )
    return rows


def extract_decisions(
    data_dir: Path,
    model_filter: str | None = None,
    *,
    memory_sizes: Sequence[int] = MEMORY_SIZES,
) -> pd.DataFrame:
    """Scan run pickles and return a long decision table."""
    rows: list[dict[str, Any]] = []
    for meta_path in scan_meta_paths(data_dir):
        try:
            meta = read_meta(meta_path)
        except PersistenceError:
            continue
        if model_filter and meta.get("model_shorthand") != model_filter:
            continue
        if meta.get("run_status") not in VALID_STATUSES:
            continue

        pickle_path = Path(meta_path).with_suffix("").with_suffix(".pkl")
        try:
            payload = load_run_pickle(pickle_path)
        except PersistenceError:
            continue

        simulation = payload["simulation"]
        for agent_id, player in simulation.items():
            if player.get("committed_tag"):
                continue
            rows.extend(
                decision_rows_for_agent(
                    run_id=meta.get("run_id", pickle_path.stem),
                    program=meta.get("program"),
                    topology=meta.get("topology"),
                    model_shorthand=meta.get("model_shorthand"),
                    agent_id=int(agent_id),
                    my_history=player.get("my_history") or [],
                    partner_history=player.get("partner_history") or [],
                    memory_sizes=memory_sizes,
                )
            )
    return pd.DataFrame(rows)


def summarize_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hit rates by program × topology × M (partner primary + pooled)."""
    if decisions.empty:
        return pd.DataFrame(
            columns=[
                "program",
                "topology",
                "M",
                "n_decisions",
                "n_valid_partner",
                "n_ties_partner",
                "p_partner",
                "n_valid_pooled",
                "n_ties_pooled",
                "p_pooled",
            ]
        )

    records: list[dict[str, Any]] = []
    group_cols = ["program", "topology", "M"]
    for keys, group in decisions.groupby(group_cols, dropna=False):
        program, topology, m = keys
        n = len(group)
        valid_p = group["hit_partner"].notna()
        valid_o = group["hit_pooled"].notna()
        n_valid_p = int(valid_p.sum())
        n_valid_o = int(valid_o.sum())
        records.append(
            {
                "program": program,
                "topology": topology,
                "M": int(m),
                "n_decisions": n,
                "n_valid_partner": n_valid_p,
                "n_ties_partner": n - n_valid_p,
                "p_partner": float(group.loc[valid_p, "hit_partner"].mean()) if n_valid_p else None,
                "n_valid_pooled": n_valid_o,
                "n_ties_pooled": n - n_valid_o,
                "p_pooled": float(group.loc[valid_o, "hit_pooled"].mean()) if n_valid_o else None,
            }
        )
    return pd.DataFrame(records).sort_values(["program", "topology", "M"]).reset_index(drop=True)


def summarize_by_program(decisions: pd.DataFrame) -> pd.DataFrame:
    """Coarser aggregate: program × M only (for the main plot)."""
    if decisions.empty:
        return pd.DataFrame(columns=["program", "M", "n_valid_partner", "p_partner", "n_valid_pooled", "p_pooled"])

    records: list[dict[str, Any]] = []
    for (program, m), group in decisions.groupby(["program", "M"], dropna=False):
        valid_p = group["hit_partner"].notna()
        valid_o = group["hit_pooled"].notna()
        n_valid_p = int(valid_p.sum())
        n_valid_o = int(valid_o.sum())
        records.append(
            {
                "program": program,
                "M": int(m),
                "n_valid_partner": n_valid_p,
                "p_partner": float(group.loc[valid_p, "hit_partner"].mean()) if n_valid_p else None,
                "n_valid_pooled": n_valid_o,
                "p_pooled": float(group.loc[valid_o, "hit_pooled"].mean()) if n_valid_o else None,
            }
        )
    return pd.DataFrame(records).sort_values(["program", "M"]).reset_index(drop=True)


def plot_p_m_by_program(by_program: pd.DataFrame, path: Path) -> None:
    """Line plot of partner-mode hit rate vs M, one line per program."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    if not by_program.empty:
        for program, group in by_program.groupby("program"):
            g = group.sort_values("M")
            ax.plot(g["M"], g["p_partner"], marker="o", label=str(program))
    ax.set_xlabel("Memory size M")
    ax.set_ylabel(r"$P$(choose modal partner label)")
    ax.set_xticks(list(MEMORY_SIZES))
    ax.set_ylim(0, 1.05)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.legend(title="Program")
    ax.set_title("Memory decision function (partner mode)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_findings(
    path: Path,
    *,
    model: str,
    summary: pd.DataFrame,
    by_program: pd.DataFrame,
    n_runs: int,
    n_decisions: int,
    caveats: Sequence[str] | None = None,
) -> None:
    """Short markdown note for Doug / TODO #4b."""
    default_caveats = [
        f"Exploratory analysis on `{model}` only — compare models via "
        "`outputs/memory_decision_compare/` when multiple models are available.",
        "Prepared CM runs start with incumbent-filled memory — early rounds are "
        "near-deterministic under a majority rule.",
        "Primary definition uses **partner** history (social signal in the prompt).",
    ]
    caveat_lines = list(caveats) if caveats is not None else default_caveats

    lines = [
        f"# Memory decision-function — `{model}`",
        "",
        "**Status:** exploratory (Doug ask / TODO #4b). **Not** Methods / confirmatory evidence.",
        "",
        "---",
        "",
        "## Limitations (read first)",
        "",
    ]
    for i, c in enumerate(caveat_lines, start=1):
        lines.append(f"{i}. {c}")
    lines.extend(
        [
            "",
            "---",
            "",
            "## Method",
            "",
            "For each non-committed agent decision at index `t`, take the previous `M` "
            "entries of `partner_history` (primary) or `my_history + partner_history` "
            "(pooled robustness). Compute the modal label; score a **hit** if the agent's "
            "choice equals the mode. Frequency ties are excluded from the hit-rate "
            "denominator. Evaluated for `M ∈ {1,…,5}` (prompt memory window).",
            "",
            f"- Runs scanned: **{n_runs}** (`completed` / `censored`)",
            f"- Decision rows: **{n_decisions:,}** (all M × decisions)",
            "",
            "## Partner-mode hit rate by program",
            "",
            "| Program | M | n_valid | p_partner |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    if by_program.empty:
        lines.append("| — | — | — | — |")
    else:
        for _, row in by_program.iterrows():
            p = row["p_partner"]
            p_str = f"{p:.3f}" if p is not None and pd.notna(p) else "—"
            lines.append(
                f"| {row['program']} | {int(row['M'])} | {int(row['n_valid_partner'])} | {p_str} |"
            )

    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `decisions.csv` — decision-level table",
            "- `summary.csv` / `summary.json` — program × topology × M",
            "- `p_M_by_program.png` — figure",
            "",
        ]
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def plot_p_m_compare(compare_df: pd.DataFrame, path: Path, *, program: str = "emergence") -> None:
    """Overlay partner-mode p(M) across models for one program."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    subset = compare_df[compare_df["program"] == program] if not compare_df.empty else compare_df
    if not subset.empty:
        for model, group in subset.groupby("model"):
            g = group.sort_values("M")
            ax.plot(g["M"], g["p_partner"], marker="o", label=str(model))
    ax.set_xlabel("Memory size M")
    ax.set_ylabel(r"$P$(choose modal partner label)")
    ax.set_xticks(list(MEMORY_SIZES))
    ax.set_ylim(0, 1.05)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.legend(title="Model")
    ax.set_title(f"Memory decision function — {program} (partner mode)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def compare_memory_decision(
    data_dir: Path,
    outputs_dir: Path,
    *,
    models: Sequence[str],
    memory_sizes: Sequence[int] = MEMORY_SIZES,
) -> dict[str, Any]:
    """Per-model extract + side-by-side emergence comparison for Doug."""
    out = Path(outputs_dir) / "memory_decision_compare"
    out.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    per_model: dict[str, Any] = {}
    for model in models:
        payload = run_memory_decision(
            data_dir, outputs_dir, model=model, memory_sizes=memory_sizes
        )
        per_model[model] = {
            "n_runs": payload["n_runs"],
            "n_decision_rows": payload["n_decision_rows"],
            "by_program": payload["by_program"],
        }
        by_prog = pd.DataFrame(payload["by_program"])
        if not by_prog.empty:
            by_prog = by_prog.copy()
            by_prog["model"] = model
            frames.append(by_prog)

    compare_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    write_analysis_csv(out / "by_program_compare.csv", compare_df)
    write_analysis_json(
        out / "compare.json",
        {"models": list(models), "per_model": per_model, "by_program": compare_df.to_dict(orient="records")},
    )
    plot_p_m_compare(compare_df, out / "p_M_emergence_compare.png", program="emergence")
    if not compare_df.empty and (compare_df["program"] == "cm").any():
        plot_p_m_compare(compare_df, out / "p_M_cm_compare.png", program="cm")

    # Comparison FINDINGS (emergence focus — Llama CM incomplete)
    lines = [
        "# Memory decision-function — model comparison",
        "",
        "**Status:** exploratory (Doug ask / TODO #4b). **Not** Methods / confirmatory evidence.",
        "",
        "---",
        "",
        "## Limitations (read first)",
        "",
        "These constrain how far the cross-model claim should travel:",
        "",
        "1. **Unequal samples.** `mistralnemo` = full **72/72** pilot grid. `llama31` usable = "
        "**21 emergence runs only** (12 mixing + 9 lattice). Most Llama CM and `random_regular` "
        "runs on the server are **`failed`** — **no CM decision-function comparison**.",
        "2. **Label-pool mismatch.** Mistral emergence used **A–J**; Llama used the **Ashery** set "
        "`Q,M,X,Y,F,J,P,R,C,D`. Macro outcomes (gates, winners) are not directly comparable; "
        "the local majority-match rate is still informative but **not a matched factorial contrast**.",
        "3. **Model ID.** Shorthand `llama31` here is Together "
        "**`meta-llama/Llama-3.3-70B-Instruct-Turbo`**, not a self-hosted Llama-3.1-70B main-study run.",
        "4. **Exploratory only.** Descriptive p(M) curves — no hypothesis test, not thesis Results.",
        "",
        "---",
        "",
        "## Partner-mode hit rate (emergence)",
        "",
        "| Model | M=1 | M=2 | M=5 | n_runs used |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for model in models:
        sub = compare_df[(compare_df["model"] == model) & (compare_df["program"] == "emergence")]
        if sub.empty:
            lines.append(f"| `{model}` | — | — | — | 0 |")
            continue

        def _p(m: int) -> str:
            row = sub[sub["M"] == m]
            if row.empty or pd.isna(row.iloc[0]["p_partner"]):
                return "—"
            return f"{float(row.iloc[0]['p_partner']):.3f}"

        n_runs = per_model[model]["n_runs"]
        n_note = f"**{n_runs}**"
        if model == "mistralnemo":
            n_note = f"**{n_runs}** (full grid)"
        elif model == "llama31":
            n_note = f"**{n_runs}** (emergence subset)"
        lines.append(f"| `{model}` | {_p(1)} | {_p(2)} | {_p(5)} | {n_note} |")

    lines.extend(
        [
            "",
            "## Interpretation (directional, subject to limitations above)",
            "",
            "- Both models follow the modal partner label far above chance in emergence.",
            "- **`llama31` looks more majority-following** than `mistralnemo` at every M "
            "(e.g. p5 ≈ 0.93 vs 0.84) — **directional only**, given the sample and label-pool caveats.",
            "- Highest rates often at **M=2** (short local streak matching).",
            "- **Do not** generalize to CM or to a completed multi-model pilot until Llama CM / "
            "full grid exists.",
            "",
            "## Files",
            "",
            "- `p_M_emergence_compare.png`",
            "- `by_program_compare.csv` / `compare.json`",
            "- Per-model detail: `outputs/{model}/memory_decision/`",
            "",
        ]
    )
    (out / "FINDINGS.md").write_text("\n".join(lines), encoding="utf-8")
    return {"out": str(out), "models": list(models), "per_model": per_model}


def run_memory_decision(
    data_dir: Path,
    outputs_dir: Path,
    *,
    model: str,
    memory_sizes: Sequence[int] = MEMORY_SIZES,
) -> dict[str, Any]:
    """Extract, aggregate, plot, and write FINDINGS under ``outputs/{model}/memory_decision/``."""
    out = Path(outputs_dir) / model / "memory_decision"
    out.mkdir(parents=True, exist_ok=True)

    decisions = extract_decisions(data_dir, model_filter=model, memory_sizes=memory_sizes)
    summary = summarize_decisions(decisions)
    by_program = summarize_by_program(decisions)

    write_analysis_csv(out / "decisions.csv", decisions)
    write_analysis_csv(out / "summary.csv", summary)
    write_analysis_csv(out / "by_program.csv", by_program)

    payload = {
        "model": model,
        "memory_sizes": list(memory_sizes),
        "n_decision_rows": int(len(decisions)),
        "n_runs": int(decisions["run_id"].nunique()) if not decisions.empty else 0,
        "by_program": by_program.to_dict(orient="records"),
        "summary": summary.to_dict(orient="records"),
        "definition": {
            "primary": "mode of partner_history[t-M:t]",
            "robustness": "mode of my_history[t-M:t] + partner_history[t-M:t]",
            "ties": "excluded from hit-rate denominator",
            "agents": "non-committed only",
        },
    }
    write_analysis_json(out / "summary.json", payload)

    if model == "mistralnemo":
        caveats = [
            "**Infra pilot, not thesis data** — full 72/72 grid, excluded from Methods / H1–H3.",
            "**Label-pool confound** — emergence used **A–J**, not Ashery Q/M/X/… (WORKING.md §17).",
            "**CM** — prepared incumbent + committed minorities disrupt partner majorities; "
            "lower CM p(M) is expected.",
            "Cross-model: see `outputs/memory_decision_compare/FINDINGS.md` "
            "(Llama sample is partial).",
        ]
    elif model == "llama31":
        caveats = [
            "**Partial data only** — **21** usable emergence runs (12 mixing + 9 lattice); "
            "most CM / random_regular runs **failed** — **no CM results**.",
            "**Not a full Llama pilot** — do not treat scope as equal to mistralnemo’s 72-run grid.",
            "**Model ID** — Together `Llama-3.3-70B-Instruct-Turbo` (shorthand `llama31`), "
            "not Stanford HPC Llama-3.1-70B.",
            "**Letter pool** — Ashery Q/M/X/… (mismatched vs mistral A–J).",
        ]
    else:
        caveats = None

    plot_p_m_by_program(by_program, out / "p_M_by_program.png")
    write_findings(
        out / "FINDINGS.md",
        model=model,
        summary=summary,
        by_program=by_program,
        n_runs=payload["n_runs"],
        n_decisions=payload["n_decision_rows"],
        caveats=caveats,
    )
    return payload
