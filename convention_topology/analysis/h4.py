"""H4 (exploratory): incumbent-label frequencies (WORKING.md §8).

Descriptive frequencies of the modal Phase 1 incumbent label (mixing);
optional chi-square goodness-of-fit vs. uniform (scipy).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

from scipy.stats import chisquare


def h4_analysis(incumbent_labels: Sequence[str]) -> dict[str, Any]:
    labels = [label for label in incumbent_labels if label is not None]
    n = len(labels)
    if n == 0:
        return {"n": 0, "frequencies": {}}

    counts = Counter(labels)
    frequencies = {label: count / n for label, count in counts.items()}
    result: dict[str, Any] = {"n": n, "frequencies": frequencies}

    if len(counts) >= 2:
        observed = list(counts.values())
        stat, p = chisquare(observed)
        result["chi2_stat"] = float(stat)
        result["chi2_p"] = float(p)
    return result
