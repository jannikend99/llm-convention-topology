# Agent prompt — Code review R2 (`llm-convention-topology`)

## Task

**Second independent review pass** (review-only). Produce [`CODE_REVIEW_REPORT_R2.md`](../CODE_REVIEW_REPORT_R2.md).

**Do not** overwrite [`CODE_REVIEW_REPORT.md`](../CODE_REVIEW_REPORT.md) (R1, 2026-07-14). **Do not** implement fixes unless the user explicitly asks afterward.

This run has two jobs:
1. **Remediation audit** — verify every R1 finding (B1, B2, M1–M4, N1–N7) against [`FIX_PLAN.md`](../FIX_PLAN.md) acceptance criteria.
2. **Fresh review** — re-read code as a new reviewer; flag **new** issues R1 missed or fixes introduced.

---

## Mandatory reads (order)

| # | Document | Why |
| ---: | --- | --- |
| 1 | [`CODE_REVIEW_REPORT.md`](../CODE_REVIEW_REPORT.md) | R1 baseline (blockers, majors, minors) |
| 2 | [`FIX_PLAN.md`](../FIX_PLAN.md) | Expected fixes + acceptance per `FIX-*` todo |
| 3 | [`WORKING.md`](../WORKING.md) + [`03_Methods.tex`](../../Thesis_Writing/chapters/03_Methods.tex) | Charter |
| 4 | [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) | Plan completion |
| 5 | **Current codebase** | Truth on disk |

On conflict: **Methods LaTeX + WORKING** > FIX_PLAN > R1 report.

---

## Verification commands (run all; record in R2 report)

```bash
cd "Master Thesis/02_Topic/Experiment_Code/llm-convention-topology"

python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests && coverage report --include="convention_topology/*,live/*" --fail-under=85

git grep -iE "sk-|api[_-]?key.*=" -- ':!*.md' ':!_prompts/' ':!CODE_REVIEW_REPORT*.md' || true
git status --short
git log -1 --format='%h %ci %s'
git rev-parse --short HEAD

python run_one.py --model mock --topology complete --k 1 --seed 0 --max-interactions 5 --smoke
python run_pilot.py --model mock --dry-run
python analyze.py --all --model mock
python run_main.py --model mock --dry-run
```

No paid API calls.

---

## Part 1 — Remediation audit (required table)

For **each** R1 ID, read the actual code (not FIX_PLAN prose) and assign:

| Status | Meaning |
| --- | --- |
| **FIXED** | Matches FIX_PLAN acceptance + Methods |
| **PARTIAL** | Improved but acceptance not fully met — say what's left |
| **OPEN** | Unchanged or wrong fix |
| **N/A** | Only if finding truly obsolete (justify) |

| R1 ID | FIX_PLAN IDs | What to verify in code |
| --- | --- | --- |
| **B1** | FIX-B1-01…06 | `h3a.py`: primary `lr_stat_gam_vs_linear` / `lr_p_gam_vs_linear`; intercept contrast **descriptive only** (`*_linear_vs_intercept`); `flip_curve` in JSON; `03_Methods.tex:228-229` |
| **B2** | FIX-B2-01…03 | No `code_commit="pilot"` anywhere; shared `get_code_commit()` in `orchestration.py` (or equivalent); pilot sidecar test |
| **M1** | FIX-M1-01…03 | `shared_shuffle=True` Phase 2 only; test both agents same order; WORKING §2 updated |
| **M2** | FIX-M2-01…02 | Single `_modal_lexicographic` in `tracker.py`; gate sidecar == `dvs.incumbent_label` on tie fixture |
| **M3** | FIX-M3-01…02 | Full grid confirmatory; zero-cell → not confirmatory |
| **M4** | FIX-M4-01…04 | CLIs thin; logic in `orchestration.py` / `analysis/dispatch.py` |
| **N1** | FIX-N1-01…02 | `persistence.write_analysis_*` + `delete_run_artifacts` |
| **N2** | FIX-N2-01…02 | `minority_size != 0` → `NotImplementedError` (≤3 lines in `networks.py`) |
| **N3** | FIX-N3-01 | `common.py` uses glob paths, no string reconstruction |
| **N4** | FIX-N4-01 | (Falls out of M4) no inline `options_set[0]` in `run_main` |
| **N5** | FIX-N5-01…02 | `flip`/`time_to_flip` raise on short Phase 2 |
| **N6** | FIX-N6-01 | `requirements.txt` matches IMPLEMENTATION_PLAN §7.2 upper bounds |
| **N7** | FIX-N7-01…02 | Typed exceptions in h3a/h3b; `reason` in exploratory JSON |

If fixes were **not** implemented yet, mark OPEN and still complete Part 2.

---

## Part 2 — Fresh review (same depth as R1)

Re-run all dimensions from [`CODE_REVIEW_PROMPT.md`](CODE_REVIEW_PROMPT.md) § Review dimensions **A–I**:

- Implementation completeness (IMPLEMENTATION_PLAN ☐/⏸)
- Methods alignment matrix (all locks — re-derive from code, don't copy R1 table)
- Module audit (include **`orchestration.py`**, **`analysis/dispatch.py`** if they exist)
- Analysis H1–H4, live analytics, tests/CI, deps/security, docs/repro
- Ashery port spot-checks
- Doug open decisions

**Explicitly hunt for:**
- Regressions from remediation (broken imports, changed run_ids, analysis JSON schema breaks)
- New blockers R1 did not list
- Tests that pass but don't assert the locked behavior (false confidence)
- Uncommitted work vs `WORKING.md` §12 commit pin
- `convention_topology/orchestration.py` duplication left behind in CLIs after M4

**Do not** re-report items already FIXED in Part 1 unless the fix is **incorrect** (then Part 2 finding references Part 1 status PARTIAL/OPEN).

---

## Report format (`CODE_REVIEW_REPORT_R2.md`)

```markdown
# Code review R2 — llm-convention-topology

**Date:** YYYY-MM-DD · **Commit:** `abc1234` · **Git status:** (clean/dirty summary)
**R1 reference:** CODE_REVIEW_REPORT.md (2026-07-14)
**Plan progress:** N/46 ✅ (X ☐, Y ⏸)

## Executive summary
- Remediation: X/13 FIXED, Y PARTIAL, Z OPEN
- **Pilot verdict:** ship / no-ship / ship-with-caveats
- New findings since R1: (count by severity)

## Verification results
(command table)

## Part 1 — Remediation audit
| R1 ID | Status | Evidence (file:line or test) | Notes |

## Part 2 — New / remaining findings

### Blockers
### Major
### Minor

## Methods alignment matrix (fresh)
## Module audit (fresh)
## Test coverage gaps
## Documentation gaps
## Ashery port spot-checks
## R1 → R2 delta
(bullets: what improved, what's still open, what's newly discovered)

## Recommended next actions
(prioritized; skip items already FIXED correctly)
```

**Severity rules:** same as R1 (`CODE_REVIEW_PROMPT.md`).

---

## Anti-patterns

- Do not overwrite `CODE_REVIEW_REPORT.md`
- Do not mark B1 FIXED if primary test is still linear-vs-intercept
- Do not mark B2 FIXED if any pilot/main sidecar still has `code_commit: "pilot"`
- Do not copy R1 findings verbatim without re-verifying in code
- Do not implement fixes; do not `git commit`

---

## Post-run self-check

- [ ] `CODE_REVIEW_REPORT_R2.md` written; R1 file untouched
- [ ] Part 1 table has all 13 R1 IDs (B1, B2, M1–M4, N1–N7)
- [ ] Part 2 Methods matrix re-derived from current code
- [ ] Pilot ship/no-ship verdict stated explicitly
- [ ] R1 → R2 delta section present
- [ ] All verification commands executed
