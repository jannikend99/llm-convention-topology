"""Strict JSON enum parser for {value, reason}."""

from __future__ import annotations

import json
from typing import Sequence


class ParseError(Exception):
    """Raised when the model output is not a valid JSON decision object."""


def parse_decision(text: str, options: Sequence[str]) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped:
        raise ParseError("empty response")
    try:
        payload = json.loads(stripped, object_pairs_hook=_reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ParseError("response is not a JSON object")
    if set(payload.keys()) != {"value", "reason"}:
        raise ParseError(f"JSON keys must be exactly value and reason, got {sorted(payload)}")
    value = payload["value"]
    reason = payload["reason"]
    if not isinstance(value, str) or value not in set(options):
        raise ParseError(f"value {value!r} is not in the enum")
    if not isinstance(reason, str) or not reason.strip():
        raise ParseError("reason must be a non-empty string")
    return value, reason


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ParseError("duplicate JSON keys")
    return dict(pairs)


def json_schema_for_options(options: Sequence[str]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "naming_game_decision",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "enum": list(options)},
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": ["value", "reason"],
                "additionalProperties": False,
            },
        },
    }
