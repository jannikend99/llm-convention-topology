"""TypeSafe Jev client for the existing Naming Game decision loop.

The counted path stays on localhost vLLM. This client implements the same
async ``complete(prompt, options)`` contract and turns Jev's Choice
distribution into the JSON object ``parse_decision`` already accepts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from typing import Sequence

from convention_topology.llm import LLMResponse


REQUESTS_PER_MINUTE = 1200
DEFAULT_MODEL = "jev-1.13.0"
CHOICE_KEY = "action"

_DROP_LINES = (
    "Please think step by step before making a decision. Examining the history explicitly is important.\n",
    'Return exactly one JSON object: {"value":"<one offered value>","reason":"<brief reason>"}.\n',
    "Do not write text outside the JSON object.\n",
)


class RpmLimiter:
    """Space request starts so the process stays at ``rpm`` and not above it."""

    def __init__(self, rpm: int = REQUESTS_PER_MINUTE):
        if rpm < 1:
            raise ValueError("rpm must be positive")
        self.rpm = int(rpm)
        self._interval = 60.0 / self.rpm
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            slot = now if now > self._next else self._next
            self._next = slot + self._interval
        delay = slot - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)


def observer_state(prompt: str) -> str:
    """Drop generation instructions. The run log still hashes the original prompt."""
    text = prompt
    for line in _DROP_LINES:
        text = text.replace(line, "")
    return text.strip()


def sample_label(probabilities: dict[str, float], rng: random.Random, temperature: float) -> str:
    """Draw one label. Temperature below 1 sharpens the returned distribution."""
    labels = list(probabilities)
    if not labels:
        raise ValueError("empty probability distribution")
    if temperature <= 0:
        return max(labels, key=lambda label: float(probabilities[label]))
    weights = [max(float(probabilities[label]), 1e-12) ** (1.0 / temperature) for label in labels]
    total = sum(weights)
    draw = rng.random() * total
    cursor = 0.0
    for label, weight in zip(labels, weights):
        cursor += weight
        if draw <= cursor:
            return label
    return labels[-1]


def _decision_rng(model_seed: int, prompt: str) -> random.Random:
    digest = hashlib.sha256(f"{model_seed}:{prompt}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


class TypeSafeNamingClient:
    def __init__(
        self,
        sdk_client,
        *,
        model_id: str,
        temperature: float,
        model_seed: int,
        limiter: RpmLimiter,
    ):
        self._sdk = sdk_client
        self.model_id = model_id
        self.temperature = temperature
        self.model_seed = model_seed
        self._limiter = limiter

    async def complete(self, prompt: str, *, options: Sequence[str]) -> LLMResponse:
        from typesafe_sdk import Choice

        await self._limiter.acquire()
        criteria = {str(option): None for option in options}
        result = await self._sdk.system_one(
            state={"observer_prompt": observer_state(prompt), "options": list(criteria)},
            questions={
                CHOICE_KEY: Choice(
                    instructions=(
                        "Which single option should Player 1 pick on this round? "
                        "Read `observer_prompt`. Choose one criteria key."
                    ),
                    criteria=criteria,
                )
            },
            model=self.model_id,
        )
        answer = result.choices[CHOICE_KEY]
        raw_probs = dict(answer.probabilities)
        probabilities = {str(option): float(raw_probs.get(str(option), 0.0)) for option in options}
        label = sample_label(probabilities, _decision_rng(self.model_seed, prompt), self.temperature)
        reason = json.dumps(
            {
                "source": "typesafe-choice",
                "model": getattr(result, "model", self.model_id),
                "sampled": label,
                "mode": str(answer.choice),
                "confidence": float(answer.confidence),
                "probabilities": probabilities,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        usage_obj = getattr(result, "usage", None)
        return LLMResponse(
            text=json.dumps({"value": label, "reason": reason}, separators=(",", ":")),
            usage={
                "prompt_tokens": getattr(usage_obj, "input_tokens", None),
                "completion_tokens": getattr(usage_obj, "output_tokens", None),
            },
            model_id=str(getattr(result, "model", self.model_id)),
            finish_reason="typesafe_choice",
        )
