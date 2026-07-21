# C-05 — OpenRouter real-API smoke (2026-07-20)

**Status:** complete (`llama31` + `qwen25`) · `gemini35` deferred  
**Scope note:** This is the **paid connectivity / routing smoke** (WORKING §3 Phase C-05 / §13 #6), **not** the 36-run Phase-1 pilot (`run_pilot.py`).  
**Repo:** `llm-convention-topology`  
**Related:** [`PROVIDER_ROUTING_PLAN.md`](../../PROVIDER_ROUTING_PLAN.md) · [`WORKING.md`](../../WORKING.md) §13 #6 · `config.yaml` models registry

---

## 1. Goal

1. Confirm `.env` → OpenRouter auth works for the two open-weight factorial models.
2. Run a short real-API loop (`run_one.py --smoke`, 20 interactions) for `llama31` and `qwen25`.
3. Discover and **pin** the OpenRouter backing provider (`openrouter_provider.only`) for reproducibility.
4. Record failures / fixes so the later pilot does not rediscover the same traps.

**Explicitly out of scope today:** Gemini key / `gemini35` smoke · GPT/Claude (Doug D1) · full pilot grid · main study.

---

## 2. What we did (procedure)

### 2.1 Environment

| Step | Action |
| --- | --- |
| 1 | Created gitignored `.env` at repo root (template + user-filled key) |
| 2 | Set `OPENROUTER_API_KEY` (prefix `sk-or-v…`; length 73) |
| 3 | Left `GEMINI_API_KEY` / OpenAI / Anthropic empty — not needed for this session |

`.env` is listed in `.gitignore` (`!! .env` in `git status --ignored`). Never commit.

### 2.2 Provider discovery (probe)

One-shot `chat.completions` probes (not the full smoke) via OpenAI SDK against `https://openrouter.ai/api/v1/`:

| Model slug | First successful backing provider | Notes |
| --- | --- | --- |
| `meta-llama/llama-3.1-70b-instruct` | **DeepInfra** | Response field `provider: "DeepInfra"`; OR slug = `deepinfra` |
| `qwen/qwen-2.5-72b-instruct` | **DeepInfra** (after retry) | Initially 429 `engine_overloaded` on DeepInfra |

**Available providers reported by OpenRouter errors:**

| Model | `available_providers` |
| --- | --- |
| Llama 3.1 70B Instruct | `deepinfra`, `amazon-bedrock`, `wandb` |
| Qwen 2.5 72B Instruct | `deepinfra`, `novita` |

**Novita** for Qwen returned HTTP 400 (`INVALID_REQUEST_BODY` / endpoint mismatch) when forced with `only: ["novita"]`. Not used for the pin.

### 2.3 Failed first smokes (before config fix)

```bash
python run_one.py --model llama31 --topology complete --k 1 --seed 0 --max-interactions 20 --smoke
# also seed 1
```

Both attempts died mid-run with `ParseError` → `RunFailedError: Exhausted 3 attempts`.  
Typical failure: long chain-of-thought text mentioning both `Q` and `M`, **no** `{'value': …}` field, finish reason effectively length-truncated at `max_tokens: 200`.

### 2.4 Root-cause check

Controlled probe with the real Ashery-style chat prompt (`build_messages` after one history turn):

| `max_tokens` | `finish_reason` | Contains `'value'` field? |
| --- | --- | --- |
| **200** | `length` (200 completion tokens) | **No** — truncated mid-reasoning |
| **512** | `stop` (~460 completion tokens) | **Yes** |

Ashery upstream (`ashery-ai-norms/run_API.py`) used Hugging Face `max_new_tokens: 12–15` on a raw-completion stack. That budget is **not** transferable to our OpenAI-compatible chat path when the prompt still asks for step-by-step reasoning before the structured answer.

### 2.5 Config changes applied

In `config.yaml` (and matching defaults/tests):

| Change | Value | Why |
| --- | --- | --- |
| `openrouter_provider.only` | `["deepinfra"]` for `llama31` + `qwen25` | Repro pin after C-05 |
| `openrouter_provider.allow_fallbacks` | `false` (already set) | Fail closed if DeepInfra unavailable |
| `max_tokens` | **200 → 512** (all registry models + `OpenAICompatClient` default) | Prevent CoT truncation before `value` |

Tests updated: `tests/test_config.py`, `tests/test_llm.py`.

### 2.6 Successful smokes (after fix)

```bash
cd llm-convention-topology
source .venv/bin/activate   # or: .venv/bin/python …

python run_one.py --model llama31 --topology complete --k 1 --seed 0 --max-interactions 20 --smoke
python run_one.py --model qwen25  --topology complete --k 1 --seed 0 --max-interactions 20 --smoke
```

Wall-clock (both sequential): ~10.1 minutes total (`elapsed_ms ≈ 606727`).

---

## 3. Results

### 3.1 Smoke outcomes

| Shorthand | `model_id` | Endpoint | Interactions | Exit | Labels observed |
| --- | --- | --- | --- | --- | --- |
| `llama31` | `meta-llama/llama-3.1-70b-instruct` | `https://openrouter.ai/api/v1` | 20/20 | **0** | Mixed `(Q,M)` / `(Q,Q)` / `(M,M)` / … — parse always recovered a single option |
| `qwen25` | `qwen/qwen-2.5-72b-instruct` | same | 20/20 | **0** | Same pattern; completed after Llama |

Smoke mode only exercises chat + `parse_label` + interaction loop. It does **not** run Phase-1 gate / Phase-2 CM / eligibility logging (that is `execute_run` / `run_pilot.py`).

### 3.2 Routing pin (locked for open-weight models)

```yaml
# config.yaml — excerpt
llama31:
  openrouter_provider:
    allow_fallbacks: false
    only: ["deepinfra"]
qwen25:
  openrouter_provider:
    allow_fallbacks: false
    only: ["deepinfra"]
```

Sidecars / `config_hash` already include these non-secret routing fields (provider routing plan §6.1).

### 3.3 Deferred

| Item | Reason |
| --- | --- |
| `gemini35` smoke | No `GEMINI_API_KEY` this session; not in four-model factorial |
| `gpt54` / `claude55` | Still `TBD-doug` (Doug D1) |
| Full pilot (36 runs / model) | Next milestone after commit |

---

## 4. Learnings (keep for pilot / Methods)

0. **Disable OpenRouter response caching** (`X-OpenRouter-Cache: false` on every OR call). If enabled (header or preset), identical request bodies return the **same** prior completion — including when two agents share a local history. That collapses independent sampling at `temperature: 0.5` and would bias convention dynamics. Default OR behaviour is off; we set the header explicitly so account presets cannot turn it on. Provider *prompt* caching (KV prefix reuse) is separate and does not replay completions; we do not inject prompt nonces (would alter Ashery prompts).
1. **OpenRouter auth works** with a single `OPENROUTER_API_KEY` for both open-weight models; `load_dotenv()` in `run_one.py` is sufficient if `.env` sits at repo root.
2. **Backing host ≠ model slug.** Same slug can be served by several providers; without `only`, load balancing can change the host between runs. Pin early.
3. **DeepInfra is the practical pin today** for both Llama and Qwen on OpenRouter. Alternatives exist for Llama (`amazon-bedrock`, `wandb`); Qwen’s second option (`novita`) failed when forced.
4. **Transient 429s are real.** Qwen hit DeepInfra `engine_overloaded` / Novita rate limits during probing. Pilot orchestration should tolerate retries (already: `RetryPolicy` 3×) and possibly longer backoff under provider overload.
5. **`max_tokens: 200` is unsafe** for the current Ashery-style prompt (“think step by step” → then `{'value'; …; 'reason': …}`). Truncation yields unparseable dual-option CoT. **512** completed cleanly in probes and smokes. Document as intentional deviation from Ashery’s HF `max_new_tokens: 12–15` (different API + generation style).
6. **Parse failures look like model quality issues but were budget issues.** After raising `max_tokens`, both models completed 20/20 without exhausted retries.
7. **Gemini stays optional** for Mehdizadeh-comparison / auxiliary tooling; not required to start the Llama pilot.
8. **Smoke ≠ pilot.** Eligibility rates, lattice/random stability, and CM dynamics remain untested on real APIs until `run_pilot.py --model llama31`.

---

## 5. Files touched this session

| Path | Change |
| --- | --- |
| `.env` | Created locally (gitignored); OpenRouter key only |
| `config.yaml` | `only: ["deepinfra"]`; `max_tokens: 512` |
| `convention_topology/llm.py` | Default `max_tokens` 512 |
| `tests/test_config.py` | Expect deepinfra pin + 512 |
| `tests/test_llm.py` | Expect default 512 |
| `WORKING.md` §13 #6 | Marked closed 2026-07-20 |
| Meta-repo `TODO.md` | Priority order updated |
| **This file** | Session record |

---

## 6. Reproduce / verify later

```bash
cd "02_Topic/Experiment_Code/llm-convention-topology"
# ensure .env has OPENROUTER_API_KEY
.venv/bin/python -m unittest tests.test_config tests.test_llm -v
.venv/bin/python run_one.py --model llama31 --topology complete --k 1 --seed 0 --max-interactions 20 --smoke
.venv/bin/python run_one.py --model qwen25  --topology complete --k 1 --seed 0 --max-interactions 20 --smoke
```

Optional: confirm pin in resolved registry:

```bash
.venv/bin/python -c "from convention_topology.config import load_config, resolve_model; \
c=load_config(); \
print(resolve_model(c,'llama31').openrouter_provider); \
print(resolve_model(c,'qwen25').openrouter_provider)"
# expected: {'allow_fallbacks': False, 'only': ['deepinfra']}
```

---

## 7. Suggested next session log

When the real pilot runs, add a sibling file, e.g.:

`docs/sessions/YYYY-MM-DD_pilot_llama31.md`

covering: command line, seed grid, eligibility counts per Centola-3 topology, censoring, cost/token totals, contingency decision (Methods Options 0/A–E).

**Sequencing lock (Doug email 2026-07-20):** open-source (Llama) first → share results with Doug → iterate if needed → only then proprietary models. Full quote + interpretation: [`01_Orga/Doug_Open_Questions.md`](../../../../../01_Orga/Doug_Open_Questions.md#doug-email-2026-07-20--design-go--open-source-first).

---

## 8. Session timeline (approx., local UTC+2)

| Time | Event |
| --- | --- |
| ~14:27 | Status check → start C-05 |
| ~14:28 | `.env` template created; user pastes OpenRouter key; Gemini deferred |
| ~14:30 | Key verified; provider probes; Llama→DeepInfra; Qwen 429 |
| ~14:32 | First Llama smokes fail on parse (`max_tokens` 200) |
| ~14:34 | Truncation diagnosed; config → 512 + `only: deepinfra`; tests updated |
| ~14:34–14:45 | Successful Llama then Qwen smokes (20/20 each) |
| ~14:45 | WORKING / TODO status closed; this session doc written |
