# Jev / System One and the Naming Game

Date: 2026-09-22.

This note answers whether TypeSafe’s System One model **Jev** can be hosted locally or via API, and whether it is worth trying in the locked Naming Game (`llm-convention-topology`). It lives in the experiment repo under `typesafe_jev/`, next to the runner. It is not thesis prose and not a protocol change. It is not legal advice.

Sources checked:

- Blog: [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) (15 Sep 2026).
- Docs: [introduction](https://docs.typesafe.ai/introduction), [System One](https://docs.typesafe.ai/concepts/system-one), [models](https://docs.typesafe.ai/models), [API](https://docs.typesafe.ai/api), [Choice](https://docs.typesafe.ai/primitives/choice), [Python SDK](https://docs.typesafe.ai/sdk/python), [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) (reviewed 2026-09-17).
- Contract text as published: [Master Customer Agreement](https://typesafe.ai/legal/mca), section 2.3(f).
- Experiment code: `convention_topology/prompting.py`, `pool.py`, `json_output.py`, `llm.py`, `config.py`, `config.yaml`. Counted path and Yen constraints in `specs/yen-configuration.md` and `specs/experimental-configuration.md`.

## Recommendation

Use Jev only as a **private exploratory pilot**, from a laptop, over the hosted API. Do not put it on Yen, and do not add it to the confirmatory campaign.

Self-hosting is not available. The public interface is `POST https://api.typesafe.ai/v1/systemone` (Python package `typesafe-sdk`). Docs describe one shared hosted weight set. There is no download, vLLM recipe, or on-prem option.

The Naming Game already asks for a closed choice (10 labels in Study 1, 2 in Study 2). That matches Jev’s Choice primitive (maximum 255 options). The scientific object is still different: Jev does not generate text, does not think step by step, and returns one probability distribution. Stochastic play has to be sampled in our code from that distribution.

The binding constraint for the thesis is legal, not compute. MCA 2.3(f) says the customer will not “publish benchmarks or performance information about the Services.” A private smoke test is compatible with a plain reading of that sentence. Putting Jev numbers in the thesis, a talk, or a repo that will become public is not, unless TypeSafe gives written permission first.

## What Jev is

System One models are trained for calibrated structured decisions (RLCD), not for chat. Input is unstructured text or JSON. Output is a typed answer plus probabilities. Jev does not write strings, reasons, or code.

Current public model (docs, 2026-09-22):

| Item | Value |
| --- | --- |
| Model | `jev-1.13.0`; aliases `jev-latest` and `jev-preview` both point at it |
| Endpoint | `POST https://api.typesafe.ai/v1/systemone` |
| Price | $0.042 per million input tokens; output tokens free ($42 per billion input tokens) |
| Rate limit | 250,000 tokens/s and 1,200 requests/minute (docs say these move without notice) |
| Context | 64k tokens per request; 32k for `state` plus the longest question |
| Input | Text, JSON object, or array of text. No image, audio, or video |
| Primitives | Choice (≤255 options), Score (2–10 levels), Noul (yes-probability) |
| Access | Early access. Waitlist at [typesafe.ai/join-the-waitlist](https://typesafe.ai/join-the-waitlist). Console: `console.typesafe.ai`. Key env: `TYPESAFE_API_KEY` |

A Choice response is the mode (`choice`), a full distribution (`probabilities`), and a `confidence` derived from that distribution. There is no temperature parameter. Docs describe the model as consistent on similar inputs: the same state should yield the same distribution. Client code samples if the experiment needs randomness.

Jaggedness that matters here (`jev-1.13`):

- It reads instructions literally and is weak at indirection.
- It does not count reliably.
- Accuracy drops when `state` contains irrelevant detail.
- It is not a generator. Chaining choices to fake text is discouraged.
- The same question asked as a Noul and as a Choice need not agree. Do not assume `P(A) + P(not A) = 1` across separate questions.

## Hosting

**API (the only path).** Install `typesafe-sdk`, set `TYPESAFE_API_KEY`, call `AsyncTypeSafeClient.system_one`. Pin `jev-1.13.0` rather than `jev-latest`, because aliases move. The SDK retries 429 and 529 with backoff.

Example shape for one Naming Game decision:

```python
response = await client.system_one(
    state={
        "options": ["abcde", "fghij"],
        "history": [
            {"round": 1, "self": "abcde", "partner": "fghij", "payoff": 0}
        ],
        "round": 2,
        "match_reward": 1,
        "mismatch_reward": 0,
    },
    questions={
        "action": Choice(
            instructions=(
                "Which option should Player 1 pick now to match Player 2, "
                "using only the history in state?"
            ),
            criteria={"abcde": None, "fghij": None},
        )
    },
    model="jev-1.13.0",
)
```

Then sample one label from `response.choices["action"].probabilities` with the run seed. Log the full distribution. Do not send the current prompt’s “think step by step” sentence; Jev cannot comply with it, and extra instruction text is a distractor.

**Local weights.** Not offered. “Customizing Jev” in the docs means putting domain text in `state` and `criteria`. The same weights serve every account. Yen vLLM, Ollama, and Apptainer cannot serve this model.

**Yen.** Wrong machine. Counted jobs are localhost vLLM on 2× A40 (`provider: openai_compat`, `base_url` must be localhost). `CLOUD_PROVIDERS` in `config.py` rejects `together`, `openrouter`, `anthropic`, `google`, `deepinfra`, and `openai`. A remote TypeSafe URL fails that rule. GPU time does not help a hosted API. Do not place the API key on scratch.

Run the pilot on the laptop (or any host with HTTPS). Keep the key out of git. Cap client concurrency so bursts stay under 1,200 requests/minute. At ~100–500 ms latency, a steady 20 requests/second needs only modest concurrency (on the order of 2–10 in flight). That is far below the vLLM `in_flight_limit` values (about 98) used for local Gemma.

## Fit to the experiment

The counted loop does not invent names. `draw_pool` builds 10 random 5-letter strings. Study 2 offers `pool[0]` and `pool[1]`. `build_user_prompt` lists those options plus the last `H=12` rounds. `parse_decision` requires JSON `{"value": <enum>, "reason": <non-empty string>}`. Gameplay uses only `value`. Committed-minority agents skip the model.

So the adapter is small:

1. A new provider (not one of `CLOUD_PROVIDERS`) that implements `AsyncLLMClient.complete(prompt, *, options)`.
2. Send structured history as `state` and the current `options` as Choice criteria.
3. Sample a label from the returned probabilities (seeded). Argmax would not match temperature 0.5 token sampling, and it would remove the stochasticity conventions depend on.
4. Return parser-valid JSON with a fixed `reason` such as `"typesafe-choice"`, or relax the parser for this provider only. Either change touches the protocol fingerprint (`prompting.py`, `llm.py`).
5. Leave networks, pool, gate, and CM swap alone. The emitted label must stay inside the pool.

Order of magnitude, from the locked protocol (`N=48`, gate from `t≥144`, cap 1500, 32 seeds, 5 topologies, CM `k∈{5,10,14}`, 640 cells per model):

| Slice | Rough completions |
| --- | --- |
| One emergence run that gates at t=144 | ~300 |
| One emergence run at the cap | ~3,000 |
| One CM run at horizon 1500 | ~2,100–2,700 |
| One full model, if many runs are long | on the order of 10^6 |

At ~400 input tokens and $0.042 / million tokens, a short emergence smoke (a few cells, early gate) is well under a dollar. A long single-model campaign is on the order of tens of dollars if runs hit the cap. Price is not the reason to skip it. Rate limit is: 10^6 calls at 20/s is about 14 hours of continuous traffic.

## Whether it is scientifically useful

Useful as a probe. Not useful as a fifth confirmatory model.

The design question is whether a non-generative, calibrated choice model can coordinate on arbitrary labels from partner history. That is adjacent to the thesis (topology × convention emergence under a committed minority, human-benchmarked, multi open-weight LLM). It is not the locked comparison. The keepers are `gemma4_31b`, `qwen38_27b`, `olmo31_32b`, and `glm4_32b`, served locally in BF16. Jev is closed, hosted, versioned by TypeSafe, and not reproducible from weights we control.

Two failure modes are likely, and a small pilot can tell them apart:

1. **Label identity.** Options are nonsense strings. Jev is aimed at semantic judgments. If the distribution stays near uniform across seeds and histories, the model is not tracking the convention. Stop there.
2. **History use.** Matching a partner is close to “which label recurred,” which is the counting / indirection failure mode in the jaggedness note. If the model locks onto one label and ignores history, it will not show topology effects. That result would still be informative privately, and it would not support a claim about conventions.

What a pilot should record, per decision: model id `jev-1.13.0`, full probability vector, sampled label, seed, and whether the sample matched the partner’s last label. A few seeds on one topology (for example one emergence cell and one CM cell) are enough to see whether coordination moves at all.

Do not rewrite the Ashery prompt into a Chain-of-Thought and expect Jev to follow it. Do not treat the returned `confidence` as a substitute for the Naming Game payoff.

## Practical sequence

The runner is `typesafe_jev/run_studies.py` in this experiment repo. It does not touch the counted Yen path. Default pace is 1200 requests per minute. Artifacts use campaign `jev-system-one`.

1. Get early access and export `TYPESAFE_API_KEY`. Pin `jev-1.13.0`.
2. `python typesafe_jev/run_studies.py --dry-run` prints Study 1 and Study 2 across the five topologies.
3. `python typesafe_jev/run_studies.py --task emergence:mixing:0-1` is a one-cell smoke. The default command runs both studies, all topologies, and 32 seeds.
4. Before any number appears in the thesis, the slides, or a public repo, get written permission that MCA 2.3(f) does not cover that report. Section 2.3 is a license restriction; breach is called out as grounds for suspension (section 6) and as an excluded claim (section 12.3).

Until step 4, keep outputs local.
