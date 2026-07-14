from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from munch import munchify

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
DOUG_OPEN_QUESTIONS_PATH = "01_Orga/Doug_Open_Questions.md"

# Secret-bearing fields excluded from config_hash (WORKING.md §6): the env
# var *name* a model looks up its key under, never the secret value itself
# (secrets never live in config).
_SECRET_FIELDS = {"api_key_env"}


class ConfigError(Exception):
    """Raised on missing/invalid config entries (no bare `except`, §0 principle 5)."""


def load_config(path: str | Path | None = None):
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        return munchify(yaml.safe_load(handle))


@dataclass(frozen=True)
class ModelSpec:
    shorthand: str
    provider: str
    model_id: str
    base_url: str
    api_key_env: str
    temperature: float
    max_tokens: int
    openrouter_provider: dict[str, Any] | None = None


def _parse_openrouter_provider(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = entry.get("openrouter_provider")
    if raw is None:
        return None
    return _to_plain(raw)


def resolve_model(config: Mapping[str, Any], shorthand: str) -> ModelSpec:
    """Look up a model registry entry (§11) and fail fast on unresolved placeholders.

    `mock` needs no env vars and resolves without touching the network
    (§0 zero-blocker contract). `TBD-doug` entries (gpt54/claude55, blocked
    on Doug's pinned model strings, §13 #1) raise `ConfigError` pointing at
    the open-questions doc instead of silently sending a bad request.
    """
    models = config["models"] if "models" in config else None
    if not models or shorthand not in models:
        raise ConfigError(f"Unknown model shorthand {shorthand!r}; not present in config.models")
    entry = models[shorthand]
    model_id = entry["model_id"]
    if isinstance(model_id, str) and model_id.startswith("TBD"):
        raise ConfigError(
            f"Model {shorthand!r} has an unresolved placeholder model_id ({model_id!r}); "
            f"see {DOUG_OPEN_QUESTIONS_PATH}"
        )
    base_url = entry["base_url"]
    provider = entry.get("provider")
    if not provider:
        if "openrouter.ai" in str(base_url):
            provider = "openrouter"
        elif shorthand == "mock":
            provider = "mock"
        else:
            provider = "unknown"
    openrouter_provider = _parse_openrouter_provider(entry) if provider == "openrouter" else None
    return ModelSpec(
        shorthand=shorthand,
        provider=provider,
        model_id=model_id,
        base_url=base_url,
        api_key_env=entry["api_key_env"],
        temperature=entry["temperature"],
        max_tokens=entry["max_tokens"],
        openrouter_provider=openrouter_provider,
    )


def _to_plain(obj: Any) -> Any:
    if hasattr(obj, "toDict"):
        return obj.toDict()
    if isinstance(obj, dict):
        return {key: _to_plain(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(value) for value in obj]
    return obj


def _strip_secrets(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _strip_secrets(value) for key, value in obj.items() if key not in _SECRET_FIELDS}
    if isinstance(obj, list):
        return [_strip_secrets(value) for value in obj]
    return obj


def config_hash(resolved_config: Mapping[str, Any]) -> str:
    """SHA-256[:16] of the sorted-keys canonical JSON of a resolved run config.

    Identical hash <=> identical run parameters. Secret-bearing fields
    (`api_key_env`) are excluded; the value never lives in config anyway.
    """
    cleaned = _strip_secrets(_to_plain(resolved_config))
    canonical = json.dumps(cleaned, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def derive_seeds(base_seed: int, topology: str, cm_k: int, seed_index: int) -> tuple[int, int]:
    """Deterministic (graph_seed, run_seed) for one pilot/main-study grid cell.

    SHA-256-based -- never Python's randomized `hash()` (§0 principle 2) --
    so the same inputs give the same seeds across processes/machines, and
    distinct cells give distinct seeds.
    """

    def _stable_seed(tag: str) -> int:
        key = f"{base_seed}:{topology}:{cm_k}:{seed_index}:{tag}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    return _stable_seed("graph"), _stable_seed("run")
