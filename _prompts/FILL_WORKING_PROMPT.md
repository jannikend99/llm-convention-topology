# Agent prompt — Fill `WORKING.md` (thesis experiment codebase)

## Task

**Fully specify** `WORKING.md` in this repository (`llm-convention-topology/`). This is a **planning / architecture pass only** — do **not** implement feature code in the same run unless the user explicitly asks afterward.

The filled `WORKING.md` becomes the charter for all subsequent implementation. Every module, script, test, and live-analytics component should be named, scoped, and acceptance-tested before anyone writes production code.

---

## Your environment (same as parent agent)

You have full repo access, shell, Zotero MCP, Granola MCP, and project skills under `Master Thesis/.cursor/skills/`. Use them — do not guess from memory.

**Workspace roots:**

| Repo | Path |
| --- | --- |
| Meta-repo | `Master Thesis/` |
| This repo | `Master Thesis/02_Topic/Experiment_Code/llm-convention-topology/` |
| Thesis writing (submodule) | `Master Thesis/02_Topic/Thesis_Writing/` |
| Ashery reference (read-only) | `Master Thesis/02_Topic/Experiment_Code/ashery-ai-norms/` |
| Collaborator API reference (optional) | `Master Thesis/02_Topic/Experiment_Code/ai-convention-formation/AI Agents & Norms/` |

---

## SSOT read order (mandatory)

1. **This repo:** `WORKING.md` (skeleton), `README.md`, `convention_topology/*`, `tests/*`, `config.yaml`
2. **Methods design locks:** `Thesis_Writing/development/03_Methods/WORKING.md` — especially code map, adopt/skip, config reference, reproducibility package
3. **Procedure + logging:** `…/M03_procedure/WORKING.md`
4. **DVs + analysis:** `…/M04_outcomes_analysis/WORKING.md`
5. **LaTeX (what we promise readers):** `chapters/03_Methods.tex`, `chapters/99_Appendix.tex` (`app:reproducibility`, `app:methods-implementation`)
6. **Ashery code audit:** read `ashery-ai-norms/` — at minimum `config.yaml`, `prompting.py`, `simulation_module.py`, `utils.py`, `runner.py`, `run_API.py`, `run_local.py`; skim `README.md`
7. **Zotero:** paper `asheryEmergentSocialConventions2024`, code `asheryAINormsZenodo2024` — confirm citekeys match LaTeX

**Protocol anchor:** Ashery et al. (2025) paper + Zenodo code release only. Collaborator repo is **optional** for OpenAI-compatible API adapter patterns — do not treat it as protocol SSOT.

---

## What to fill in `WORKING.md`

Replace every `<!-- AGENT: FILL -->` block and empty tables with concrete, actionable content.

### §1 Target architecture

- Proposed package tree under `convention_topology/` and top-level scripts (`run_pilot.py`, `run_main.py`, `analyze.py`, …)
- `data/` / `logs/` / `outputs/` layout
- Entrypoints and how a replicator runs pilot vs main study

### §2 Ashery → thesis porting map

- **File-by-file** and, where helpful, **function-by-function** mapping from `ashery-ai-norms/` to this repo
- Mark each item: **adopt verbatim**, **adapt**, **reimplement**, **skip**
- Explicitly document thesis deviations already locked: gate **0.95**, lattice topology, `max_phase1_interactions: 5000`, factorial k grid, four models, flip taxonomy (no `flip_resisted`)

### §3 Implementation phases

- Ordered phases A→… with dependencies, files touched, and **acceptance criteria** (testable)
- Suggested order: mock LLM layer → real API smoke → full run unit → pilot batch → live analytics → analysis scripts → main-study runner

### §4 LLM API layer

- Provider abstraction; env vars (no secrets committed)
- JSON response parsing; 3× retry then abort (`run_status = failed`)
- Model pinning per run; logging `model_id` + endpoint config
- How CM agents skip API calls

### §5 Run orchestration

- Exact factorial grids (topology × k × seed × model)
- Pilot: 12 attempted Phase 1 / topology (per model strategy — specify)
- Main study targets from Methods M01/M04
- CLI examples (copy-paste ready)

### §6 Logging and persistence

- Align with M03 logging schema and Appendix `app:methods-implementation`
- Pickle + sidecar metadata format; `config_hash` computation
- Failed vs censored vs completed runs

### §7 Dependent variables (code)

- Module/function per DV; unit tests for each
- Dominant share denominator: **2 × 3N = 144** label emissions in final window
- Primary flip + Centola 50% sensitivity metric
- Critical mass at (topology × model) condition level

### §8 Analysis pipeline

- One script (or module) per confirmatory hypothesis H1–H3b + H4 exploratory
- Per-model execution; **Llama-3.1-70B primary** confirmatory rule for thesis-level claims
- Regime proportion share > τ = 0.90 — descriptive only
- Libraries (`scipy`, `statsmodels`, `pygam`, …) locked in `requirements.txt` proposal

### §9 Live analytics (required — user priority)

Propose a **concrete** pilot/main monitoring solution (notebook, Streamlit, Rich terminal dashboard, or hybrid). Specify:

- What updates in real time vs batch refresh
- Minimum widgets/plots (eligibility by topology, run progress, API errors, dominant-share snapshots, optional cost)
- Where it lives in repo (`live/` or `notebooks/pilot_dashboard.ipynb`)
- How it reads run logs without corrupting active runs

### §10–§12

- Testing layers (mock LLM fixtures essential)
- Extended `config.yaml` schema + CLI
- Reproducibility pins linking to Appendix `tab:appendix-repro-pins`

### §13 Open decisions

- Code-blocking items only; link `01_Orga/Doug_Open_Questions.md` for model ID locks

### Sign-off table

- Set milestone **0** to ✅ when WORKING.md is complete
- Leave milestones 1–6 as ☐

---

## Secondary outputs (same run)

1. **Update `README.md`** — sync the Implementation status table with your WORKING.md plan (still ☐ until code lands)
2. **Append a session-log line** to `WORKING.md` §14 with date and summary
3. **Do not** edit `ashery-ai-norms/` or Methods LaTeX unless you find a **factual mismatch** — if so, note it in §13 and stop short of prose edits unless asked

---

## Quality bar

- Every table row filled — no placeholder “TBD” without owner + blocker
- Acceptance criteria are **testable** (“`python -m unittest` green”, “one mixing run produces valid metadata JSON”, …)
- Ashery alignment: when deviating from upstream, cite **locked Methods reason** (not ad hoc)
- Live analytics: must be feasible during pilot week, not a research project itself
- English prose in WORKING.md; concise, implementation-focused

---

## Anti-patterns

- Do not rewrite existing `gate.py` / `networks.py` in this pass
- Do not import Mehdizadeh graph families or extra topologies into v1 scope
- Do not duplicate the Methods chapter — link and operationalize
- Do not commit API keys or `.env` contents
- Do not create new repos or meta-repo files unless necessary (prompt + WORKING live **here**)

---

## Post-run self-check

- [ ] All `<!-- AGENT: FILL -->` markers removed
- [ ] Sign-off milestone 0 marked complete
- [ ] README status table matches §1–§3
- [ ] At least one end-to-end “happy path” CLI sequence documented
- [ ] Live analytics section has named files and refresh strategy
- [ ] Ashery porting map covers all `.py` files in `ashery-ai-norms/` root
