"""Strict JSON enum parser for {value, reason}."""

from __future__ import annotations

import json
import re
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


def match_option_in_text(text: str, options: Sequence[str]) -> tuple[str, str]:
    """Diag-only: map free text onto exactly one pool option. Not the counted parser."""
    stripped = text.strip()
    if not stripped:
        raise ParseError("empty response")
    try:
        return parse_decision(stripped, options)
    except ParseError:
        pass
    hits: list[str] = []
    for option in options:
        if not option:
            continue
        if len(option) == 1:
            pattern = rf"(?<![A-Za-z0-9]){re.escape(option)}(?![A-Za-z0-9])"
            if re.search(pattern, stripped):
                hits.append(option)
        elif option in stripped:
            hits.append(option)
    uniq = list(dict.fromkeys(hits))
    if len(uniq) == 1:
        return uniq[0], stripped
    if not uniq:
        raise ParseError("no option found in text")
    raise ParseError("multiple options found in text")
