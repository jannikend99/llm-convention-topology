# llm-convention-topology — Implementation Working Document

**Repository:** [github.com/jannikend99/llm-convention-topology](https://github.com/jannikend99/llm-convention-topology)  
**Meta-repo path:** `Master Thesis/02_Topic/Experiment_Code/llm-convention-topology/`  
**Last updated:** 2026-07-24 (Pilot strategy — §5; mistralnemo pilot → optional Llama pilot → Stanford main study)  
**Language:** English (code + docs)

---

## Charter

This document is the **single source of truth for thesis experiment code**. All implementation work is planned, tracked, and signed off here before (and while) code is written.

**Orientation:** Extend the public Ashery et al. (2025) LLM Naming Game release — Zenodo [`asheryAINormsZenodo2024`](../../Thesis_Writing/literature.bib) / GitHub `Ariel-Flint-Ashery/AI-norms` — read-only at `../ashery-ai-norms/`. Do **not** edit the Ashery submodule in place.

**Thesis extensions (locked in Methods):** Centola-3 topologies (mixing, random regular deg 4, 1D ring lattice deg 4), stability gate at **0.95** (not Ashery repo default 1.0), Phase 1 cap **5000**, factorial Phase 2 CM sweep **k ∈ {1…6}**, four-model between-run factor, eligibility logging, analysis aligned to H1–H3b (+ exploratory H4).

**Out of scope for v1 main study:** `meta_prompting*.py`, `NG_module.py` minimal-theory battery, scale-free/ER topologies, Mehdizadeh Mason–Watts graphs.

---

## Status

| Field | Value |
| --- | --- |
| Stage | Offline build ✅ · C-05 ✅ · Ashery-split code ✅ · **async engine ✅** (§15) · **pre-pilot proofs complete** (emergence 8/8 · CM smoke · k=6 flip) · **Step ① ✅** · **infra provider (#0b) ✅** |
| Methods LaTeX | Locked prose still sequential in places — **sync after pilot** (Ashery split already in code) |
| Next gate | **Pilot** (`mistralnemo`) → review → **optional Llama pilot?** (#1b) → **main study @ Stanford HPC** |
| Pilot (`mistralnemo`) | **Ready to run** — recipe §5; **not Methods/thesis data**; **not started** |
| Main study | Code ready; **thesis confirmatory runs** planned Stanford HPC (TODO **16a**) |

### Next steps (live checklist)

| # | Step | Status | Notes |
| --- | --- | --- | --- |
| 1 | Mixing emergence proof (Ashery W=10, 8 seeds) | ✅ **done 2026-07-23** | [`docs/sessions/2026-07-21_together_ashery_proof.md`](docs/sessions/2026-07-21_together_ashery_proof.md) |
| 2 | CM smoke + k=6 flip demo | ✅ **done 2026-07-23** | log §7.3–7.4 |
| **2c** | **Async engine (A1/A2/A3/A6 + ⑤ pool scaffold + ⑥ adaptive limiter)** — parallel p1+p2, global API gate, run-level pool | ✅ **done 2026-07-24** | Async is now the **default** engine (`--engine async`). See §15 · meta `TODO.md` **#0** / **#16b** |
| **2d** | **Step ① — measure baseline + real 429 ceiling** | ✅ **done 2026-07-24** | `mistralnemo` / DeepInfra direct: **0× 429** at 4→192; **200/200 OK** at 192; hard cap **200** concurrent/model. Production pin: **`--api-concurrency 192`** (§5 · §15) |
| **2e** | **Provider setup (pilot path)** | ✅ **done 2026-07-24** | `mistralnemo` registry + `DEEPINFRA_API_KEY`; smoke ✅; `max_tokens: 2000`. Multi-endpoint `ProviderPool` N>1 **deferred** |
| 3 | **Pilot** (`mistralnemo`) | ⬜ **next — user-run** | 72 runs, sequential emergence → cm, 64/192. Same protocol as thesis design; **only model differs**. **Not Methods chapter data** |
| 3b | Review pilot + `analyze.py --model mistralnemo` | ⬜ after **#3** | Exploratory; inform topology direction + Stanford planning |
| 3c | **Optional Llama pilot?** — cost estimate + go/no-go (TODO **#1b**) | ⬜ after **#3b** | ~$25–80 for 72 API runs; **skip → Stanford main study** |
| 4 | Stanford HPC + main study (`llama31`) | ⬜ after **#3c** | TODO **16a** — default thesis data path |
| 5 | Optional Doug preview (directional) | ⬜ | Not confirmatory claims |
| 6 | Theory/Methods LaTeX sync (split protocol) | ⬜ | TODO **D4**; Methods describes **main study**, not `mistralnemo` pilot runs |

### Scaling & infra (backlog — TODO #16)

| Sub | What | Trigger | Status |
| --- | --- | --- | --- |
| **16b** | Orchestration A1/A3/A6 (async engine) | **Before Centola-3 pilot** | ✅ done 2026-07-24 (§15) |
| 16a | Stanford HPC (Doug D7) | After pilot + **#1b** decision | ⬜ **default thesis data path** |
| 16c | API providers — Pilot host | Before Pilot | ✅ DeepInfra `mistralnemo` |

### Performance / async optimization (✅ implemented — async engine, §15)

**Context:** Wall-clock dominated by sequential LLM I/O. The async engine (§15) is now the **default** path (`--engine async`); the sync `--workers` path is retained only as the offline mock/reference engine. Detailed design, concurrency knobs, determinism lock and run recipe live in **§15**.

| ID | Opportunity | Where | Status |
| --- | --- | --- | --- |
| **A1** | Parallel p1+p2 per interaction | `async_simulation.py` | ✅ `asyncio.gather` on the two player calls (④); RNG drained in sync order first |
| **A2** | Unified async client | `async_llm.py` | ✅ `AsyncOpenAICompatClient` + `AsyncRetryPolicy` (②), wire-identical to sync |
| **A3** | Global API concurrency semaphore | `async_llm.py::RateLimiter` | ✅ shared ceiling across all runs (③⑥); honours `Retry-After` |
| **A6** | Run-level pool (pilot + main) | `async_orchestration.py` | ✅ `asyncio.gather` + `Semaphore` over runs; global queue, not cell-sequential (③) |
| ⑤ | Multi-key / provider pool + failover | `async_llm.py::ProviderPool` | ✅ **scaffold** (N=1 today); adding keys/hosts is config-only (§15 "Providers later") |
| A5 | CM early-stop after flip | — | **Rejected** (protocol deviation) |

**Gate:** ✅ cleared — async engine + Step ① done. **Next:** Pilot (checklist **#3**).

### Pilot vs. main study (locked 2026-07-24)

| | **Pilot** (`mistralnemo`, now) | **Main study** (`llama31`, thesis) |
| --- | --- | --- |
| **Model** | `mistralnemo` (Mistral Nemo 12B, DeepInfra API) | `llama31` (Llama-3.1-70B, **Stanford HPC** self-hosted) |
| **Grid** | Same 72-run pilot CLI (`run_pilot.py`) | `run_main.py` eligible-count targeting |
| **Protocol** | Identical (Centola-3, gate 0.95, CM k∈1…6, seeds) | Identical |
| **In Methods chapter?** | **No** — exploratory / pipeline only | **Yes** — confirmatory |

**After pilot:** optional **Llama API pilot** (same 72-run grid, `llama31`) — **decision after cost estimate** (TODO **#1b**, ~$25–80). **Default if skip:** main study @ **Stanford HPC** (self-hosted Llama; no per-token API).

**Stanford handoff:** After pilot, expected code changes = `config.yaml` registry (cluster endpoint) + env vars — simulation, orchestration, analysis unchanged.

### Sign-off (implementation plan)

| # | Milestone | Owner | Status | Date |
| --- | --- | --- | --- | --- |
| 0 | WORKING.md fully specified (this doc) | Jannik (agent-drafted) | ✅ complete | 2026-07-13 |
| 1 | LLM runner + one dry-run (mixing, k=1, Llama) | Jannik (agent-drafted) | ⚠ code complete offline (A+B+C-01…C-04); real llama31 smoke ⏸ C-05 pending §13 #1/#3 | 2026-07-14 |
| 2 | Full run unit (Phase 1→2, logging, flip coding) | Jannik (agent-drafted) | ✅ complete (B + F-01…F-03) | 2026-07-14 |
| 3 | Pilot orchestration (12 attempted / topology / model) | Jannik (agent-drafted) | ✅ complete (D), verified live on mocked 36-run batch | 2026-07-14 |
| 4 | Live analytics usable during pilot | Jannik (agent-drafted) | ✅ complete (E: Rich + Streamlit + notebook) | 2026-07-14 |
| 5 | Analysis scripts H1–H3b + H4 descriptive | Jannik (agent-drafted) | ✅ complete (F), verified live via `analyze.py --all --model mock` | 2026-07-14 |
| 6 | Main-study batch runner + commit pin for thesis | Jannik (agent-drafted) | ⚠ runner + R1/R2 remediation complete offline (G-01/G-02); commit pin ⏸ G-03/G-04 deferred to analysis freeze (post real data) | 2026-07-14 |

---

## SSOT links (read before coding)

| Priority | Document | Path (from meta-repo) |
| ---: | --- | --- |
| 1 | **This file** | `02_Topic/Experiment_Code/llm-convention-topology/WORKING.md` |
| 2 | Methods chapter hub | `02_Topic/Thesis_Writing/development/03_Methods/WORKING.md` |
| 3 | Procedure locks + logging schema | `…/development/03_Methods/M03_procedure/WORKING.md` |
| 4 | DVs + analysis plan | `…/development/03_Methods/M04_outcomes_analysis/WORKING.md` |
| 5 | Methods LaTeX | `02_Topic/Thesis_Writing/chapters/03_Methods.tex` |
| 6 | Appendix reproducibility | `02_Topic/Thesis_Writing/chapters/99_Appendix.tex` (`app:reproducibility`) |
| 7 | Ashery reference code | `02_Topic/Experiment_Code/ashery-ai-norms/` |
| 8 | Ashery config baseline | `ashery-ai-norms/config.yaml` |

**Optional API reference only (not protocol SSOT):** `02_Topic/Experiment_Code/ai-convention-formation/AI Agents & Norms/` — OpenAI-compatible adapter patterns.

---

## Design locks (summary — detail in Methods)

| Parameter | Lock |
| --- | --- |
| N | 24 |
| Topologies | `complete` (mixing), `random_regular` deg 4, `lattice` (1D ring, nearest + next-nearest) |
| Memory H | 5 |
| Label pool W | 2 (`Q`, `M`) |
| Payoffs | +100 match, −50 mismatch |
| Temperature | 0.5 |
| Gate window | 3N = 72 interactions |
| Gate threshold | **0.95** dyadic success rate |
| Phase 1 max | 5000 interactions |
| Phase 2 horizon | 1000 post-gate interactions |
| CM injection | `swap` mode; k ∈ {1,2,3,4,5,6} |
| Flip (primary) | ≥95%/3N **and** modal label = `committed_to` |
| Non-flip | Single category; right-censor at 1000 |
| Run unit | Ashery split: emergence (W=10 organic) ‖ CM (W=2 prepared) |
| API retries | 3× then `run_status = failed` |
| Models (provisional) | Llama-3.1-70B (primary), Qwen2.5-72B, GPT-5.4, Claude 5.5 |

---

## Current scaffold (implemented)

| Module | Path | Status |
| --- | --- | --- |
| Stability gate | `convention_topology/gate.py` | ✅ |
| Centola-3 networks | `convention_topology/networks.py` | ✅ |
| Phase 1/2 loop skeleton | `convention_topology/simulation.py` | ✅ partial |
| Tracker helpers | `convention_topology/tracker.py` | ✅ partial |
| Config loader | `convention_topology/config.py` + `config.yaml` | ✅ partial |
| Unit tests | `tests/test_gate.py` | ✅ |

```bash
python -m unittest discover -s tests -v
```

---

## 1. Target architecture

### Package tree (target v1)

```text
llm-convention-topology/
├── config.yaml                    # thesis defaults (extended schema — §11)
├── requirements.txt               # pinned stack (§8, §12)
├── run_pilot.py                   # entrypoint: pilot batch (12 attempted Phase 1 / topology / model)
├── run_main.py                    # entrypoint: main-study batch (eligible-count targets per cell)
├── run_one.py                     # entrypoint: single run (debug / smoke / resume)
├── analyze.py                     # entrypoint: H1–H3b + H4 + cross-model dispatch (§8)
├── convention_topology/
│   ├── config.py                  # loader (✅) + config_hash() + model registry resolution
│   ├── networks.py                # Centola-3 graphs + adjacency_hash (✅ — do not rewrite)
│   ├── gate.py                    # 0.95/3N stability gate (✅ — do not rewrite)
│   ├── tracker.py                 # tracker helpers + modal label (✅ partial)
│   ├── simulation.py              # Phase 1/2 loops + swap_committed (✅ partial → wire LLM step)
│   ├── prompting.py               # ported Ashery rules/prompt builder (chat-message format — §2, §4)
│   ├── llm.py                     # provider abstraction: LLMClient protocol, OpenAICompatClient,
│   │                              #   MockLLMClient, RetryPolicy(3×), label parsing (§4)
│   ├── run.py                     # run unit: init → Phase 1 → gate → CM inject → Phase 2 →
│   │                              #   persist pickle + metadata sidecar (§6)
│   ├── persistence.py             # run_id layout, pickle + .meta.json I/O, events .jsonl writer (§6)
│   ├── dvs.py                     # all dependent-variable functions (§7)
│   └── analysis/
│       ├── common.py              # run loader, per-model filtering, eligibility tables
│       ├── h1.py  h2.py  h3.py  h4.py  cross_model.py   # (§8)
├── live/
│   ├── reader.py                  # shared read-only tail of logs/ + meta → DataFrames (§9)
│   ├── monitor.py                 # Rich terminal dashboard (§9)
│   ├── web.py                     # Streamlit localhost graphs (§9)
│   └── cost.py                    # token/cost aggregation from events (§9)
├── notebooks/
│   └── pilot_dashboard.ipynb      # batch-refresh pilot plots (§9)
├── tests/                         # unittest suite + fixtures/ (mock LLM scripts) (§10)
├── data/runs/{model}/{topology}/  # {run_id}.pkl + {run_id}.meta.json  (gitignored)
├── logs/                          # {run_id}.events.jsonl (append-only; live analytics source)
└── outputs/                       # analysis exports (CSV/JSON), figures for Results
```

**Run-ID convention:**
- Emergence: `{model_shorthand}_{topology}_emerg_s{run_seed}` (e.g. `llama31_lattice_emerg_s0042`)
- CM: `{model_shorthand}_{topology}_k{cm_k}_s{run_seed}` (e.g. `llama31_lattice_k3_s0042`)

Programs are separate (Ashery split): organic Phase 1 vs prepared CM.

**Replicator path:** `pip install -r requirements.txt -r requirements-dev.txt` → set provider env vars (§4) → `python run_pilot.py --model llama31` → `python live/monitor.py` + `streamlit run live/web.py` (pilot) → `python run_main.py --model llama31` → `python analyze.py --all --model llama31`.

| Module / script | Responsibility | Status |
| --- | --- | --- |
| `convention_topology/gate.py` | Stability gate 0.95/3N, eligibility, censoring | ✅ |
| `convention_topology/networks.py` | Centola-3 graphs, seeds, adjacency hash | ✅ |
| `convention_topology/tracker.py` | Tracker updates, success coding, modal label (`modal_lexicographic`) | ✅ |
| `convention_topology/simulation.py` | Phase 1/2 loops, `swap_committed`, `shared_shuffle` | ✅ |
| `convention_topology/config.py` | Config load + `config_hash` + model registry | ✅ |
| `convention_topology/orchestration.py` | Shared run dispatch, `get_code_commit`, pilot/main grids | ✅ |
| `convention_topology/prompting.py` | Ashery prompt/rules port (chat-message format) | ✅ |
| `convention_topology/llm.py` | Provider abstraction, retries, parsing, mock | ✅ |
| `convention_topology/run.py` | End-to-end run unit + persistence hooks | ✅ |
| `convention_topology/persistence.py` | run_id, pickle + sidecar JSON, events stream, analysis writers | ✅ |
| `convention_topology/dvs.py` | DV functions (§7) | ✅ |
| `convention_topology/analysis/` | H1–H3b, H4, cross-model + `dispatch.py` | ✅ |
| `run_pilot.py` / `run_main.py` / `run_one.py` | Batch + single-run CLIs (§5) — thin dispatch | ✅ |
| `analyze.py` | Analysis dispatch CLI (§8) | ✅ |
| `live/reader.py`, `live/monitor.py`, `live/web.py` + `notebooks/pilot_dashboard.ipynb` | Live analytics (§9) | ✅ |

---

## 2. Ashery → thesis porting map

Reference tree: `../ashery-ai-norms/` @ `e57aeef` (`publish` tag). Audited 2026-07-13 — all root `.py` files covered below.

| Ashery file / symbol | Thesis destination | Action | Notes |
| --- | --- | --- | --- |
| `config.yaml` | `config.yaml` | **adapt** ✅ | Thesis deviations already applied: `convergence_threshold: 0.95` (repo default **1.0**), `max_phase1_interactions: 5000` (new key), `minority_size_set: [1..6]` (repo `[0]`); drop `alpha/beta/erdos_p` (scale-free/ER out of scope); extend with model registry (§11) |
| `prompting.py::get_rules` | `convention_topology/prompting.py` | **adapt** | Keep rule text verbatim (payoffs +100/−50, 100-round framing); strip hard-coded Llama-3 header tokens — role structure moves to OpenAI-compatible chat `messages` (system/user), provider applies its own template. Documented deviation: token-level template is model-specific in Ashery; thesis uses chat API roles for the four-model factor |
| `prompting.py::get_prompt` | `convention_topology/prompting.py` | **adapt** | Keep H=5 memory windowing, local score, history dict lines, `{'value': …; 'reason': …}` response format verbatim; same header-token strip as above |
| `prompting.py::get_meta_prompt` | — | **skip** | Meta-prompting out of scope v1 |
| `simulation_module.py::population` | `convention_topology/simulation.py::run_phase1` + `run.py` | **reimplement** ✅ partial | Loop skeleton done; wire interaction step (random agent → random neighbour, per-agent option shuffle, prompt → LLM → payoff → `update_dict`/`update_tracker`). Deviations: gate 0.95, **5000 hard cap** (Ashery loops until gate, unbounded), periodic checkpoint via `persistence.py` instead of inline pickle |
| `simulation_module.py::committed` | `convention_topology/simulation.py::run_phase2` + `run.py` | **reimplement** ✅ partial | CM agents emit `committed_to` **without LLM call** (adopt); horizon 1000 (adopt); incumbent = modal label in trailing 3N at gate (thesis lock — Ashery prepared populations use `options[1]` by construction) |
| `simulation_module.py::individual` | — | **skip** | Individual bias battery replaced by H4 run-level incumbent-label distribution (Methods lock) |
| `simulation_module.py::simulate_meta_prompting` | — | **skip** | Out of scope v1 |
| `utils.py::get_interaction_network` | `networks.py` | **adapt** ✅ | Done: adds `lattice` (1D ring deg 4 — thesis extension, Centola 2015), seeds `random_regular` (Ashery draws unseeded), drops `scale_free`/`ER`; adds `adjacency_hash` |
| `utils.py::has_tracker_converged` | `gate.py` | **adapt** ✅ | Done: threshold parameterized, thesis 0.95 (locked Methods deviation from repo 1.0); adds `GateResult`/eligibility/censoring semantics (new — Ashery has no eligibility concept) |
| `utils.py::get_outcome`, `update_dict`, `update_tracker` | `tracker.py` | **adopt** ✅ | Verbatim semantics incl. success rule `outcome > 5` |
| `utils.py::swap_committed` | `simulation.py::swap_committed` | **adopt** ✅ | `swap` mode locked; `add_committed` (inject) **skip** |
| `utils.py::set_initial_state`, `get_prepared_population`, `test_if_initialisation_worked`, `get_random_prepared_player` | `prepared.py` | **adopt** ✅ | CM program: prepared consensus (Ashery `committed_runner`) |
| `utils.py::load_mainframe`, `get_empty_population`, `get_player` | `persistence.py` | **reimplement** | Replace bare-`except` pickle resume with explicit run_id-addressed I/O + metadata sidecar (§6) |
| `runner.py::bias_runner` / `committed_runner` | `run_pilot.py` / `run_main.py` (`--program`) | **reimplement** ✅ | Separate emergence vs CM grids |
| `run_API.py::query`, `get_response` | `llm.py` | **reimplement** | Ashery: HF serverless, infinite retry loop, quote-split parsing. Thesis: OpenAI-compatible chat client, **3× retry then `run_status = failed`** (M03 lock), regex/JSON parse of `{'value': …}` against valid options; `get_meta_response` skip |
| `run_local.py` | — | **skip** | Local 4-bit GPU inference not used; all four models via API (Methods lock). Revisit only if provider access fails |
| `NG_module.py`, `run_NG.py` | — | **skip** | Minimal-theory Naming Game — paper figure S3 only; theory reference |
| `meta_prompting.py`, `meta_prompting_runner.py`, `real_player_meta_prompting.py`, `run_real_player_metaprompting.py` | — | **skip** | Meta-prompting battery out of scope v1 (Methods lock) |
| `analyse_individual_bias.py` | — | **skip** | Individual bias analysis not used (H4 replaces) |
| `plotter.ipynb` | `notebooks/` + `analysis/` | **reference** | Reuse metric ideas (rolling success, label shares) — no verbatim port |
| `README.md` | `README.md` | **reference** | Llama-2 token substitutions irrelevant after chat-API move; shorthand conventions inform run_id scheme |

### Locked thesis deviations from upstream (cite Methods, not ad hoc)

| Deviation | Upstream | Thesis lock | Methods source |
| --- | --- | --- | --- |
| Gate threshold | `convergence_threshold: 1.0` | **0.95** | M03 / hub design locks (Ashery *paper* criterion) |
| Phase 1 cap | none (loop until gate) | **5000**, `censored` status | M03 (pilot observes censoring) |
| Topologies | `complete` only in practice | **Centola-3** incl. 1D ring lattice deg 4 | M02 / hub (Centola 2015) |
| CM grid | `minority_size_set: [0]` | **k ∈ {1…6}**, factorial | M01 (locked 2026-07-10) |
| Models | Llama-family, HF API | **4-model between-run factor**, OpenAI-compatible adapter | M02 (Llama-3.1-70B primary confirmatory) |
| Flip taxonomy | none (post-hoc in notebook) | flip vs. **single non-flip/censored** category — **no `flip_resisted`** | M03/M04 R2 fix 2026-07-13 |
| Run unit | Separate emergence ‖ CM programs (prepared CM) | Ashery split (2026-07-21) |
| Retry policy | infinite retry w/ sleeps | **3× then `run_status = failed`** | M03 API error handling |
| Phase 2 option shuffle | `committed()` shuffles options **once per interaction**, shared by both players, before `p1`/`p2` are chosen | **restored to upstream fidelity** (2026-07-14, code review M1): `make_interaction_step(..., shared_shuffle=True)` for Phase 2. Phase 1 keeps `population()`'s **per-agent independent shuffle** (`shared_shuffle=False`, default) | M1 fix, `simulation.py::make_interaction_step` |

**N2 (2026-07-14, code review, minimal touch — `networks.py` stays locked "do not rewrite"):** `get_interaction_network`'s `minority_size` branch (module-level `random.sample`) is dead code — committed-minority assignment always goes through `simulation.py::swap_committed`'s injected-rng path instead, and `execute_run` always calls with `minority_size=0`. A guard now raises `NotImplementedError` if `minority_size != 0` is ever passed, so the dead path can't be silently reactivated; the branch itself is untouched.

### Adopt vs. skip (seed — agent completes)

| Component | Adopt? | Notes |
| --- | --- | --- |
| `prompting.py` | ✅ | Core protocol |
| `simulation_module.py` | ✅ | Extend loops; CM + gate |
| `utils.py` | ⚠️ partial | Networks + gate; lattice in `networks.py` |
| `runner.py` | ✅ adapt | Factorial orchestration |
| `run_API.py` / `run_local.py` | ✅ adapt | Model backends |
| `NG_module.py` | ❌ | Theory reference only |
| `meta_prompting*.py` | ❌ | Out of scope v1 |
| `individual()` bias battery | ❌ | H4 from run-level labels instead |

---

## 3. Implementation phases

| Phase | Deliverable | Depends on | Files touched | Acceptance criteria (testable) | Status |
| --- | --- | --- | --- | --- | --- |
| A | **Mock LLM layer + prompting port** — `llm.py` (`LLMClient` protocol, `MockLLMClient` with scripted/convergent policies, label parser, `RetryPolicy`), `prompting.py` port | — | `llm.py`, `prompting.py`, `tests/test_llm.py`, `tests/test_prompting.py`, `tests/fixtures/` | `python -m unittest discover -s tests -v` green; parser recovers label from ≥5 canned response fixtures incl. malformed → retry path; prompt snapshot fixture matches Ashery content minus header tokens | ✅ |
| B | **Full run unit (mocked)** — `run.py` + `persistence.py`: init → Phase 1 → gate → swap → Phase 2 → pickle + `.meta.json` + events `.jsonl` | A | `run.py`, `persistence.py`, `simulation.py` (wire step), `tests/test_run_integration.py` | One mocked mixing run (k=1, seed 0) completes < 10 s and produces pickle + sidecar with **all §6 metadata fields non-null** and valid `config_hash`; censored + failed paths covered by tests | ✅ |
| C | **Real API smoke** — `OpenAICompatClient` + model registry + env-var wiring | A, B | `llm.py`, `config.py`, `config.yaml`, `run_one.py` | Offline path (C-01…C-04) ✅; **C-05** (paid llama31 smoke) ⏸ — needs §13 #1/#3 | ⚠ C-01…C-04 ✅; C-05 ⏸ |
| D | **Pilot batch runner** — `run_pilot.py` factorial CLI with resume-by-sidecar | B, C | `run_pilot.py`, `persistence.py` | Dry-run mode prints exactly the §5 pilot grid (36 runs/model); interrupted batch resumes without re-running `completed`/`censored` runs; failed runs re-attempted only with `--retry-failed` | ✅ |
| E | **Live analytics** — `live/reader.py` + Rich `monitor.py` + **Streamlit `web.py`** + notebook (§9) | B (events stream), D | `live/`, `notebooks/` | Terminal monitor ≤5 s refresh on mocked 6-run batch; Streamlit localhost renders §9 graph panels; `data/` mtimes unchanged after 2-min session | ✅ |
| F | **DV module + analysis scripts** — `dvs.py`, `analysis/`, `analyze.py` (§7–§8) | B | `dvs.py`, `analysis/*`, `analyze.py`, `tests/test_dvs.py` | Unit tests per DV green (incl. 144-denominator case); `python analyze.py --all --model mock` emits H1–H4 JSON/CSV to `outputs/` without error | ✅ |
| G | **Main-study runner + repro freeze** — `run_main.py` eligible-count targeting, §12 pins | C, D, F | `run_main.py`, `WORKING.md`, `README.md` | G-01/G-02 ✅ (dry run + mocked targeting); **G-03/G-04** ⏸ post-data (exact pins + freeze tag) | ⚠ G-01/G-02 ✅; G-03/G-04 ⏸ |

Order rationale (matches user priority): mock layer first so everything downstream is testable without API cost; live analytics (E) lands **before** the real pilot week; analysis (F) can proceed in parallel with D/E on mocked data.

---

## 4. LLM API layer

**Design:** single `LLMClient` protocol in `convention_topology/llm.py`; two implementations.

| Implementation | Purpose |
| --- | --- |
| `OpenAICompatClient(base_url, model_id, api_key_env, params, openrouter_provider?)` | Open-weight models (Llama, Qwen) via **OpenRouter** (`https://openrouter.ai/api/v1`); proprietary models via **direct** provider endpoints — OpenAI, Anthropic (OpenAI-compat layer), Google Gemini (OpenAI-compat layer). All use `/chat/completions` through the OpenAI Python SDK. |
| `MockLLMClient(policy, rng)` | Deterministic test/dev backend — no network. Policies: `scripted` (fixture playback), `imitate_modal` (answers modal label of own memory → converges), `always(label)`, `random` (never converges → exercises censoring) |

**Model registry (in `config.yaml`, §11):** per model — `provider`, `shorthand`, `model_id` (pinned string), `base_url`, `api_key_env`, `temperature: 0.5`, `max_tokens`; optional `openrouter_provider` for OpenRouter routing pins. Four-model factorial: `llama31`, `qwen25`, `gpt54`, `claude55` — GPT/Claude strings blocked on Doug (§13 #1). Auxiliary registry entry **`gemini35`** (`gemini-3.5-flash`, Google direct) — code-only, not part of the four-model factorial.

**Env vars (never committed; `.env` in `.gitignore`):** `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (auxiliary). Startup check fails fast with a clear message if the required var for the selected model is unset.

**Prompting → messages:** `prompting.py` returns `(system, user)` content strings (rules → system; history + query → user); client assembles provider `messages`. Response format request stays in-prompt (`{'value': <LABEL>; 'reason': <TEXT>}`) exactly as Ashery.

**Parsing:** extract label by (1) attempt structured parse of `'value':` field, (2) fallback regex match of any valid option token surrounded by quotes/word boundaries, mirroring Ashery quote-split semantics. Ambiguous (0 or ≥2 distinct options matched) → parse failure.

**Retry policy (M03 lock):** timeout, rate limit, HTTP error, or parse failure → retry same call up to **3×** (exponential backoff 2/4/8 s). Still failing → raise `RunFailedError` → run aborts, sidecar `run_status = failed`, excluded from confirmatory analysis, **not auto-replaced**. Every attempt logged to events stream with error class (feeds §9 error widget).

**Per-run logging:** `model_id`, `base_url`, decoding params, and prompt-template version string written to `.meta.json`; token usage per call appended to events `.jsonl` (feeds cost widget).

**CM agents:** `run.py` short-circuits before any client call — committed agents emit `committed_to` directly (Ashery `committed()` behavior); zero API cost, unaffected by retry policy.

---

## 5. Run orchestration

### Factorial grid

Full design space per model: **topology ∈ {complete, random_regular, lattice} × k ∈ {1…6} × seeds**. Every run is sequential Phase 1→2 with its own k (M03 run-unit lock); `graph_seed` and `run_seed` derived deterministically from `(topology, k, seed_index)` via a fixed base seed so the grid is reproducible.

### Pilot grid (`mistralnemo`)

**Two programs, run separately** (`--program emergence` **then** `--program cm` — one CLI invocation each; **do not** run both in parallel at full `--api-concurrency`; see recipe below).

| Program | Runs | What each run does |
| --- | ---: | --- |
| **emergence** | 36 | Organic Phase 1 (W=10) until stability gate or cap 5000; **no CM** |
| **cm** | 36 | Prepared population (W=2, incumbent **Q**) → `swap_committed` **k** agents → Phase 2 horizon **1000** |

Per program: **12 seeds × 3 topologies** (`complete`, `random_regular`, `lattice`). CM assigns **k cyclically** per topology (seeds 1–12 → k = 1,2,3,4,5,6,1,2,…) — **2 runs per (topology × k) cell**. Seeds are **deterministic** (`derive_seeds` from `run.base_seed`); **which agents** are committed is a **seeded random sample** of k nodes (`swap_committed`), not fixed node IDs.

**Scope lock (2026-07-24):** 72-run **pilot** on `mistralnemo` — same protocol as main study; **only model differs**. **Excluded from Methods manuscript.** Informs pipeline readiness, directional topology/CM patterns, and Stanford planning. Thesis claims → **main study** (`llama31` @ Stanford HPC).

Doug email 2026-07-20: open-source first — directional preview from pilot may support early share; confirmatory results from **main study**.

### Main study targets (per model — M01 locks)

| Stratum | Target | Runner behavior |
| --- | --- | --- |
| Mixing, per k cell (6 cells) | **15–20 eligible** Phase 2 runs | `run_main.py` keeps launching seeds in a cell until eligible count ≥ target or attempted cap (default 3× target) reached |
| Lattice / random, per (topology × k) cell | **8–10 eligible** (conditional on pilot eligibility — Contingency Option A default) | Same targeting; cells may be demoted to exploratory after pilot |
| H1/H2 | All attempted Phase 1 runs per topology (incl. censored) | No extra runs needed — pooled from the above |

### CLI (copy-paste ready)

```bash
cd "/Users/jannikendress/Master Thesis/02_Topic/Experiment_Code/llm-convention-topology"
# Requires DEEPINFRA_API_KEY in .env for mistralnemo; OPENROUTER_API_KEY for llama31

# Dry-run (preview grid)
python3 run_pilot.py --model mistralnemo --program emergence --dry-run
python3 run_pilot.py --model mistralnemo --program cm --dry-run

# --- Pilot (mistralnemo; NOT thesis Methods data) ---
# Same protocol as main study; only --model mistralnemo differs.
python3 run_pilot.py --model mistralnemo --program emergence \
  --run-concurrency 64 --api-concurrency 192

python3 run_pilot.py --model mistralnemo --program cm \
  --run-concurrency 64 --api-concurrency 192

# Exploratory analysis (do not import into thesis Results)
python3 analyze.py --all --model mistralnemo

# Resume after interruption (skips completed/censored; default)
python3 run_pilot.py --model mistralnemo --program emergence --retry-failed

# Main study (thesis confirmatory — Stanford HPC, llama31; endpoints TBD)
python3 run_main.py --model llama31 --topology complete

# Offline mock / reference engine (deterministic, no network)
python3 run_pilot.py --model mock --engine sync --workers 4
```

**Parallelization policy:** interactions within a run are sequential (Markov chain). Parallelism = **`--api-concurrency`** (global in-flight API calls — **set from Step ①**) + **`--run-concurrency`** (how many runs share the event loop; target `≥ api-concurrency / 2`). Within one interaction, two player calls overlap (`asyncio.gather`, ④). **Do not** launch emergence + cm in parallel at full `--api-concurrency` each — separate processes do not share a `RateLimiter` (192+192 > DeepInfra cap 200).

**Decoding lock (2026-07-24):** `max_tokens: 2000` on `llama31` and `mistralnemo` — CoT + `{'value':…}` must not truncate (C-05 / proof D6; 512 caused parse fails).

**Checkpointing:** tracker + simulation state pickled every 50 interactions (Ashery cadence) to `{run_id}.pkl` with `run_status = in_progress` in the sidecar; final write flips status. A crashed run resumes from the last checkpoint on next batch invocation.

### Pilot (locked)

| Unit | Target |
| --- | ---: |
| Phase 1 attempted runs / topology | 12 |
| Purpose | Eligibility triage per Centola-3 topology |

### Main study (locked — per model)

| Stratum | Target |
| --- | --- |
| Mixing Phase 2 eligible / CM level k | 15–20 |
| Lattice/random eligible / (topology × k) cell | 8–10 |
| H1/H2 | Pool all attempted Phase 1 per topology |

---

## 6. Logging and persistence

**Layout:** `data/runs/{model_shorthand}/{topology}/{run_id}.pkl` + `{run_id}.meta.json`; `logs/{run_id}.events.jsonl`. `data/` and `logs/` gitignored; `outputs/` holds analysis exports.

**Pickle schema (Ashery-compatible superset):**

```python
{
  "simulation": {node_id: {my_history, partner_history, interactions, score,
                           score_history, outcome, committed_tag, neighbours}},
  "tracker":    {"players": [...], "answers": [...], "outcome": [...]},
  "convergence": {"converged_index": t_gate, "committed_to": label},
}
```

**Metadata sidecar `.meta.json` (M03 schema + Appendix `app:methods-implementation`):** `run_id`, `topology`, `cm_k`, `model_id`, `model_shorthand`, `endpoint_base_url`, `graph_seed`, `run_seed`, `adjacency_hash`, `t_gate`, `t_phase1_end`, `eligibility`, `incumbent_label`, `committed_to`, `phase2_horizon` (=1000), `config_hash`, `run_status`, plus operational extras: `started_at`, `finished_at`, `n_api_calls`, `n_retries`, `prompt_template_version`, `code_commit`.

**`config_hash`:** SHA-256 (first 16 hex chars) of the canonical JSON serialization (sorted keys) of the fully **resolved** run config (defaults + CLI overrides), with secret-bearing fields (`api_key_env` values) excluded. Computed in `config.py::config_hash()`; identical hash ⇔ identical run parameters.

**Run status semantics:**

| `run_status` | Meaning | Analysis handling |
| --- | --- | --- |
| `completed` | Gate passed, Phase 2 horizon finished | All DVs; confirmatory |
| `censored` | 5000-cap hit without gate (`eligibility = 0`) | Phase 1 DVs only (H1/H2); counted in eligibility denominators |
| `failed` | Aborted after 3× API retry failure | Excluded from confirmatory analysis; **not auto-replaced**; effective *n* reported in Results |
| `in_progress` | Checkpointed, still running / resumable | Ignored by analysis; visible to §9 monitor |

**Events stream (`.jsonl`, append-only, one line per event):** interaction summaries every 10 interactions (`t`, phase, rolling 3N success, dominant share), API errors/retries, phase transitions, token usage. Written by `persistence.py::EventWriter` with line-buffered appends — the only file the live monitor tails, so readers never touch pickles of active runs.

---

## 7. Dependent variables (code)

All DVs in `convention_topology/dvs.py`, pure functions over tracker (+ metadata), unit-tested in `tests/test_dvs.py` with hand-computed fixtures.

**Label-share denominator (locked):** windows are counted in **label emissions** — the final 3N = 72 interactions contribute 2 labels each ⇒ denominator **2 × 3N = 144** for all share/entropy computations. `label_shares(tracker, window=72)` is the single shared helper; every share DV routes through it.

| DV | Computation (function) | Module | Tests |
| --- | --- | --- | --- |
| Dominant label share (final 3N) | `dominant_share(tracker)` = max label count / **144** over final-72-interaction emissions | `dvs.py` | ✅ `test_dvs.py` (100/144, denominator 144) |
| Shannon entropy (descriptive) | `shannon_entropy(tracker)` = −Σ pᵢ ln pᵢ over same 144-emission shares | `dvs.py` | ✅ uniform → ln 2; degenerate → 0 |
| Rounds to gate | `t_gate` from `GateResult` (already computed); exposed via `dvs.rounds_to_gate(meta)`, censored = 5000 flag | `gate.py`/`dvs.py` | ✅ gate tests + `dvs.rounds_to_gate` |
| Flip (primary) | `flip(tracker, committed_to, t_start)` = 1 iff ∃ trailing-3N window in Phase 2 with success ≥ 0.95 **and** modal emission = `committed_to`; else 0 (single non-flip/censored category — **no `flip_resisted`**, R2 lock) | `dvs.py` | ✅ flip, non-flip, re-convergence-on-incumbent |
| Flip (Centola 50% sensitivity) | `flip_50(simulation, tracker, committed_to)` = 1 iff > 50% of **noncommitted** agents have modal own-emission = `committed_to` in final 3N window; secondary only, agreement table → Appendix | `dvs.py` | ✅ boundary at exactly 50% (must be 0) |
| Time-to-flip | `time_to_flip(...)` = interactions from CM injection (`t_gate`) to end of first qualifying flip window; censored at 1000 if no flip | `dvs.py` | ✅ censoring value + known-flip fixture |
| Critical mass | `critical_mass(runs_df)` = smallest k with flip rate ≥ 0.5 among **eligible** runs, computed at **(topology × model) condition level**; `None` if never reached | `analysis/common.py` | ✅ synthetic flip-rate table incl. no-CM case |
| H4 incumbent label | `incumbent_label(tracker, t_gate)` = modal emission in trailing 3N at gate (also drives CM injection); H4 = distribution of incumbents across runs | `dvs.py` | ✅ `modal_lexicographic` tie-break (shared w/ production) |
| Eligibility | from `GateResult` (`gate.py`) | `gate.py` | ✅ |

---

## 8. Analysis pipeline

Entry: `python analyze.py --h1|--h2|--h3a|--h3b|--h4|--cross-model|--all --model {shorthand}`. Every script runs **per model** (`--model` required except `--cross-model`); results exported as JSON (stats) + CSV (run-level table) to `outputs/{model}/`. **PDF figures deferred** to Results/real-data time (WORKING §8 figure promise open by design). **Llama-3.1-70B is the primary confirmatory model** — thesis-level hypothesis-support statements read from its outputs only; the other three models are descriptive robustness strata, never pooled or majority-voted (Methods cross-model rule, locked 2026-07-13).

**H1/H2 input window (R2-B1 fix, 2026-07-14):** `analysis/common.py::_phase1_end_tracker` slices the tracker to Phase 1 end (`[:t_gate]` for completed runs; full tracker for censored) before computing `dominant_share`/`shannon_entropy`. Censored runs are included in H1/H2 (Methods:212/246).

| Hypothesis | Script | Test (locked M04) | Input | Output |
| --- | --- | --- | --- | --- |
| H1 | `analysis/h1.py` | One-sample *t* vs. τ = 0.90 on dominant share (mixing, all attempted Phase 1); Wilcoxon signed-rank as primary robustness if left-skewed; 95% CI. Plus **descriptive regime proportion**: share of runs with dominant share > τ = 0.90 (no test) | run table from `analysis/common.py` | `outputs/{model}/h1.json/.csv` + share distribution figure |
| H2 | `analysis/h2.py` | 2 pre-planned one-tailed Welch *t* contrasts (lattice < mixing; random < mixing), α = .05 each, no correction; Mann–Whitney *U* robustness; Shannon entropy reported descriptively alongside | all attempted Phase 1 runs per topology | `h2.json/.csv` + per-topology share/entropy figure |
| H3a | `analysis/h3a.py` | Logistic GAM `flip ~ s(cm_k)` (`pygam.LogisticGAM`); LR test vs. linear logistic (`statsmodels Logit`); mixing primary, sparse strata conditional on eligibility floor | eligible Phase 2 runs | `h3a.json/.csv` + flip-curve figure |
| H3b | `analysis/h3b.py` | Logistic regression `flip ~ cm_k × topology` (statsmodels), LR test vs. main-effects model; auto-check confirmatory condition (≥2 topologies × ≥8 eligible/cell) and label output `confirmatory` vs. `exploratory/informative-null` | eligible Phase 2 runs | `h3b.json/.csv` |
| H4 (exploratory) | `analysis/h4.py` | Descriptive incumbent-label frequencies (mixing); optional χ² vs. uniform (scipy) | Phase 1 incumbents | `h4.json/.csv` |
| Cross-model robustness | `analysis/cross_model.py` | Descriptive comparison of dominant share, flip curves, critical mass across the four models; no pooled inference | all models' outputs | `outputs/cross_model.json` + comparison figures |
| Reporting | `analysis/common.py --eligibility` | Attempted / eligible / censored / failed counts by topology × model (Phase 2 denominators, Results table) | sidecars | `outputs/{model}/eligibility.csv` |
| Sensitivity | inside `h3a.py --sensitivity-50` | 95% vs. 50% flip-indicator agreement (mixing) → Appendix `tab:appendix-flip-agreement` | eligible mixing runs | `flip_agreement.csv` |

**Stats stack (locked in `requirements.txt`, pinned at Phase F):** `numpy`, `pandas`, `scipy` (t/Wilcoxon/Mann–Whitney/χ²), `statsmodels` (logistic + LR tests), `pygam` (H3a spline), `matplotlib` (figures), plus existing `networkx`, `PyYAML`, `munch`; runtime: `openai` (OpenAI-compatible client), `rich` (monitor), `python-dotenv`.

---

## 9. Live analytics (pilot + main)

**Decision: triple hybrid — Rich terminal (KPIs/alerts) + Streamlit on `localhost:8501` (live graphs) + Jupyter notebook (batch deep-dive).** Rationale: Rich stays lightweight for a second terminal next to the batch runner; Streamlit adds browser charts (eligibility curves, trajectories, distributions) with ~1–2 days extra work and no deploy; notebook handles publication-quality replots on demand. All three share **`live/reader.py`** (single read-only data layer).

**Files:** `live/reader.py` (shared tail/scan → DataFrames), `live/monitor.py` (Rich), `live/web.py` (Streamlit), `live/cost.py`, `notebooks/pilot_dashboard.ipynb`.

**Read path (no corruption of active runs):** all live components read **only** append-only `logs/*.events.jsonl` and `.meta.json` sidecars. Never open `data/**/*.pkl` of active runs. Read-only by construction.

| Component | Update mode | Content |
| --- | --- | --- |
| Run table (`monitor.py` + `web.py` KPIs) | real time, 5 s | Per topology × model: in_progress / completed / censored / failed; per active run: t, phase, rolling 3N success |
| Eligibility panel | real time | Rolling gate-pass rate per topology (pilot triage) — **line chart in Streamlit** |
| Dominant-share panel | real time | Snapshot + distribution — **bar/violin in Streamlit** |
| API health panel | real time | Error/retry counts — terminal + Streamlit |
| Cost panel | real time | Cumulative tokens + $ estimate |
| Coordination trajectories | real time (**Streamlit**) + batch (notebook) | Phase 1 success curves per run |
| t_gate histograms, full share distributions | **batch** (notebook) | On-demand deep plots |

```bash
python live/monitor.py --watch logs/ --refresh 5          # terminal 2
streamlit run live/web.py --server.port 8501              # browser → localhost:8501
jupyter nbconvert --to notebook --execute notebooks/pilot_dashboard.ipynb
```

**Minimum pilot dashboards:**

- [x] Runs completed / failed / in progress by topology × model → run table + Streamlit KPIs
- [x] Gate eligibility rate by topology (rolling) → eligibility panel (Streamlit line chart)
- [x] Phase 1 dominant-share distribution → Streamlit bar/violin + notebook full distribution
- [x] API error rate and retry counts → API health panel
- [x] Cost / token estimates → cost panel
- [x] Live coordination-success trajectories → **Streamlit line chart** (+ notebook batch)

---

## 10. Testing strategy

Framework: stdlib `unittest` (already in use); runner `python -m unittest discover -s tests -v`. CI: GitHub Actions workflow running the suite on push (unit + integration only — never real API).

**Mock LLM fixtures (essential, Phase A):** `MockLLMClient` policies (§4) + `tests/fixtures/` golden files: canned raw responses (well-formed, malformed, ambiguous → parser/retry paths), a scripted convergent Phase 1 transcript, and a prompt snapshot (golden prompt text for a known 5-interaction history — guards the Ashery port against drift).

| Layer | Scope | How | Status |
| --- | --- | --- | --- |
| Unit | gate, networks, tracker | `test_gate.py` | ✅ |
| Unit | prompting port, label parser, retry policy | `test_prompting.py`, `test_llm.py` vs. golden fixtures; retry asserts exactly 3 attempts then `RunFailedError` | ✅ |
| Unit | DV functions incl. 144 denominator, flip taxonomy, 50% boundary | `test_dvs.py` hand-computed fixtures (§7) | ✅ |
| Integration | one mocked full run per topology (Phase 1→2, persistence, metadata completeness, resume-from-checkpoint) | `test_run_integration.py` with `imitate_modal` + `random` (censoring) policies | ✅ |
| Integration | analysis pipeline on synthetic run set with known statistical answers; Phase-1-window + censored-inclusion (R2-B1) | `test_analysis.py` | ✅ |
| Integration | orchestration (grid, resume, `get_code_commit` cwd-pin) | `test_orchestration.py` | ✅ |
| Smoke (manual, costs money) | one real API call per model; 20-interaction mini run | `run_one.py --smoke` (§3 Phase C-05) — excluded from CI | ⏸ |

---

## 11. Configuration and CLI

**Schema extension (backwards-compatible with current `config.yaml`; Ashery keys retained where meaningful):**

```yaml
network:
  network_type: complete            # complete | random_regular | lattice (CLI-overridable)
  degree: 4
minority:
  minority_size_set: [1, 2, 3, 4, 5, 6]
  committment_index: 1              # kept for Ashery compat; incumbent derived at gate
params:
  temperature: 0.5
  total_interactions: 1000          # Phase 2 horizon
  max_phase1_interactions: 5000
  N: 24
  convergence_time: 72              # 3N
  convergence_threshold: 0.95
  rewards_set: [[-50, 100]]
  memory_size_set: [5]
  options_set: [[Q, M]]
run:
  base_seed: 20260713               # grid-seed derivation root
  checkpoint_every: 50
  workers: 1
  pilot_attempted_per_topology: 12
  main_eligible_targets: {complete: [15, 20], random_regular: [8, 10], lattice: [8, 10]}
  attempted_cap_factor: 3
models:                             # registry (§4); active model chosen by CLI --model
  llama31: {provider: openrouter, model_id: meta-llama/llama-3.1-70b-instruct, base_url: https://openrouter.ai/api/v1, api_key_env: OPENROUTER_API_KEY, openrouter_provider: {allow_fallbacks: false}, max_tokens: 200}
  qwen25:  {provider: openrouter, model_id: qwen/qwen-2.5-72b-instruct, base_url: https://openrouter.ai/api/v1, api_key_env: OPENROUTER_API_KEY, openrouter_provider: {allow_fallbacks: false}, max_tokens: 200}
  gpt54:   {provider: openai, model_id: TBD-doug, base_url: https://api.openai.com/v1, api_key_env: OPENAI_API_KEY, max_tokens: 200}
  claude55: {provider: anthropic, model_id: TBD-doug, base_url: https://api.anthropic.com/v1/, api_key_env: ANTHROPIC_API_KEY, max_tokens: 200}
  gemini35: {provider: google, model_id: gemini-3.5-flash, base_url: https://generativelanguage.googleapis.com/v1beta/openai/, api_key_env: GEMINI_API_KEY, max_tokens: 200}
paths: {data: data/runs, logs: logs, outputs: outputs}
```

Retired Ashery keys: `network.alpha/beta/erdos_p` (scale-free/ER), `params.initial*`, `params.runs` (superseded by `run:` targets), `sim.mode` (`gpu` path dropped), `model.API_TOKEN` (secrets → env vars only).

**Override precedence:** defaults in `config.yaml` → optional `--config other.yaml` → CLI flags (`--model --topology --k --seed --max-interactions --workers --dry-run --retry-failed --smoke`). The fully resolved config is what `config_hash` hashes and what the sidecar snapshot stores. Example commands: §5.

---

## 12. Reproducibility hooks

**Workflow:** (1) every run sidecar records `code_commit` (repo `HEAD` at launch) + `config_hash`; (2) at **analysis freeze**, tag the repo (`v1.0-analysis-freeze`), record the commit here and in Appendix `tab:appendix-repro-pins` (`99_Appendix.tex`); (3) pin `requirements.txt` to exact versions (`pip freeze` of the run environment) at Phase G; (4) alignment snapshot = the §2 porting map (adopt/adapt/skip vs. `ashery-ai-norms` @ `e57aeef`, `publish` tag), cross-referenced by Appendix `app:reproducibility`.

| Artifact | Pin location | Current value |
| --- | --- | --- |
| Thesis repo commit | `WORKING.md` + Appendix `tab:appendix-repro-pins` | `e182e4f` (Phases A–G + R1/R2 + provider routing; pilot/main-study baseline). **Analysis-freeze tag** (`v1.0-analysis-freeze`) + exact `pip freeze` pins still TBD at G-03/G-04 after real data. |
| Ashery Zenodo release | Bib key `asheryAINormsZenodo2024` | DOI 10.5281/zenodo.14937173 |
| Ashery submodule commit (alignment snapshot) | README + Appendix | `e57aeef` = `publish` tag |
| Model identifiers | Per-run sidecar `model_id` + Methods §2 | Llama/Qwen pinned; GPT-5.4/Claude 5.5 TBD (§13 #1) |
| Python dependency versions | `requirements.txt` (exact pins at Phase G) | ranges for now |

---

## 13. Open decisions and blockers

*Code-blocking items only. Model-ID locks tracked in [`01_Orga/Doug_Open_Questions.md`](../../../01_Orga/Doug_Open_Questions.md).*

| # | Item | Blocks | Owner | Status |
| --- | --- | --- | --- | --- |
| 1 | GPT-5.4 / Claude 5.5 pinned model strings + provider access | §4 registry entries; Phase C smoke for those two models (Llama/Qwen unaffected) | Doug / Jannik | **deferred 2026-07-20** — Doug email: open-source first; strings after result share ([Doug_Open_Questions.md](../../../01_Orga/Doug_Open_Questions.md)) |
| 2 | **Bib mismatch found 2026-07-13:** `asheryAINormsZenodo2024` cited in Methods/Appendix | Appendix repro citations | Jannik | **closed 2026-07-14** — entry in `thesis-writing/literature.bib` (uncommitted) |
| 3 | OpenRouter for Llama-3.1-70B + Qwen2.5-72B (`OPENROUTER_API_KEY`; pin `openrouter_provider.only` after C-05 smoke) | §4 registry; Phase C smoke | Jannik | **closed 2026-07-14** — see [`PROVIDER_ROUTING_PLAN.md`](PROVIDER_ROUTING_PLAN.md) |
| 4 | API budget + per-provider rate limits | Phase D/G scheduling | Jannik | **partial 2026-07-24** — pilot ~$1–3 (`mistralnemo`); optional Llama pilot ~$25–80 (#1b); main study @ Stanford HPC |
| 5 | **Structured Output vs. Ashery parsing** — API JSON-schema/constrained enum `{Q,M}` vs. in-prompt format + `parse_label()` (see Doug **D6**) | Pre-pilot protocol lock; `llm.py` / `OpenAICompatClient` if switching before main study | Doug / Jannik | **deferred** — keep Ashery parse path unless pilot failure rates force revisit |
| 6 | **C-05 smoke + OpenRouter `only` pin** — after `OPENROUTER_API_KEY` / `GEMINI_API_KEY` in `.env`, run `run_one.py --smoke` for `llama31`, `qwen25`, `gemini35`; add discovered `openrouter_provider.only` slugs to `config.yaml` | Reproducible backing host for open-weight models | Jannik | **closed 2026-07-20** — `llama31`+`qwen25` smoke 20/20 via DeepInfra; `only: ["deepinfra"]` + `max_tokens: 512` (200 truncated CoT before `value`); `gemini35` deferred |

---

## 14. Session log

| Date | Change |
| --- | --- |
| 2026-07-10 | Initial scaffold: gate, networks, simulation skeleton, tests |
| 2026-07-13 | WORKING.md created; implementation plan sign-off table; fill prompt added |
| 2026-07-13 | **IMPLEMENTATION_PLAN.md created** — WORKING §3 phases A–G decomposed into 45 verifiable todos (master checklist, per-phase entry/exit gates, file creation order, test matrix, cumulative CLI smoke sequence, blocker→todo mapping, milestone sign-off mapping); README linked |
| 2026-07-13 | IMPLEMENTATION_PLAN.md rev. 4 — Streamlit localhost dashboard (E-06): shared `live/reader.py`, six browser panels, `requirements-dev.txt`; WORKING §9 updated to triple hybrid (Rich + Streamlit + notebook) |
| 2026-07-13 | IMPLEMENTATION_PLAN.md rev. 3 — §7 dependency stack researched (PyPI Jul 2026): openai 2.45 SDK patterns, scipy&lt;1.17/pygam pin, Together/Anthropic registry defaults, Rich/nbconvert/coverage CI, stats analysis code patterns |
| 2026-07-13 | **WORKING.md fully specified (milestone 0 ✅)** — filled §1–§13 from Methods SSOT (hub + M03/M04) and full Ashery root-file audit (`e57aeef`/`publish`): target architecture + run_id layout; complete file-by-file porting map with 8 locked deviations; phases A–G with testable acceptance criteria; OpenAI-compatible LLM layer w/ mock backend + 3×-retry lock; pilot (12/topology, k cyclic) + main-study eligible-count orchestration with CLIs; pickle+sidecar+events persistence and `config_hash` spec; DV functions with 144-emission denominator; per-model H1–H3b/H4 analysis scripts (scipy/statsmodels/pygam) under Llama-primary rule; **live analytics = Rich terminal dashboard + notebook hybrid** reading append-only events; testing layers with mock-LLM golden fixtures; extended config schema; repro pins. Flagged bib mismatch (`asheryAINormsZenodo2024` missing from `literature.bib`) as §13 #2. README status table synced |
| 2026-07-13 — Phase A complete (A-01…A-09) | `prompting.py` (`get_rules`/`build_messages`, header tokens stripped, byte-exact golden fixtures vs. Ashery); `llm.py` (`LLMClient` protocol, `LLMResponse`, `parse_label` w/ structured+regex fallback, `RetryPolicy` 3×/2-4-8s, `MockLLMClient` w/ `scripted`/`imitate_modal`/`always`/`random`); `tests/test_prompting.py` + `tests/test_llm.py` (31 tests total, full suite green); `.coveragerc` + `.github/workflows/tests.yml` + `requirements-dev.txt` — coverage 91% (≥85% gate). |
| 2026-07-13 — Phase B complete (B-01…B-10) | `tracker.py::update_dict`; `persistence.py` (`build_run_id`, `RunPaths`, pickle I/O, `.meta.json` w/ all §6 fields, `EventWriter` append-only jsonl); `config.py::config_hash()` (SHA-256[:16], secret fields excluded); `simulation.py::make_interaction_step` (per-agent option shuffle, `RetryPolicy`-wrapped client call, CM short-circuit — zero client calls verified) + `swap_committed` now takes injected `rng` (dropped module-level `random`); `run.py::execute_run` (init → Phase 1 → gate → incumbent (modal @ gate) → swap → Phase 2 horizon 1000 → finalize; checkpoint every 50; resume-from-checkpoint verified to skip completed Phase 1 rather than replay it; `RunFailedError` → `run_status=failed`). **Design deviation from plan wording:** `imitate_modal` mock policy imitates the modal of *partner*-observed answers (not the caller's own history) — self-history-only mode is absorbing after round 1 and never propagates information across a population, so it cannot converge at N=24; partner-modal converges a 24-agent mixing run in ~180 interactions. `tests/test_run_integration.py` — 18 tests (completed/censored/failed/resume/CM-zero-calls/per-topology), full suite 48 tests green, coverage 96% (≥85% gate). |
| 2026-07-13 — Phase C complete (C-01…C-04, C-05 ⏸ deferred) | `config.yaml` extended to §11 schema (`run:`/`models:`/`paths:`; retired `params.initial`/`runs`, `sim.*`, `model.*`); `config.py::resolve_model()` + `ModelSpec` + `ConfigError` (`mock` needs no env vars; `TBD-doug` gpt54/claude55 fail fast pointing at `Doug_Open_Questions.md`); `llm.py::OpenAICompatClient` (openai SDK v2, `max_retries=0`, stubbed-transport unit test, `OPENAI_RETRY_EXCEPTIONS` tuple for `RetryPolicy`); `run_one.py` CLI (`--model/--topology/--k/--seed/--max-interactions/--smoke/--config/--mock-policy`, `load_dotenv()` at entry) — offline smoke verified: `python run_one.py --model mock --topology complete --k 1 --seed 0 --max-interactions 20 --smoke` → 20 parsed labels; full (non-smoke) path verified too via `execute_run`. **Fixed a bug caught during manual smoke testing:** `--smoke` mode with `--k>0` produced a literal `None` label for committed agents (no gate-derived incumbent exists in smoke mode, unlike `execute_run`) — fixed by fixing an arbitrary `committed_to = options[0]` for smoke runs only, documented in `run_one.py`. **Config path fix:** `config.yaml`'s `paths.data` corrected to `data` (not `data/runs`) — `persistence.py::run_paths()` already appends `runs/{model}/{topology}` itself (§6), so the WORKING §11 example value would have doubled the segment. `tests/test_config.py` (4 tests) + `OpenAICompatClient` tests added to `test_llm.py`; full suite 54 tests green, coverage 96% (≥85% gate); secrets grep empty. |
| 2026-07-13 — Phase D complete (D-01…D-05) | `config.py::derive_seeds()` (SHA-256-based, no Python `hash()`); `run_pilot.py` (`pilot_grid()` — 36 rows, k cyclic 1..6,1..6 verified; resume-by-sidecar skips `completed`/`censored`, `failed` only re-attempted with `--retry-failed` which deletes the stale pickle+meta first; `--workers N` via `ThreadPoolExecutor`, each worker builds its own client/config — no shared state). Verified live: `python run_pilot.py --model mock --dry-run` → exactly 36 rows; `python run_pilot.py --model mock` → 36/36 completed in ~2.6s; re-running the same command afterwards resumes in ~0.7s (all skipped). `tests/test_orchestration.py` (9 tests: seed determinism, grid shape/cyclic-k, resume/retry-failed gating, workers=2 parity); full suite 63 tests green, coverage 96% (≥85% gate). |
| 2026-07-14 — Phase G complete (G-01, G-02); **one-shot offline build done** | `run_main.py` (`cell_targets()` — 18 rows = 3 topologies × 6 k, targets pulled from `config.yaml`'s `run.main_eligible_targets`/`attempted_cap_factor`; `run_cell_targeted()` keeps launching seeds per (topology, cm_k) cell until eligible count reaches the target or the attempted cap is hit; reuses `run_pilot.py`'s client/config/retry-policy builders — no third copy of that logic). Verified live: `python run_main.py --model mock --dry-run` → exactly 18 rows with correct [15-20]/[8-10] targets and 45/24 attempted caps; a forced-censoring mocked cell (`--mock-policy random`) stops exactly at the attempted cap with 0 eligible, matching on-disk sidecars. `tests/test_orchestration.py` +3 tests (grid shape/targets, forced-censoring cap, early-stop-on-target). **Ran the full §6 CLI smoke sequence end-to-end** (`run_one.py --smoke`, `run_pilot.py --dry-run`/full batch, `analyze.py --all`, `run_main.py --dry-run`) plus the secrets grep — all pass offline. Full suite: **121 tests green, coverage 92%** (≥85% gate). All 43 non-⏸ todos in `IMPLEMENTATION_PLAN.md` are now ✅; only C-05 (paid real-API smoke) and G-03/G-04 (dependency freeze + repro pins, by definition after real data collection) remain, correctly deferred outside the one-shot build. |
| 2026-07-14 — Phase F complete (F-01…F-07) | `dvs.py` (`label_shares`/`dominant_share`/`shannon_entropy` — 144-emission denominator, single shared helper; `flip`/`flip_50`/`time_to_flip`/`incumbent_label`/`rounds_to_gate` — no `flip_resisted`, lexicographic tie-break documented in the module docstring); `analysis/common.py` (`load_run_table` joins sidecar + pickle-derived DVs, `eligibility_table`, `critical_mass`); `analysis/h1.py`/`h2.py`/`h3a.py`/`h3b.py`/`h4.py`/`cross_model.py` (scipy t/Wilcoxon/Mann-Whitney/chi2, statsmodels Logit + LR tests, pygam `LogisticGAM`, confirmatory/exploratory auto-labeling on the eligibility floor, cross-model kept descriptive/unpooled); `analyze.py` CLI dispatch. Added `numpy`/`scipy<1.17`/`statsmodels`/`pygam==0.12.0` to `requirements.txt` per §7.2 pin. Verified live: `python analyze.py --all --model mock` against a real 36-run mocked pilot batch produced sane H1-H4 JSON + eligibility.csv with exit code 0 (small-n perfect-separation warnings from statsmodels/pygam are expected on 36-row mocked data, not errors). `tests/test_dvs.py` (17 tests) + `tests/test_analysis.py` (23 tests, incl. an `analyze.py` CLI integration test against a mocked batch); full suite 118 tests green, coverage 92% (≥85% gate). |
| 2026-07-14 — Phase E complete (E-01…E-06) | `live/reader.py`, `live/cost.py`, `live/monitor.py`, `live/web.py` (Streamlit), `notebooks/pilot_dashboard.ipynb`; read-only verification + bug fixes (resume CM growth, reader model filter). Full suite 78 tests at E exit; later 150 after R1/R2. |
| 2026-07-14 — Code review R1 remediation (FIX_PLAN.md) | All R1 findings fixed: **B1** H3a primary GAM-vs-linear LR; **B2** real `code_commit` via `orchestration.get_code_commit`; **M1** Phase 2 `shared_shuffle=True`; **M2** single `modal_lexicographic`; **M3** H3b full-grid confirmatory check; **M4** thin CLIs + `orchestration.py`/`analysis/dispatch.py`; **N1–N7** persistence writers, networks guard, glob-path pickle loading, dvs guards, dependency pins, typed exceptions. 146 tests green, 91% coverage. (Detailed R1/R2 review reports + fix plans removed 2026-07-24 in the repo cleanup; this row is the retained summary.) |
| 2026-07-14 — Provider routing (OpenRouter + direct APIs) | `config.yaml` registry: Llama/Qwen → OpenRouter (`meta-llama/llama-3.1-70b-instruct`, `qwen/qwen-2.5-72b-instruct`); GPT/Claude → direct OpenAI/Anthropic; auxiliary `gemini35` → Google OpenAI-compat. `ModelSpec.provider` + `openrouter_provider`; `OpenAICompatClient` sends OR headers + `extra_body.provider`; `config_hash` includes routing pins. 153 tests green, 91% coverage. **C-05 follow-up:** pin `openrouter_provider.only` after paid smoke. See [`PROVIDER_ROUTING_PLAN.md`](PROVIDER_ROUTING_PLAN.md). |
| 2026-07-20 — **C-05 complete** (OpenRouter smoke) | Paid smoke `llama31` + `qwen25` 20/20; pin `only: ["deepinfra"]`; `max_tokens` 200→512 (CoT truncation before `{'value':…}`). Full write-up: [`docs/sessions/2026-07-20_C05_openrouter_smoke.md`](docs/sessions/2026-07-20_C05_openrouter_smoke.md). `gemini35` deferred. Next: commit → real pilot. |
| 2026-07-20 — OpenRouter response cache off | `OpenAICompatClient` sends `X-OpenRouter-Cache: false` on every OR call (overrides presets). Response caching would replay identical completions for identical agent histories → confound Naming Game. Prompt-prefix caching left alone. |
| 2026-07-20 — Doug email (open-source first) | Design ready as-is; Llama pilot → share results → possible iteration → expensive models later. §13 #1/#4/#5 deferred. See [`01_Orga/Doug_Open_Questions.md`](../../../01_Orga/Doug_Open_Questions.md). |
| 2026-07-24 — **Async engine (checklist #2c ✅)** | New default parallelisation path — steps ②–⑥ of §15. `async_llm.py` (`AsyncOpenAICompatClient`, `AsyncRetryPolicy` — exact async twin of `RetryPolicy`; `RateLimiter` global ceiling + `Retry-After` cooldown ⑥; `ProviderPool` round-robin + 429 failover ⑤ scaffold, N=1 today; `AsyncClientAdapter` wraps the sync `MockLLMClient`). `async_simulation.py` (`make_async_interaction_step` — RNG drained in sync order, then both player calls via `asyncio.gather` ④). `async_run.py` (`execute_run_async` — each run stays a sequential coroutine; persistence/gate/resume/checkpoint reused verbatim from `run.py`). `async_orchestration.py` (`run_pilot_async`/`run_main_study_async` — `asyncio.gather` + `Semaphore` over runs ③, shared `ProviderPool`/`RateLimiter`). `run_pilot.py`/`run_main.py` default to `--engine async` with `--run-concurrency`/`--api-concurrency`; sync `--workers` retained as the offline mock/reference engine only. **Determinism lock verified:** `tests/test_async_run_integration.py` asserts byte-identical emergence + CM trajectories vs. the sync engine for the same seed/mock. Tests: +14 (`test_async_llm.py`, `test_async_run_integration.py`); full async subsuite green (retry/backoff order, rate-limiter bound, pool round-robin + failover, sync↔async equivalence, CM zero-API short-circuit). **No legacy async fallback** (per instruction). **Providers later:** multi-key/multi-host fan-out is config-only via `build_provider_pool` (pass N clients to `ProviderPool`; `from_specs` constructor is the planned convenience, not yet built) — no simulation change. Next: **Step ① 429-ceiling measurement** (#2d) to set `--api-concurrency`. |
| 2026-07-24 — **Async review remediation** (reviewer #2/#3) | **#2 live-429 gap fixed:** `ProviderPool.complete` now catches the SDK's real `openai.RateLimitError` (not only the synthetic `RateLimitedError`) → `_retry_after_seconds` reads `Retry-After`, endpoint cooldown + global `RateLimiter.pause()` fire before re-raise, so ⑥ throttles the whole loop on live 429s instead of every worker retrying independently. **#3 run-level test added:** `test_async_batch_matches_sync_batch_and_resumes` asserts `run_batch_async` ↔ sync `run_batch` identical `{run_id: status}` for the mock and that a second pass skips all (resume). +3 async tests (17 total, all green). #1 (Step ① measurement) stays the user's pre-pilot run; #4 (async↔sync duplication) accepted, guarded by the equivalence tests; #5 (start `--run-concurrency 6 --api-concurrency 4`, then scale) folded into the §15 run recipe. Defaults left at 12/8 (documented as optimistic). |
| 2026-07-24 — **Pilot strategy (#3 scope lock)** | 72-run pilot on `mistralnemo` (same protocol; model only differs); excluded from Methods. **After pilot:** optional Llama API pilot (**#1b** cost + decision) **or** Stanford main study (`llama31`). §5 + `TODO.md` updated. |

---

## 15. Async engine (parallelisation)

**Purpose.** Wall-clock is dominated by sequential LLM I/O. This section is the design spec for the async engine that removes that bottleneck. It is the **default** run path (`--engine async` on `run_pilot.py`/`run_main.py`); the synchronous `--workers` (`ThreadPoolExecutor`) path is retained **only** as the offline mock/reference engine. There is no legacy async fallback — one async code path serves all real-provider runs.

**Two-engine split (why both exist).** The sync engine (`llm.py` / `simulation.py` / `run.py` / `orchestration.py`) stays the unit-tested, offline, deterministic reference. The async engine (`async_*.py`) is a strict throughput sibling: every non-I/O decision (seeding, grid construction, gating, resume, checkpointing, metadata, persistence) is **reused verbatim** from the sync modules so the two engines cannot drift. The reproducibility guarantee is a test, not a hope: `tests/test_async_run_integration.py` asserts **byte-identical** emergence and CM trajectories (`tracker.outcome`/`answers`/`players`, `t_gate`, `committed_to`, `incumbent_label`) between engines for the same seed and mock policy.

### Implementation order (the six steps)

| Step | What | Where | Status |
| --- | --- | --- | --- |
| **①** | **Measure baseline + real 429 ceiling** — sweep `--api-concurrency` on live provider; pin production ceiling. | pilot CLI / burst probe | ✅ **done 2026-07-24** — `mistralnemo`/DeepInfra: stable to **192**; hard cap **200** concurrent/model |
| **②** | **Async client** — `AsyncOpenAICompatClient` (`AsyncOpenAI`); `complete` is a coroutine. Wire assembly (OpenRouter referer/title/cache headers, `extra_body.provider`) is byte-identical to the sync client. `AsyncRetryPolicy` is the exact async twin of `RetryPolicy` (same `max_attempts`, 2/4/8 s backoff, one code path for transport/rate-limit/API/parse failures — M03 lock; only `await asyncio.sleep` instead of blocking). SDK auto-retries stay off (`max_retries=0`). | `async_llm.py` | ✅ |
| **③** | **Async run scheduler** — the `ThreadPoolExecutor` batch is replaced by `asyncio.gather` + `asyncio.Semaphore(run_concurrency)`. Each run stays a **sequential coroutine** (`await` per interaction) — the Markov chain is untouched; hundreds of runs simply share one event loop instead of threads. | `async_orchestration.py` | ✅ |
| **④** | **Both player calls concurrent** — in one interaction the two non-committed player completions overlap via `asyncio.gather` instead of a `for player` loop. Committed agents short-circuit to `committed_to` with **zero** client calls (CM zero-API lock). ~2× per interaction when both players call the LLM. | `async_simulation.py` | ✅ |
| **⑤** | **Multi-key / provider pool + failover** — `ProviderPool` is one `AsyncLLMClient` facade over N interchangeable endpoints for the **same model weights**. Each call picks the next endpoint not cooling down; a `RateLimitedError`/429 marks that endpoint on cooldown and re-raises so `AsyncRetryPolicy` retries on a sibling. This is the "anbieter-switching" lever — it is what actually **raises** the Step ① ceiling. | `async_llm.py::ProviderPool` | ✅ **scaffold, N=1 today** |
| **⑥** | **Adaptive rate limiter** — `RateLimiter` is a global `asyncio.Semaphore` (the Step ① ceiling) plus a shared cooldown gate that honours `Retry-After`: one worker hitting a 429 backs **all** workers off together (`pause(seconds)`) instead of hammering a limited endpoint. `max_concurrency<=0` = unbounded (offline mock). **Live-API lock:** `ProviderPool.complete` catches **both** the pool's synthetic `RateLimitedError` **and** the SDK's real `openai.RateLimitError`, extracts `Retry-After` (`_retry_after_seconds`), cools the endpoint down, and calls `RateLimiter.pause()` before re-raising for retry — so a real 429 throttles the whole loop, not just the one call. | `async_llm.py::RateLimiter`/`ProviderPool` | ✅ |

### Concurrency model — two independent knobs

- **`--run-concurrency`** (`asyncio.Semaphore` over runs): how many *runs* share the event loop at once. Coarse bound; also the *only* bound for the offline mock (no rate limiter).
- **`--api-concurrency`** (the `RateLimiter` inside one shared `ProviderPool`): the global ceiling on *in-flight API calls* across **all** runs. **Set this to the Step ① measured limit.** With multiple runs each firing two player calls, `run-concurrency × 2` can exceed the provider ceiling — the `RateLimiter` is what keeps total in-flight calls at or under `api-concurrency` regardless.

### Determinism lock (why gathering is statistically neutral)

Inside `make_async_interaction_step`, **all RNG draws happen synchronously, in the exact sync-engine order, before either LLM call is awaited**: the shared/per-player option shuffles, the `p1 = rng.choice(...)` agent pick and its neighbour pick, and the interaction-history appends. The two completions are independent — each player builds its prompt from its own memory and neither sees the other's current answer before the shared `update_dict`/`update_tracker` — so `asyncio.gather`-ing them cannot change any outcome. With the sync `MockLLMClient` wrapped in `AsyncClientAdapter` (its `complete` runs to completion with no intervening `await`), gathered calls resolve in submission order and the mock's RNG draw order is preserved → byte-identical results, which is exactly what the equivalence test pins.

### Providers later (Step ⑤ extension — config-only)

Today each real model resolves to **one** endpoint (`build_provider_pool` → one `AsyncOpenAICompatClient`). The extension point is `build_provider_pool` (in `async_orchestration.py`): to lift the ceiling later, resolve additional clients for the **same model weights** — more keys on one provider and/or more hosts of the same open-weight model — and pass them all to `ProviderPool([...], rate_limiter=...)`; nothing in the simulation, run, or orchestration layer changes. (A `ProviderPool.from_specs` convenience constructor that builds the endpoint list straight from a config block is the intended next addition — not yet implemented.)

**Guardrail (Methods lock):** every endpoint in a pool must serve the **same model identity**. Never mix Llama/Qwen (or different weight releases) inside one pool — that would break per-run model provenance. Only spread the *same* weight state across endpoints. This is a caller-side contract, not enforced in code.

### Run recipe

```bash
# Step ① result (2026-07-24): DeepInfra mistralnemo — pin --api-concurrency 192

# Pilot — sequential emergence → cm (NOT Methods data)
python3 run_pilot.py --model mistralnemo --program emergence \
  --run-concurrency 64 --api-concurrency 192
python3 run_pilot.py --model mistralnemo --program cm \
  --run-concurrency 64 --api-concurrency 192

# Main study (thesis confirmatory — Stanford HPC, llama31; endpoints TBD)
python3 run_main.py --model llama31 --topology complete

# Offline mock / reference engine (deterministic, no rate limiter):
python3 run_pilot.py --model mock --engine sync --workers 4
```

### Tests

`tests/test_async_llm.py` — `AsyncRetryPolicy` (first-attempt no-sleep, 3-attempt 2/4/8 s backoff order, mid-retry recovery); `RateLimiter` (semaphore bound, zero = unbounded); `ProviderPool` (round-robin across healthy endpoints, 429 → cooldown + re-raise → retry succeeds on sibling); `AsyncOpenAICompatClient` (missing-env-var guard, OpenRouter header/`extra_body` assembly, usage parsing); `AsyncClientAdapter` (wraps sync mock, preserves `model_id`). `tests/test_async_run_integration.py` — full async emergence completes with metadata; **sync↔async byte-identical** emergence and CM trajectories; all-committed Phase 2 makes zero client calls; **async batch ↔ sync `run_batch` identical `{run_id: status}` + resume-skips-all** (run-level scheduler lock). Plus the two ⑥ live-429 tests above. All green (17 async tests; the sync engine's existing suites are unchanged).

### Deferred

- **Step ⑤** real multi-endpoint fan-out — scaffold is live at N=1; adding endpoints is config-only (optional DeepInfra limit increase to 400; not required at 192 cap).
