"""Serve probe: N emergence naming-game schema decisions, then exit."""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any, Mapping

from openai import APIConnectionError, APITimeoutError

from convention_topology.json_output import ParseError, parse_decision
from convention_topology.llm import classify_error
from convention_topology.orchestration import build_client
from convention_topology.pool import draw_pool, options_for_program
from convention_topology.prompting import build_user_prompt


DEFAULT_TECH_CHECK_N = 100
PASS_SHARE = 0.95

FIXTURE_PLAYER = {
    "my_history": (),
    "partner_history": (),
    "outcome": (),
}


def evaluate_pass(*, n_completed: int, n_schema_valid: int, serve_startup: bool) -> tuple[float, bool]:
    share = (n_schema_valid / n_completed) if n_completed else 0.0
    passed = (not serve_startup) and n_completed > 0 and share >= PASS_SHARE
    return share, passed


def _fixture_options(config: Mapping[str, Any]) -> list[str]:
    explicit = config.get("pool", {}).get("labels")
    if explicit:
        pool_labels = list(explicit)
    else:
        pool_labels = draw_pool(
            seed=int(config["pool"]["seed"]),
            string_length=int(config["protocol"]["string_length"]),
        )
    return options_for_program(pool_labels, "emergence")


def _is_serve_startup(exc: BaseException) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError, ConnectionError, OSError)):
        return True
    return classify_error(exc) == "transport"


def _write_probe_log(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, indent=2, sort_keys=True)
        handle.flush()
    tmp.replace(path)


async def _probe_async(
    config: Mapping[str, Any],
    model_spec,
    *,
    n: int,
    mock_policy: str,
) -> dict[str, Any]:
    protocol = config["protocol"]
    options = _fixture_options(config)
    option_order = list(options)
    rng = random.Random(int(config["run"]["base_seed"]))
    rng.shuffle(option_order)
    rewards = (int(protocol["rewards_mismatch"]), int(protocol["rewards_match"]))
    prompt = build_user_prompt(FIXTURE_PLAYER, int(protocol["H"]), rewards, option_order)
    client = build_client(model_spec, mock_policy, int(config["run"]["base_seed"]), option_order, json_schema=True)
    n_completed = 0
    n_schema_valid = 0
    serve_startup = False
    for _ in range(n):
        try:
            response = await client.complete(prompt, options=option_order)
        except Exception as exc:
            if _is_serve_startup(exc):
                serve_startup = True
                break
            continue
        n_completed += 1
        try:
            parse_decision(response.text, option_order)
        except ParseError:
            continue
        n_schema_valid += 1
    share, passed = evaluate_pass(
        n_completed=n_completed, n_schema_valid=n_schema_valid, serve_startup=serve_startup
    )
    return {
        "n": n,
        "n_completed": n_completed,
        "n_schema_valid": n_schema_valid,
        "share": share,
        "serve_startup": serve_startup,
        "model": model_spec.shorthand,
        "passed": passed,
    }


def run_tech_check(
    config: Mapping[str, Any],
    model_spec,
    *,
    campaign_dir: Path,
    n: int,
    mock_policy: str = "imitate_modal",
) -> int:
    payload = asyncio.run(
        _probe_async(config, model_spec, n=n, mock_policy=mock_policy)
    )
    _write_probe_log(Path(campaign_dir) / "tech-check.json", payload)
    return 0 if payload["passed"] else 1
