"""Versioned SHA-256 seed scheme (experimental-configuration Seeds)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


SEED_SCHEME_VERSION = 1
ENVIRONMENT_TAGS = ("pairing", "option", "committed", "committed_label")


def hash_tuple(*parts: Any) -> int:
    payload = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def graph_seed(base_seed: int, topology: str) -> int:
    return hash_tuple(base_seed, "graph", topology)


def environment_seed(
    base_seed: int,
    program: str,
    topology: str,
    cm_k: int | None,
    seed_index: int,
) -> int:
    return hash_tuple(base_seed, "environment", program, topology, cm_k, seed_index)


def model_seed(
    base_seed: int,
    model_id: str,
    program: str,
    topology: str,
    cm_k: int | None,
    seed_index: int,
) -> int:
    return hash_tuple(base_seed, "model", model_id, program, topology, cm_k, seed_index)


def substream(environment: int, tag: str) -> int:
    if tag not in ENVIRONMENT_TAGS:
        raise ValueError(f"unknown environment tag {tag!r}")
    return hash_tuple(environment, tag)


def attempt_seed(model: int, decision_id: str, attempt_index: int) -> int:
    return hash_tuple(model, "attempt", decision_id, attempt_index)
