"""Load and validate the single counted-path config.yaml."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

TOPOLOGIES = ("mixing", "random_regular", "lattice", "watts_strogatz", "barabasi_albert")
K_SET = (2, 4, 6, 8, 10, 12)
SERVE_PROFILE_KEYS = (
    "dtype",
    "quantization",
    "gpus",
    "tp",
    "max_model_len",
    "max_concurrent_runs",
    "in_flight_limit",
    "max_num_seqs",
    "seed_indices_per_slice",
    "max_tokens",
)
CLOUD_PROVIDERS = frozenset(
    {"together", "openrouter", "anthropic", "google", "deepinfra", "openai"}
)
BANNED_CONFIG_KEYS = frozenset(
    {
        "convergence_time",
        "options_emergence",
        "options_cm",
        "memory_size_set",
        "minority_size_set",
        "main_eligible_targets",
        "attempted_cap_factor",
        "pilot_attempted_per_topology",
        "workers",
        "TBD-doug",
        "slate",
    }
)
BANNED_CAMPAIGN_NAMES = frozenset({"slate-a", "fit-slate-a"})

LOCK_PROTOCOL = {
    "N": 48,
    "H": 12,
    "string_length": 5,
    "W_emergence": 10,
    "W_cm": 2,
    "gate_threshold": 0.95,
    "gate_window": 144,
    "cap_phase1": 5000,
    "phase2_horizon": 1000,
    "rewards_mismatch": -50,
    "rewards_match": 100,
    "success_rule": "payoff_gt_5",
    "retry_max_attempts": 3,
    "temperature": 0.5,
}


class ConfigError(Exception):
    """Invalid counted-path configuration."""


@dataclass(frozen=True)
class ModelSpec:
    shorthand: str
    provider: str
    model_id: str
    revision: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    thinking: bool
    thinking_always_on: bool
    reasoning_effort: str | None
    dtype: str | None
    quantization: str | None
    gpus: int
    tp: int
    max_model_len: int
    max_concurrent_runs: int
    in_flight_limit: int
    max_num_seqs: int
    seed_indices_per_slice: dict[str, int]
    fallback_from: str | None = None
    send_chat_template_kwargs: bool = True
    thinking_token_budget: int | None = None


def _plain(obj: Any) -> Any:
    if hasattr(obj, "toDict"):
        return obj.toDict()
    if isinstance(obj, dict):
        return {key: _plain(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(value) for value in obj]
    return obj


def _walk_keys(obj: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            keys.add(str(key))
            keys |= _walk_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _walk_keys(item)
    return keys


def is_localhost_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).hostname
    return host in {"127.0.0.1", "localhost", "::1"}


def _reject_banned(raw: Mapping[str, Any]) -> None:
    keys = _walk_keys(raw)
    banned_hit = sorted(keys & BANNED_CONFIG_KEYS)
    if banned_hit:
        raise ConfigError(f"banned config keys present: {banned_hit}")
    blob = json.dumps(_plain(raw), default=str)
    if "TBD-doug" in blob:
        raise ConfigError("banned placeholder TBD-doug is not allowed")
    protocol = raw.get("protocol") or {}
    if protocol.get("N") == 24:
        raise ConfigError("N=24 is banned; locked N is 48")
    if protocol.get("H") == 5:
        raise ConfigError("H=5 is banned; locked H is 12")
    if protocol.get("gate_window") == 72:
        raise ConfigError("gate_window 72 is banned; locked window is 144")
    network = raw.get("network") or {}
    topologies = list(network.get("topologies") or [])
    if "complete" in topologies:
        raise ConfigError("topology id mixing is required; complete is banned")
    minority = raw.get("minority") or {}
    k_set = list(minority.get("k_set") or [])
    if k_set == [1, 2, 3, 4, 5, 6] or k_set == list(range(1, 7)):
        raise ConfigError("k in {1..6} is banned; locked k_set is [2, 4, 6, 8, 10, 12]")
    run = raw.get("run") or {}
    if run.get("checkpoint_every") == 50:
        raise ConfigError("checkpoint_every 50 is banned; locked value is 1")
    serve = raw.get("serve") or {}
    provider = str(serve.get("provider") or "")
    if provider in CLOUD_PROVIDERS:
        raise ConfigError(f"cloud provider {provider!r} is banned on the counted path")
    models = raw.get("models") or {}
    for name, entry in models.items():
        if not isinstance(entry, dict):
            continue
        model_provider = str(entry.get("provider") or "")
        if model_provider in CLOUD_PROVIDERS:
            raise ConfigError(f"cloud provider {model_provider!r} on model {name!r} is banned")
        if str(entry.get("model_id") or "").startswith("TBD"):
            raise ConfigError(f"model {name!r} has a banned TBD placeholder")


def _validate_protocol(raw: Mapping[str, Any]) -> None:
    protocol = raw.get("protocol")
    if not isinstance(protocol, dict):
        raise ConfigError("config must contain a protocol section")
    for key, expected in LOCK_PROTOCOL.items():
        if key not in protocol:
            raise ConfigError(f"protocol missing locked key {key!r}")
        if protocol[key] != expected:
            raise ConfigError(
                f"protocol.{key}={protocol[key]!r} does not equal lock {expected!r}"
            )
    extra_protocol = sorted(set(protocol) - set(LOCK_PROTOCOL))
    if extra_protocol:
        raise ConfigError(f"protocol has unlocked keys: {extra_protocol}")
    n = int(protocol["N"])
    computed_window = 3 * n
    if int(protocol["gate_window"]) != computed_window:
        raise ConfigError(
            f"protocol.gate_window must equal 3*N={computed_window}, got {protocol['gate_window']!r}"
        )
    network = raw.get("network")
    if not isinstance(network, dict):
        raise ConfigError("config must contain a network section")
    topologies = tuple(network.get("topologies") or ())
    if topologies != TOPOLOGIES:
        raise ConfigError(f"network.topologies must be {list(TOPOLOGIES)}, got {list(topologies)}")
    if int(network.get("degree")) != 4:
        raise ConfigError("network.degree must be 4")
    if int(network.get("ws_k")) != 4 or float(network.get("ws_p")) != 0.1:
        raise ConfigError("WS parameters must be ws_k=4, ws_p=0.1")
    if int(network.get("ba_m")) != 2:
        raise ConfigError("BA parameter must be ba_m=2")
    if network.get("require_connected") is not True:
        raise ConfigError("network.require_connected must be true")
    minority = raw.get("minority")
    if not isinstance(minority, dict):
        raise ConfigError("config must contain a minority section")
    k_set = tuple(int(v) for v in minority.get("k_set") or ())
    if k_set != K_SET:
        raise ConfigError(f"minority.k_set must be {list(K_SET)}")
    if minority.get("mode") != "swap":
        raise ConfigError("minority.mode must be swap")
    pool = raw.get("pool")
    if not isinstance(pool, dict) or "seed" not in pool:
        raise ConfigError("pool.seed is required")
    extra_pool = sorted(set(pool) - {"seed"})
    if extra_pool:
        raise ConfigError(f"pool has unlocked keys: {extra_pool}")
    run = raw.get("run")
    if not isinstance(run, dict):
        raise ConfigError("config must contain a run section")
    if int(run.get("attempted_per_cell")) != 32:
        raise ConfigError("run.attempted_per_cell must be 32")
    if run.get("sampling_plan") != "fixed_attempted":
        raise ConfigError("run.sampling_plan must be fixed_attempted")
    if int(run.get("checkpoint_every")) != 1:
        raise ConfigError("run.checkpoint_every must be 1")
    if int(run.get("seed_scheme_version")) != 1:
        raise ConfigError("run.seed_scheme_version must be 1")
    check_campaign_name(str(run.get("campaign") or ""))
    serve = raw.get("serve")
    if not isinstance(serve, dict):
        raise ConfigError("config must contain a serve section")
    provider = serve.get("provider")
    if provider not in {"openai_compat", "mock"}:
        raise ConfigError("serve.provider must be openai_compat or mock")
    if serve.get("api_key") != "EMPTY":
        raise ConfigError("serve.api_key must be EMPTY")
    base_url = str(serve.get("base_url") or "")
    if provider != "mock" and not is_localhost_url(base_url):
        raise ConfigError("non-localhost serve.base_url fails unless provider is mock")
    if "serve_wait_timeout" not in serve:
        raise ConfigError("serve.serve_wait_timeout is required")


def _validate_models(raw: Mapping[str, Any]) -> None:
    models = raw.get("models")
    if not isinstance(models, dict) or "mock" not in models:
        raise ConfigError("models.mock is required")
    jobs = raw.get("jobs") or {}
    job_models = jobs.get("models")
    if not isinstance(job_models, list) or not job_models:
        raise ConfigError("jobs.models must be a non-empty list")
    programs = list(jobs.get("programs") or [])
    if programs and set(programs) - {"emergence", "cm"}:
        raise ConfigError("jobs.programs must be emergence and/or cm")
    for shorthand, entry in models.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"model {shorthand!r} must be a mapping")
        missing = [key for key in SERVE_PROFILE_KEYS if key not in entry]
        if missing:
            raise ConfigError(f"model {shorthand!r} missing serve-profile keys: {missing}")
        if entry.get("max_tokens") in (None, 0, ""):
            raise ConfigError(f"model {shorthand!r} requires max_tokens")
        slices = entry.get("seed_indices_per_slice")
        if not isinstance(slices, dict) or "emergence" not in slices or "cm" not in slices:
            raise ConfigError(f"model {shorthand!r} needs seed_indices_per_slice for both programs")
        if not isinstance(entry.get("thinking"), bool):
            raise ConfigError(f"model {shorthand!r} thinking must be a boolean")
        if "send_chat_template_kwargs" in entry and not isinstance(
            entry.get("send_chat_template_kwargs"), bool
        ):
            raise ConfigError(f"model {shorthand!r} send_chat_template_kwargs must be a boolean")
        effort = entry.get("reasoning_effort")
        if effort not in (None, "low", "medium", "high"):
            raise ConfigError(f"model {shorthand!r} has invalid reasoning_effort")
        if effort == "high" and not entry.get("thinking_always_on"):
            raise ConfigError("reasoning_effort high is not allowed when none vs high is the only control")
        budget = entry.get("thinking_token_budget")
        if budget is not None:
            if not entry.get("thinking"):
                raise ConfigError(f"model {shorthand!r} thinking_token_budget requires thinking")
            if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
                raise ConfigError(f"model {shorthand!r} thinking_token_budget must be a positive int")
            if budget >= int(entry["max_tokens"]):
                raise ConfigError(f"model {shorthand!r} thinking_token_budget must be below max_tokens")
    for name in job_models:
        if name not in models:
            raise ConfigError(f"jobs.models lists unknown shorthand {name!r}")


def validate_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = _plain(raw)
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")
    _reject_banned(data)
    required = ("protocol", "network", "minority", "pool", "run", "jobs", "serve", "models")
    missing = [section for section in required if section not in data]
    if missing:
        raise ConfigError(f"config missing sections: {missing}")
    _validate_protocol(data)
    _validate_models(data)
    return data


def check_campaign_name(name: str) -> str:
    campaign = str(name or "").strip()
    if not campaign:
        raise ConfigError("run.campaign is required")
    if campaign in BANNED_CAMPAIGN_NAMES:
        raise ConfigError(
            f"campaign {campaign!r} is banned; use technical-smoke, pilot-run, or experiment"
        )
    return campaign


# Ashery emergence ten-letter set (not a counted default; diag campaigns only).
DIAG_LETTER_POOL = ("Q", "M", "X", "Y", "F", "J", "P", "R", "C", "D")


DIAG_DECODE_VALUES = ("json_schema", "parse")


def apply_diag_protocol(
    config: dict[str, Any],
    *,
    memory_h: int,
    pool_kind: str,
    cap_phase1: int | None = None,
    population_n: int | None = None,
    decode: str | None = None,
) -> dict[str, Any]:
    """Override H / pool / N / decode after validate_config. Counted defaults stay locked."""
    campaign = str(config["run"]["campaign"])
    if not campaign.startswith("diag-"):
        raise ConfigError("diag protocol overrides require a campaign name starting with diag-")
    if memory_h not in (5, 12):
        raise ConfigError("diag memory_h must be 5 or 12")
    if pool_kind not in ("strings", "letters"):
        raise ConfigError("diag pool_kind must be strings or letters")
    config["protocol"]["H"] = int(memory_h)
    if population_n is not None:
        n = int(population_n)
        if n not in (24, 48):
            raise ConfigError("diag population_n must be 24 or 48")
        config["protocol"]["N"] = n
        config["protocol"]["gate_window"] = 3 * n
    if decode is not None:
        kind = str(decode)
        if kind not in DIAG_DECODE_VALUES:
            raise ConfigError("diag decode must be json_schema or parse")
        config["protocol"]["diag_decode"] = kind
    if cap_phase1 is not None:
        cap = int(cap_phase1)
        if cap < int(LOCK_PROTOCOL["gate_window"]) or cap > int(LOCK_PROTOCOL["cap_phase1"]):
            raise ConfigError("diag cap_phase1 must lie between the gate window and the counted cap")
        config["protocol"]["cap_phase1"] = cap
    if pool_kind == "letters":
        config["protocol"]["string_length"] = 1
        config["pool"]["labels"] = list(DIAG_LETTER_POOL)
    else:
        config["pool"].pop("labels", None)
        config["protocol"]["string_length"] = int(LOCK_PROTOCOL["string_length"])
    return config


def apply_diag_tech_interactions(config: dict[str, Any], n_interactions: int) -> dict[str, Any]:
    """Stop after a few pairings so a serve smoke does not run the gate/cap."""
    campaign = str(config["run"]["campaign"])
    if not campaign.startswith("diag-"):
        raise ConfigError("diag tech interactions require a campaign name starting with diag-")
    n = int(n_interactions)
    if n < 1 or n > 20:
        raise ConfigError("diag tech interactions must be between 1 and 20")
    config["protocol"]["cap_phase1"] = n
    return config



def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return validate_config(raw)


def resolve_model(config: Mapping[str, Any], shorthand: str) -> ModelSpec:
    models = config.get("models") or {}
    if shorthand not in models:
        raise ConfigError(f"Unknown model shorthand {shorthand!r}")
    entry = models[shorthand]
    serve = config["serve"]
    provider = "mock" if shorthand == "mock" else serve["provider"]
    base_url = "" if provider == "mock" else str(serve["base_url"])
    if provider != "mock" and not is_localhost_url(base_url):
        raise ConfigError("non-localhost base_url fails unless provider is mock")
    return ModelSpec(
        shorthand=shorthand,
        provider=provider,
        model_id=str(entry["model_id"]),
        revision=str(entry.get("revision") or ""),
        base_url=base_url,
        api_key=str(serve.get("api_key") or "EMPTY"),
        temperature=float(config["protocol"]["temperature"]),
        max_tokens=int(entry["max_tokens"]),
        thinking=bool(entry["thinking"]),
        thinking_always_on=bool(entry["thinking_always_on"]),
        reasoning_effort=entry.get("reasoning_effort"),
        dtype=entry.get("dtype"),
        quantization=entry.get("quantization"),
        gpus=int(entry["gpus"]),
        tp=int(entry["tp"]),
        max_model_len=int(entry["max_model_len"]),
        max_concurrent_runs=int(entry["max_concurrent_runs"]),
        in_flight_limit=int(entry["in_flight_limit"]),
        max_num_seqs=int(entry["max_num_seqs"]),
        seed_indices_per_slice={
            "emergence": int(entry["seed_indices_per_slice"]["emergence"]),
            "cm": int(entry["seed_indices_per_slice"]["cm"]),
        },
        fallback_from=entry.get("fallback_from"),
        send_chat_template_kwargs=bool(entry.get("send_chat_template_kwargs", True)),
        thinking_token_budget=entry.get("thinking_token_budget"),
    )


def config_hash(resolved_config: Mapping[str, Any]) -> str:
    canonical = json.dumps(_plain(resolved_config), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


_TRAJECTORY_MODULES = ("prompting.py", "llm.py", "persistence.py")


def trajectory_module_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in _TRAJECTORY_MODULES
    }


def apply_serve_base_url(config: dict[str, Any], url: str) -> None:
    if config["serve"]["provider"] != "mock" and not is_localhost_url(url):
        raise ConfigError("non-localhost serve.base_url fails unless provider is mock")
    config["serve"]["base_url"] = url


def protocol_fingerprint(config: Mapping[str, Any]) -> str:
    payload = {
        "protocol": _plain(config["protocol"]),
        "modules": trajectory_module_hashes(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
