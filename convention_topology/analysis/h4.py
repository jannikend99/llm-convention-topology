"""H4 (exploratory): Study-1 mixing winners from the interaction stream + pool."""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

from scipy.stats import chisquare


def h4_analysis(winners: Sequence[str], pool: Sequence[str] | None = None) -> dict[str, Any]:
    labels = [label for label in winners if label]
    n = len(labels)
    if n == 0:
        frequencies = {label: 0.0 for label in (pool or [])}
        return {"n": 0, "frequencies": frequencies, "counts": dict.fromkeys(pool or [], 0)}

    counts = Counter(labels)
    if pool:
        for label in pool:
            counts.setdefault(label, 0)
    frequencies = {label: count / n for label, count in counts.items()}
    result: dict[str, Any] = {"n": n, "frequencies": frequencies, "counts": dict(counts)}

    keys = list(pool) if pool else list(counts)
    observed = [counts[label] for label in keys]
    if len(observed) >= 2 and n >= 2 and any(v > 0 for v in observed):
        try:
            stat, p = chisquare(observed)
            result["chi2_stat"] = float(stat)
            result["chi2_p"] = float(p)
        except ValueError:
            pass
    return result
