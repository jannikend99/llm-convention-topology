# Code review — llm-convention-topology

**Date:** 2026-07-14 · **Commit:** `10912a6` (working tree has all Phase A–G implementation uncommitted — see note below) · **Plan progress:** 43/46 ✅ (0 ☐, 3 ⏸)

**Note on commit hash:** the codebase's implementation (Phases A–G, ~55 files) is currently **uncommitted** in the working tree. `10912a6` is the last commit on disk (`Document label-conditioned flip success rule in README.`, 2026-07-10) — it predates the entire implementation reviewed here. This matters directly: see Blocker #2 below (`code_commit` sidecar field).

---

## Executive summary

- **No-ship for the pilot as-is.** One Blocker (H3a's implemented statistical test does not match the test locked in both `03_Methods.tex` and `WORKING.md` §8) means H3a results would answer a different question than the one the thesis claims to test. Must fix before any real data collection that will be used for H3a inference.
- **Second Blocker:** `code_commit` is hardcoded to the literal string `"pilot"` for every pilot/main-study run (`run_pilot.py:88`, inherited by `run_main.py`) instead of the real git commit — breaks the reproducibility guarantee promised in Appendix `tab:appendix-repro-pins` and WORKING §12 for all non-`run_one.py` runs, i.e. for the entire actual pilot and main study.
- **Everything else checked out clean:** all other Methods/WORKING locks (gate 0.95/72, Phase 1 cap 5000, Phase 2 horizon 1000, CM swap zero-API-call, 3x-retry, flip taxonomy incl. no `flip_resisted`, 144-emission denominator, flip_50 strict->0 at exactly 50%, pilot cyclic-k grid, main-study eligible-count targeting) match, with code citations, in the alignment matrix below.
- **121 tests green, 92% coverage** (gate ≥85%); all CLI smoke commands (`run_one.py --smoke`, `run_pilot.py --dry-run`/full batch, `analyze.py --all`, `run_main.py --dry-run`) run clean offline; secrets grep empty.
- **One undocumented Ashery-fidelity deviation:** Phase 2's option shuffle is per-agent (matches Ashery's `population()`) where upstream's `committed()` shuffles once per interaction shared by both players — real, silent, not in WORKING's locked-deviations table.
- **Architecture-doc violations are real but low-risk:** CLIs (`run_pilot.py`, `run_main.py`, `analyze.py`) hold more orchestration logic than the "thin CLI" principle states, and `analyze.py`/retry-cleanup paths write/delete files outside `persistence.py`. None of these corrupt data or break reproducibility on their own — flagged as Minor/nits, not Blockers.

---

## Verification results

| Command | Result | Note |
| --- | --- | --- |
| `python -m unittest discover -s tests -v` | ✅ pass | 121 tests, 0 failures |
| `coverage run ... && coverage report --fail-under=85` | ✅ pass | 92% on `convention_topology/` + `live/` |
| `git grep -iE "sk-\|api[_-]?key.*=" ...` | ✅ pass | empty — no committed secrets |
| `git log -1` / `git rev-parse --short HEAD` | ✅ ran | `10912a6`, 2026-07-10 (predates uncommitted implementation) |
| `run_one.py --model mock ... --smoke` | ✅ pass | 5 parsed labels, model_id + endpoint logged |
| `run_pilot.py --model mock --dry-run` | ✅ pass | 36 rows, correct cyclic k |
| `run_pilot.py --model mock` (full batch) | ✅ pass | exit 0, 36/36 completed |
| `analyze.py --all --model mock` | ✅ pass | exit 0, h1–h4 JSON + eligibility.csv written |
| `run_main.py --model mock --dry-run` | ✅ pass | 18 rows, correct [15-20]/[8-10] targets |

---

## Findings

### Blockers (must fix before pilot)

| ID | Area | File:line | Issue | Methods ref |
| --- | --- | --- | --- | --- |
| B1 | H3a statistical test | `convention_topology/analysis/h3a.py:33-41` | Code computes an LR test of **linear logistic vs. intercept-only** (`null_fit = sm.Logit(y, np.ones((n,1)))`). Both `03_Methods.tex:53` ("likelihood-ratio test linear vs. spline") and `WORKING.md:385` ("LR test vs. linear logistic" — i.e. GAM-vs-linear) lock a **GAM vs. linear** comparison. A `LogisticGAM` is fit (lines 45-54) but its deviance is never compared against the linear fit — the locked nonlinear-vs-linear test is not computed anywhere in code. `IMPLEMENTATION_PLAN.md:585`'s "Practical H3a lock" note is the apparent root cause: it documents linear-vs-intercept as the primary contrast, which itself contradicts WORKING.md's own §8 table one file over. Per this review's stated priority (Methods LaTeX + WORKING > IMPLEMENTATION_PLAN), the code must implement GAM-vs-linear as the primary LR test; linear-vs-intercept may still be reported as a secondary/simpler descriptive if desired, but cannot stand in for the locked test. | `03_Methods.tex:53`; `WORKING.md:385` |
| B2 | Reproducibility sidecar field | `run_pilot.py:88` (`_build_run_config`, `code_commit="pilot"`), inherited unchanged by `run_main.py` (imports `_build_run_config`) | Every pilot and main-study run's `.meta.json` records the literal string `"pilot"` in `code_commit` instead of the actual git HEAD hash. `run_one.py::_code_commit()` (`run_one.py:34-40`) correctly shells out to `git rev-parse --short HEAD`, but `run_pilot.py`/`run_main.py` never call it. This silently breaks the Appendix `tab:appendix-repro-pins` / WORKING §12 promise that every run sidecar pins the exact commit that produced it — for every run except manual single-run debugging via `run_one.py`, which is not how pilot/main-study data will actually be collected. | WORKING.md §12; Appendix `tab:appendix-repro-pins` |

### Major (should fix before main study)

| ID | Area | File:line | Issue |
| --- | --- | --- | --- |
| M1 | Ashery port fidelity | `convention_topology/simulation.py:113-116` vs. `ashery-ai-norms/simulation_module.py:156` | Phase 2's `make_interaction_step` reshuffles options independently per agent (matches Ashery `population()`, correct for Phase 1). Ashery's `committed()` (Phase 2) shuffles **once per interaction**, shared by both players, *before* `p1`/`p2` are even chosen. The thesis reuses the same `make_interaction_step` for both phases, silently changing Phase 2's shuffle granularity from upstream. Not listed in WORKING.md's "Locked thesis deviations from upstream" table (WORKING.md:196-207). Either document as an explicit deviation or reconcile to match Ashery's shared-shuffle-per-interaction Phase 2 semantics. |
| M2 | Incumbent tie-break inconsistency | `convention_topology/tracker.py:50-60` (`modal_label_in_window`, used by `run.py::execute_run` for the actual `incumbent_label`/`committed_to` written to `meta.json`) vs. `convention_topology/dvs.py:58-63` (`incumbent_label`, lexicographic tie-break, tested in `test_dvs.py::test_tie_break_is_lexicographic`) | Two different tie-break rules for "modal label in a window" exist in the codebase. The one that actually determines the real experimental treatment (which label is incumbent, which becomes `committed_to` for a run) uses `Counter.most_common()` insertion-order tie-break, **not** the lexicographic rule WORKING §7 documents and `dvs.py` implements. On an exact tie at gate time, the real run and `dvs.py`'s independent recomputation could disagree. `dvs.incumbent_label()` is currently dead code in the production path (real pipeline reads `incumbent_label` straight from `meta.json`), but its only test verifies a rule the actual run-time code doesn't follow — reproducibility-relevant if any future code path routes through it, and worth reconciling now while it's cheap. |
| M3 | H3b confirmatory auto-label blind spot | `convention_topology/analysis/h3b.py:35-40` (`_is_confirmatory`) | `cell_counts = df.groupby(["topology","cm_k"]).size()` only sees `(topology, cm_k)` pairs that have **at least one row**. A cell with **zero** eligible runs (e.g. every seed in that cell censored/failed) is invisible to the `.groupby()` result, so `(cell_counts >= MIN_CELL_N).all()` can still be `True` even though an entire cell is empty — `h3b_analysis` would label the result `"confirmatory"` despite a structurally missing cell, a stronger and false claim relative to "some cells underfilled." Needs an explicit check over the full expected `(topology, cm_k)` grid, not just observed groups. |
| M4 | CLI orchestration logic depth | `run_pilot.py` (`pilot_grid`, `run_cell`, `run_batch`, incl. `ThreadPoolExecutor` dispatch and resume/retry filtering), `run_main.py` (`cell_targets`, `run_cell_targeted` — the entire eligible-count targeting loop), `analyze.py` (`run_h1`...`run_h4`, `run_cross_model`, DataFrame filtering + JSON/CSV writing) | IMPLEMENTATION_PLAN.md §0 principle 6 states CLIs should be "argument parsing + one call into orchestration." All three files hold substantial business logic directly. This does not currently cause a functional bug (the logic is well-tested via direct import in `tests/test_orchestration.py`/`tests/test_analysis.py`, satisfying the *spirit* — testable without subprocess — even though it violates the letter), but it means `convention_topology/run.py`/`analysis/common.py` are not the single home for this orchestration, raising future-maintenance risk (e.g. finding B2 above is exactly the kind of duplication this invites: `run_pilot.py` and `run_one.py` each independently build `RunConfig`/clients). Consider moving grid/targeting/dispatch logic into `convention_topology/` modules, leaving the CLIs as thin wrappers. |

### Minor / nits

| ID | Area | File:line | Issue |
| --- | --- | --- | --- |
| N1 | Single-writer principle | `analyze.py:26-29` (`_write_json`), `analyze.py:80` (`table.to_csv`), `run_pilot.py:168-169` / `run_main.py:83-84` (direct `paths.meta_path.unlink()`/`paths.pickle_path.unlink()` for retry-failed cleanup) | IMPLEMENTATION_PLAN §0 principle 3 states `persistence.py` is the only file-writing module. `outputs/` exports and retry-cleanup unlinks bypass it. Low risk in practice (`outputs/` is a distinct write-once export tree not read by any live process; unlinks are `missing_ok=True` and target only already-failed runs), but worth either relaxing the stated rule's scope explicitly (run-artifact writes only) or centralizing these operations in `persistence.py` for consistency. |
| N2 | Dead-code random non-determinism | `convention_topology/networks.py:82` (`get_interaction_network`'s `minority_size` path uses module-level `random.sample`) | Already flagged and consciously left as-is in the prior code-review pass (2026-07-14): `networks.py` is locked "do not rewrite," and the path is currently unreachable from `execute_run` (which always calls with `minority_size=0`; committed-minority assignment goes through `simulation.py::swap_committed`'s injected-rng path instead). Re-flagging here only because it surfaced independently in two of this review's agents — no new action needed unless `minority_size` is ever wired up again. |
| N3 | `analysis/common.py` path reconstruction | `convention_topology/analysis/common.py:38` (`_run_dvs`) | Rebuilds `meta_path`/`pickle_path` from `data_dir/model_shorthand/topology/run_id` components instead of reusing the path `scan_meta_paths` (`**/*.meta.json` glob) actually found. Currently safe because `persistence.py::run_paths` always writes to exactly that layout, but it's a tight-coupling smell — a run whose sidecar lives anywhere else (recovered file, future layout change) silently vanishes from all pickle-derived DVs with no error surfaced. |
| N4 | `run_main.py` config-accessor duplication | `run_main.py:86` | Inlines `list(config.params.options_set[0])` instead of calling `run_pilot.py`'s `_options(config)`, even though `_build_run_config` (called two lines later) internally does call it. Currently produces the same value; a future change to `_options()` (e.g. validation/reordering) would desynchronize the client's option list from `RunConfig`'s. |
| N5 | `dvs.py` no minimum-length guard | `convention_topology/dvs.py:85-102` (`flip`), `128-145` (`time_to_flip`) | No check that `len(tracker["answers"]) >= t_start + window`. With the thesis-locked `phase2_horizon=1000 >> window=72` this is unreachable in practice, but a non-default/misconfigured run with a short Phase 2 would silently return `flip=0` / `time_to_flip=censor_value` — indistinguishable from a genuine non-flip rather than "no valid window existed." Low priority given current locked config, but cheap to guard. |
| N6 | Loose dependency pins | `requirements.txt`: `networkx>=3.0`, `PyYAML>=6.0`, `munch>=4.0` | IMPLEMENTATION_PLAN §7.2 documents `networkx>=3.6,<4`, `PyYAML>=6.0.3,<7`, `munch>=4.0,<5` (all pre-existing, not touched this session). Installed ranges are looser (no upper bound, lower floor) than documented. The three critical Phase-F pins (`scipy>=1.14,<1.17`, `pygam==0.12.0`, `pandas>=2.2,<3`) are correct. |
| N7 | Broad `except Exception` in analysis fits | `convention_topology/analysis/h3a.py:40,52`, `h3b.py:59` | Statsmodels/pygam fit failures on tiny/degenerate n are caught with bare `except Exception` rather than a typed exception, in tension with IMPLEMENTATION_PLAN §0 principle 5's "errors are typed" intent — though the comments correctly note these are expected-not-fatal small-n conditions, not silently swallowed logic errors. |

---

## Methods alignment matrix

| Lock | Expected (cite) | Code location | Status |
| --- | --- | --- | --- |
| N=24, options {Q,M}, H=5 | Methods §Experimental Setup; WORKING design locks | `config.yaml:11,16,15`; `RunConfig` via `run_pilot.py:57-58,71` | MATCH |
| Centola-3 topologies (mixing, random-regular deg4, 1D ring lattice deg4) | Methods; WORKING design locks | `convention_topology/networks.py:22-29,42-86` | MATCH |
| Stability gate >=95% over trailing 3N=72 | Methods; WORKING §gate | `convention_topology/gate.py:27-43` (locked, unchanged) | MATCH |
| Phase 1 cap 5000, censored semantics | Methods; WORKING design locks | `convention_topology/simulation.py:37-38`; `run.py:198-215` | MATCH |
| Phase 2 horizon 1000 | Methods; WORKING design locks | `run.py:257-261`; `config.yaml:9` | MATCH |
| Committed minority: swap mode, k in {1..6} | Methods; WORKING design locks | `simulation.py:66-76`; `config.yaml:5`; `run_pilot.py:42-50` | MATCH |
| CM agents make NO API call | Methods; WORKING §4 | `simulation.py:109-112` | MATCH |
| Run unit: sequential Phase1->Phase2 per (topology,k,seed,model), no prepared-population shortcut | Methods; WORKING §2, M03 lock | `run.py::execute_run`, `run.py:104-271` | MATCH |
| 3x retry -> `run_status=failed`, not auto-replaced | Methods; WORKING §4 | `llm.py::RetryPolicy` (`llm.py:72-106`); `run.py:266-268`; `run_pilot.py` `--retry-failed` gating | MATCH |
| Sidecar metadata fields (§6) | Appendix; WORKING §6 | `persistence.py::META_FIELDS` (`persistence.py:77-101`) | MATCH (fields present; see Blocker B2 for `code_commit` content bug) |
| `config_hash` excludes secret fields | WORKING §6 | `config.py::config_hash`, `_SECRET_FIELDS={"api_key_env"}` (`config.py:18,79-95`) | MATCH |
| Flip: >=0.95 success AND modal=committed_to; no `flip_resisted` | Methods; WORKING §7, R2 lock | `dvs.py::flip` (`dvs.py:85-102`) | MATCH |
| Label-share denominator = 144 (2x3N) | Methods; WORKING §7 | `dvs.py::label_shares`, `DEFAULT_WINDOW=72` (`dvs.py:17,30-39`) | MATCH |
| `flip_50` boundary: exactly 50% -> 0 (strict >) | Appendix; WORKING §7 | `dvs.py::flip_50` (`dvs.py:105-125`) | MATCH |
| Incumbent label: modal at gate, deterministic lexicographic tie-break | WORKING §7 | `dvs.py::incumbent_label` (lexicographic, `dvs.py:58-63`) vs. `tracker.py::modal_label_in_window` (insertion-order, actually used by `run.py`) | **MISMATCH** (Major M2) |
| H1: one-sample t vs tau=0.90 + Wilcoxon + 95% CI + regime proportion | Methods Table; WORKING §8 | `analysis/h1.py::h1_analysis` (`h1.py:18-52`) | MATCH |
| H2: two one-tailed Welch, no correction, + Mann-Whitney, entropy descriptive | Methods Table; WORKING §8 | `analysis/h2.py` (`h2.py:18-42,54-72`) | MATCH |
| H3a: GAM + LR test vs. linear (mixing primary) | Methods Table row H3a (`03_Methods.tex:53`); WORKING §8 (`WORKING.md:385`) | `analysis/h3a.py::h3a_analysis` (`h3a.py:33-41` computes linear-vs-null instead) | **MISMATCH** (Blocker B1) |
| H3b: interaction logistic + confirmatory/exploratory auto-label per >=2 topologies x >=8/cell | Methods Table; WORKING §8 | `analysis/h3b.py::h3b_analysis` (`h3b.py:35-68`) | MATCH, with edge-case gap (Major M3) |
| H4: descriptive incumbent frequencies + optional chi-square | Methods Table; WORKING §8 | `analysis/h4.py::h4_analysis` | MATCH |
| Llama-3.1-70B primary confirmatory; cross-model descriptive only, never pooled | Methods; WORKING §8 | `analyze.py` per-model dispatch; `analysis/cross_model.py::cross_model_summary` | MATCH |
| Pilot: 12 attempted/topology, k cyclic 1..6,1..6 | Methods; WORKING §5 | `run_pilot.py::pilot_grid` (`run_pilot.py:42-50`) | MATCH |
| Main study: eligible targets (mixing 15-20, lattice/random 8-10), attempted cap 3x target | Methods; WORKING §5 | `run_main.py::cell_targets` (`run_main.py:26-43`); `config.yaml:22-23` | MATCH |
| Appendix reproducibility fields populated per run | Appendix; WORKING §12 | `persistence.py::META_FIELDS`, written in `run.py::execute_run::checkpoint` | MATCH structurally; **content bug** for `code_commit` on pilot/main runs (Blocker B2) |

---

## Module audit

| Module | Public API | Purpose | Architecture check |
| --- | --- | --- | --- |
| `convention_topology/prompting.py` | `get_rules`, `build_messages`, `PROMPT_TEMPLATE_VERSION` | Ashery prompt port (H=5 windowed history -> chat messages) | OK — pure |
| `convention_topology/llm.py` | `LLMClient`, `LLMResponse`, `parse_label`, `RetryPolicy`, `OpenAICompatClient`, `MockLLMClient`, `OPENAI_RETRY_EXCEPTIONS` | LLM boundary: parsing, retry, real + mock clients | OK — boundary module, DI-compliant (`sleep`, `rng` injected) |
| `convention_topology/tracker.py` | `get_outcome`, `update_dict`, `update_tracker`, `modal_label_in_window`, `empty_tracker` | Per-interaction bookkeeping | OK — pure. Tie-break behavior flagged in M2 |
| `convention_topology/gate.py` | `GateResult`, `has_tracker_converged`, `evaluate_phase1_gate` | Phase 1 stability gate (locked, not rewritten) | OK — pure |
| `convention_topology/networks.py` | `lattice_neighbours`, `adjacency_hash`, `get_interaction_network` | Centola-3 network construction | Minor violation N2 (dead code path) |
| `convention_topology/simulation.py` | `run_phase1`, `run_phase2`, `swap_committed`, `make_interaction_step` | Phase 1/2 interaction loops | OK — pure core, fully DI'd. Ashery fidelity gap M1 (Phase 2 shuffle granularity) |
| `convention_topology/run.py` | `RunConfig`, `execute_run` | Orchestrates init->Phase1->gate->CM->Phase2->finalize | OK — composes core + boundaries correctly |
| `convention_topology/persistence.py` | `build_run_id`, `run_paths`, `save_run_pickle`/`load_run_pickle`, `write_meta`/`read_meta`, `EventWriter` | Single-writer run artifact I/O | OK — sole writer as designed for run artifacts (see N1 for `outputs/`/analysis scope) |
| `convention_topology/config.py` | `load_config`, `resolve_model`, `config_hash`, `derive_seeds` | Config loading, registry, hashing, seeding | OK |
| `convention_topology/dvs.py` | `label_shares`, `dominant_share`, `shannon_entropy`, `flip`, `flip_50`, `time_to_flip`, `incumbent_label`, `rounds_to_gate` | Post-hoc dependent variables | OK — pure. See M2, N5 |
| `convention_topology/analysis/common.py` | `load_run_table`, `eligibility_table`, `critical_mass` | Run-table loader + aggregation | OK. See N3 |
| `convention_topology/analysis/h1.py` / `h2.py` / `h3a.py` / `h3b.py` / `h4.py` | `h1_analysis`, `h2_analysis`, `h3a_analysis`+`sensitivity_50_agreement`, `h3b_analysis`, `h4_analysis` | Per-hypothesis statistical tests | h1/h2/h4 OK; h3a **Blocker B1**; h3b Major M3; both use broad `except Exception` (N7) |
| `convention_topology/analysis/cross_model.py` | `cross_model_summary` | Descriptive-only cross-model comparison | OK — never pools |
| `live/reader.py` | `read_events`, `scan_sidecars`, `runs_dataframe`, `events_dataframe`, `load_dashboard_state` | Shared read-only data layer | OK — read-only, tolerant of torn writes |
| `live/monitor.py` | `main`, `build_layout` | Rich terminal dashboard | OK (soft: table-building logic embedded in CLI file, documented/tested) |
| `live/web.py` | `kpi_frame`...`cost_frame`, `main` | Streamlit dashboard, 6 panels | OK — frame builders pure & tested; `main()` manual-smoke-only |
| `live/cost.py` | `estimate_cost_usd`, `cost_summary` | Token/cost aggregation | OK |
| `run_one.py` | `main`, `run_smoke`, `run_full` | Single-run CLI | Soft violation (business logic beyond argparse), correct `code_commit` |
| `run_pilot.py` | `pilot_grid`, `run_batch`, `main` | Pilot batch CLI | Major M4 (orchestration depth); root cause of Blocker B2 |
| `run_main.py` | `cell_targets`, `run_cell_targeted`, `main` | Main-study targeting CLI | Major M4; inherits B2 via `run_pilot._build_run_config`; N4 |
| `analyze.py` | `run_h1`...`run_h4`, `run_cross_model`, `main` | Analysis dispatch CLI | Major M4; N1 (direct file writes) |

No `NotImplementedError` stubs found in production paths (only the deliberately-guarded 2-option binary lock in `run.py::_pick_committed_label`). No TODO/FIXME comments anywhere in `convention_topology/`, `live/`, or top-level CLIs.

---

## Test coverage gaps

No test-matrix row from `IMPLEMENTATION_PLAN.md` §5 is missing a corresponding test file; all 9 files under `tests/` exist and are appropriately sized (121 tests total). All IMPLEMENTATION_PLAN §0 branch-critical paths are explicitly covered:

- Parser malformed/ambiguous — `test_llm.py::ParseLabelTests`
- Retry-policy 3-attempt exhaustion — `test_llm.py::RetryPolicyTests::test_exhausts_exactly_three_attempts_then_raises`
- Flip taxonomy 50%-boundary + re-convergence-on-incumbent — `test_dvs.py::Flip50Tests`, `FlipTests::test_re_convergence_on_incumbent_is_not_a_flip`
- Resume-from-checkpoint (incl. the post-Phase-2 double-`swap_committed` regression) — `test_run_integration.py::ExecuteRunTests::test_resume_from_checkpoint_does_not_replay_completed_phase1`, `test_resume_after_phase2_start_does_not_re_swap_committed`
- Committed-minority zero-API-call guarantee — `test_run_integration.py::InteractionStepTests::test_all_committed_phase2_makes_zero_client_calls`

**New gap found by this review:** no test exercises `code_commit` on a `run_pilot.py`/`run_main.py`-produced sidecar (would have caught Blocker B2), and no test compares `dvs.incumbent_label()`'s output against the `meta.json` `incumbent_label` actually produced by a real run (would have caught Major M2). Neither H3a's GAM-vs-linear LR nor H3b's zero-cell blind spot (M3) has a fixture testing that specific scenario.

---

## Documentation gaps

- `README.md`: "Implementation status" table and "Status" section accurately reflect Phases A–G complete, deferred items correctly noted, links to WORKING.md/IMPLEMENTATION_PLAN.md present. No stale claims found.
- `WORKING.md` §12 "Reproducibility hooks": thesis repo commit pin (`10912a6`) and Ashery submodule pin (`e57aeef`) both match actual git state — consistent, but see the header note above: `10912a6` predates the uncommitted implementation reviewed here, so this pin will need updating once the work is committed, before it's trustworthy as a "current value."
- WORKING.md's locked-deviations table (§2) does not document the Phase 2 option-shuffle granularity change from Ashery (Major M1) — should be added if the deviation is intentional, or fixed if not.
- `IMPLEMENTATION_PLAN.md:585`'s "Practical H3a lock" note conflicts with `WORKING.md:385`'s own H3a spec one file over, and is the apparent origin of Blocker B1 — worth correcting once B1 is fixed in code, so the plan doesn't reintroduce the same bug on a future edit.

---

## Ashery port spot-checks

| File::symbol | Destination | Action (WORKING §2) | Verdict |
| --- | --- | --- | --- |
| `prompting.py::get_rules` | `prompting.py::get_rules` | adapt | OK — verbatim rule text, documented header-token strip |
| `prompting.py::get_prompt` | `prompting.py::build_messages` | adapt | OK — H=5 windowing, off-by-design round numbering (`idx+2`), response format all verbatim |
| `utils.py::get_outcome` / `update_dict` / `update_tracker` | `tracker.py` | adopt | OK — verbatim semantics incl. `outcome>5` success rule |
| `utils.py::swap_committed` | `simulation.py::swap_committed` | adopt | OK — swap mode preserved; rng injected (documented deviation) |
| `simulation_module.py::population` | `simulation.py::make_interaction_step` (Phase 1) | reimplement | OK — random agent/neighbour, per-agent shuffle, CM n/a in Phase 1 |
| `simulation_module.py::committed` | `simulation.py::make_interaction_step` (Phase 2, reused) | reimplement | **Issue** — shuffle granularity diverges from Ashery, undocumented (Major M1) |
| `utils.py::get_interaction_network` | `networks.py::get_interaction_network` | adapt | OK — lattice added, scale_free/ER dropped, seeded random_regular, `adjacency_hash` new |
| `utils.py::has_tracker_converged` | `gate.py::has_tracker_converged` | adapt | OK — threshold parameterized, 0.95 vs Ashery's 1.0 (documented) |
| `run_API.py::query`/`get_response` | `llm.py::OpenAICompatClient`+`parse_label` | reimplement | OK — quote-split-derivative parsing, matches D6 working assumption (Ashery-parse path, not structured output) |
| `run_API.py` retry (infinite) | `llm.py::RetryPolicy` (3x) | reimplement | OK — matches M03-locked deviation exactly |

---

## Open decisions (non-blocking, note only)

- **Doug D1–D6** (all `open` in `01_Orga/Doug_Open_Questions.md`, last updated 2026-07-13): model strings for GPT-5.4/Claude 5.5 (D1), API budget/provider access (D2), overall methodology sign-off (D3), CM eligibility contingency (D4), expected gate rates (D5), structured output vs. Ashery parsing (D6 — code correctly implements the "default" working assumption, Ashery-parse path, pending Doug confirmation).
- **WORKING §13 blockers** #1 (GPT-5.4/Claude 5.5 model strings) and #3 (hosted-inference provider for Llama/Qwen) both correctly gate only the deferred C-05 real-API smoke and real data collection — do not block any code path in the one-shot offline build, consistent with code (`config.py::resolve_model` fails fast on `TBD-doug` placeholders).
- **WORKING §13 blocker #2** (Zenodo bib key `asheryAINormsZenodo2024` missing from `literature.bib`) is a thesis-writing-repo issue, out of scope for this codebase; correctly not touched here.

---

## Recommended next actions

1. **Fix Blocker B1** — implement the GAM-vs-linear LR test in `h3a.py` per `03_Methods.tex`/`WORKING.md:385`; correct `IMPLEMENTATION_PLAN.md:585`'s note to match.
2. **Fix Blocker B2** — thread a real `code_commit` (reuse `run_one.py::_code_commit()`, or hoist it into `convention_topology/run.py` so all three CLIs share it) into `run_pilot.py`/`run_main.py`'s `RunConfig` construction.
3. **Resolve Major M1** — either document the Phase 2 shuffle-granularity deviation in WORKING §2's locked-deviations table, or make `make_interaction_step` reproduce Ashery's shared-per-interaction shuffle for Phase 2.
4. **Resolve Major M2** — reconcile `tracker.py::modal_label_in_window`'s tie-break with `dvs.py`'s documented lexicographic rule (either make the production path lexicographic, or update the WORKING §7 doc + `dvs.py` to match insertion-order and explain why).
5. **Fix Major M3** — `h3b.py::_is_confirmatory` should check the full expected `(topology, cm_k)` grid, not just observed groups, so a fully-empty cell can't slip through as "confirmatory."
6. Consider Major M4 as a post-pilot refactor (not urgent): hoist `run_pilot.py`/`run_main.py`/`analyze.py`'s business logic into `convention_topology/` modules to match the stated thin-CLI principle and reduce duplication risk like B2.
7. Address Minor nits N1–N7 opportunistically; none block the pilot.
8. Once B1/B2/M1/M2/M3 are fixed, **commit the implementation** — `WORKING.md` §12's commit pin (`10912a6`) currently predates all of Phases A–G and is not a trustworthy reproducibility anchor yet.

---

## Remediation status (2026-07-14, per `FIX_PLAN.md`)

All findings B1–B2, M1–M4, N1–N7 fixed in this working tree (uncommitted — see commit-pin note above and item 8). 146 tests green (up from 121), coverage maintained ≥85%.

| Finding | Status | Commit/PR |
| --- | --- | --- |
| B1 | fixed — `h3a.py` now computes `lr_stat_gam_vs_linear`/`lr_p_gam_vs_linear` as the primary LR test; linear-vs-intercept renamed `lr_stat_linear_vs_intercept`/`lr_p_linear_vs_intercept`, documented secondary/descriptive | — (uncommitted) |
| B2 | fixed — `convention_topology/orchestration.py::get_code_commit`/`build_run_config` shared by all three CLIs; integration test proves pilot-batch sidecars record the real git commit, never `"pilot"` | — (uncommitted) |
| M1 | fixed — `make_interaction_step(..., shared_shuffle=True)` for Phase 2 (Ashery `committed()` fidelity); Phase 1 keeps per-agent shuffle | — (uncommitted) |
| M2 | fixed — single `tracker.modal_lexicographic` used by both `modal_label_in_window` (production) and `dvs.incumbent_label`; integration test proves they agree on real-run ties | — (uncommitted) |
| M3 | fixed — `h3b.py::_is_confirmatory` checks the full expected `cm_k` grid per topology; a topology missing an entire k-cell no longer silently qualifies | — (uncommitted) |
| M4 | fixed — `convention_topology/orchestration.py` (pilot/main dispatch) + `convention_topology/analysis/dispatch.py` (H1–H4/eligibility/cross-model); all four CLIs are argparse + one call, no CLI imports another | — (uncommitted) |
| N1 | fixed — `persistence.py::write_analysis_json`/`write_analysis_csv`/`delete_run_artifacts`; `analyze.py` and retry-cleanup paths route through them | — (uncommitted) |
| N2 | fixed — `networks.py::get_interaction_network` raises `NotImplementedError` if `minority_size != 0`; no rewrite | — (uncommitted) |
| N3 | fixed — `analysis/common.py::_run_dvs` derives the pickle path from the `scan_meta_paths`-found `meta_path`, not reconstructed string components | — (uncommitted) |
| N4 | fixed — closed by M4's `run_main.py` extraction; single `_options`/`build_run_config` source, no inlined `options_set[0]` | — (uncommitted) |
| N5 | fixed — `dvs.py::flip`/`time_to_flip` raise `ValueError` if the tracker is shorter than `t_start + window` | — (uncommitted) |
| N6 | fixed — `requirements.txt` pins tightened to `networkx>=3.6,<4`, `PyYAML>=6.0.3,<7`, `munch>=4.0,<5` per IMPLEMENTATION_PLAN §7.2 | — (uncommitted) |
| N7 | fixed — `h3a.py`/`h3b.py` catch a narrow `(LinAlgError, PerfectSeparationError, ValueError)` tuple instead of bare `except Exception`; exploratory JSON carries a `reason` field | — (uncommitted) |
