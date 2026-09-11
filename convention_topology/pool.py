"""Campaign 5-character lowercase label pool."""

from __future__ import annotations

import hashlib
import json
import random
import string
from typing import Sequence


ALPHABET = string.ascii_lowercase


def draw_pool(*, seed: int, string_length: int = 5, size: int = 10) -> list[str]:
    rng = random.Random(seed)
    labels: list[str] = []
    seen: set[str] = set()
    while len(labels) < size:
        token = "".join(rng.choice(ALPHABET) for _ in range(string_length))
        if token not in seen:
            seen.add(token)
            labels.append(token)
    return labels


def pool_sha256(labels: Sequence[str]) -> str:
    canonical = json.dumps(list(labels), separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def options_for_program(pool: Sequence[str], program: str) -> list[str]:
    if program == "emergence":
        return list(pool)
    if program == "cm":
        return [pool[0], pool[1]]
    raise ValueError(f"unknown program {program!r}")
