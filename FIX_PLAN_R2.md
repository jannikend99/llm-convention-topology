# Fix plan — R2 remediation

**Source:** CODE_REVIEW_REPORT_R2.md (2026-07-14) · **Scope:** R2-B1, R2-M1, R2-m2, R2-m4 (locked — pure code, no theory conflict) · R2-m1 pending user decision · R2-m3 partially in scope (CSVs; figures deferred)
**Charter precedence:** `03_Methods.tex` + `WORKING.md` > `IMPLEMENTATION_PLAN.md` > report prose.

## Decision needed before implementing (flagged, not a code bug)

- **R2-m1 — H3a labeling when the GAM collapses to linear (edof ≤ 2).** Current code labels this `exploratory` (same bucket as a genuine fit failure). This conflates "the model couldn't fit" with "the model fit fine and found no nonlinearity" — the latter is itself informative evidence against a tipping-point shape. Two options: (a) keep as-is (`exploratory`, simplest, matches `03_Methods.tex` literally — it doesn't discuss this edge case), or (b) add a distinct label (e.g. `"informative-null-linear"`) with its own `reason`, decided on and documented in WORKING §8 before the pilot readout. **Not implemented in this pass** — needs your call since it affects thesis-facing confirmatory/exploratory labeling semantics, not just code correctness.

## Todo checklist (all remaining items — pure code, implemented this pass)

| ID | Finding | Files | Fix | Tests |
| --- | --- | --- | --- | --- |
| FIX-R2B1-01 | R2-B1 (Blocker) | `convention_topology/analysis/common.py::_run_dvs` | Compute `dominant_share`/`shannon_entropy` over the **Phase-1-end** window (`answers[:t_gate][-72:]` for completed runs; full tracker's trailing 72 for censored runs, since a censored tracker *is* all-Phase-1) instead of the raw tracker's trailing 72 (which is Phase-2-end for completed runs). Include **censored** runs in this computation (Methods:212/246 pools all attempted Phase 1 trajectories) — only `flip`/`time_to_flip`/`flip_50` stay completed-only (Phase 2 concepts). | New fixture: Phase 1 window has a different dominant share than the Phase 2 tail → assert `dominant_share` reflects Phase 1, not Phase 2. New fixture: censored run → `dominant_share` non-null, flows into `run_h1`. |
| FIX-R2M1-01 | R2-M1 (Major) | `convention_topology/orchestration.py::get_code_commit` | Pin `git rev-parse` to the package's own directory (`cwd=<repo root>`), not the process cwd. | Test: chdir into a throwaway tmp git repo, call `get_code_commit()`, assert it still returns *this* repo's HEAD, not the tmp repo's. |
| FIX-R2m2-01 | R2-m2 (Minor) | `convention_topology/analysis/dispatch.py::run_h3a` | Export `flip_agreement.csv` (WORKING §8 lock) instead of `.json`. | Existing sensitivity-50 CLI path re-verified; format assertion added. |
| FIX-R2m3-01 | R2-m3 (Minor, partial) | `convention_topology/analysis/dispatch.py` | Add the "CSV (run-level table)" export WORKING §8 promises for each hypothesis script — the run-level rows that fed each test. **PDF figures deferred**: generating publication figures before real data exists is premature; WORKING §8's figure promise is left open and should be revisited at Results time, not fixed here. | Output-file existence assertions per script. |
| FIX-R2m4-01 | R2-m4 (Minor) | `tests/test_analysis.py` | Folded into FIX-R2B1-01's tests — the exact gap the R2 report named. | — |

## Verification (run after implementation)

```bash
cd "Master Thesis/02_Topic/Experiment_Code/llm-convention-topology"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/coverage run -m unittest discover -s tests && .venv/bin/coverage report --include="convention_topology/*,live/*" --fail-under=85
.venv/bin/python run_pilot.py --model mock --dry-run
.venv/bin/python run_pilot.py --model mock
.venv/bin/python analyze.py --all --model mock
.venv/bin/python run_main.py --model mock --dry-run
```

## Acceptance criteria

- **R2-B1:** a run whose Phase 1 and Phase 2 tails have different dominant labels/shares yields an `analysis/common.py`-loaded `dominant_share` matching the Phase-1-end window, not the tracker's raw tail. A censored run's `dominant_share`/`shannon_entropy` are non-null and appear in `run_h1`'s/`run_h2`'s input.
- **R2-M1:** `get_code_commit()` called from any cwd returns this repo's HEAD (or `"unknown"` only if genuinely outside any repo), never a different repo's commit.
- **R2-m2:** `flip_agreement.csv` exists after `analyze.py --h3a --sensitivity-50`; no `flip_agreement.json`.
- **R2-m3:** `h1.csv`/`h2.csv`/`h3a.csv`/`h3b.csv`/`h4.csv` exist per model after `analyze.py --all`, alongside the existing `.json`.
