# Agent prompt — Plan fixes from `CODE_REVIEW_REPORT.md` (plan mode only)

## Task

**Planning pass only** — produce [`FIX_PLAN.md`](../FIX_PLAN.md) in this repo root. Do **not** implement code in the same run unless the user explicitly asks afterward.

Input: [`CODE_REVIEW_REPORT.md`](../CODE_REVIEW_REPORT.md) (2026-07-14). Charter: [`WORKING.md`](../WORKING.md), [`03_Methods.tex`](../../Thesis_Writing/chapters/03_Methods.tex). On conflict: **Methods LaTeX + WORKING** > IMPLEMENTATION_PLAN > report prose.

**Scope (user-locked 2026-07-14):** **All** review findings — Blockers **B1–B2**, Majors **M1–M4**, Minors **N1–N7**. Nothing deferred except git commit (user decides) and Doug D6 structured output. **Do not** rewrite `gate.py` / `networks.py` beyond the minimal N2 touch described below.

---

## Read before planning

1. `CODE_REVIEW_REPORT.md` — full findings + module audit
2. All affected modules (see per-finding sections below)
3. Methods: `03_Methods.tex` H3a/H3b; `WORKING.md` §2, §7–§8, §0 architecture principles
4. Ashery: `ashery-ai-norms/simulation_module.py::committed` (M1)
5. Existing CLIs: `run_one.py`, `run_pilot.py`, `run_main.py`, `analyze.py`

---

## User-approved fix directions (2026-07-14)

### B1 — H3a: GAM vs. linear LR (Blocker) ✅ approved

**Problem:** Primary LR is linear vs. intercept-only; Methods locks **GAM spline vs. linear logistic**.

**User lock:**
- **Primary inferential contrast:** GAM vs. linear LR (`lr_stat_gam_vs_linear`, `lr_p_gam_vs_linear`, document `df`)
- **Linear-vs-intercept:** retain only as **secondary/descriptive** fields (rename e.g. `lr_stat_linear_vs_intercept` — never the primary H3a claim)
- GAM supplies flip-curve figure data in JSON output
- Update `tests/test_analysis.py`, `IMPLEMENTATION_PLAN.md` §7.9 (~line 585)
- Code must match `03_Methods.tex:228-229` — no LaTeX change unless impossible

**Plan hint:** `statsmodels.Logit` linear + `pygam.LogisticGAM(s(0))`; deviance LR; small-n GAM fail → `exploratory`.

---

### B2 — `code_commit` sidecar (Blocker) ✅ approved

**User lock:** Hoist shared `get_code_commit()` (from `run_one.py` pattern); all CLIs use it. Integration test on pilot-produced sidecar.

---

### M1 — Phase 2 shared option shuffle ✅ approved

**Fix:** `shared_shuffle: bool` on `make_interaction_step`; Phase 2 `True`, Phase 1 `False` (Ashery `committed()` fidelity). Update WORKING §2 deviations/fidelity table. Tests for Phase 2 using same shuffled order for both agents in one interaction.

---

### M2 — Incumbent lexicographic tie-break ✅ approved

**Fix:** Single `_modal_lexicographic` in `tracker.py`; `modal_label_in_window` + `dvs.incumbent_label` share it. Tests: tie at gate; sidecar matches `dvs.incumbent_label(tracker, t_gate)`.

---

### M3 — H3b full-grid confirmatory check ✅ approved

**Fix:** `_is_confirmatory` over full `(topology × cm_k)` grid; zero-count cells fail. Caller passes expected topologies + `k ∈ {1..6}`. Tests: missing cell → not confirmatory.

---

### M4 — Thin CLI / orchestration centralization ✅ approved (in scope)

**Problem:** `run_pilot.py`, `run_main.py`, `analyze.py` hold business logic; duplicates `RunConfig`/client wiring (root cause of B2 class bugs).

**Plan must specify a concrete module split** (names justified), e.g.:

| New / extended module | Moves here from CLI |
| --- | --- |
| `convention_topology/orchestration.py` (or `batch.py`) | `pilot_grid`, `run_batch`, resume/retry filtering, `ThreadPoolExecutor` dispatch, shared `_build_run_config` / client factory |
| `convention_topology/main_study.py` (or section in orchestration) | `cell_targets`, `run_cell_targeted`, eligible-count loop |
| `convention_topology/analysis/dispatch.py` (or extend `common.py`) | `run_h1`…`run_h4`, `run_cross_model`, output path helpers |

**End state:** each CLI = `argparse` + **one** call (`orchestration.run_pilot(...)`, `main_study.run(...)`, `analysis.dispatch.run_all(...)`). Existing `tests/test_orchestration.py` / `test_analysis.py` imports updated — behavior unchanged.

**Plan todos:** incremental (extract shared config first — supports B2 — then pilot, then main, then analyze) so each step stays test-green.

---

### N1 — Single-writer principle ✅ approved

**Fix (pick one, justify in plan):**
- **Preferred:** add `persistence.py` helpers: `write_analysis_json`, `write_analysis_csv`, `delete_run_artifacts(paths)`; CLIs call these
- **Alternative:** narrow IMPLEMENTATION_PLAN §0 principle 3 text to "run artifacts under `data/` + `logs/`" and document `outputs/` as separate export tree

Either way: no functional change to live-monitor read paths.

---

### N2 — `networks.py` minority_size dead path ✅ approved (minimal touch)

**Constraint:** `networks.py` is **not** rewritten (gate/networks lock).

**Fix:**
- Document in WORKING §2: `minority_size` branch unused; CM via `swap_committed` only
- Add **guard** at start of `get_interaction_network`: if `minority_size != 0`, raise `NotImplementedError` with pointer to `swap_committed` (≤3 lines — not a rewrite)
- Test: `minority_size=1` raises; `execute_run` path still uses `minority_size=0`

---

### N3 — `analysis/common.py` path coupling ✅ approved

**Fix:** `_run_dvs` accepts optional `meta_path` / `pickle_path` from `scan_meta_paths` glob result; do not reconstruct paths from string components. Test: loader still finds runs; optional test with mismatched reconstruction would fail before fix.

---

### N4 — `run_main.py` `_options` duplication ✅ approved

**Fix:** After M4 extraction, single `_options(config)` / `_build_run_config` in orchestration module; `run_main` never inlines `options_set[0]`. One-line test or rely on existing orchestration tests.

---

### N5 — `dvs.py` Phase 2 length guard ✅ approved

**Fix:** In `flip` / `time_to_flip`, if `len(answers) < t_start + window`, raise `ValueError` (or return explicit sentinel documented in docstring — plan must pick one and test). Prefer **raise** so misconfiguration is visible.

---

### N6 — Dependency pins ✅ approved

**Fix:** Align `requirements.txt` with IMPLEMENTATION_PLAN §7.2:
- `networkx>=3.6,<4`
- `PyYAML>=6.0.3,<7`
- `munch>=4.0,<5`
- Confirm scipy/pygam/pandas pins unchanged

---

### N7 — Typed analysis fit failures ✅ approved

**Fix:** Replace bare `except Exception` in `h3a.py` / `h3b.py` with narrow tuple (e.g. `LinAlgError`, `PerfectSeparationError`, `ValueError`) + optional custom `AnalysisFitError`; log reason in returned JSON `reason` field on exploratory path. Tests: degenerate *n* still returns exploratory dict, not crash.

---

## Suggested implementation phases (for FIX_PLAN DAG)

```
Phase 1 — Blockers:     B2 (+ shared config extract seeds M4-partial) → B1
Phase 2 — Majors:       M2 → M1 → M3
Phase 3 — M4 finish:    orchestration extract (pilot → main → analyze dispatch)
Phase 4 — Minors:       N1, N3, N4, N5, N6, N7, N2 (order flexible; N4 after M4)
Phase 5 — Docs + report: WORKING §2, IMPLEMENTATION_PLAN, CODE_REVIEW_REPORT remediation table
```

Each phase ends with full verification block below.

---

## Post-fix verification (mandatory in FIX_PLAN)

```bash
cd "Master Thesis/02_Topic/Experiment_Code/llm-convention-topology"
python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests && coverage report --include="convention_topology/*,live/*" --fail-under=85
python analyze.py --all --model mock
python run_pilot.py --model mock --dry-run
python run_pilot.py --model mock   # short batch optional if plan marks smoke-only
python run_main.py --model mock --dry-run
git grep -iE "sk-|api[_-]?key.*=" -- ':!*.md' ':!_prompts/' ':!CODE_REVIEW_REPORT.md' || true
```

---

## Explicitly out of scope

- Git commit / push (user decides)
- Methods LaTeX edits (WORKING §2 rows OK)
- Doug D6 structured output
- Rewriting `gate.py` or broad `networks.py` refactor

---

## `FIX_PLAN.md` output structure

```markdown
# Fix plan — code review remediation

**Source:** CODE_REVIEW_REPORT.md · **User scope:** B1–B2, M1–M4, N1–N7 · **Target:** pilot + main-study ready

## Executive summary (3–5 bullets)

## Todo checklist
| ID | Finding | Files | Steps | Tests | Verify |

IDs: `FIX-B1-01`, `FIX-B2-01`, `FIX-M4-03`, `FIX-N6-01`, …

## Dependency DAG (mermaid or ordered list)

## Per-finding acceptance criteria (map 1:1 to B1…N7)

## Docs to update

## Remediation status table (for appending to CODE_REVIEW_REPORT.md)

| Finding | Status | Commit/PR |
```

**Granularity:** ≥25 todos total; M4 may be 4–6 todos; each todo ≤1 session.

---

## Anti-patterns

- Do not implement in this run
- Do not drop N1–N7 as "optional"
- Do not make linear-vs-intercept the primary H3a test (user rejected)
- Do not broad-rewrite `networks.py` (N2 guard only)

---

## Post-run self-check

- [ ] `FIX_PLAN.md` covers B1, B2, M1–M4, N1–N7
- [ ] B1 primary = GAM vs linear; intercept model descriptive only
- [ ] M4 module names and moved symbols listed
- [ ] N2 respects networks.py minimal-edit constraint
- [ ] DAG + verification block present
- [ ] No findings listed under Deferred (except git commit, D6)
