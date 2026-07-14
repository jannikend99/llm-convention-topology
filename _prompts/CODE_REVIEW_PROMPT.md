# Agent prompt — Code review (`llm-convention-topology`)

## Task

**Review-only pass** on the thesis experiment codebase. Produce a structured report: [`CODE_REVIEW_REPORT.md`](../CODE_REVIEW_REPORT.md) in this repo root.

**Do not implement fixes** in the same run unless the user explicitly asks afterward. Read code, run verification commands, compare against Methods + charter, write findings.

**Re-runnable:** each review run writes a dated report. **R1:** overwrites [`CODE_REVIEW_REPORT.md`](../CODE_REVIEW_REPORT.md). **R2+:** use [`CODE_REVIEW_PROMPT_R2.md`](CODE_REVIEW_PROMPT_R2.md) → writes [`CODE_REVIEW_REPORT_R2.md`](../CODE_REVIEW_REPORT_R2.md) and leaves R1 intact.

---

## SSOT read order (mandatory)

| Priority | Document | What to verify |
| ---: | --- | --- |
| 1 | [`WORKING.md`](../WORKING.md) | Design locks §, porting map §2, logging §6, DVs §7, analysis §8, live §9 |
| 2 | [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) | Which todos are ✅; §0 architecture principles; §7 dependency patterns |
| 3 | **All implemented code** | `convention_topology/`, `live/`, `run_*.py`, `analyze.py`, `tests/`, `config.yaml`, `requirements*.txt` |
| 4 | Methods (thesis-writing submodule) | `development/03_Methods/WORKING.md`, `M03_procedure/WORKING.md`, `M04_outcomes_analysis/WORKING.md` |
| 5 | Methods LaTeX (what we promise readers) | `chapters/03_Methods.tex`, `chapters/99_Appendix.tex` (`app:reproducibility`, `app:methods-implementation`) |
| 6 | [`README.md`](../README.md) | Status table matches reality |
| 7 | Ashery reference (spot-check ports) | `../ashery-ai-norms/` — `prompting.py`, `utils.py`, `simulation_module.py`, `run_API.py` |
| 8 | Open decisions | `01_Orga/Doug_Open_Questions.md` D6 (structured output vs parsing) |

On conflict: **Methods LaTeX + WORKING** > IMPLEMENTATION_PLAN > code comments.

---

## Verification commands (run all; paste summaries into report)

```bash
cd "Master Thesis/02_Topic/Experiment_Code/llm-convention-topology"

python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests 2>/dev/null && coverage report --include="convention_topology/*,live/*" --fail-under=85

git grep -iE "sk-|api[_-]?key.*=" -- ':!*.md' ':!_prompts/' ':!CODE_REVIEW_REPORT.md' || true
git log -1 --format='%h %ci %s'
git rev-parse --short HEAD

# If CLIs exist and mock path works:
python run_one.py --model mock --topology complete --k 1 --seed 0 --max-interactions 5 --smoke 2>/dev/null || echo "run_one smoke: skip/fail"
python run_pilot.py --model mock --dry-run 2>/dev/null | tail -5 || true
python analyze.py --all --model mock 2>/dev/null || echo "analyze: skip/fail"
```

Note pass/fail for each. Do not call paid APIs.

---

## Review dimensions (cover every section in the report)

### A. Implementation completeness

- Cross-check `IMPLEMENTATION_PLAN.md` §2: list every ☐ / ⏸ todo with blocker if still open.
- Cross-check WORKING §1 status table vs files on disk.
- Missing files from target tree (§1 WORKING / §4 IMPLEMENTATION_PLAN): flag each.
- `README.md` implementation status: accurate or stale?

### B. Methods alignment (core)

For each **locked parameter**, cite **code location** + **match / mismatch / undocumented deviation**:

| Lock | Expected |
| --- | --- |
| N=24, W=2 labels {Q,M}, H=5 | config + simulation |
| Centola-3 topologies | `networks.py` |
| Gate ≥0.95 over 3N=72 | `gate.py` — do not suggest rewrite |
| Phase 1 cap 5000, censored semantics | `simulation.py` / `run.py` |
| Phase 2 horizon 1000 | `run.py` |
| CM `swap`, k∈{1…6} | `simulation.py`, orchestration |
| CM agents: no API call | integration test / code path |
| Run unit: sequential P1→P2 per (topology, k, seed, model) | `run.py` |
| 3× retry → `failed`, not auto-replaced | `llm.py`, `run.py` |
| Sidecar metadata §6 fields | `persistence.py` |
| `config_hash` excludes secrets | `config.py` |
| Flip: ≥95% + modal = `committed_to`; **no `flip_resisted`** | `dvs.py` |
| Label-share denominator **144** (2×3N emissions) | `dvs.py` |
| `flip_50` boundary: exactly 50% → 0 | `dvs.py` |
| H1–H3b tests per spec (M04) | `analysis/h*.py` |
| Llama-primary confirmatory; cross-model descriptive only | `analyze.py`, `cross_model.py` |
| Pilot: 12 attempted/topology, cyclic k | `run_pilot.py` |
| Main: eligible-count targets | `run_main.py` |

### C. Function & module audit

For **every module** below, list **public functions/classes**, one-line purpose, and findings (or “OK”):

`prompting.py`, `llm.py`, `tracker.py`, `gate.py`, `networks.py`, `simulation.py`, `run.py`, `persistence.py`, `config.py`, `dvs.py`, `analysis/*`, `live/reader.py`, `live/monitor.py`, `live/web.py`, `live/cost.py`, `run_one.py`, `run_pilot.py`, `run_main.py`, `analyze.py`

Flag per module:
- Architecture violations (§0 IMPLEMENTATION_PLAN): pure core doing I/O, bare `except`, module-level `random`, CLIs with business logic
- Ashery port fidelity where marked **adopt/adapt** in WORKING §2
- Dead code, stubs, `NotImplementedError` left in production paths

### D. Analysis pipeline

- H1: one-sample t vs τ=0.90, Wilcoxon robustness, regime proportion descriptive
- H2: two one-tailed Welch, no correction, Mann–Whitney
- H3a: GAM + LR vs linear; sensitivity 50%
- H3b: interaction logistic + confirmatory/exploratory label
- H4: descriptive only
- Outputs land in `outputs/{model}/` with JSON+CSV+figures

### E. Live analytics

- `live/reader.py` single data layer; no writes to `data/`
- Rich monitor + Streamlit web + notebook: panels match WORKING §9
- Read-only guarantee tested?

### F. Tests & CI

- Map `tests/*` → what they cover; gaps vs IMPLEMENTATION_PLAN §5 test matrix
- Branch-critical paths: parser, retry, flip taxonomy, resume, CM zero-API
- `.github/workflows/tests.yml` present and valid?
- Coverage ≥85% on `convention_topology/` + `live/`?

### G. Dependencies & security

- `requirements.txt` / `requirements-dev.txt` vs §7.2 pins (`scipy<1.17` for pygam, etc.)
- No committed secrets; `.env` gitignored
- OpenAI client `max_retries=0` (app RetryPolicy owns retries)?

### H. Documentation & reproducibility

- `README.md`: clone, run path, status, links to WORKING + IMPLEMENTATION_PLAN
- `WORKING.md` §12 repro pins vs actual `git` state
- Appendix-promised fields in sidecar / events schema
- Deviations from Ashery: each flagged with Methods rationale or marked **missing doc**

### I. Open decisions (non-blocking but note)

- Doug D1–D6 items that code assumes provisionally (model strings, structured output, provider)
- WORKING §13 blockers

---

## Report format (`CODE_REVIEW_REPORT.md`)

```markdown
# Code review — llm-convention-topology

**Date:** YYYY-MM-DD · **Commit:** `abc1234` · **Plan progress:** N/46 ✅ (X ☐, Y ⏸)

## Executive summary
(3–6 bullets: ship/no-ship for pilot, top blockers)

## Verification results
(table: command → pass/fail + one line)

## Findings

### Blockers (must fix before pilot)
| ID | Area | File:line | Issue | Methods ref |

### Major (should fix before main study)
...

### Minor / nits
...

## Methods alignment matrix
(full table from dimension B)

## Module audit
(compact table from dimension C)

## Test coverage gaps
...

## Documentation gaps
...

## Ashery port spot-checks
(file → adopt/adapt/skip → OK / issue)

## Recommended next actions
(numbered, prioritized; do not implement here)
```

**Severity rules:**
- **Blocker:** wrong DV, wrong gate, breaks reproducibility, secrets, pilot would produce invalid inference
- **Major:** missing test for locked behavior, stale README, orchestration bug with workaround
- **Minor:** style, missing type hint, doc drift

---

## Anti-patterns

- Do not rewrite `gate.py` / `networks.py` as “fixes” in the review — only flag if genuinely wrong
- Do not edit `ashery-ai-norms/` or Methods LaTeX — note mismatches for human follow-up
- Do not dismiss a Methods lock because “code works” — alignment is the criterion
- Do not produce a praise-only report; empty sections must say “no issues found” explicitly
- Do not run `git commit` / `git push`

---

## Post-run self-check

- [ ] `CODE_REVIEW_REPORT.md` written with all sections
- [ ] Every module in dimension C mentioned
- [ ] Methods alignment matrix complete (all locks in B)
- [ ] Verification commands executed and recorded
- [ ] Blockers have file:line or file:function references
- [ ] IMPLEMENTATION_PLAN ☐/⏸ todos cross-referenced
