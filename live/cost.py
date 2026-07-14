"""Token/cost aggregation from `token_usage` events (WORKING.md §9 cost panel).

Read-only: consumes `live.reader.events_dataframe()` output, never opens
pickles or writes anything.
"""

from __future__ import annotations

import pandas as pd

# USD per 1M tokens (prompt, completion). OpenRouter / Google list pricing,
# July 2026 snapshot -- update alongside the model registry (§7.4).
# Best-effort: an unknown model_id falls back to a zero rate (cost panel
# stays best-effort if provider `usage` is absent, per WORKING §9 watch-out).
PRICE_TABLE_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "meta-llama/llama-3.1-70b-instruct": (0.40, 0.40),
    "qwen/qwen-2.5-72b-instruct": (0.36, 0.40),
    "gemini-3.5-flash": (0.15, 0.60),
    "mock": (0.0, 0.0),
}

DEFAULT_RATE_USD_PER_MILLION = (0.0, 0.0)


def estimate_cost_usd(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_rate, completion_rate = PRICE_TABLE_USD_PER_MILLION.get(model_id, DEFAULT_RATE_USD_PER_MILLION)
    return (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000


def cost_summary(events: pd.DataFrame) -> pd.DataFrame:
    """Per-model cumulative token totals and $ estimate from `token_usage` events."""
    columns = ["model_id", "prompt_tokens", "completion_tokens", "n_calls", "cost_usd"]
    if events.empty or "type" not in events.columns:
        return pd.DataFrame(columns=columns)

    usage = events[events["type"] == "token_usage"].copy()
    if usage.empty:
        return pd.DataFrame(columns=columns)

    for col in ("prompt_tokens", "completion_tokens"):
        if col not in usage.columns:
            usage[col] = 0
        usage[col] = usage[col].fillna(0)

    grouped = usage.groupby("model_id").agg(
        prompt_tokens=("prompt_tokens", "sum"),
        completion_tokens=("completion_tokens", "sum"),
        n_calls=("model_id", "count"),
    ).reset_index()

    grouped["cost_usd"] = grouped.apply(
        lambda row: estimate_cost_usd(row["model_id"], row["prompt_tokens"], row["completion_tokens"]),
        axis=1,
    )
    return grouped[columns]
