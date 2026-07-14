# Code review R2 — llm-convention-topology

**Date:** 2026-07-14 · **Commit:** `10912a6` · **Git status:** dirty — the entire Phases A–G implementation **and all R1 remediation fixes remain uncommitted** in the working tree (`10912a6` is the 2026-07-10 scaffold commit; nothing reviewed here is committed)
**R1 reference:** CODE_REVIEW_REPORT.md (2026-07-14)
**Plan progress:** 43/46 ✅ (0 ☐, 3 ⏸ — C-05 real-API smoke, G-03/G-04 repro freeze, all correctly deferred)

---

## Executive summary

- **Remediation: 13/13 FIXED** (B1, B2, M1–M4, N1–N7). Every FIX_PLAN acceptance criterion was re-verified against the actual code, its tests, and live CLI runs — not against FIX_PLAN prose. No fix regressed anything: 146 tests green, coverage 91% (gate ≥85%), all CLI smokes pass, no CLI imports another CLI, sidecars from a live mock pilot batch record the real git commit.
- **Pilot verdict: ship-with-caveats.** All *data-collection-side* locks (gate, phases, CM swap, retry, sidecar schema, seeds, run unit) verify clean, so the pilot can collect data — with one operational caveat: **launch all batch CLIs from the repo directory** (see R2-M1 below), and commit the implementation first so the recorded `code_commit` is meaningful. However, **H1/H2 analysis must not be run for inference until the new Blocker R2-B1 is fixed** — this is analysis-side only and does not corrupt collected data (DVs are recomputed post-hoc from pickles).
- **New findings since R1: 1 Blocker, 1 Major, 4 Minor.**
  - **R2-B1 (Blocker, missed by R1):** H1/H2's dominant share and entropy are computed over the **final 3N window of the whole tracker** — for completed runs that is the *end of Phase 2, after CM injection*, not "Phase 1 end" as Methods locks — and **censored runs are silently excluded** from H1/H2 although Methods pools all attempted Phase 1 trajectories.
  - **R2-M1 (Major, latent flaw in the B2 fix):** `get_code_commit()` resolves git HEAD from the process **cwd**. Launched from the meta-repo root, sidecars record the *meta-repo's* commit — demonstrated live (`dcd3472` instead of `10912a6`): a wrong but plausible-looking hash, worse than `"unknown"`.
- Uncommitted-work status is unchanged from R1 and remains the top follow-up after the R2-B1 fix.

---

## Verification results

All commands run with the project venv (`.venv/bin/python`; the bare `python` shim is broken under pyenv on this machine — `pyenv: python: command not found`).

| Command | Result | Note |
| --- | --- | --- |
| `python -m unittest discover -s tests -v` | ✅ pass | **146 tests**, 0 failures (R1: 121) |
| `coverage run … && coverage report --fail-under=85` | ✅ pass | **91%** on `convention_topology/` + `live/` |
| Secrets grep (working tree, incl. untracked) | ✅ clean | only a fake test key in `test_llm.py` and env-var *names*; note `git grep` is vacuous here — all implementation files are untracked, so the R1-prompt command inspects nothing; re-run with plain `grep -r` (done) |
| `git log -1` / `git rev-parse --short HEAD` | ✅ ran | `10912a6` 2026-07-10 — predates the entire reviewed implementation |
| `git status --short` | dirty | all of `convention_topology/`, `live/`, `tests/`, CLIs, docs untracked |
| `run_one.py --model mock --topology complete --k 1 --seed 0 --max-interactions 5 --smoke` | ✅ pass | 5 parsed labels, model_id + endpoint printed |
| `run_pilot.py --model mock --dry-run` | ✅ pass | exactly 36 rows, cyclic k 1–6,1–6 |
| `run_pilot.py --model mock` (full batch) | ✅ pass | 36/36 completed in ~3.6 s (data dir was empty; batch re-created) |
| `analyze.py --all --model mock` | ✅ pass | exit 0; h1–h4 JSON + eligibility.csv written; h3a JSON carries `lr_stat_gam_vs_linear`/`flip_curve`; on the mock batch the GAM's edof = 1.93 → LR undefined → correctly labeled `exploratory` with `reason` |
| `run_main.py --model mock --dry-run` | ✅ pass | 18 cells, [15–20]/[8–10] targets, caps 45/24 |

Live sidecar audit of the fresh 36-run batch: 36/36 `completed`, `code_commit` = `10912a6` on every sidecar (real HEAD, never `"pilot"`).

---

## Part 1 — Remediation audit

All 13 R1 findings re-verified in code (file:line) and tests. **13 FIXED, 0 PARTIAL, 0 OPEN.**

| R1 ID | Status | Evidence (file:line or test) | Notes |
| --- | --- | --- | --- |
| **B1** | **FIXED** | `analysis/h3a.py:77-97` fits `LogisticGAM(s(0))`, computes `lr_stat_gam_vs_linear = 2·(ll_gam − ll_linear)`, `df = edof − 2` (documented), `lr_p_gam_vs_linear = chi2.sf`; intercept contrast renamed `lr_stat_linear_vs_intercept`/`lr_p_linear_vs_intercept` (`h3a.py:50-51,108-109`), docstring marks it secondary; `flip_curve` over k=1..6 (`h3a.py:94-96`); fit failure → `exploratory` + `reason` (`h3a.py:98-101`); `IMPLEMENTATION_PLAN.md:587` note corrected. Tests: `test_analysis.py::test_primary_contrast_is_gam_vs_linear_not_linear_vs_intercept`, `::test_linear_vs_intercept_is_renamed_and_secondary` (old names asserted absent), `::test_flip_curve_present_on_confirmatory_fit`, `::test_degenerate_n_returns_exploratory_dict_not_crash`. Matches `03_Methods.tex:227-229` with no LaTeX change. | `label="confirmatory"` only when the GAM-vs-linear LR is actually computable (`h3a.py:86-90`) — FIX-B1-04 met. See new Minor R2-m1 on the edof ≤ 2 path. |
| **B2** | **FIXED** | `convention_topology/orchestration.py:30-37` `get_code_commit()` (real `git rev-parse --short HEAD` or `"unknown"`, never a literal); `build_run_config` sets `code_commit=get_code_commit()` (`orchestration.py:92`); all three CLIs import from `orchestration` (`run_one.py:19-25`, `run_pilot.py:17`, `run_main.py:20`); no `"pilot"` literal anywhere in production code (grep clean). Integration test `test_orchestration.py::CodeCommitSidecarTests::test_pilot_batch_sidecar_records_real_commit` runs a real mock batch into a tmp dir and asserts sidecar `code_commit == git rev-parse` and `!= "pilot"`. Verified live: all 36 fresh batch sidecars record `10912a6`. | Acceptance fully met as written; a **new cwd-dependence flaw** in this same function is reported as R2-M1 (Part 2) — it does not reopen B2's acceptance but must be fixed before multi-directory use. |
| **M1** | **FIXED** | `simulation.py:89,108-111,127-131`: `shared_shuffle: bool = False`; when `True`, options shuffled once per interaction *before* p1/p2 are chosen — matches Ashery `committed()` (`ashery-ai-norms/simulation_module.py:156` shuffle precedes player choice; re-verified upstream this pass). `run.py:245` passes `shared_shuffle=True` for Phase 2 only; Phase 1 step (`run.py:186-195`) uses the default per-agent shuffle. Tests: `test_run_integration.py::test_shared_shuffle_true_gives_both_players_the_same_option_order` (prompt-capturing client, 15 interactions, every pair identical) and `::test_shared_shuffle_false_gives_players_independent_option_orders`. WORKING §2 deviations table updated (row "Phase 2 option shuffle", `WORKING.md:208`). | |
| **M2** | **FIXED** | Single `tracker.py::modal_lexicographic` (`tracker.py:50-63`); production `modal_label_in_window` routes through it (`tracker.py:74`); `dvs.py:17` imports it (no second implementation). Tests: `test_gate.py::test_modal_label_in_window_exact_tie_breaks_lexicographically` (production path, forced tie), `test_dvs.py::test_tie_break_is_lexicographic` (dvs path), and integration `test_run_integration.py::test_sidecar_incumbent_label_matches_dvs_recomputation` (real-run sidecar `incumbent_label` == `dvs.incumbent_label` recomputation, same window). | Integration test agrees on a real (non-tie) run; tie agreement is structural (one shared implementation) plus per-path tie unit tests — acceptance intent met. |
| **M3** | **FIXED** | `h3b.py:40-57` `_is_confirmatory(df, expected_cm_ks)` checks every expected k per topology via `observed_counts.get((topology, k), 0)` — a zero-row cell can no longer hide; ≥2 topologies must clear the full k grid. Tests: `test_analysis.py::test_zero_count_cell_does_not_slip_through_as_confirmatory` (lattice missing k=6 entirely → not confirmatory), `::test_full_grid_at_floor_is_confirmatory`. | Expected k grid is a parameter with default `1..6` (`h3b.py:21,62`); `dispatch.run_h3b` relies on the default rather than passing it explicitly — functionally equivalent to the acceptance, noted only for precision. |
| **M4** | **FIXED** | `orchestration.py` holds `pilot_grid`/`existing_status`/`run_cell`/`run_batch` (ThreadPoolExecutor + resume/retry filtering)/`run_pilot`/`cell_targets`/`run_cell_targeted`/`run_main_study`; `analysis/dispatch.py` holds `run_h1..run_h4`/`run_eligibility`/`run_cross_model`/`run_all` with all output writing. `run_pilot.py` (63 lines), `run_main.py` (69), `analyze.py` (55) are argparse + one call. No CLI imports another CLI (import grep clean). Full mock pilot + dry-runs behaviorally identical. | `run_one.py` retains its `--smoke` loop (network + stepping logic in the CLI file) — pre-existing, explicitly outside M4's scope (R1 M4 listed only pilot/main/analyze), unchanged risk. |
| **N1** | **FIXED** | `persistence.py:128-151`: `write_analysis_json`, `write_analysis_csv`, `delete_run_artifacts` (missing_ok unlinks); `analysis/dispatch.py:22` uses the writers exclusively; retry-failed cleanup in `orchestration.py:195,304` uses `delete_run_artifacts`. Tests: `test_run_integration.py::test_write_analysis_json_round_trips`, `::test_write_analysis_csv_round_trips`, `::test_delete_run_artifacts_removes_meta_and_pickle`, `::test_delete_run_artifacts_is_missing_ok`. | |
| **N2** | **FIXED** | `networks.py:55-61`: guard raises `NotImplementedError` when `minority_size != 0`; rest of the module byte-untouched (dead branch below the guard preserved, per the "do not rewrite" lock). WORKING §2 note added (`WORKING.md:210`). | |
| **N3** | **FIXED** | `analysis/common.py:32-46`: `_run_dvs(meta, meta_path)` derives the pickle path from the glob-found `meta_path` (`with_suffix` chain), no string reconstruction from `model_shorthand/topology/run_id`. Test: `test_analysis.py::test_sidecar_in_nonstandard_location_still_yields_pickle_dvs` (deliberately non-`run_paths` layout still yields pickle DVs). | |
| **N4** | **FIXED** | Grep for `options_set[0]` across all four CLIs: zero hits; single `orchestration.options(config)` source used by `run_one.py` and `build_run_config`. Falls out of M4-02 as planned. | |
| **N5** | **FIXED** | `dvs.py:96-101` (`flip`) and `dvs.py:146-151` (`time_to_flip`) raise `ValueError` when `len < t_start + window`; rationale in both docstrings. Tests: `test_dvs.py::test_flip_raises_on_tracker_shorter_than_t_start_plus_window`, `::test_flip_boundary_exact_length_does_not_raise` + the `time_to_flip` pair. | |
| **N6** | **FIXED** | `requirements.txt`: `networkx>=3.6,<4`, `PyYAML>=6.0.3,<7`, `munch>=4.0,<5` — verbatim IMPLEMENTATION_PLAN §7.2; Phase-F pins (`scipy>=1.14,<1.17`, `pygam==0.12.0`, `pandas>=2.2,<3`) untouched. | |
| **N7** | **FIXED** | `h3a.py:25` / `h3b.py:23`: `_FIT_EXCEPTIONS = (LinAlgError, PerfectSeparationError, ValueError)` — no bare `except Exception` remains in either module; exploratory JSON carries `reason` (`h3a.py:34,59,101,117`; `h3b.py:70,82,92`). Tests: both `::test_unexpected_exception_type_is_not_swallowed` tests assert a non-fit `TypeError`-class error propagates. | |

---

## Part 2 — New / remaining findings

### Blockers

| ID | Area | File:line | Issue | Methods ref |
| --- | --- | --- | --- | --- |
| **R2-B1** | H1/H2 dependent variable — wrong window + censored runs dropped | `convention_topology/analysis/common.py:54-56` (`_run_dvs`) | Two coupled defects in the confirmatory H1/H2 DV. **(a) Wrong window:** `dominant_share(tracker)` / `shannon_entropy(tracker)` are computed over the trailing 72 interactions of the **entire tracker**. For a completed run the tracker ends after Phase 2's 1000 post-CM interactions, so the "dominant share" H1/H2 actually test is the **end-of-Phase-2, post-committed-minority-injection** share — not "the trailing $3N=72$ interactions **at Phase 1 end**" that `03_Methods.tex:199` locks as "the primary Phase 1 outcome for H1 and H2". Runs that flip (or are mid-transition) at Phase 2's end feed perturbed shares into a hypothesis about *unperturbed convention emergence*. The correct window for eligible runs is `answers[:t_gate][-72:]` (exactly what `dvs.incumbent_label` already slices). **(b) Censored runs silently excluded:** the guard `if meta["run_status"] == "completed"` leaves `dominant_share=None` for censored runs, so dispatch's `.notna()` filter drops them — but `03_Methods.tex:212` locks "H1 and H2 pool **all attempted** Phase 1 trajectories" and `:246` "Gate-censored runs contribute Phase 1 outcomes". Censored runs are precisely the low-share, fragmented outcomes; dropping them inflates mean dominant share for exactly the sparse topologies most likely to censor, invalidating both the H1 level test and the H2 contrasts. For a censored run the correct window is simply the tracker's trailing 72 (Phase 1 is the whole tracker). Pre-existing since Phase F; **missed by R1** (its matrix checked test statistics and the 144 denominator, not window placement); not a remediation regression. Analysis-side only — collected pickles/sidecars are unaffected and DVs can be recomputed after the fix. | `03_Methods.tex:199,212,216,221,246`; WORKING §6 run-status table ("censored → Phase 1 DVs only (H1/H2)"), §8 H1/H2 rows |

### Major

| ID | Area | File:line | Issue |
| --- | --- | --- | --- |
| **R2-M1** | `code_commit` is cwd-dependent | `convention_topology/orchestration.py:30-37` (`get_code_commit`) | `subprocess.check_output(["git","rev-parse","--short","HEAD"])` runs in the process **cwd**, not the repo containing the code. Demonstrated live: invoked with cwd = the meta-repo root (`Master Thesis/`, itself a git repo), it returns the **meta-repo's** HEAD `dcd3472`, not this repo's `10912a6` — a wrong but plausible-looking pin, silently poisoning the exact reproducibility guarantee B2 was fixed to restore. From a non-repo cwd it returns `"unknown"` (correct fallback). The B2 integration tests can't catch this: the test runner's cwd is the repo. Fix is one argument: `subprocess.check_output([...], cwd=Path(__file__).resolve().parent)`. Until fixed, the operational caveat is: launch every CLI from the repo directory (the documented workflow already does). |

### Minor

| ID | Area | File:line | Issue |
| --- | --- | --- | --- |
| R2-m1 | H3a: near-linear truth yields non-confirmatory label | `analysis/h3a.py:85-92` | When the fitted GAM's edof ≤ 2 (spline collapses to ~linear), `lr_df_gam_vs_linear ≤ 0`, the LR test is skipped, and the whole H3a output is labeled `exploratory` — observed live on the mock batch (edof = 1.93). This matches FIX-B1-04 as written, but it conflates "GAM fit failed" with "the spline finds nothing beyond linear", which under Methods is an *informative* result about the size–flip shape (evidence toward linearity), not a degraded analysis. Risk: a genuinely steep/linear flip curve in the real study routinely produces a non-confirmatory primary H3a output. Consider a distinct label/`reason` (e.g. informative-null-linear) or documenting the interpretation in Methods notes before the pilot readout. |
| R2-m2 | Sensitivity-50 export format | `analysis/dispatch.py:52` | Writes `flip_agreement.json`; WORKING §8 locks `flip_agreement.csv` feeding Appendix `tab:appendix-flip-agreement`. Trivial format mismatch — align either side. |
| R2-m3 | Promised CSV/figure exports absent | `analysis/dispatch.py` (all runners); WORKING §8 header | WORKING §8 promises per-script "JSON (stats) + CSV (run-level table) + PDF figure to `outputs/{model}/`"; the pipeline writes only per-hypothesis JSON + `eligibility.csv`. `matplotlib` is pinned (§7.2 "F figures") but never imported by any analysis module. Presumably deferred to Results/notebook time — either implement or scope WORKING §8's promise down so the doc matches code before the pilot. |
| R2-m4 | Test false-confidence gap around R2-B1 | `tests/test_analysis.py`, `tests/test_dvs.py` | No test pins the H1/H2 DV *window semantics*: analysis tests feed pre-computed `dominant_share` columns (bypassing `_run_dvs`), and the one end-to-end fixture (`test_sidecar_in_nonstandard_location…`) uses an all-same-label tracker where Phase-1-end and Phase-2-end windows coincide. A fixture whose Phase 2 flips (different modal label after CM) would have caught R2-B1 — add it alongside the fix, plus a censored-run-contributes-to-H1 assertion. |

---

## Methods alignment matrix (fresh — re-derived from current code)

| Lock | Expected (cite) | Code location | Status |
| --- | --- | --- | --- |
| N=24, options {Q,M}, H=5, payoffs +100/−50, T=0.5 | Methods; WORKING design locks | `config.yaml` params block; threaded via `orchestration.build_run_config` | MATCH |
| Centola-3 topologies (complete, random_regular deg 4, 1D ring lattice deg 4) | Methods; WORKING | `networks.py:40-92`; `lattice_neighbours` (nearest + next-nearest) | MATCH |
| Stability gate ≥0.95 over trailing 3N=72 | Methods; WORKING | `gate.py:27-43` (`sum(recent) >= threshold * convergence_time`); `config.yaml` 0.95/72 | MATCH |
| Phase 1 cap 5000, censored semantics | Methods §Procedure:160 | `config.yaml`; `run.py:197-215` via `evaluate_phase1_gate` | MATCH |
| Phase 2 horizon 1000 post-gate | Methods; WORKING | `config.yaml total_interactions: 1000`; `run.py:258-262`, `simulation.py:run_phase2` | MATCH |
| CM: swap mode, k ∈ {1..6}, injected rng | Methods; WORKING | `simulation.py:66-76`; `run.py:232`; grid k cyclic (`orchestration.py:145-153`) | MATCH |
| CM agents make zero API calls | WORKING §4 | `simulation.py:123-125` short-circuit before client; `test_run_integration.py::test_all_committed_phase2_makes_zero_client_calls` | MATCH |
| Phase 2 option shuffle shared per interaction; Phase 1 per-agent | WORKING §2 (M1 lock, upstream fidelity) | `simulation.py:108-131`; `run.py:245` (`shared_shuffle=True` Phase 2 only) — cross-checked against `ashery-ai-norms/simulation_module.py:156` | MATCH |
| Run unit: sequential P1→P2 per (topology,k,seed,model), no prepared populations | WORKING §2/M03 | `run.py::execute_run`; no `set_initial_state`/prepared-population port exists | MATCH |
| 3× retry → `run_status=failed`, not auto-replaced | M03 | `llm.py::RetryPolicy`; `run.py:267-269`; `orchestration.run_batch`/`run_cell_targeted` re-attempt only with `--retry-failed` | MATCH |
| Sidecar schema (§6) incl. real `code_commit` | WORKING §6/§12; Appendix repro pins | `persistence.py::META_FIELDS`; `run.py::checkpoint`; `orchestration.get_code_commit` | MATCH from repo cwd; **cwd-dependent** (Major R2-M1) |
| `config_hash` excludes secrets | WORKING §6 | `config.py::config_hash`/`_strip_secrets`; `test_run_integration.py::test_api_key_env_value_irrelevant_to_hash` | MATCH |
| Flip: ≥0.95/3N **and** modal = committed_to; single non-flip category, no `flip_resisted` | Methods:184-185, 204-205 | `dvs.py::flip` (`dvs.py:77-105`); re-convergence-on-incumbent test | MATCH |
| Label-share denominator 144 (2×3N emissions) | Methods:199 (window def); WORKING §7 | `dvs.py::label_shares` (`denominator = 2 * window`, default 72) | MATCH |
| **H1/H2 dominant share = trailing 3N at Phase 1 end, all attempted runs incl. censored** | Methods:199, 212, 246 | `analysis/common.py:54-56` computes it over the **full tracker** (Phase 2 end) and **only for completed runs** | **MISMATCH** (Blocker R2-B1) |
| `flip_50` strict > at exactly 50%, noncommitted agents only | Appendix; WORKING §7 | `dvs.py::flip_50:128` (`> 0.5`); boundary test | MATCH |
| Time-to-flip censored at 1000 | Methods:206 | `dvs.py::time_to_flip` (`censor_value=1000`) | MATCH |
| Incumbent = modal at gate, lexicographic tie-break, single implementation | WORKING §7 (M2 lock) | `tracker.py::modal_lexicographic`; both production and `dvs` paths route through it | MATCH |
| H1: one-sample t vs τ=0.90 + Wilcoxon + 95% CI + descriptive regime proportion | Methods Table row H1 | `analysis/h1.py:18-52` | MATCH (test spec; input data affected by R2-B1) |
| H2: two one-tailed Welch (lattice<mixing, random<mixing), α=.05 each, no correction; Mann–Whitney; entropy descriptive | Methods Table row H2 | `analysis/h2.py` | MATCH (same R2-B1 caveat) |
| H3a: GAM `flip~s(cm_k)` vs. linear logistic, LR test, mixing primary | `03_Methods.tex:226-229`; WORKING §8 | `analysis/h3a.py:77-97` primary `lr_stat_gam_vs_linear` | MATCH (see Minor R2-m1 on the edof≤2 labeling) |
| H3b: interaction logistic + LR vs. main effects; confirmatory floor ≥2 topologies × ≥8/cell over the full k grid; informative-null framing | Methods:236-239 | `analysis/h3b.py`; zero-cell check (M3 fix) | MATCH |
| H4: descriptive incumbent frequencies (mixing) + optional χ² | Methods:240-242 | `analysis/h4.py`; dispatch filters mixing | MATCH |
| Llama primary confirmatory; cross-model descriptive, never pooled | Methods:243-244 | per-model dispatch (`--model` required); `cross_model.py` per-model dict, no pooling | MATCH |
| Pilot: 12 attempted/topology, k cyclic 1..6,1..6 | WORKING §5 | `orchestration.pilot_grid`; dry-run verified 36 rows | MATCH |
| Main study: eligible targets complete [15-20], lattice/random [8-10], attempted cap 3× | WORKING §5/M01 | `orchestration.cell_targets`/`run_cell_targeted`; dry-run verified | MATCH |
| Eligibility reporting (attempted/eligible/censored/failed by topology × model) | Methods:245-246 | `analysis/common.py::eligibility_table`; `outputs/{model}/eligibility.csv` | MATCH |

---

## Module audit (fresh)

Modules re-read in full this pass: `orchestration.py`, `analysis/dispatch.py`, `h3a.py`, `h3b.py`, `h1.py`, `h2.py`, `h4.py`, `cross_model.py`, `common.py`, `persistence.py`, `tracker.py`, `dvs.py`, `simulation.py`, `run.py`, `networks.py` (guard region), `gate.py`, `config.yaml`, all four CLIs. `llm.py`, `prompting.py`, `config.py`, `live/*` were untouched by remediation (confirmed against FIX_PLAN's file list) and spot-checked at API level only; R1's clean verdict stands for them.

| Module | Architecture check | Delta vs R1 |
| --- | --- | --- |
| `convention_topology/orchestration.py` **(new)** | Single home for RunConfig/client/retry construction + pilot grid/batch + main-study targeting; clean DI; broad `except` in `_worker` is deliberate and reports on-disk truth | Resolves R1 M4/B2; carries new Major R2-M1 (`get_code_commit` cwd) |
| `convention_topology/analysis/dispatch.py` **(new)** | All output writes via `persistence` writers (N1); per-model filtering correct; mixing filters for H1/H3a/H4 correct | Resolves R1 M4/N1; `flip_agreement.json` vs locked `.csv` (R2-m2); no figures (R2-m3) |
| `run_one.py` / `run_pilot.py` / `run_main.py` / `analyze.py` | Thin (argparse + one call); no cross-CLI imports; `run_one.py --smoke` retains its loop (pre-existing, out of M4 scope) | Resolves R1 M4/N4/B2 |
| `tracker.py` | Pure; single `modal_lexicographic` tie-break | Resolves R1 M2 |
| `dvs.py` | Pure; N5 guards in `flip`/`time_to_flip`; imports the shared tie-break | Resolves R1 M2/N5 |
| `simulation.py` | Pure core, fully DI'd; `shared_shuffle` faithful to both Ashery loops | Resolves R1 M1 |
| `run.py` | Composition unchanged; resume guards intact; Phase 2 gets `shared_shuffle=True` | OK |
| `persistence.py` | Sole writer incl. analysis outputs + artifact deletion | Resolves R1 N1 |
| `networks.py` | 3-line N2 guard; module otherwise untouched per lock | Resolves R1 N2 |
| `analysis/common.py` | Glob-path-derived pickle loading (N3 fixed) | **New Blocker R2-B1 lives here** (`_run_dvs` window + censored exclusion) |
| `analysis/h3a.py` / `h3b.py` | Primary GAM-vs-linear LR; full-grid confirmatory check; typed exceptions + `reason` | Resolves R1 B1/M3/N7; R2-m1 labeling nuance |
| `analysis/h1.py`/`h2.py`/`h4.py`/`cross_model.py` | Match locked tests; cross-model never pools | OK (H1/H2 inputs poisoned upstream by R2-B1) |
| `gate.py`, `llm.py`, `prompting.py`, `config.py`, `live/*` | Untouched by remediation; suite + smokes green | OK per R1 |

No TODO/FIXME comments in production code; the only `NotImplementedError`s are the two deliberate locks (`networks.py` minority_size guard, `run.py::_pick_committed_label` binary lock).

---

## Test coverage gaps

- **R2-m4 (new):** nothing pins the H1/H2 DV window (Phase 1 end vs. end of tracker) or censored runs' inclusion in H1/H2 — the gap that let R2-B1 survive both reviews' green suites. Add with the fix: (a) an `execute_run`-produced fixture whose Phase 2 flips, asserting the loaded `dominant_share` equals the *gate-window* share, not the flipped end-state; (b) a censored fixture asserting `dominant_share` is non-null and enters `run_h1`'s input.
- No test pins `get_code_commit()` behavior from a foreign cwd (would catch R2-M1); the existing tests run with cwd = repo and necessarily pass.
- Every FIX_PLAN-mandated test exists and genuinely asserts the locked behavior (checked each one's body, not just its name — see Part 1 evidence). The M2 integration test asserts agreement on a real run rather than a forced tie, acceptable given the shared single implementation plus per-path tie unit tests.
- Remaining soft gaps from R1 (Streamlit `main()` manual-smoke-only, `live/monitor.py` 69% file coverage) unchanged; the 85% aggregate gate holds at 91%.

---

## Documentation gaps

- `WORKING.md` §2 (M1 shuffle row + N2 note) and §12 (commit-pin staleness warning) updated as planned; `IMPLEMENTATION_PLAN.md` §0/§5/§7.9 updated (corrected H3a lock at line 587, module inventory + test-matrix rows for `orchestration.py`/`dispatch.py`); `README.md` status rows + remediation pointer updated; R1 report carries the remediation table. All FIX-DOC items verified present.
- **Remaining:** WORKING §8's promised per-script CSV/PDF-figure exports don't exist (R2-m3) and `flip_agreement.csv` is written as `.json` (R2-m2). `WORKING.md` "Last updated: 2026-07-13" header and the §1 module-status table (still showing `☐`/`✅ partial` for long-completed modules) are stale relative to the session log below them — cosmetic.
- WORKING §13 #2 (missing `asheryAINormsZenodo2024` bib entry) is still open in the thesis-writing repo — unchanged, out of scope here.

---

## Ashery port spot-checks

R1's ten-row port audit re-confirmed where remediation touched it; unchanged rows spot-checked, not re-derived:

| File::symbol | Verdict |
| --- | --- |
| `simulation_module.py::committed` → `make_interaction_step(shared_shuffle=True)` | **OK now** — upstream re-read this pass: `committed()` shuffles once per interaction *before* p1/p2 selection (`simulation_module.py:156-161`); thesis Phase 2 step reproduces exactly that ordering (R1 M1 resolved) |
| `simulation_module.py::population` → Phase 1 step (per-agent shuffle) | OK — default `shared_shuffle=False` preserves upstream `population()` semantics |
| `utils.py::swap_committed` → `simulation.py::swap_committed` | OK — swap mode, injected rng (documented deviation) |
| `utils.py::get_outcome`/`update_dict`/`update_tracker` → `tracker.py` | OK — verbatim incl. `outcome > 5` success rule |
| `prompting.py::get_rules`/`get_prompt` → `prompting.py` | OK per R1 (untouched by remediation; golden fixtures still green in suite) |
| `run_API.py` retry (infinite) → `RetryPolicy` (3×) | OK — locked deviation |

---

## R1 → R2 delta

- **Improved:** all 13 R1 findings correctly remediated, with regression tests that genuinely assert the locked behaviors; test suite 121 → 146; the two R1 Blockers are gone — H3a now computes the Methods-locked GAM-vs-linear LR as primary, and live batch sidecars record the real git commit; Phase 2 shuffle restored to upstream fidelity and documented; thin-CLI architecture now literally true for pilot/main/analyze; single-writer principle extended to analysis outputs and deletions.
- **Newly discovered:** one Blocker — R2-B1, the H1/H2 dominant-share/entropy window is taken at Phase 2 end (post-CM) instead of Phase 1 end, and censored runs are dropped from H1/H2 against the Methods pooling lock (pre-existing since Phase F, missed by R1); one Major — R2-M1, `get_code_commit()` records whatever repo the process cwd is inside (demonstrated: meta-repo hash `dcd3472`); four Minors (H3a edof≤2 labeled exploratory rather than informative-linear; flip-agreement JSON-vs-CSV; promised CSV/figure exports absent; missing window-semantics tests).
- **Still open:** the entire implementation remains uncommitted — `WORKING.md` §12's pin (`10912a6`) predates everything reviewed here, exactly as in R1; C-05 real-API smoke and G-03/G-04 freeze remain correctly blocked on Doug D1/D2 and real data. Doug D1–D6 all still `open` (checked `01_Orga/Doug_Open_Questions.md` this pass).

---

## Recommended next actions

1. **Fix Blocker R2-B1** (`analysis/common.py::_run_dvs`): compute `dominant_share`/`shannon_entropy` over the Phase-1-end window — `tracker["answers"][:t_gate][-72:]` for eligible runs, full-tracker trailing 72 for censored runs — and include censored runs (drop the `== "completed"` guard for these two DVs). Add the two window-semantics tests from "Test coverage gaps".
2. **Fix Major R2-M1**: pin `get_code_commit()`'s subprocess to the package directory (`cwd=Path(__file__).resolve().parent`); add a foreign-cwd test using a tmp git repo.
3. **Commit the implementation** and refresh `WORKING.md` §12's commit pin — precondition for any sidecar's `code_commit` being a meaningful anchor for the pilot (unchanged R1 action, still the gating step before real data collection).
4. Decide the H3a edof≤2 semantics (R2-m1) before the pilot readout — informative-null-linear vs. exploratory — and document the choice in WORKING §8/IMPLEMENTATION_PLAN §7.9.
5. Align the sensitivity-50 export with the lock (`flip_agreement.csv`, R2-m2) and either implement or descope WORKING §8's per-script CSV/figure promise (R2-m3).
6. Then proceed to the real-API smoke (C-05) once Doug's model strings/provider access land — no code-side blocker remains for it beyond items 1–3.

---

## Remediation status (2026-07-14, per `FIX_PLAN_R2.md`)

All pure-code findings fixed in this working tree (uncommitted — see commit-pin note above). 150 tests green (up from 146), coverage maintained at 91% (≥85% gate). **R2-m1 (H3a edof≤2 labeling) reviewed with the user and intentionally left as-is** — `exploratory` is the correct label for now per explicit decision; not a defect.

| Finding | Status | Notes |
| --- | --- | --- |
| R2-B1 | fixed | `analysis/common.py::_phase1_end_tracker` slices the tracker to `[:t_gate]` before computing `dominant_share`/`shannon_entropy` (Phase-1-end window, not the raw tracker tail); censored runs now included (`run_status in ("completed","censored")` gates the DV, matching Methods:212/246). New tests: `test_analysis.py::Phase1WindowDVTests` (window-discrimination + censored-inclusion fixtures) |
| R2-M1 | fixed | `orchestration.py::get_code_commit` pins `cwd=_REPO_ROOT` (`Path(__file__).resolve().parent.parent`); demonstrated live from the meta-repo root now returns `10912a6` (this repo), not `dcd3472` (meta-repo). New test: `test_orchestration.py::test_get_code_commit_ignores_process_cwd` (tmp git repo, chdir, asserts result is *this* repo's HEAD) |
| R2-m1 | not a defect (user decision, 2026-07-14) | Keep `exploratory` label for GAM-collapses-to-linear (edof≤2) — no code change |
| R2-m2 | fixed | `analysis/dispatch.py::run_h3a` writes `flip_agreement.csv` via `write_analysis_csv`, not `.json`. New test: `test_analysis.py::test_sensitivity_50_exports_csv_not_json` |
| R2-m3 | partially fixed | CSV run-level table now exported per hypothesis (`h1.csv`…`h4.csv`) alongside each JSON, closing the WORKING §8 CSV promise. **PDF figures intentionally deferred** to Results/real-data time — premature to generate now; WORKING §8's figure promise remains open by design, not a code gap |
| R2-m4 | fixed | Folded into R2-B1's new tests — the exact window/censored-inclusion coverage gap the report named |

Verified live: full pilot batch (`run_pilot.py --model mock`, 36/36 completed) → `analyze.py --all --model mock --sensitivity-50` → `outputs/mock/` now contains `h1..h4.{json,csv}`, `eligibility.csv`, `flip_agreement.csv` (no `.json` variant); H1's `dominant_share` values now cluster consistently (~0.98) across mixing runs — a plausible, uniform Phase-1-window statistic, unlike the pre-fix mixture of Phase-1/Phase-2-tail values.
