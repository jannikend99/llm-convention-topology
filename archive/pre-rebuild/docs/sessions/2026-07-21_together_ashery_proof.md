# Together AI switch + Ashery mixing proof log (2026-07-21 → 22)

**Status:** emergence 8/8 ✅ · CM smoke 2/2 ✅ · **CM flip demo k=6 ✅** (aborted early after flip)  
**Scope:** Cheap Phase-1 **emergence** proof on mixing (`complete`) for `llama31` — **not** the full 12/topology pilot, **not** CM/W=2.  
**Repo:** `llm-convention-topology`  
**Related:**  
- [`2026-07-20_C05_openrouter_smoke.md`](2026-07-20_C05_openrouter_smoke.md) — paid connectivity smoke (OpenRouter/DeepInfra)  
- [`2026-07-21_ashery_split_design.md`](2026-07-21_ashery_split_design.md) — emergence ‖ prepared CM  
- [`2026-07-20_ashery_baseline_plan.md`](2026-07-20_ashery_baseline_plan.md) — mixing baseline plan  
- `WORKING.md` §4 / §5 · `config.yaml`

---

## 1. Goal of this track

1. Get a **live** Ashery-style mixing emergence run working after C-05 (OpenRouter) failed under load.
2. Confirm qualitative convention formation (gate reached, parseable labels) before spending a full Llama pilot.
3. Align the **label pool** with Ashery’s Fig. 1 / plotter W=10 set (not an ad-hoc A–J alphabet).
4. Scale from a tiny `--limit 3` sanity check to **`--limit 8`** independent emergence seeds for a first distribution look (winners, `t_gate`).

**Explicitly out of scope here:** full 36-run pilot grid · CM / prepared populations · Theory/Methods LaTeX rewrite · GPT/Claude · Qwen pilot.

---

## 2. Decision log (locked choices)

| # | Decision | Choice | Why |
| --- | --- | --- | --- |
| D1 | Protocol | Ashery **split**: emergence (organic, W=10) ‖ CM (prepared, W=2) | Match Ashery Fig. 1 + CM code; sequential P1→P2 abandoned for runs |
| D2 | Proof focus | **Emergence only**, mixing (`complete`) | Cheapest Ashery Fig. 1 analogue; CM later |
| D3 | Host for `llama31` | **Together AI direct** (not OpenRouter) | Sustained `429 engine_overloaded` on DeepInfra via OpenRouter during pilot-scale traffic |
| D4 | Model string | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Together: Llama-3.1-70B Turbo is **dedicated-only**, not serverless. Closest serverless 70B Instruct Turbo. Shorthand stays `llama31` for paths/grid |
| D5 | Auth | `TOGETHER_API_KEY` in gitignored `.env` | Never commit keys |
| D6 | `max_tokens` (`llama31`) | **2000** (was 512 after C-05) | Together proof: CoT truncated mid-answer before `{'value':…}` at 512; completion often ≪ 2000 when successful (~790 peak observed) |
| D7 | Label pool (emergence) | **`Q, M, X, Y, F, J, P, R, C, D`** | Ashery plotter / code W=10 set. **Not** A–J (introduces A-primacy; Ashery’s set has **no A**) |
| D8 | CM pool | `[Q, M]` unchanged | Ashery W=2 bias/CM |
| D9 | Cheap proof size | First `--limit 3`, then **`--limit 8`** | 3 = connectivity/gate sanity; 8 = first winner/`t_gate` distribution (full topology pilot remains 12 without `--limit`) |
| D10 | Workers | `--workers 2` for 8-seed run | Parallel across runs; keep modest vs provider limits |
| D11 | How to run long jobs | **Manual Terminal**, not Cursor agent background shells | Agent-started long pilots were aborted (`exit_code: unknown` / terminated); user owns the process |
| D12 | Theory/Methods LaTeX | **Deferred** until after pilot data | Split already in code; manuscript catch-up later |

---

## 3. Path taken (chronology)

### 3.1 Starting point (post C-05)

- OpenRouter smoke ✅ for `llama31` + `qwen25` via DeepInfra pin (`only: ["deepinfra"]`).
- `max_tokens` raised **200 → 512** in C-05 (CoT truncation before structured `value`).
- Ashery split implemented in thesis code (separate emergence vs prepared CM).
- Progress monitoring added: `[batch]`/`[start]`/`[alive]`/`[progress]`/`[done]`; CLIs `--topology`, `--limit`, `--workers`, `--quiet`.

### 3.2 Failed path: OpenRouter pilot under load

- Attempted mixing emergence pilot traffic through OpenRouter → DeepInfra.
- Hit sustained **`429 engine_overloaded`**.
- Retry/backoff could not make a multi-run batch reliable.

**Lesson:** C-05 smoke ≠ pilot capacity. Provider pin that works for 20 interactions can choke under parallel/long runs.

### 3.3 Switch to Together AI

| Field | Before (C-05) | After (proof track) |
| --- | --- | --- |
| `llama31.provider` | `openrouter` | `together` |
| `model_id` | `meta-llama/llama-3.1-70b-instruct` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| `base_url` | `https://openrouter.ai/api/v1` | `https://api.together.xyz/v1` |
| `api_key_env` | `OPENROUTER_API_KEY` | `TOGETHER_API_KEY` |
| Provider pin | `only: [deepinfra]` | *(none — direct Together)* |

`qwen25` stays on OpenRouter/DeepInfra for now.

**Model caveat (document in Methods later):** shorthand `llama31` ≠ literal Llama-3.1 on Together serverless. Real string is Llama-**3.3**-70B-Instruct-Turbo. Do not claim exact Ashery Llama-3.1 replication without noting this.

### 3.4 First Together proof (`--limit 3`, options still A–J)

CLI pattern:

```bash
PYTHONUNBUFFERED=1 .venv/bin/python -u run_pilot.py \
  --program emergence --model llama31 \
  --topology complete --limit 3 --workers 2
```

**Before `max_tokens` bump (still 512):**

- 1/3 completed (incumbent **A**, `t_gate` ≈ 105)
- 2/3 failed — parse/truncation (CoT cut before complete `{'value':…}`)
- Parser itself OK when the value dict was complete (0/24 cases of missed complete value)

**After `max_tokens: 2000`:**

- **3/3 completed**
- All incumbent **A**
- `t_gate` ≈ 117 / 118 / 132
- Retries were timeouts/503 only (not systematic parse fail)
- Peak `completion_tokens` ≈ 790 ≪ 2000 → headroom, not waste-driven cost

**Vs Ashery (qualitative only):**

- Mixing emergence works (gate reached).
- Faster to gate than Ashery’s ~15 population-time on Fig. 1 (~5N here) — model is 3.3 not 3.1; n=3 tiny.
- All-A winners suspicious under uniform W=10 (~0.1% if independent uniform); consistent with **A-primacy** from an A–J pool, not chance.

### 3.5 Critical finding: label pool mismatch

| Source | W=10 set |
| --- | --- |
| Thesis config (early proof) | `A, B, C, D, E, F, G, H, I, J` |
| Ashery plotter / code | **`Q, M, X, Y, F, J, P, R, C, D`** (no **A**) |

Ashery’s Llama-3.1 histograms favor **M/Y**-like patterns, not A. Using A–J likely **introduced** A as a privileged first letter and made the 3/3-A result non-comparable to Ashery Fig. 1.

**Action (2026-07-22):** lock `params.options_emergence` to Ashery’s set; CM stays `[Q, M]`.

### 3.6 Ops / tooling lessons

| Lesson | Detail |
| --- | --- |
| Cursor background shells | Long `run_pilot.py` jobs started from the agent were repeatedly killed; **run proofs in a real Terminal** |
| Resume + `run_id` | Changing options (or host) without deleting sidecars/pickles → resume skips “completed” A–J runs. **Always clean artifacts** before a new proof cohort |
| Progress UX | `[alive]` ~30s and `[progress]` every 50 interactions are enough to see liveness without live dashboards |
| `--limit` | First N cells after topology filter; scientific pilot remains 12/topology without `--limit` |

---

## 4. Current config snapshot (emergence proof)

```yaml
# config.yaml (relevant bits)
params:
  options_emergence: [Q, M, X, Y, F, J, P, R, C, D]
  options_cm: [Q, M]
models:
  llama31:
    provider: together
    model_id: meta-llama/Llama-3.3-70B-Instruct-Turbo
    base_url: https://api.together.xyz/v1
    api_key_env: TOGETHER_API_KEY
    max_tokens: 2000
```

---

## 5. Next run — Ashery letters, 8 seeds (manual)

**Clean old A–J / prior complete-emergence artifacts first** (same `run_id`s would otherwise be skipped):

```bash
cd "/Users/jannikendress/Master Thesis/02_Topic/Experiment_Code/llm-convention-topology"

rm -f logs/llama31_complete_emerg_*.events.jsonl
rm -f data/runs/llama31/complete/*.meta.json
rm -f data/runs/llama31/complete/*.pkl

# optional sanity
.venv/bin/python run_pilot.py --program emergence --model llama31 \
  --topology complete --limit 8 --dry-run

PYTHONUNBUFFERED=1 .venv/bin/python -u run_pilot.py \
  --program emergence \
  --model llama31 \
  --topology complete \
  --limit 8 \
  --workers 2
```

**What to look at when done:**

- Status mix: `completed` / `failed` / `censored`
- Incumbent / winner letter counts (compare to Ashery M/Y-ish pattern; do **not** expect figure-identical shares)
- `t_gate` distribution vs prior A–J run (~117–132)
- Retry reasons (503/timeout vs parse)

**Pass criteria (still qualitative):**

- Most of 8 runs reach gate (or clearly progress without systematic parse death)
- Low sustained 429 rate on Together
- Winner distribution **not** dominated by a letter that is absent/privileged only in a non-Ashery alphabet
- Do **not** expect Ashery figure-identical numbers (different model string, small n)

---

## 6. Open items after the 8-seed proof

1. ~~Record winner histogram + `t_gate` table~~ → §7.2.
2. ~~8-seed emergence~~ → **pass** (8/8); enough to proceed without another emergence bump.
3. ~~CM prepared path smoke~~ → **pass** (§7.3).
4. ~~CM flip demo k=6~~ → **pass** (§7.4).
5. **Next:** Centola-3 Llama pilot (emergence + CM programs).
5. Methods note later: Together model string + Ashery letter set + `max_tokens` rationale.
6. Theory/Methods LaTeX: sync split protocol when pilot narrative is stable.

---

## 7. Results appendix (fill after runs)

### 7.1 Limit-3 proof (A–J pool, Together, `max_tokens=2000`) — done

| Seed index | Status | Incumbent | `t_gate` (approx.) | Notes |
| --- | --- | --- | --- | --- |
| 1–3 | 3/3 completed | **A, A, A** | ~117 / 118 / 132 | Retries = timeout/503; not parse |

### 7.2 Limit-8 proof (Ashery W=10 letters) — done (2026-07-22/23)

First pass: 4/8 completed, 4/8 failed (Together 503/502/timeout).  
Retry: `--retry-failed --workers 1` → **8/8 completed**.

| run_id (suffix) | Status | Incumbent | `t_gate` | `t_gate/N` |
| --- | --- | --- | --- | --- |
| s3421927570 | completed | Q | 143 | 6.0 |
| s90557159 | completed | D | 182 | 7.6 |
| s2276544829 | completed | D | 228 | 9.5 |
| s601132211 | completed | R | 236 | 9.8 |
| s3161562569 | completed | C | 237 | 9.9 |
| s1827656529 | completed | C | 292 | 12.2 |
| s2900733621 | completed | P | 324 | 13.5 |
| s67336590 | completed | C | 335 | 14.0 |

**Winner counts:** C×3, D×2, P×1, Q×1, R×1 (no M/Y in this n=8).  
**Pool / model:** Ashery W=10 · Together `Llama-3.3-70B-Instruct-Turbo`.

### 7.3 CM smoke (prepared W=2, mixing) — done (2026-07-23)

`run_pilot.py --program cm --topology complete --limit 2 --workers 1`

| k | N share | Status | Incumbent | Committed | Flip | Q share | M share | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4.2 % | completed | Q | M | 0 | 0.90 | 0.10 | 1000 Phase-2 steps; ~668 API calls |
| 2 | 8.3 % | completed | Q | M | 0 | 0.78 | 0.22 | Failed at t≈880 (503); resumed via `run_status→in_progress` |

**Ashery comparison (qualitative):** CM mechanics match (prepared population, W=2 `{Q,M}`, 1000-horizon, committed agents short-circuit LLM). No flip at k=1/2 is **consistent** with Ashery — critical mass is model-dependent and often ≫8 %. Dose response visible: higher k → higher M share, lower Q dominance.

**Infra:** Together 503/timeouts caused one fail; resume-from-checkpoint worked (do **not** use `--retry-failed` if you want to keep partial progress).

### 7.4 CM flip demo (k=6, ~25 %) — done (2026-07-23)

`run_one.py --program cm --topology complete --k 6 --seed 0`  
Run id: `llama31_complete_k6_s0000`

| Field | Value |
| --- | --- |
| k | 6 (25 % of N=24) |
| Incumbent / committed | Q → M |
| Phase-2 steps run | **400 / 1000** (stopped manually after flip plateau) |
| Sidecar `run_status` | `in_progress` *(aborted early — flip DV read from pickle)* |
| **flip** | **1** |
| **time_to_flip** | **292** |
| Trailing 3N at stop | 100 % M |
| API calls | ~600 · ~$0.46 · 2 retries |

**Dynamics (qualitative):** t≈72 modal still Q; flip window reached at **t=292**; from t≈350 onward stable **100 % M** coordination (`rolling_success=1.0`). No further information expected in remaining 600 steps — early stop justified for proof track.

**Ashery comparison:** Committed minority at ~25 % can overturn prepared Q-incumbent on mixing — qualitatively consistent with Ashery/Centola CM tipping (not 1:1 threshold match; model = Llama-3.3 on Together).

**Note for thesis / `analyze.py`:** Formal batch analysis expects `run_status=completed` and full 1000-horizon for CM cells; this demo run is **documentation-only** unless re-run to completion or meta finalized later.

---

## 8. Thesis-ready summary (Methods / pilot validation, 2026-07-23)

**Stack validated before Centola-3 pilot:**

| Track | Design | n | Result | Ashery-relevant claim |
| --- | --- | --- | --- | --- |
| Emergence | Mixing, W=10 Ashery letters, organic | 8 seeds | 8/8 gated | Spontaneous convention emergence ✅ |
| CM | Mixing, W=2 prepared `{Q,M}`, horizon 1000 | k=1, k=2 | 2/2 completed, 0/2 flip | CM protocol + stability at low k ✅ |
| CM flip demo | Same, k=6 (25 %) | 1 (early stop) | **flip=1, t_flip=292** | CM tipping on mixing ✅ |

**Document for thesis:** model string `meta-llama/Llama-3.3-70B-Instruct-Turbo` (shorthand `llama31`); provider Together direct; `max_tokens=2000`; emergence pool `Q,M,X,Y,F,J,P,R,C,D`; CM pool `Q,M`; gate 0.95 / 3N; Phase-2 cap 1000 (Ashery).

**Not claimed:** quantitative replication of Ashery Fig. 1/CM curves; human 25 % flip rate under identical operational definition.

---

## Changelog (this doc)

| Date | Note |
| --- | --- |
| 2026-07-21 | Initial Together switch + `--limit 3` CLI sketch |
| 2026-07-22 | Expanded: full decision/path/experience log; Ashery letter lock; 8-seed next run |
| 2026-07-23 | §7.2 filled — 8/8 completed after retry; next = CM smoke then topology pilot |
| 2026-07-23 | §7.4 k=6 flip demo: flip=1 @ t=292; stopped t=400 after M plateau |
