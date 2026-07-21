# IMPLEMENTATION_PLAN.md — Execution checklist

**Charter / SSOT:** [WORKING.md](WORKING.md) (milestone 0 ✅ 2026-07-13). This file decomposes WORKING §3 phases A–G into session-sized todos; it never overrides a WORKING lock. On any conflict, WORKING wins.

**Created:** 2026-07-13 (rev. 4: Streamlit localhost web dashboard — E-06) · **Language:** English · **Test runner:** `python -m unittest discover -s tests -v` · **Python target:** 3.12 (pygam requires ≥3.10, &lt;3.15)

---

## 0. Zero-blocker build contract

The plan is structured so that **every todo except three (⏸-marked) can be implemented and tested in one uninterrupted pass, fully offline** — no API keys, no Doug model strings, no provider decision required:

- A built-in **`mock` model registry entry** (C-01) resolves to `MockLLMClient`, so `run_one.py`, `run_pilot.py`, and `run_main.py` execute end-to-end without network. All acceptance criteria for C-04, D-02…D-05, E-01…E-06, F-01…F-07, G-01, G-02 run against this mock path (Streamlit E-06: unit-tested frame builders + manual localhost smoke).
- The only deferred items are: **C-05** (paid manual API smoke — needs keys + provider + model strings) and **G-03/G-04** (dependency freeze + repro pins — by definition after real data collection). They are marked ⏸ and sit outside the one-shot build.

**Definition of done for the one-shot build:** all non-⏸ todos checked, full suite green, coverage gate met (see below).

### Coverage gate (applies at every phase exit)

Add `coverage` as a dev dependency (A-09). Each phase's exit criterion additionally requires:

```bash
coverage run -m unittest discover -s tests && coverage report --include="convention_topology/*,live/*" --fail-under=85
```

Target: **≥85% line coverage** over `convention_topology/` + `live/` (CLIs `run_*.py`/`analyze.py` are thin dispatch — covered indirectly via orchestration tests, not gated). Branch-critical logic (gate, parser, retry, flip taxonomy, resume) must have explicit tests for every branch regardless of the percentage.

### Architecture principles (bindings for all phases)

Layered dependency rule — imports only point downward; violations are a review-blocker:

```
CLIs (run_one/run_pilot/run_main/analyze, live/monitor, live/web)   # thin: argparse / streamlit → call reader + render
  └─→ orchestration (run.py, orchestration.py, analysis/dispatch.py, analysis/*)   # composes core + boundaries
        ├─→ boundaries (llm.py, persistence.py)            # ONLY modules doing network / file I/O
        └─→ pure core (prompting, tracker, gate, networks, simulation, dvs, config-hashing)
```

1. **Pure core stays pure.** `prompting.py`, `tracker.py`, `gate.py`, `networks.py`, `simulation.py`, `dvs.py` perform no I/O, read no config files, hold no module-level state. (Deliberate deviation from Ashery, whose modules load `config.yaml` at import time — that pattern is banned here.)
2. **Dependency injection everywhere it hurts testability:** the LLM client, `random.Random` instances, clock (`now()`), and sleep function are constructor/parameter-injected — never `random.*` module globals, never `time.sleep` called directly in logic under test. (`simulation.swap_committed` currently uses module-level `random` — fix in B-07 by threading the injected rng through.)
3. **Single-writer principle:** `persistence.py` is the only module that writes files; `live/` is read-only by construction; each run_id has exactly one owning worker. (2026-07-14, code review N1: `write_analysis_json`/`write_analysis_csv`/`delete_run_artifacts` extend this to `outputs/` writes and run-artifact deletes, previously inlined in `analyze.py`/CLI retry-cleanup paths.)
4. **Boundaries return data, not effects:** `llm.py` returns `LLMResponse`; parsing/retry decisions are separate, unit-testable functions.
5. **Errors are typed:** `ParseError`, `RunFailedError`, config errors — no bare `except` (Ashery's `load_mainframe` anti-pattern is explicitly not ported).
6. **CLIs contain no logic:** argument parsing + one call into orchestration; everything testable without subprocess. (2026-07-14, code review M4: `convention_topology/orchestration.py` now holds `get_code_commit`/`build_run_config`/`build_client`/`retry_policy_for` (closes B2's duplicated-`code_commit` bug) plus `run_pilot`/`run_main_study` (grid, batch dispatch, eligible-count targeting — moved out of `run_pilot.py`/`run_main.py`); `convention_topology/analysis/dispatch.py` holds `run_h1`…`run_h4`/`run_eligibility`/`run_cross_model`/`run_all` (moved out of `analyze.py`). All four CLIs are now argparse + one call; no CLI imports another CLI.)

---

## 1. Header

### Scaffold snapshot (2026-07-13)

| Exists ✅ | Missing ☐ |
| --- | --- |
| `convention_topology/gate.py` (0.95/3N gate, `GateResult`) — **do not rewrite** | `convention_topology/prompting.py`, `llm.py`, `run.py`, `persistence.py`, `dvs.py` |
| `convention_topology/networks.py` (Centola-3 + `adjacency_hash`) — **do not rewrite** | `convention_topology/analysis/` (common, h1–h4, cross_model) |
| `convention_topology/simulation.py` (Phase 1/2 loops + `swap_committed`; interaction step NOT wired) | `run_one.py`, `run_pilot.py`, `run_main.py`, `analyze.py` |
| `convention_topology/tracker.py` (`get_outcome`, `update_tracker`, `modal_label_in_window`; **no `update_dict`** yet) | `live/reader.py`, `live/monitor.py`, `live/web.py`, `live/cost.py`, `notebooks/pilot_dashboard.ipynb` |
| `convention_topology/config.py` (loader only; no `config_hash`, no registry) | `tests/test_prompting.py`, `test_llm.py`, `test_run_integration.py`, `test_dvs.py`, `test_analysis.py`, `test_orchestration.py`, `tests/fixtures/` |
| `config.yaml` (thesis locks applied; **no `run:`/`models:`/`paths:` sections yet** — §11 schema pending) | `.github/workflows/tests.yml` (CI) |
| `tests/test_gate.py` (gate/networks/tracker units, green) | `data/`, `logs/`, `outputs/` dirs + gitignore entries |

### Critical path

```
A (mock LLM + prompting)
└─→ B (full mocked run unit)
    ├─→ C (real API smoke)  ──→ D (pilot batch) ──→ G (main study + freeze)
    ├─→ E (live analytics)  ──────────────↑ (E before real pilot week)
    └─→ F (DVs + analysis)  ──────────────────────→ G
```

E and F only need B (mocked events / mocked runs) — they **parallelize** with C/D. G needs C, D, F.

### Session boundaries (suggested)

| Session | Scope | Parallelizable? |
| --- | --- | --- |
| 1 | Phase A (A-01…A-09) | — |
| 2 | Phase B (B-01…B-10) | — |
| 3 | Phase C (C-01…C-04) — short, fully offline; ⏸ C-05 fires later when keys/strings exist | with session 4/5 after C-01 |
| 4 | Phase D (D-01…D-05) — entirely on `--model mock` | with 5, 6 |
| 5 | Phase E (E-01…E-06) | with 4, 6 |
| 6 | Phase F (F-01…F-07) — largest; may split F-01…F-03 / F-04…F-07 | with 4, 5 |
| 7 | Phase G (G-01, G-02) — mocked; ⏸ G-03/G-04 at analysis freeze, after real data | — |

---

## 2. Master checklist

### Phase A — Mock LLM layer + prompting port

| ✔ | ID | Task | Files | Depends on | Acceptance | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| ✅ | A-01 | Port `get_rules(rewards, options)` from Ashery `prompting.py`, rule text verbatim (+100/−50, 100-round framing), Llama header tokens stripped; returns system-content string | `convention_topology/prompting.py` | — | Golden snapshot matches Ashery content minus `<\|begin_of_text\|>…` tokens | `python -m unittest tests.test_prompting -v` |
| ✅ | A-02 | Port `get_prompt(player, memory_size, rules)` → `build_messages(player, memory_size, rewards, options)` returning `(system, user)`; keep H=5 windowing, local score, history-dict lines, `{'value': …; 'reason': …}` format verbatim; add `PROMPT_TEMPLATE_VERSION` constant | `convention_topology/prompting.py` | A-01 | Empty-history and 5-interaction golden prompts match fixtures byte-for-byte | `python -m unittest tests.test_prompting -v` |
| ✅ | A-03 | Create prompt golden fixtures: empty history + known 5-interaction history (system and user parts) | `tests/fixtures/prompt_empty_history.txt`, `tests/fixtures/prompt_5_interactions.txt` | A-02 | Fixtures exist; test asserts equality against them | `python -m unittest tests.test_prompting -v` |
| ✅ | A-04 | Define `LLMClient` protocol (`complete(system, user) -> LLMResponse`) + `LLMResponse` dataclass (`text`, `usage`, `model_id`) | `convention_topology/llm.py` | — | Importable; MockLLMClient (A-06) satisfies protocol | `python -c "from convention_topology.llm import LLMClient, LLMResponse"` |
| ✅ | A-05 | Implement `parse_label(text, options)`: (1) structured parse of `'value':` field, (2) regex fallback — valid option token at quote/word boundary (mirrors Ashery quote-split); 0 or ≥2 distinct options matched → `ParseError` | `convention_topology/llm.py` | A-04 | Recovers label from ≥5 canned fixtures incl. malformed + ambiguous → ParseError (WORKING §3-A) | `python -m unittest tests.test_llm -v` |
| ✅ | A-06 | Implement `MockLLMClient(policy, rng)` with policies `scripted` (fixture playback), `imitate_modal` (modal of own `my_history` → converges), `always(label)`, `random` (never converges); deterministic under seeded rng | `convention_topology/llm.py`, `tests/fixtures/canned_responses.json` | A-04 | `imitate_modal` population converges in a toy loop; `random` never passes gate; scripted replays fixture order | `python -m unittest tests.test_llm -v` |
| ✅ | A-07 | Implement `RetryPolicy`: exactly 3 attempts, exponential backoff 2/4/8 s (injectable sleep for tests), then raise `RunFailedError`; every attempt reported via callback (events hook, wired in B) | `convention_topology/llm.py` | A-04, A-05 | Test asserts exactly 3 attempts then `RunFailedError`; backoff sequence [2, 4, 8] captured via fake sleep | `python -m unittest tests.test_llm -v` |
| ✅ | A-08 | Write `tests/test_prompting.py` + `tests/test_llm.py` covering A-01…A-07 (golden prompts, ≥5 parser fixtures, retry, mock policies) | `tests/test_prompting.py`, `tests/test_llm.py` | A-01…A-07 | Full suite green | `python -m unittest discover -s tests -v` |
| ✅ | A-09 | Add CI per **§7.9** (`.coveragerc`, `.github/workflows/tests.yml`, `requirements-dev.txt` with `coverage`) | `.coveragerc`, `.github/workflows/tests.yml`, `requirements-dev.txt` | A-08 | Workflow valid; coverage gate passes locally (§0) | `coverage run -m unittest discover -s tests && coverage report --fail-under=85` |

### Phase B — Full run unit (mocked)

| ✔ | ID | Task | Files | Depends on | Acceptance | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| ✅ | B-01 | Add `update_dict(player, my_answer, partner_answer, outcome)` to tracker (verbatim Ashery semantics: score, histories, score_history, outcome) | `convention_topology/tracker.py` | — | Unit test: score accumulates, histories append in order | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-02 | Implement `run_id` builder `{model_shorthand}_{topology}_k{cm_k}_s{run_seed:04d}` + path layout `data/runs/{model}/{topology}/{run_id}.pkl/.meta.json`, `logs/{run_id}.events.jsonl`; gitignore `data/`, `logs/`, `outputs/`, `.env` | `convention_topology/persistence.py`, `.gitignore` | — | `build_run_id("llama31","lattice",3,42) == "llama31_lattice_k3_s0042"`; dirs auto-created | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-03 | Implement pickle I/O (save/load of `{simulation, tracker, convergence}` Ashery-compatible superset, §6) with explicit errors — no bare `except` | `convention_topology/persistence.py` | B-02 | Round-trip test preserves schema keys | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-04 | Implement `.meta.json` writer/reader with **all §6 fields**: run_id, topology, cm_k, model_id, model_shorthand, endpoint_base_url, graph_seed, run_seed, adjacency_hash, t_gate, t_phase1_end, eligibility, incumbent_label, committed_to, phase2_horizon, config_hash, run_status, started_at, finished_at, n_api_calls, n_retries, prompt_template_version, code_commit | `convention_topology/persistence.py` | B-02 | Test asserts every §6 key present and non-null on a completed run | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-05 | Implement `EventWriter` (append-only `.jsonl`, line-buffered): interaction summaries every 10 (`t`, phase, rolling 3N success, dominant share), API errors/retries, phase transitions, token usage | `convention_topology/persistence.py` | B-02 | Mocked run emits ≥1 event per type; file parses line-by-line as JSON | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-06 | Implement `config.py::config_hash()`: SHA-256[:16] of sorted-keys canonical JSON of the fully resolved run config, secret-bearing fields excluded | `convention_topology/config.py` | — | Same config ⇒ same hash; changed param ⇒ different hash; `api_key_env` value irrelevant to hash | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-07 | Wire interaction step in `simulation.py`: factory `make_interaction_step(simulation, client, memory_size, rewards, options, rng, committed_to=None)` — random agent → random neighbour, per-agent option shuffle, prompt → client → `parse_label` → payoff → `update_dict` × 2 + `update_tracker`; record partner ids in `interactions`; thread the injected rng into `swap_committed` (drop module-level `random`, §0 principle 2) | `convention_topology/simulation.py` | A-02, A-06, B-01 | Mocked mixing Phase 1 with `imitate_modal` passes gate; tracker/simulation stay consistent (lengths match) | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-08 | CM short-circuit: committed agents (`committed_tag`) emit `committed_to` directly — **no client call, no retries**; assert zero mock invocations for CM agents in test | `convention_topology/simulation.py` | B-07 | Test: k=24 all-committed Phase 2 makes 0 client calls | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-09 | Implement `run.py::execute_run(config, client, …)`: init network → Phase 1 → gate → incumbent = `modal_label_in_window(3N·2 emissions)` at gate → `swap_committed(k)` → Phase 2 (horizon 1000) → finalize sidecar status; checkpoint every 50 interactions (`run_status=in_progress`); resume from last checkpoint; `RunFailedError` → `run_status=failed`; censored → skip Phase 2 | `convention_topology/run.py` | B-02…B-08 | Mocked mixing run (k=1, seed 0) completes < 10 s; sidecar all-non-null + valid config_hash (WORKING §3-B) | `python -m unittest tests.test_run_integration -v` |
| ✅ | B-10 | Write `tests/test_run_integration.py`: completed path (`imitate_modal`), censored path (`random`, reduced cap), failed path (always-malformed mock → 3 retries → failed sidecar), resume-from-checkpoint, metadata completeness, one run per topology | `tests/test_run_integration.py` | B-01…B-09 | All paths green; suite total runtime < 60 s | `python -m unittest discover -s tests -v` |

### Phase C — Real API smoke

| ✔ | ID | Task | Files | Depends on | Acceptance | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| ✅ | C-01 | Extend `config.yaml` to §11 schema + **§7.4 registry defaults** (`run:`, `models:`, `paths:`); retire `params.initial`, `params.runs`, `sim.mode`, `model.*`; `resolve_model(config, shorthand)` in `config.py`; built-in **`mock`** entry (+ `--mock-policy`) → `MockLLMClient`; `TBD-doug` ids fail fast | `config.yaml`, `convention_topology/config.py` | B-06 | Existing tests green; `resolve_model(cfg,"llama31").model_id` matches §7.4; `resolve_model(cfg,"mock")` needs no env vars | `python -m unittest discover -s tests -v` |
| ✅ | C-02 | Implement `OpenAICompatClient` per **§7.3** (`openai>=2.45`, `max_retries=0`, `chat.completions.create`, system+user messages); capture `usage` → `LLMResponse`; map `APIConnectionError`/`APITimeoutError`/`RateLimitError`/`APIError` for `RetryPolicy` | `convention_topology/llm.py`, `requirements.txt` | A-04, A-07, C-01 | Unit test with stubbed transport: messages assembled as system+user, params correct, usage captured (no network in CI) | `python -m unittest tests.test_llm -v` |
| ✅ | C-03 | Env-var wiring: load `.env` via `python-dotenv`; fail fast with clear message if the selected model's `api_key_env` is unset; confirm `.env` gitignored | `convention_topology/llm.py` or `config.py`, `.gitignore` | C-01, C-02 | Unset var → startup error naming the variable; secrets grep empty | `git grep -iE "sk-\|api[_-]?key.*=" -- ':!*.md' ':!IMPLEMENTATION_PLAN.md'` (empty) |
| ✅ | C-04 | Implement `run_one.py` CLI: `--model --topology --k --seed --max-interactions --smoke --config`; `--smoke` caps interactions, logs each parsed label + model_id + endpoint, skips Phase 2 | `run_one.py` | B-09, C-01…C-03 | Mocked invocation works end-to-end offline: `python run_one.py --model mock --topology complete --k 1 --seed 0 --max-interactions 20 --smoke` | command in Acceptance |
| ✅ | C-05 | **Done 2026-07-20** — OpenRouter smoke `llama31` + `qwen25` 20/20; pin `only: ["deepinfra"]`; `max_tokens` 512. Session log: [`docs/sessions/2026-07-20_C05_openrouter_smoke.md`](docs/sessions/2026-07-20_C05_openrouter_smoke.md). (`gemini35` / GPT/Claude still deferred) | — (run only) | C-04 + external inputs | WORKING §3 Phase C criterion verbatim | `python run_one.py --model llama31 --topology complete --k 1 --seed 0 --max-interactions 20 --smoke` |

### Phase D — Pilot batch runner

| ✔ | ID | Task | Files | Depends on | Acceptance | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| ✅ | D-01 | Implement deterministic seed derivation: `derive_seeds(base_seed, topology, k, seed_index) -> (graph_seed, run_seed)` (stable hash, no Python-hash randomness) | `convention_topology/config.py` or `persistence.py` | — | Same inputs ⇒ same outputs across processes; distinct cells ⇒ distinct seeds | `python -m unittest tests.test_orchestration -v` |
| ✅ | D-02 | Implement `run_pilot.py`: per model, 12 attempted Phase 1 runs/topology, k assigned cyclically (seeds 1–12 → k = 1…6,1…6) = 36 runs/model; `--dry-run` prints exact grid | `run_pilot.py` | B-09, C-04, D-01 | Dry run prints exactly 36 rows (3 topologies × 12 seeds) with correct cyclic k (WORKING §3-D) | `python run_pilot.py --model llama31 --dry-run` |
| ✅ | D-03 | Resume-by-sidecar: skip runs whose sidecar says `completed`/`censored`; resume `in_progress` from checkpoint; re-attempt `failed` **only** with `--retry-failed` | `run_pilot.py`, `convention_topology/persistence.py` | B-04, D-02 | Interrupted mocked batch resumes without re-running finished runs; failed only re-run under flag | `python -m unittest tests.test_orchestration -v` |
| ✅ | D-04 | `--workers N` across-run parallelism (default 1; each worker owns its run_id files; no shared state); document ≤4/provider recommendation | `run_pilot.py` | D-02 | Mocked batch with `--workers 2` produces identical run set to serial (same run_ids, statuses) | `python -m unittest tests.test_orchestration -v` |
| ✅ | D-05 | Write `tests/test_orchestration.py`: grid content + cyclic k, seed determinism, resume filtering, retry-failed gating (all mocked) | `tests/test_orchestration.py` | D-01…D-04 | Suite green | `python -m unittest discover -s tests -v` |

### Phase E — Live analytics

| ✔ | ID | Task | Files | Depends on | Acceptance | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| ✅ | E-01 | Implement `live/cost.py`: aggregate token usage from events `.jsonl` per model; price table constant; $ estimate | `live/cost.py` | B-05 | Unit test with synthetic events: known token totals ⇒ known cost | `python -m unittest tests.test_monitor -v` |
| ✅ | E-02 | Implement shared **`live/reader.py`**: events tailer + sidecar scanner (read-only, tolerant of partial last jsonl line); pure functions → pandas DataFrames for dashboards; **never** opens `data/**/*.pkl` | `live/reader.py` | B-04, B-05 | Grep confirms reader has no `open(..., "w")`/pickle on `data/`; unit tests on fixture logs/meta | `python -m unittest tests.test_monitor -v` |
| ✅ | E-03 | Build Rich terminal dashboard in `live/monitor.py` per **§7.6** — imports `live/reader.py`; `refresh_per_second=0.2` (5 s); all WORKING §9 KPI widgets | `live/monitor.py`, `requirements.txt` (`rich`) | E-01, E-02 | Runs against a live mocked 6-run batch; all five terminal widgets populated | `python live/monitor.py --watch logs/ --refresh 5` |
| ✅ | E-04 | Create `notebooks/pilot_dashboard.ipynb`; batch run per **§7.7** | `notebooks/pilot_dashboard.ipynb`, `requirements-dev.txt` | B-04, B-05, E-02 | Executes cleanly on mocked pilot data | `jupyter nbconvert --to notebook --execute notebooks/pilot_dashboard.ipynb --ExecutePreprocessor.timeout=600` |
| ✅ | E-05 | Read-only verification: record `data/` mtimes, run monitor **and** exercise web reader for 2 min against active mocked batch, assert unchanged | `tests/test_monitor.py` | E-03 | mtimes identical before/after monitor + reader polling session | `python -m unittest tests.test_monitor -v` |
| ✅ | E-06 | **Streamlit localhost dashboard** `live/web.py` per **§7.8**: browser graphs on `localhost:8501`, 5 s auto-refresh, same read path as monitor via `live/reader.py` | `live/web.py`, `requirements-dev.txt` (`streamlit`) | E-01, E-02 | Unit tests: chart-ready DataFrames non-empty on fixture batch; manual: 6 panels render on mocked pilot (see §7.8) | `python -m unittest tests.test_monitor -v` |

### Phase F — DVs + analysis

| ✔ | ID | Task | Files | Depends on | Acceptance | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| ✅ | F-01 | Implement shared `label_shares(tracker, window=72)` (denominator = 2×3N = **144 emissions**) + `dominant_share()` + `shannon_entropy()` routed through it | `convention_topology/dvs.py` | B-01 | Fixture with known 100/144 split; uniform → ln 2; degenerate → 0; denominator asserted 144 | `python -m unittest tests.test_dvs -v` |
| ✅ | F-02 | Implement `flip(tracker, committed_to, t_start)` (∃ trailing-3N Phase 2 window: success ≥ 0.95 **and** modal emission = committed_to; single non-flip category, **no flip_resisted**), `flip_50()` (>50% of noncommitted agents' modal own-emission; boundary at exactly 50% ⇒ 0), `time_to_flip()` (censored at 1000), `incumbent_label()` (modal at gate, lexicographic tie-break — document), `rounds_to_gate()` wrapper | `convention_topology/dvs.py` | F-01 | Fixtures: flip, non-flip, re-convergence-on-incumbent ⇒ 0, 50% boundary ⇒ 0, censoring value 1000, deterministic tie-break | `python -m unittest tests.test_dvs -v` |
| ✅ | F-03 | Write `tests/test_dvs.py` with hand-computed fixtures for every §7 DV | `tests/test_dvs.py` | F-01, F-02 | Suite green incl. 144-denominator case | `python -m unittest tests.test_dvs -v` |
| ✅ | F-04 | Implement `analysis/common.py`: sidecar/pickle run loader → run-level DataFrame, per-model filtering, eligibility table (attempted/eligible/censored/failed by topology×model), `critical_mass(runs_df)` (smallest k with flip rate ≥ 0.5 among eligible, per topology×model; `None` if never) | `convention_topology/analysis/__init__.py`, `analysis/common.py` | F-02 | Synthetic flip-rate table ⇒ known critical mass incl. no-CM `None` case | `python -m unittest tests.test_analysis -v` |
| ✅ | F-05 | Implement `analysis/h1.py` (one-sample t vs τ=0.90 + Wilcoxon + 95% CI + regime proportion) and `analysis/h2.py` (2 one-tailed Welch contrasts α=.05 no correction + Mann–Whitney + entropy descriptives) | `analysis/h1.py`, `analysis/h2.py` | F-04 | Synthetic fixtures with known statistical answers reproduce expected direction/decision | `python -m unittest tests.test_analysis -v` |
| ✅ | F-06 | Implement `analysis/h3a.py` (LogisticGAM `flip ~ s(cm_k)` + LR vs linear Logit + `--sensitivity-50` agreement export), `h3b.py` (`flip ~ cm_k × topology` + LR vs main effects + auto confirmatory/exploratory label per ≥2 topologies × ≥8/cell), `h4.py` (incumbent frequencies + optional χ²), `cross_model.py` (descriptive only, never pooled) | `analysis/h3a.py`, `h3b.py`, `h4.py`, `cross_model.py` | F-04 | Constructed flip tables ⇒ known outputs; h3b label switches on eligibility floor | `python -m unittest tests.test_analysis -v` |
| ✅ | F-07 | Implement `analyze.py` dispatch; write `tests/test_analysis.py`; add stats deps per **§7.2** (`scipy<1.17` + `pygam==0.12.0` + `pandas<3`) | `analyze.py`, `tests/test_analysis.py`, `requirements.txt` | F-05, F-06 | `python analyze.py --all --model mock` on synthetic fixture runs emits H1–H4 outputs without error (WORKING §3-F, offline) | `python -m unittest tests.test_analysis -v && python analyze.py --all --model mock` |

### Phase G — Main-study runner + repro freeze

| ✔ | ID | Task | Files | Depends on | Acceptance | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| ✅ | G-01 | Implement `run_main.py`: per (topology × k) cell keep launching seeds until **eligible** count ≥ target (mixing 15–20; lattice/random 8–10, conditional on pilot) or attempted cap (3× target) reached; same resume/`--retry-failed` semantics as pilot | `run_main.py` | C-04, D-03, F-04 | Mocked cell with forced censoring stops at attempted cap; eligible counting matches sidecars | `python -m unittest tests.test_orchestration -v` |
| ✅ | G-02 | `--dry-run` prints per-cell attempted/eligible targets for the full §5 grid | `run_main.py` | G-01 | Output rows = 3 topologies × 6 k cells with correct targets (WORKING §3-G) | `python run_main.py --model llama31 --dry-run` |
| ⏸ | G-03 | **Deferred to analysis freeze** (after real data collection): pin `requirements.txt` to exact versions (`pip freeze` of the run venv) | `requirements.txt` | F-07 + real data collected | No `>=` ranges remain | `grep -c ">=" requirements.txt` returns 0 |
| ⏸ | G-04 | **Deferred to analysis freeze:** record repro pins — freeze commit + tag `v1.0-analysis-freeze`, Ashery submodule `e57aeef`, update WORKING §12 table + README for Appendix `tab:appendix-repro-pins` | `WORKING.md`, `README.md` | G-01…G-03 | Pins present in both files; tag exists | `git tag -l v1.0-analysis-freeze && git log -1 --format=%h` |

**Todo count: 46 — 43 in the one-shot offline build, 3 deferred (⏸ C-05, G-03, G-04).**

---

## 3. Per-phase detail

### Phase A — Mock LLM + prompting port
- **Goal:** Everything downstream testable without network or API cost.
- **Entry:** current suite green (`test_gate.py`).
- **Exit (gate):** full suite green; parser recovers labels from ≥5 canned fixtures incl. malformed→retry; prompt snapshot matches Ashery content minus header tokens.
- **Order:** A-01 → A-02 → A-03 → A-04 → A-05 → A-06 → A-07 → A-08 → A-09.
- **Watch-outs:** (1) Ashery's prompt embeds Llama-3 header tokens *inside* `new_query` mid-string — the split into system/user must preserve wording exactly (documented deviation: chat roles replace token template). (2) `get_prompt` computes round number from `idx+2` — replicate off-by-design exactly, snapshot guards it. (3) `RetryPolicy` covers timeout, rate limit, HTTP error, **and parse failure** — one code path. (4) Injectable sleep, or tests take 14 s per retry case.

### Phase B — Full run unit (mocked)
- **Goal:** One command produces a complete Phase 1→2 run artifact set (pickle + sidecar + events) from a mock client.
- **Entry:** Phase A exit gate green.
- **Exit (gate):** mocked mixing run (k=1, seed 0) < 10 s with all §6 metadata non-null + valid `config_hash`; censored + failed paths tested.
- **Order:** B-01, B-02 (parallel) → B-03/B-04/B-05/B-06 → B-07 → B-08 → B-09 → B-10.
- **Watch-outs:** (1) CM agents must **never** hit the client — count mock invocations in tests (B-08). (2) Incumbent = modal label in trailing 3N **at gate** (144 emissions), not Ashery's `options[1]` convention. (3) Censored runs skip Phase 2 entirely but still get full sidecars (`eligibility=0`). (4) Checkpoint cadence 50 = Ashery; resume must not double-count interactions. (5) `update_dict` per-player `outcome` list is the payoff history the prompt reads — distinct from tracker `outcome` (0/1 success).

### Phase C — API client + CLI (code offline; real smoke deferred)
- **Goal:** Provider-agnostic OpenAI-compatible client + `run_one.py`, fully built and tested against stubs/mock; the paid smoke (C-05) fires later, unchanged, once keys/strings exist.
- **Entry:** Phase B exit gate green.
- **Exit (gate, offline):** C-01…C-04 green; `run_one.py --model mock … --smoke` works end-to-end; secrets grep empty; coverage gate met. **C-05 is ⏸ and not part of this gate.**
- **Order:** C-01 → C-02 → C-03 → C-04 → C-05.
- **Watch-outs:** (1) GPT-5.4/Claude 5.5 model strings blocked (§13 #1) — registry ships with `TBD-doug` placeholders that fail fast if selected. (2) Open-weight models route via OpenRouter (§13 #3 closed 2026-07-14) — pin `openrouter_provider.only` after C-05 smoke. (3) Never commit `.env`; API keys via env vars only.

### Phase D — Pilot batch runner
- **Goal:** `run_pilot.py --model llama31` executes the 36-run pilot grid unattended with resume.
- **Entry:** Phase B green + C-04 (CLI plumbing); real smoke NOT required — develop and gate entirely on `--model mock`.
- **Exit (gate):** dry-run prints exact 36-run grid; a full mocked pilot batch (`--model mock`) completes; interrupted batch resumes; failed re-attempted only with `--retry-failed`; coverage gate met.
- **Order:** D-01 → D-02 → D-03 → D-04 → D-05.
- **Watch-outs:** (1) k is cyclic over seed index — off-by-one here silently corrupts the pilot design (seeds 1–12 → k = 1,2,3,4,5,6,1,2,3,4,5,6). (2) Seed derivation must not use Python's randomized `hash()`. (3) Failed runs are **not auto-replaced** (M03 lock) — the pilot runner has no eligible-count targeting; that is `run_main.py` only.

### Phase E — Live analytics (terminal + browser + notebook)
- **Goal:** Three-layer monitoring before the real pilot week — Rich terminal (alerts/KPIs), **Streamlit on localhost** (live graphs), notebook (deep batch plots).
- **Entry:** Phase B (events stream + sidecars exist); D useful for realistic multi-run testing.
- **Exit (gate):** Rich monitor on mocked 6-run batch ≤5 s refresh; Streamlit `live/web.py` renders all §7.8 panels on same fixtures; `data/` mtimes unchanged after 2-min monitor+reader session.
- **Order:** E-01 → E-02 → E-03 → E-06 (E-03 and E-06 parallelizable after E-02) → E-04 → E-05.
- **Watch-outs:** (1) **`live/reader.py` is the single data layer** — monitor, web, and notebook must not duplicate tail/parse logic. (2) Read **only** `logs/*.events.jsonl` + sidecars — never pickles of active runs. (3) Tolerate torn/partial last jsonl line. (4) Streamlit is **localhost pilot tooling** (`requirements-dev.txt`) — excluded from CI headless gate; frame builders unit-tested instead. (5) Cost panel best-effort if provider `usage` absent.

### Phase F — DVs + analysis
- **Goal:** All §7 DVs + §8 per-model analysis scripts working on synthetic data before real data arrives.
- **Entry:** Phase B (run artifacts to load); real data not required.
- **Exit (gate):** per-DV unit tests green incl. 144-denominator case; `analyze.py --all --model llama31` on fixtures emits H1–H4 outputs.
- **Order:** F-01 → F-02 → F-03 → F-04 → F-05 → F-06 → F-07 (F-05/F-06 parallelizable after F-04).
- **Watch-outs:** (1) **144-emission denominator** everywhere — one shared `label_shares()`, no per-script re-derivation. (2) **No `flip_resisted`** category (R2 lock) — flip vs single non-flip/censored. (3) Re-convergence on incumbent must score flip=0 (success ≥0.95 alone isn't a flip). (4) `flip_50` counts **noncommitted** agents' own emissions; exactly 50% ⇒ 0. (5) Llama-primary rule: cross_model.py is descriptive only, never pooled inference. (6) **scipy/pygam:** must use `scipy>=1.14,<1.17` + `pygam==0.12.0` — see §7.2; do not `pip install -U scipy` blindly.

### Phase G — Main-study runner (offline) + repro freeze (deferred)
- **Goal:** Eligible-count-targeted main-study batch runner, built and tested mocked; pins frozen later at analysis freeze.
- **Entry:** C-04, D, F done; pilot results later inform lattice/random cell demotions (config values, no code change).
- **Exit (gate, offline):** G-01/G-02 green — dry run prints per-cell targets, mocked targeting behaves per M01 locks; coverage gate met. **G-03/G-04 are ⏸ post-data.**
- **Order:** G-01 → G-02 → (after real data) G-03 → G-04.
- **Watch-outs:** (1) Targeting counts **eligible** (gate-passed) runs, not attempted; attempted cap = 3× target guards runaway censoring cells. (2) Freeze (G-03/G-04) happens at analysis freeze, after data collection — do not pin prematurely.

---

## 4. File creation order

| # | File | Mode | Phase |
| --- | --- | --- | --- |
| 1 | `convention_topology/prompting.py` | implement fully | A |
| 2 | `convention_topology/llm.py` | implement (mock half; `OpenAICompatClient` stub raising `NotImplementedError` for import-graph sanity) | A (C completes) |
| 3 | `tests/fixtures/` (canned responses, prompt goldens) | implement fully | A |
| 4 | `tests/test_prompting.py`, `tests/test_llm.py` | implement fully | A |
| 5 | `.github/workflows/tests.yml` | implement fully | A |
| 6 | `convention_topology/persistence.py` | implement fully | B |
| 7 | `convention_topology/run.py` | implement fully | B |
| 8 | `tests/test_run_integration.py` | implement fully | B |
| 9 | `run_one.py` | implement fully | C |
| 10 | `run_pilot.py` | implement fully | D |
| 11 | `tests/test_orchestration.py` | implement fully | D |
| 12 | `live/cost.py`, `live/reader.py`, `live/monitor.py` | implement fully | E |
| 13 | `live/web.py` | implement fully | E |
| 14 | `tests/test_monitor.py` | implement fully | E |
| 15 | `notebooks/pilot_dashboard.ipynb` | implement fully | E |
| 16 | `convention_topology/dvs.py` | implement fully | F |
| 17 | `tests/test_dvs.py` | implement fully | F |
| 18 | `convention_topology/analysis/__init__.py` + `common.py` | implement fully | F |
| 19 | `analysis/h1.py`, `h2.py`, `h3a.py`, `h3b.py`, `h4.py`, `cross_model.py` | stub early → implement | F |
| 20 | `analyze.py` | implement fully | F |
| 21 | `tests/test_analysis.py` | implement fully | F |
| 22 | `run_main.py` | implement fully | G |

Existing files **modified** (never recreated): `simulation.py` (B-07/B-08), `tracker.py` (B-01), `config.py` (B-06, C-01, D-01), `config.yaml` (C-01), `requirements.txt` (C-02, F-07, G-03), `.gitignore` (B-02, C-03), `README.md`/`WORKING.md` (G-04). `gate.py` and `networks.py` untouched.

---

## 5. Test matrix

| Level | Module under test | Test file | Fixture / mock policy | Phase |
| --- | --- | --- | --- | --- |
| Unit | gate, networks, tracker | `test_gate.py` ✅ | hand-built trackers | done |
| Unit | prompting port (goldens) | `test_prompting.py` | `prompt_empty_history.txt`, `prompt_5_interactions.txt` | A |
| Unit | `parse_label` | `test_llm.py` | ≥5 canned responses: well-formed, malformed, ambiguous | A |
| Unit | `RetryPolicy` | `test_llm.py` | failing mock + fake sleep (asserts 3 attempts, 2/4/8 s) | A |
| Unit | Mock policies | `test_llm.py` | `scripted`, `imitate_modal`, `always`, `random` | A |
| Unit | `config_hash`, run_id, sidecar schema, EventWriter | `test_run_integration.py` | synthetic configs / runs | B |
| Integration | full run per topology, resume, CM zero-API | `test_run_integration.py` | `imitate_modal` (completed), `random` (censored), always-malformed (failed) | B |
| Unit | `OpenAICompatClient` assembly (no network) | `test_llm.py` | stubbed transport | C |
| Integration | pilot grid, seeds, resume, workers | `test_orchestration.py` | mocked batches | D |
| Unit/Integration | `live/reader.py` tailer, frames, cost, read-only guarantee | `test_monitor.py` | synthetic events; live mocked batch | E |
| Manual smoke | Streamlit web panels on localhost | — (excluded from CI) | mocked batch + `streamlit run live/web.py` | E |
| Unit | every §7 DV (144 denominator, flip taxonomy, 50% boundary, tie-break, censoring) | `test_dvs.py` | hand-computed trackers | F |
| Integration | analysis pipeline, critical mass, h3b labeling | `test_analysis.py` | synthetic run sets with known statistical answers | F |
| Integration | main-study targeting / attempted cap | `test_orchestration.py` | mocked censoring cells | G |
| Smoke (manual, $) | one real call per model; 20-interaction run | — (excluded from CI) | real API | C |
| Integration | `convention_topology/orchestration.py` (`get_code_commit`, `build_run_config`, `run_pilot`, `run_main_study` — moved from `run_pilot.py`/`run_main.py`, code review M4) | `test_orchestration.py` | mocked batches; sidecar `code_commit` vs. real git HEAD | B2/M4 (2026-07-14) |
| Integration | `convention_topology/analysis/dispatch.py` (`run_h1`…`run_h4`, `run_eligibility`, `run_cross_model`, `run_all` — moved from `analyze.py`, code review M4) | `test_analysis.py` | mocked pilot batch → `analyze.main(["--all", ...])` | M4 (2026-07-14) |

---

## 6. CLI smoke sequence (cumulative — run after each phase)

```bash
# After EVERY phase (baseline + coverage gate)
python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests && coverage report --include="convention_topology/*,live/*" --fail-under=85

# After B  (+ mocked end-to-end artifact check)
python -m unittest tests.test_run_integration -v

# After C  (offline CLI smoke — no API key needed)
python run_one.py --model mock --topology complete --k 1 --seed 0 --max-interactions 20 --smoke
git grep -iE "sk-|api[_-]?key.*=" -- ':!*.md' ':!IMPLEMENTATION_PLAN.md'   # must be empty
# ⏸ later, once keys/strings exist (C-05):
# python run_one.py --model llama31 --topology complete --k 1 --seed 0 --max-interactions 20 --smoke

# After D  (+ grid preview + full mocked pilot batch)
python run_pilot.py --model mock --dry-run             # exactly 36 rows, cyclic k
python run_pilot.py --model mock                       # completes offline

# After E  (+ terminal monitor + Streamlit web + notebook)
python live/monitor.py --watch logs/ --refresh 5
streamlit run live/web.py --server.headless true --server.port 8501   # manual: open localhost:8501
jupyter nbconvert --to notebook --execute notebooks/pilot_dashboard.ipynb --ExecutePreprocessor.timeout=600

# After F  (+ analysis on synthetic fixtures)
python analyze.py --all --model mock

# After G  (+ main-study preview; pins ⏸ at analysis freeze)
python run_main.py --model mock --dry-run
# ⏸ at freeze (G-03): grep -c ">=" requirements.txt   # must be 0
```

WORKING §5 pilot dry-run (`run_pilot.py --model llama31 --dry-run`) and §3 Phase C smoke are both embedded above.

---

## 7. External dependencies & implementation patterns

**Researched:** 2026-07-13 (PyPI + upstream docs). Implement todos **must** follow these patterns; exact pins land in `requirements.txt` at **F-07** (ranges during build) and **G-03** (freeze after data).

### 7.1 Install layout

Split dependencies so CI and offline dev stay lean:

| File | When added | Contents |
| --- | --- | --- |
| `requirements.txt` | A-09 (coverage only) → C-02 (openai) → F-07 (stats stack) | **Runtime** — everything needed to run experiments + analysis |
| `requirements-dev.txt` | A-09 | **Dev/CI only** — `coverage`, `ipykernel` (notebook kernel); optional `jupyter` if notebook not executed in CI |

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt
```

**Do not** use Ashery's legacy `openai.ChatCompletion.create` or `openai.error.OpenAIError` — collaborator notebooks are pre–SDK-v1.

### 7.2 Version matrix (recommended ranges — July 2026 PyPI)

| Package | Pin (build phase) | Latest checked | Used in | Notes |
| --- | --- | --- | --- | --- |
| `networkx` | `>=3.6,<4` | 3.6.1 | `networks.py` ✅ | Already in repo |
| `PyYAML` | `>=6.0.3,<7` | 6.0.3 | `config.py` ✅ | Use `yaml.safe_load` only |
| `munch` | `>=4.0,<5` | 4.0.0 | `config.py` ✅ | |
| `openai` | `>=2.45,<3` | **2.45.0** | C-02 `OpenAICompatClient` | SDK v2+; Chat Completions API (not Responses API) |
| `python-dotenv` | `>=1.2,<2` | 1.2.2 | C-03 | Load `.env` once at CLI entry |
| `rich` | `>=15.0,<16` | 15.0.0 | E-03 monitor | `Live` + `Layout` + `Table` |
| `streamlit` | `>=1.42,<2` | 1.59.2 | E-06 web | **`requirements-dev.txt` only** — localhost pilot UI |
| `numpy` | `>=2.0,<3` | 2.5.1 | F stats | pygam + statsmodels both support NumPy 2.x |
| `pandas` | `>=2.2,<3` | 3.0.3 exists | F analysis | **Stay on 2.x** until G-03 freeze validates statsmodels/pygam on pandas 3 |
| `scipy` | `>=1.14,<1.17` | 1.18.0 exists | F H1/H2/H4 | **Hard cap:** `pygam==0.12.0` requires `scipy<1.17` ([issue #584](https://github.com/dswah/pyGAM/issues/584) open for ≥1.17) |
| `statsmodels` | `>=0.14.6,<0.15` | 0.14.6 | F H3b | `Logit` + `compare_lr_test` |
| `pygam` | `==0.12.0` | 0.12.0 | F H3a | Pin exact; do not float |
| `matplotlib` | `>=3.9,<4` | 3.11.0 | F figures | `matplotlib.use("Agg")` before pyplot in headless/CI |
| `coverage` | `>=7.15,<8` | 7.15.1 | A-09 CI | See §7.8 |
| `jupyter` + `nbconvert` | `jupyter>=1.1`, `nbconvert>=7.17` | 1.1.1 / 7.17.1 | E-04 | Dev dep acceptable if notebook is manual-only |

**Conflict resolver:** if `pip install` fails on scipy, install `scipy>=1.14,<1.17` **before** `pygam`. Never bump scipy to 1.17+ without a new pygam release.

### 7.3 `OpenAICompatClient` (`openai` SDK v2) — C-02

Single client for OpenRouter and direct provider OpenAI-compat layers (OpenAI, Anthropic, Google). **Disable SDK auto-retries** — thesis `RetryPolicy` owns all 3× attempts (M03 lock); stacking SDK retries (default 2) breaks backoff semantics.

```python
import os
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError

class OpenAICompatClient:
    def __init__(self, base_url: str, model_id: str, api_key_env: str,
                 temperature: float = 0.5, max_tokens: int = 200, timeout: float = 120.0):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing env var {api_key_env} for model {model_id}")
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/") + "/",  # SDK normalizes; trailing slash OK
            max_retries=0,                          # ← application RetryPolicy only
            timeout=timeout,
        )
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url

    def complete(self, system: str, user: str) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            usage={"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens}
                 if usage else {},
            model_id=self.model_id,
        )
```

**RetryPolicy catch tuple:** `APIConnectionError`, `APITimeoutError`, `RateLimitError`, `APIError`, plus local `ParseError`. Map HTTP 4xx/5xx via `APIError` / `RateLimitError` (429).

**Unit tests:** mock `client.chat.completions.create` (or inject a fake `OpenAI` instance) — **never** hit network in CI.

### 7.4 Model registry defaults (`config.yaml` §11) — C-01

Provider strings below are **July 2026 docs**; Doug may override GPT/Claude ids (§13 #1). Open-weight models route via **OpenRouter** (decision 2026-07-14).

| Shorthand | `provider` | `model_id` | `base_url` | `api_key_env` |
| --- | --- | --- | --- | --- |
| `llama31` | `openrouter` | `meta-llama/llama-3.1-70b-instruct` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| `qwen25` | `openrouter` | `qwen/qwen-2.5-72b-instruct` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| `gpt54` | `openai` | `TBD-doug` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `claude55` | `anthropic` | `TBD-doug` | `https://api.anthropic.com/v1/` | `ANTHROPIC_API_KEY` |
| `gemini35` | `google` | `gemini-3.5-flash` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` |
| `mock` | `mock` | `mock` | `""` | `""` | → resolves to `MockLLMClient` (§0) |

**OpenRouter:** OpenAI SDK with `base_url=https://openrouter.ai/api/v1` ([docs](https://openrouter.ai/docs/quickstart)). Optional `openrouter_provider` in YAML → `extra_body.provider` (pin `only` after C-05 smoke).

**Anthropic compat:** `max_tokens` required; OpenAI-compat layer at `api.anthropic.com/v1/` ([docs](https://platform.claude.com/docs/en/api/openai-sdk)).

**Google compat:** Gemini via `generativelanguage.googleapis.com/v1beta/openai/` ([docs](https://ai.google.dev/gemini-api/docs/openai)). `gemini35` is auxiliary — not in the four-model factorial.

**Fail-fast:** if `model_id` starts with `TBD`, raise at registry resolution with pointer to `01_Orga/Doug_Open_Questions.md`.

### 7.5 Environment variables — C-03

```python
# At run_one.py / run_pilot.py / run_main.py entry (once per process):
from dotenv import load_dotenv
load_dotenv()  # reads .env if present; does not override existing env
```

`.env` example (never commit):

```bash
OPENROUTER_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...   # auxiliary gemini35 only
```

### 7.6 Rich live monitor — E-03

Plan says `--refresh 5` (seconds); Rich API uses **refreshes per second**:

```python
from rich.live import Live
from rich.layout import Layout
from rich.table import Table

# refresh_per_second=0.2 → one refresh every 5 s
with Live(build_layout(), refresh_per_second=0.2, screen=False) as live:
    while True:
        live.update(build_layout())  # or live.refresh() if auto_refresh=False
        time.sleep(5)  # only needed when auto_refresh=False
```

Prefer `Layout.split` / `split_row` for the five §9 panels ([Rich Live docs](https://rich.readthedocs.io/en/stable/live.html)). **Read-only:** no `open(..., "w")` on `data/`; tail `logs/*.events.jsonl` with seek-from-end; tolerate partial last JSON line.

### 7.7 Notebook batch refresh — E-04

`jupyter execute` exists but **nbconvert is the stable automation path** ([nbconvert execute](https://nbconvert.readthedocs.io/en/stable/execute_api.html)):

```bash
jupyter nbconvert --to notebook --execute notebooks/pilot_dashboard.ipynb \
  --ExecutePreprocessor.timeout=600 --output-dir /tmp
```

For in-place refresh during dev: add `--inplace`. Pin `ipykernel` in `requirements-dev.txt` so the venv kernel matches CI.

### 7.8 Streamlit web dashboard (`localhost`) — E-06

**Decision (rev. 4):** add a **browser dashboard** alongside Rich terminal + notebook. Streamlit runs locally only (`localhost:8501`) — no deploy, no remote exposure. Shares **`live/reader.py`** with `monitor.py` (no duplicate jsonl parsing).

**Dependency:** `streamlit>=1.42,<2` in `requirements-dev.txt` (latest checked: **1.59.2**). Not required for CI unit tests.

**Launch (3rd terminal during pilot/main):**

```bash
streamlit run live/web.py --server.headless true --server.port 8501
# → http://localhost:8501
```

**Refresh pattern** (default 5 s, sidebar slider 2–30 s):

```python
import streamlit as st
from live.reader import load_dashboard_state  # returns dataclass / dict of DataFrames

st.set_page_config(page_title="Naming Game Pilot", layout="wide")
refresh_s = st.sidebar.slider("Refresh (s)", 2, 30, 5)
st.sidebar.caption("Read-only · logs/*.jsonl + sidecars")

@st.fragment(run_every=f"{refresh_s}s")  # Streamlit ≥1.33; else st_autorefresh package
def panels():
    state = load_dashboard_state(logs_dir, data_dir, model_filter=None)
    # render six panels below from state.*_df

panels()
```

If `st.fragment(run_every=…)` unavailable at pinned version, fallback: `from streamlit_autorefresh import st_autorefresh` (add to dev deps) or manual `st.button("Refresh")` + document in README.

**Required panels (map to WORKING §9 + pilot triage):**

| # | Panel | Streamlit widget | Data source |
| --- | --- | --- | --- |
| 1 | **Run status KPIs** | `st.metric` columns | sidecars: counts by topology × `run_status` |
| 2 | **Eligibility rate** | `st.line_chart` | cumulative eligible/attempted per topology over wall time |
| 3 | **Coordination trajectories** | `st.line_chart` (multi-run) | events: rolling 3N success vs `t` for active + recent runs |
| 4 | **Dominant share** | `st.bar_chart` or Altair violin | latest snapshot per topology (mixing vs sparse contrast) |
| 5 | **API health** | `st.bar_chart` + `st.expander` last error | events: retry/error counts by class |
| 6 | **Cost** | `st.line_chart` cumulative | `live/cost.py` aggregation on token events |

**Sidebar filters:** model shorthand (optional), topology multiselect, show only `in_progress` runs.

**Read-only contract (same as monitor):** `live/web.py` imports only `live/reader.py` + `live/cost.py` — no writes to `data/`, `logs/`, or `outputs/`. Unit-test `load_dashboard_state()` and frame builders in `tests/test_monitor.py` on fixture directories.

**Manual acceptance (E-06):** with mocked 6-run batch running, open `localhost:8501` — all six panels populated, refresh updates line charts without restart.

### 7.9 Coverage + CI — A-09

Add `.coveragerc` (or `[tool.coverage.run]` in `pyproject.toml` if introduced):

```ini
[run]
source = convention_topology, live
omit = */tests/*

[report]
fail_under = 85
show_missing = true
```

GitHub Actions (`.github/workflows/tests.yml`):

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -U pip && pip install -r requirements.txt -r requirements-dev.txt
      - run: coverage run -m unittest discover -s tests -v
      - run: coverage report --fail-under=85
```

### 7.10 Analysis stack — F-05…F-07

**H1** (`scipy.stats`):

```python
from scipy import stats
t_stat, p_two = stats.ttest_1samp(dominant_shares, popmean=0.90)
# one-sided H1: dominant > 0.90 → p_one = p_two/2 if t_stat > 0 else 1 - p_two/2
w_stat, p_w = stats.wilcoxon(dominant_shares - 0.90, alternative="greater")
ci_low, ci_high = stats.ttest_1samp(dominant_shares, popmean=0.90).confidence_interval(0.95)  # scipy ≥1.9
```

**H2:** `stats.ttest_ind(a, b, equal_var=False)` (Welch); robustness `stats.mannwhitneyu(a, b, alternative="less")` for lattice/random &lt; mixing.

**H3a** (`pygam` — single spline on `cm_k`):

```python
import numpy as np
from pygam import LogisticGAM, s

X = np.asarray(cm_k, dtype=float).reshape(-1, 1)
y = np.asarray(flip, dtype=int)
gam = LogisticGAM(s(0, n_splines=6, spline_order=3)).fit(X, y)
# LR vs linear: fit statsmodels Logit(y, sm.add_constant(X)) on same data;
# compare via gam.statistics_['pseudo_r2'] or manual deviance difference — prefer
# statsmodels LogitResults.compare_lr_test between nested linear models for the
# locked LR test, and use GAM for the smooth term plot + AIC comparison table.
```

**Practical H3a lock (corrected 2026-07-14, code review B1):** primary inferential contrast = **logistic GAM `flip ~ s(cm_k)` vs. linear logistic `flip ~ cm_k`** via a likelihood-ratio test on log-likelihoods (`lr_stat_gam_vs_linear`, `lr_p_gam_vs_linear`, `df = edof_gam - 2`) — matches `03_Methods.tex:228-229` and `WORKING.md:385` ("LR test vs linear logistic"). GAM also supplies the flip-curve figure data (`flip_curve`, predicted probability over `cm_k ∈ {1..6}`). Linear-vs-intercept-only is retained **only as a secondary/descriptive** contrast (`lr_stat_linear_vs_intercept`, `lr_p_linear_vs_intercept`) — it must never be reported as the primary H3a test. If the GAM fit fails on tiny *n*, emit `exploratory` label + `reason` in output JSON.

**H3b:**

```python
import statsmodels.api as sm
# Design: cm_k (centered), C(topology), cm_k:C(topology)
full = sm.Logit(y, X_full).fit(disp=0, method="lbfgs", maxiter=200)
main = sm.Logit(y, X_main).fit(disp=0, method="lbfgs", maxiter=200)
lr_stat, p_lr, df = full.compare_lr_test(main)  # nested: main effects ⊂ interaction model
```

**H4:** `stats.chisquare(observed_counts)` vs uniform; descriptive tables in pandas.

**Figures:** `matplotlib.pyplot.savefig` to `outputs/{model}/`; close figures after save to avoid leaks in batch runs.

### 7.11 Phase → dependency touch map

| Phase | Add to `requirements.txt` | New config / dotfiles |
| --- | --- | --- |
| A-09 | `coverage` → move to `requirements-dev.txt` | `.coveragerc`, `.github/workflows/tests.yml` |
| C-02/C-03 | `openai`, `python-dotenv` | `.env.example` (optional, no secrets) |
| E-03 | `rich` | — |
| E-06 | `streamlit` | — (`requirements-dev.txt`) |
| E-04 | — (jupyter in dev) | `requirements-dev.txt`: `jupyter`, `nbconvert`, `ipykernel` |
| F-07 | `numpy`, `pandas`, `scipy`, `statsmodels`, `pygam`, `matplotlib` | enforce scipy&lt;1.17 per §7.2 |
| G-03 | exact pins via `pip freeze` | — |

---

## 8. Blockers & decisions (from WORKING §13)

**Net effect after rev. 2: no WORKING §13 item blocks any todo in the one-shot build.** All four blockers gate only the ⏸ items (C-05 paid smoke, real data batches, G-03/G-04 freeze). Detail:

| # | Blocker | Blocks (todo IDs) | Unblocked work |
| --- | --- | --- | --- |
| 1 | GPT-5.4 / Claude 5.5 pinned model strings + provider access (Doug) | C-05 for `gpt54`/`claude55` only; their pilot batches (D) and G data collection for those strata | **Everything else.** Registry entries ship as `TBD-doug` placeholders (C-01) that fail fast if selected. Llama/Qwen path fully unblocked; the entire mock path (A, B, D–F on mocked data) is unaffected |
| 2 | `asheryAINormsZenodo2024` missing from `literature.bib` (thesis-writing repo) | **no code todos** — Appendix citations only | All of A–G. Fix lives in the thesis-writing repo, out of scope here |
| 3 | OpenRouter for Llama/Qwen (implemented 2026-07-14) | C-05 (real smoke + `only` pin) | Registry + `OpenAICompatClient` OR support done; smoke pending keys |
| 4 | API budget + rate limits | D-04 `--workers` tuning, G wall-clock planning — **not code structure** | All implementation todos; estimate from pilot cost panel (E-01) |

No TBD in this plan lacks an owner: #1 Doug/Jannik, #2 Jannik (thesis-writing), #3 Jannik, #4 Jannik (post-pilot).

---

## 9. Sign-off mapping (WORKING § Status milestones 1–6)

| Milestone | WORKING wording | Completes when | Adjustment vs. seed mapping |
| --- | --- | --- | --- |
| 1 | LLM runner + one dry-run (mixing, k=1, Llama) | Code portion: **A + B + C-01…C-04** (offline, `--model mock` dry-run); milestone signs off fully at ⏸ **C-05** (real llama31 smoke) | Seed said "A + C", but WORKING §3 makes C depend on B (`run_one.py` needs `run.py`/`persistence.py`); real-smoke half deferred behind §13 #1/#3 |
| 2 | Full run unit (Phase 1→2, logging, flip coding) | **B** complete + **F-01…F-03** (flip coding is `dvs.py`, Phase F) | "Flip coding" is not in Phase B's file set; pulling F-01…F-03 forward here keeps the milestone honest without reordering phases |
| 3 | Pilot orchestration (12 attempted / topology / model) | **D** complete | as seeded |
| 4 | Live analytics usable during pilot | **E** complete (Rich + **Streamlit** + notebook) | as seeded |
| 5 | Analysis scripts H1–H3b + H4 | **F** complete (F-04…F-07 remaining after milestone 2) | as seeded |
| 6 | Main-study batch runner + commit pin | **G** complete | as seeded |

---

*Maintained alongside [WORKING.md](WORKING.md). Check off IDs as phases land; update the WORKING § Status sign-off table at each milestone. Dependency pins: §7 (rev. 4); re-check PyPI before G-03 freeze.*
