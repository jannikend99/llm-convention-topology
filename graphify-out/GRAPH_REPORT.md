# Graph Report - llm-convention-topology  (2026-09-28)

## Corpus Check
- 67 files · ~44,696 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 3, .slurm 1, .ini 1)

## Summary
- 983 nodes · 2915 edges · 37 communities (29 shown, 8 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 104 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2eb77c05`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- persistence.py
- config.py
- dispatch.py
- test_health.py
- MockLLMClient
- common.py
- load_run_table
- campaign.py
- run.py
- parse_decision
- llm.py
- fake_slice
- TechCheckProbeTests
- test_analysis.py
- test_json.py
- TechCheckCliTests
- typing
- h2.py
- Diag ladder and path to `pilot-run`
- d1_funnel
- h3a_analysis
- DirtyWorktreeError
- fill_r_ladder_eval.py
- _yen_scratch.sh
- delayed_execute
- h1_per_model
- llm-convention-topology
- analysis/__init__.py
- pack_yen_runs.sh
- tech_check.py
- parse_task
- orchestration.py
- DirtyGitCliTests
- client.py
- Jev / System One and the Naming Game
- TypeSafe Jev sidecar
- typesafe_jev/__init__.py

## God Nodes (most connected - your core abstractions)
1. `execute_run_async()` - 47 edges
2. `MockLLMClient` - 46 edges
3. `load_config()` - 45 edges
4. `read_meta()` - 44 edges
5. `resolve_model()` - 39 edges
6. `_cfg()` - 36 edges
7. `DirtyGitCliTests` - 34 edges
8. `read_health_snapshot()` - 33 edges
9. `run_slice_async()` - 33 edges
10. `main()` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Cleanup scan — llm-convention-topology` --references--> `campaign_requires_full_diag_knobs()`  [INFERRED]
  CLEANUP.md → convention_topology/config.py
- `Fit to the experiment` --references--> `parse_decision()`  [INFERRED]
  typesafe_jev/jev-system-one-experiment-fit.md → convention_topology/json_output.py
- `Fit to the experiment` --references--> `draw_pool()`  [INFERRED]
  typesafe_jev/jev-system-one-experiment-fit.md → convention_topology/pool.py
- `Fit to the experiment` --references--> `build_user_prompt()`  [INFERRED]
  typesafe_jev/jev-system-one-experiment-fit.md → convention_topology/prompting.py
- `StreamLoadTests` --uses--> `AnalysisMismatchError`  [INFERRED]
  tests/test_analysis.py → convention_topology/analysis/stream.py

## Import Cycles
- None detected.

## Communities (37 total, 8 thin omitted)

### Community 0 - "persistence.py"
Cohesion: 0.06
Nodes (52): ast, _decreased(), extend_bounds(), ExtendBoundsError, _extension(), Any, Exception, Path (+44 more)

### Community 1 - "config.py"
Cohesion: 0.05
Nodes (40): Cleanup scan — llm-convention-topology, apply_cli_protocol_env(), apply_diag_protocol(), apply_diag_tech_interactions(), apply_pilot_bounds(), apply_serve_base_url(), campaign_requires_full_diag_knobs(), check_campaign_name() (+32 more)

### Community 2 - "dispatch.py"
Cohesion: 0.30
Nodes (19): Analysis dispatch: named spine IDs on the locked grid., plot_d1(), plot_f1(), plot_f13(), plot_f14(), plot_f18(), plot_f24(), plot_f3() (+11 more)

### Community 3 - "test_health.py"
Cohesion: 0.08
Nodes (78): _assign_verdict(), _cell_key(), _elapsed_label(), format_health_text(), _format_unknown(), HealthSnapshot, _interaction_t(), _is_true() (+70 more)

### Community 4 - "MockLLMClient"
Cohesion: 0.09
Nodes (25): MockLLMClient, read_events(), read_meta(), execute_run(), BaseException, Injected or SIGTERM persistence-boundary stop., StopRequested, _cfg() (+17 more)

### Community 5 - "common.py"
Cohesion: 0.08
Nodes (46): _committed_id_set(), prepared_memory_policy_shares(), Any, Path, Shared run-table loader and gate/critical-mass helpers., Rebuild t=0 memory incumbent share and committed-policy share from inventories.…, _run_dvs(), scan_meta_paths() (+38 more)

### Community 6 - "load_run_table"
Cohesion: 0.32
Nodes (9): load_run_table(), save_run_pickle(), _interactions(), _meta(), Path, StreamLoadTests, _tracker_from(), _write_events() (+1 more)

### Community 7 - "campaign.py"
Cohesion: 0.11
Nodes (35): _atomic_write_json(), _atomic_write_yaml(), build_graphs_payload(), campaign_config_hash(), campaign_identity_config(), CampaignError, Any, Exception (+27 more)

### Community 8 - "run.py"
Cohesion: 0.06
Nodes (65): AsyncLLMClient, Exception, RunFailedError, ensure_run_dirs(), EventWriter, RunPaths, assert_prepared(), committed_label() (+57 more)

### Community 9 - "parse_decision"
Cohesion: 0.19
Nodes (9): match_option_in_text(), parse_decision(), ParseError, Exception, Raised when the model output is not a valid JSON decision object., Diag-only: map free text onto exactly one pool option. Not the counted parser., _reject_duplicates(), JsonEnumTests (+1 more)

### Community 10 - "llm.py"
Cohesion: 0.18
Nodes (9): json_schema_for_options(), Strict JSON enum parser for {value, reason}., AsyncClientAdapter, error_raw(), BaseException, LLM client: localhost OpenAI-compat or mock. JSON enum only., openai, re (+1 more)

### Community 12 - "TechCheckProbeTests"
Cohesion: 0.15
Nodes (6): TechCheckProbeTests, wrap_client(), wrap_client(), tracked(), wrap_client(), complete()

### Community 13 - "test_analysis.py"
Cohesion: 0.16
Nodes (21): main(), CLI: analysis dispatch for H1-H4 on the locked cell identity., prepared_valid_cm(), _load_pool(), Any, DataFrame, Path, run_all() (+13 more)

### Community 14 - "test_json.py"
Cohesion: 0.14
Nodes (10): chat_completion_kwargs(), openai_extra_body(), OpenAICompatClient, Any, build_user_prompt(), format_history(), prompt_template_hash(), Canonical Ashery observer prompt with JSON enum instruction. (+2 more)

### Community 16 - "typing"
Cohesion: 0.15
Nodes (16): collections, Cross-model robustness comparison — confirmatory models are compared, not…, H1: dominant-share coordination test vs tau=0.90, per model., H3a: mixing-only flip differences at the tested committed-minority sizes., H3b: flip ~ cm_k x topology interaction (WORKING.md §8, locked M04).…, h4_analysis(), Any, H4 (exploratory): Study-1 mixing winners from the interaction stream + pool. (+8 more)

### Community 17 - "h2.py"
Cohesion: 0.24
Nodes (13): cohens_d_unequal_n(), _contrast(), _entropy_descriptives(), h2_analysis(), _metadata(), Any, ndarray, H2: directed lattice and random-regular contrasts against mixing. The… (+5 more)

### Community 18 - "Diag ladder and path to `pilot-run`"
Cohesion: 0.11
Nodes (17): Diag ladder and path to `pilot-run`, Early stop vs Ashery time-to-convention, Extra seeds (repeat Phase A shape, schema only) — done (indices 1–3), Operator notes, Phase A decode (Mixing, emergence, seed 0, \(N=24\), \(H=5\), letters, cap 400), Phase A — done (all six), Phase B — one-factor, **JSON schema only** — done (seed 0, cap 400), Phase C — readout (2026-09-12) (+9 more)

### Community 19 - "d1_funnel"
Cohesion: 0.25
Nodes (7): critical_mass(), d1_funnel(), d5_prepared(), DataFrame, cross_model_summary(), Any, DataFrame

### Community 20 - "h3a_analysis"
Cohesion: 0.11
Nodes (14): _empirical(), _fit_logit(), h3a_analysis(), _metadata(), Any, ndarray, sensitivity_50_agreement(), _design_matrices() (+6 more)

### Community 21 - "DirtyWorktreeError"
Cohesion: 0.29
Nodes (3): DirtyWorktreeError, Exception, Counted campaign writes require a clean Git worktree.

### Community 22 - "fill_r_ladder_eval.py"
Cohesion: 0.52
Nodes (6): _engine_stats(), main(), Path, Summarize fill-ladder campaigns: JSON-schema share + last Engine 000 lines., _schema_share(), _scratch()

### Community 23 - "_yen_scratch.sh"
Cohesion: 0.18
Nodes (12): fill_r_ladder_a40_len.sh script, submit_chain(), fill_r_ladder_h200_hi.sh script, submit_chain(), fill_r_ladder_h200_qwen_glm.sh script, submit_chain(), fill_r_ladder_h200.sh script, submit_chain() (+4 more)

### Community 25 - "h1_per_model"
Cohesion: 0.40
Nodes (5): h1_analysis(), h1_per_model(), Any, DataFrame, T-H1 rows: mixing, one row per model, not pooled.

### Community 26 - "llm-convention-topology"
Cohesion: 0.50
Nodes (3): Commands, llm-convention-topology, Locks (mirrored in `config.yaml`)

### Community 30 - "tech_check.py"
Cohesion: 0.16
Nodes (19): classify_error(), draw_pool(), pool_sha256(), Campaign 5-character lowercase label pool., evaluate_pass(), _fixture_options(), _is_serve_startup(), _probe_async() (+11 more)

### Community 31 - "parse_task"
Cohesion: 0.10
Nodes (14): ArgumentParser, contextlib, _queue_cells(), flatten_tasks(), parse_task(), ValueError, Invalid --task grammar or duplicate cells., seed_slices() (+6 more)

### Community 35 - "orchestration.py"
Cohesion: 0.06
Nodes (55): argparse, asyncio, ensure_campaign_files(), load_config(), ModelSpec, Path, resolve_model(), current_commit() (+47 more)

### Community 38 - "client.py"
Cohesion: 0.18
Nodes (10): LLMClient, LLMResponse, Protocol, _decision_rng(), observer_state(), Random, TypeSafe Jev client for the existing Naming Game decision loop. The counted…, Drop generation instructions. The run log still hashes the original prompt. (+2 more)

### Community 39 - "Jev / System One and the Naming Game"
Cohesion: 0.25
Nodes (7): Fit to the experiment, Hosting, Jev / System One and the Naming Game, Practical sequence, Recommendation, What Jev is, Whether it is scientifically useful

## Knowledge Gaps
- **25 isolated node(s):** `_yen_scratch.sh script`, `pack_yen_runs.sh script`, `Locks (mirrored in `config.yaml`)`, `Commands`, `Recommended order (why)` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 241 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `orchestration.py` to `persistence.py`, `config.py`, `test_health.py`, `MockLLMClient`, `campaign.py`, `run.py`, `TechCheckProbeTests`, `test_json.py`, `TechCheckCliTests`, `tech_check.py`, `parse_task`?**
  _High betweenness centrality (0.068) - this node is a cross-community bridge._
- **Why does `DirtyGitCliTests` connect `DirtyGitCliTests` to `orchestration.py`, `fake_slice`, `DirtyWorktreeError`, `delayed_execute`, `parse_task`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `read_meta()` connect `MockLLMClient` to `persistence.py`, `orchestration.py`, `common.py`, `load_run_table`, `run.py`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `execute_run_async()` (e.g. with `AsyncLLMClient` and `RunPaths`) actually correct?**
  _`execute_run_async()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `MockLLMClient` (e.g. with `JsonEnumTests` and `DyadGatherTests`) actually correct?**
  _`MockLLMClient` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_yen_scratch.sh script`, `pack_yen_runs.sh script`, `Locks (mirrored in `config.yaml`)` to the rest of the system?**
  _25 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `persistence.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0579476861167002 - nodes in this community are weakly interconnected._