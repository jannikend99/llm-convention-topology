# Agent prompt — Implementation plan for thesis experiment code

## Task

Create a **detailed, executable implementation plan** for building all remaining code in `llm-convention-topology/`. This is a **planning pass only** — do **not** write production code in the same run unless the user explicitly asks afterward.

**Input SSOT:** [`WORKING.md`](../WORKING.md) (milestone 0 ✅ — fully specified 2026-07-13). Treat it as law; do not re-litigate design locks.

**Output:** new file [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) in this repo root — the day-to-day checklist for coding sessions.

---

## Context you already have

- Thesis: LLM Naming Game, Centola-3 topologies, CM perturbation, organizational-resilience DVs (H1–H3b + H4).
- Extend Ashery (`../ashery-ai-norms/` @ `e57aeef`) — **read-only**; port/adapt per WORKING §2.
- Scaffold done: `gate.py`, `networks.py`, `simulation.py` (partial), `tracker.py` (partial), `config.py`, `config.yaml`, `tests/test_gate.py`.
- Everything else is ☐ per WORKING §1 status table and phases A–G (§3).

**Workspace roots:** meta-repo `Master Thesis/` · this repo `02_Topic/Experiment_Code/llm-convention-topology/` · Methods `Thesis_Writing/development/03_Methods/` · Ashery `ashery-ai-norms/`.

---

## Mandatory read (before planning)

1. [`WORKING.md`](../WORKING.md) — full file, especially §1–§10, §13
2. Existing code: `convention_topology/*`, `tests/*`, `config.yaml`
3. Ashery sources referenced in WORKING §2 porting map (at minimum `prompting.py`, `simulation_module.py`, `utils.py`, `run_API.py`, `runner.py`)
4. On ambiguity only: `Thesis_Writing/development/03_Methods/M03_procedure/WORKING.md`, `M04_outcomes_analysis/WORKING.md`

Do **not** re-audit Methods from scratch. Operationalize what WORKING already locks.

---

## What `IMPLEMENTATION_PLAN.md` must contain

### 1. Header

- Link to WORKING.md as charter
- Current scaffold snapshot (what exists vs missing)
- Critical path: phases A→G in dependency order
- Estimated session boundaries (suggest 1 phase ≈ 1 focused agent run; flag phases that can parallelize)

### 2. Master checklist

One markdown checkbox per **concrete deliverable** (file or test file), grouped under WORKING phases A–G. Every item must have:

| Column | Requirement |
| --- | --- |
| **ID** | `A-01`, `B-03`, … (phase letter + sequence) |
| **Task** | Imperative, one action (“Implement `parse_label()` in `llm.py`”) |
| **Files** | Exact paths created or modified |
| **Depends on** | IDs of blocking tasks (empty if none) |
| **Acceptance** | Copy testable criterion from WORKING §3 (or §7/§10 for DVs/tests) — must be verifiable via shell command |
| **Verify** | Single copy-paste command (e.g. `python -m unittest tests.test_llm -v`) |

**Granularity rule:** at least **3–8 todos per phase**; no vague items like “implement simulation”. Decompose into: wire interaction step, checkpoint hook, CM short-circuit, sidecar field X, etc.

### 3. Per-phase detail blocks (A–G)

For each phase, append a short subsection with:

- **Goal** (one sentence)
- **Entry criteria** (what must be green before starting)
- **Exit criteria** (phase gate — from WORKING §3 acceptance)
- **Ordered todo list** (the IDs above, in execution order)
- **Risks / watch-outs** (e.g. 144-emission denominator, no `flip_resisted`, CM agents skip API)

### 4. File creation order

Single ordered list of **all new files** to create (from WORKING §1 target tree), with “create empty stub” vs “implement fully” noted. Flag files that can be stubbed early for import graph sanity.

### 5. Test matrix

Table mapping: **unit / integration / smoke** × **module** × **fixture/policy** (e.g. `MockLLMClient.imitate_modal`, `random` for censoring). Align with WORKING §10.

### 6. CLI smoke sequence

End-to-end command sequence a developer runs after each phase completes (cumulative — later phases include earlier checks). Start from:

```bash
python -m unittest discover -s tests -v
```

Build up to WORKING §5 pilot dry-run and §3 Phase C smoke.

### 7. Blockers & decisions

Pull from WORKING §13; for each blocker, state **which todo IDs are blocked** vs **which work can proceed without it** (e.g. GPT/Claude strings block Phase C smoke for those models only — Llama mock path unblocked).

### 8. Sign-off mapping

Map WORKING milestones 1–6 (§ Status table) to phase completion:

| Milestone | Completes when |
| --- | --- |
| 1 | Phase A + C (LLM runner dry-run) |
| 2 | Phase B |
| 3 | Phase D |
| 4 | Phase E |
| 5 | Phase F |
| 6 | Phase G |

Adjust if your decomposition suggests a tighter mapping — but explain any change.

---

## Phase-specific decomposition hints (use as seed, expand fully)

### Phase A — Mock LLM + prompting

- Port `get_rules` / `get_prompt` → `prompting.py` (chat `system`/`user`; strip Ashery header tokens)
- `LLMClient` protocol, `MockLLMClient` policies: `scripted`, `imitate_modal`, `always`, `random`
- `parse_label()` with structured + regex fallback; ambiguous → failure
- `RetryPolicy`: exactly 3 attempts, exponential 2/4/8 s, `RunFailedError`
- `tests/fixtures/`: canned responses, prompt golden snapshot, malformed/ambiguous cases
- `tests/test_prompting.py`, `tests/test_llm.py`

### Phase B — Full run unit (mocked)

- `persistence.py`: run_id layout, pickle I/O, `.meta.json` (all §6 fields), `EventWriter` jsonl
- `config.py`: `config_hash()` (secrets excluded)
- `run.py`: init → Phase 1 → gate → swap CM → Phase 2 → finalize status
- Wire `simulation.py` interaction step (random agent/neighbour, shuffle, prompt→mock→payoff→tracker)
- CM agents: emit `committed_to` without API
- Checkpoint every 50 interactions; resume path
- `tests/test_run_integration.py`: mixing k=1 seed 0; censored + failed paths

### Phase C — Real API smoke

- `OpenAICompatClient` + model registry resolution from `config.yaml`
- Env-var fail-fast; no secrets in repo
- `run_one.py` with `--smoke`, `--max-interactions`
- Manual acceptance only (not CI)

### Phase D — Pilot batch

- `run_pilot.py`: 36 runs/model grid, k cyclic, `--dry-run`, resume via sidecar, `--retry-failed`
- Seed derivation from `base_seed` + (topology, k, seed_index)

### Phase E — Live analytics

- `live/monitor.py` (Rich): tail jsonl + read-only meta; 5 s refresh; §9 widgets
- `live/cost.py`, `notebooks/pilot_dashboard.ipynb`
- Verify monitor never writes to `data/`

### Phase F — DVs + analysis

- `dvs.py`: all §7 functions; 144 denominator via shared `label_shares()`
- `analysis/common.py`, `h1.py` … `h4.py`, `cross_model.py`
- `analyze.py` CLI; `tests/test_dvs.py`, `tests/test_analysis.py`
- Pin stats deps in `requirements.txt`

### Phase G — Main study + repro

- `run_main.py`: eligible-count targeting per cell, attempted cap
- Record commit pin in WORKING §12 / README
- `pip freeze` → exact `requirements.txt` pins

---

## Secondary outputs (same run)

1. Add link in [`README.md`](../README.md) under Implementation status → “Execution checklist: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)”
2. Append one line to WORKING §14 session log: “IMPLEMENTATION_PLAN.md created”
3. Do **not** edit `ashery-ai-norms/`, Methods LaTeX, or rewrite `gate.py` / `networks.py`

---

## Quality bar

- **No TBD** without owner + blocker reference (WORKING §13 or Doug open questions)
- Every acceptance criterion has a **verify command**
- Dependencies form a DAG — no circular deps
- Todos are small enough for one PR or one agent session (~1–3 h human equivalent)
- English prose; implementation-focused, not thesis narrative

---

## Anti-patterns

- Do not duplicate WORKING.md content — link and decompose into todos
- Do not implement code in this pass
- Do not add scope (scale-free, meta-prompting, Mehdizadeh graphs, extra topologies)
- Do not commit `.env` or API keys
- Do not create files outside this repo except README link

---

## Post-run self-check

- [ ] `IMPLEMENTATION_PLAN.md` exists with all 8 sections above
- [ ] ≥40 checkbox todos across phases A–G
- [ ] Every phase has entry + exit criteria
- [ ] CLI smoke sequence is cumulative and copy-paste ready
- [ ] Blockers mapped to specific todo IDs
- [ ] README links to IMPLEMENTATION_PLAN.md
- [ ] WORKING §14 session log updated
