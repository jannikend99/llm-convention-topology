# Graph Report - llm-convention-topology  (2026-09-28)

## Corpus Check
- 67 files · ~43,846 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 966 nodes · 2916 edges · 43 communities (32 shown, 11 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 100 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `38e9accc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- write_meta
- config.py
- dispatch.py
- test_health.py
- MockLLMClient
- common.py
- load_run_table
- campaign.py
- run.py
- ParseError
- llm.py
- fake_slice
- TechCheckProbeTests
- run_h2
- ClientTests
- TechCheckCliTests
- h3a.py
- h2.py
- Diag ladder and path to `pilot-run`
- d1_funnel
- test_json.py
- DirtyWorktreeError
- fill_r_ladder_eval.py
- _yen_scratch.sh
- _peak_for
- orchestration.py
- llm-convention-topology
- analysis/__init__.py
- pack_yen_runs.sh
- load_config
- tech_check.py
- run_main.py
- cross_model.py
- persistence.py
- _HttpLimiter
- run_studies.py
- DirtyGitCliTests
- PrintQueueCliTests
- client.py
- Jev / System One and the Naming Game
- TypeSafe Jev sidecar
- CLEANUP.md
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
- `StreamLoadTests` --uses--> `AnalysisMismatchError`  [INFERRED]
  tests/test_analysis.py → convention_topology/analysis/stream.py
- `RecordingTests` --uses--> `CampaignError`  [INFERRED]
  tests/test_run.py → convention_topology/campaign.py
- `ClientTests` --uses--> `ConfigError`  [INFERRED]
  tests/test_json.py → convention_topology/config.py
- `main()` --uses--> `ConfigError`  [INFERRED]
  typesafe_jev/run_studies.py → convention_topology/config.py
- `main()` --uses--> `ExtendBoundsError`  [INFERRED]
  run_main.py → convention_topology/extend_bounds.py

## Import Cycles
- None detected.

## Communities (43 total, 11 thin omitted)

### Community 0 - "write_meta"
Cohesion: 0.08
Nodes (42): ast, _decreased(), extend_bounds(), ExtendBoundsError, _extension(), Any, Exception, Path (+34 more)

### Community 1 - "config.py"
Cohesion: 0.06
Nodes (38): apply_cli_protocol_env(), apply_diag_protocol(), apply_diag_tech_interactions(), apply_pilot_bounds(), apply_serve_base_url(), campaign_requires_full_diag_knobs(), check_campaign_name(), config_hash() (+30 more)

### Community 2 - "dispatch.py"
Cohesion: 0.21
Nodes (25): Analysis dispatch: named spine IDs on the locked grid., run_h1(), plot_d1(), plot_f1(), plot_f13(), plot_f14(), plot_f18(), plot_f24() (+17 more)

### Community 3 - "test_health.py"
Cohesion: 0.08
Nodes (78): _assign_verdict(), _cell_key(), _elapsed_label(), format_health_text(), _format_unknown(), HealthSnapshot, _interaction_t(), _is_true() (+70 more)

### Community 4 - "MockLLMClient"
Cohesion: 0.12
Nodes (20): MockLLMClient, read_events(), read_meta(), execute_run(), BaseException, Injected or SIGTERM persistence-boundary stop., StopRequested, _cfg() (+12 more)

### Community 5 - "common.py"
Cohesion: 0.12
Nodes (30): _committed_id_set(), prepared_memory_policy_shares(), Any, Shared run-table loader and gate/critical-mass helpers., Rebuild t=0 memory incumbent share and committed-policy share from inventories.…, _run_dvs(), _window(), AnalysisMismatchError (+22 more)

### Community 6 - "load_run_table"
Cohesion: 0.32
Nodes (11): load_run_table(), Path, scan_meta_paths(), save_run_pickle(), _interactions(), _meta(), Path, StreamLoadTests (+3 more)

### Community 7 - "campaign.py"
Cohesion: 0.10
Nodes (38): _atomic_write_json(), _atomic_write_yaml(), build_graphs_payload(), campaign_config_hash(), campaign_identity_config(), CampaignError, ensure_campaign_files(), Any (+30 more)

### Community 8 - "run.py"
Cohesion: 0.05
Nodes (71): asyncio, AsyncLLMClient, Exception, RunFailedError, ensure_run_dirs(), EventWriter, RunPaths, assert_prepared() (+63 more)

### Community 9 - "ParseError"
Cohesion: 0.17
Nodes (11): match_option_in_text(), parse_decision(), ParseError, Exception, Strict JSON enum parser for {value, reason}., Raised when the model output is not a valid JSON decision object., Diag-only: map free text onto exactly one pool option. Not the counted parser., _reject_duplicates() (+3 more)

### Community 10 - "llm.py"
Cohesion: 0.12
Nodes (14): json_schema_for_options(), AsyncClientAdapter, AsyncOpenAICompatClient, chat_completion_kwargs(), error_raw(), LLMClient, LLMResponse, openai_extra_body() (+6 more)

### Community 12 - "TechCheckProbeTests"
Cohesion: 0.15
Nodes (6): TechCheckProbeTests, wrap_client(), wrap_client(), tracked(), wrap_client(), complete()

### Community 13 - "run_h2"
Cohesion: 0.15
Nodes (25): main(), CLI: analysis dispatch for H1-H4 on the locked cell identity., argparse, _load_pool(), Any, DataFrame, Path, run_all() (+17 more)

### Community 14 - "ClientTests"
Cohesion: 0.21
Nodes (3): OpenAICompatClient, request_timeout(), ClientTests

### Community 16 - "h3a.py"
Cohesion: 0.11
Nodes (17): collections, H3a: flip curve over committed-minority size cm_k (WORKING.md §8, locked M04).…, _design_matrices(), h3b_analysis(), _is_confirmatory(), Any, DataFrame, H3b: flip ~ cm_k x topology interaction (WORKING.md §8, locked M04). Logistic… (+9 more)

### Community 17 - "h2.py"
Cohesion: 0.18
Nodes (13): H1: dominant-share coordination test vs tau=0.90, per model., cohens_d_unequal_n(), _contrast(), _entropy_descriptives(), h2_analysis(), Any, ndarray, H2: four one-sided Welch contrasts vs mixing, Bonferroni alpha=0.0125. (+5 more)

### Community 18 - "Diag ladder and path to `pilot-run`"
Cohesion: 0.11
Nodes (17): Diag ladder and path to `pilot-run`, Early stop vs Ashery time-to-convention, Extra seeds (repeat Phase A shape, schema only) — done (indices 1–3), Operator notes, Phase A decode (Mixing, emergence, seed 0, \(N=24\), \(H=5\), letters, cap 400), Phase A — done (all six), Phase B — one-factor, **JSON schema only** — done (seed 0, cap 400), Phase C — readout (2026-09-12) (+9 more)

### Community 19 - "d1_funnel"
Cohesion: 0.15
Nodes (6): d1_funnel(), d5_prepared(), prepared_valid_cm(), DataFrame, FunnelAndSmokeTests, H3H4Tests

### Community 20 - "test_json.py"
Cohesion: 0.17
Nodes (12): Campaign 5-character lowercase label pool., build_user_prompt(), format_history(), prompt_template_hash(), Canonical Ashery observer prompt with JSON enum instruction., hashlib, json, random (+4 more)

### Community 21 - "DirtyWorktreeError"
Cohesion: 0.29
Nodes (3): DirtyWorktreeError, Exception, Counted campaign writes require a clean Git worktree.

### Community 22 - "fill_r_ladder_eval.py"
Cohesion: 0.57
Nodes (6): _engine_stats(), main(), Path, Summarize fill-ladder campaigns: JSON-schema share + last Engine 000 lines., _schema_share(), _scratch()

### Community 23 - "_yen_scratch.sh"
Cohesion: 0.18
Nodes (12): fill_r_ladder_a40_len.sh script, submit_chain(), fill_r_ladder_h200_hi.sh script, submit_chain(), fill_r_ladder_h200_qwen_glm.sh script, submit_chain(), fill_r_ladder_h200.sh script, submit_chain() (+4 more)

### Community 25 - "orchestration.py"
Cohesion: 0.18
Nodes (13): allocation_job_id(), cell_grid(), heartbeat_path(), JobSlice, planned_models(), planned_programs(), print_jobs(), Any (+5 more)

### Community 26 - "llm-convention-topology"
Cohesion: 0.50
Nodes (3): Commands, llm-convention-topology, Locks (mirrored in `config.yaml`)

### Community 29 - "load_config"
Cohesion: 0.34
Nodes (13): load_config(), run_slice_async(), _heartbeat_loop(), _heartbeat_payload(), _one(), _write_heartbeat(), _utc_stamp(), build_run_id() (+5 more)

### Community 30 - "tech_check.py"
Cohesion: 0.24
Nodes (14): classify_error(), build_client(), draw_pool(), options_for_program(), evaluate_pass(), _fixture_options(), _is_serve_startup(), _probe_async() (+6 more)

### Community 31 - "run_main.py"
Cohesion: 0.13
Nodes (16): ArgumentParser, contextlib, Path, require_clean_worktree(), _queue_cells(), flatten_tasks(), parse_task(), ValueError (+8 more)

### Community 32 - "cross_model.py"
Cohesion: 0.40
Nodes (5): critical_mass(), cross_model_summary(), Any, DataFrame, Cross-model robustness comparison — confirmatory models are compared, not…

### Community 33 - "persistence.py"
Cohesion: 0.16
Nodes (21): _mean_ci(), phase_points(), DataFrame, ndarray, Time-series aggregates from the interaction stream for F1, F5, F7., success_by_round(), interactions_from_events(), Any (+13 more)

### Community 35 - "run_studies.py"
Cohesion: 0.13
Nodes (17): ModelSpec, current_commit(), Campaign-writing CLIs fail on a dirty Git worktree., format_queue_summary(), install_process_sigterm(), Install one process-wide SIGTERM/SIGINT handler shared by concurrent runs., subprocess, Space request starts so the process stays at ``rpm`` and not above it. (+9 more)

### Community 38 - "client.py"
Cohesion: 0.33
Nodes (7): _decision_rng(), observer_state(), Random, TypeSafe Jev client for the existing Naming Game decision loop. The counted…, Drop generation instructions. The run log still hashes the original prompt., Draw one label. Temperature below 1 sharpens the returned distribution., sample_label()

### Community 39 - "Jev / System One and the Naming Game"
Cohesion: 0.25
Nodes (7): Fit to the experiment, Hosting, Jev / System One and the Naming Game, Practical sequence, Recommendation, What Jev is, Whether it is scientifically useful

## Knowledge Gaps
- **27 isolated node(s):** `_yen_scratch.sh script`, `pack_yen_runs.sh script`, `Cleanup scan — llm-convention-topology`, `Locks (mirrored in `config.yaml`)`, `Commands` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 241 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `load_config` to `write_meta`, `config.py`, `test_health.py`, `MockLLMClient`, `PrintQueueCliTests`, `run_studies.py`, `campaign.py`, `run.py`, `TechCheckProbeTests`, `ClientTests`, `TechCheckCliTests`, `test_json.py`, `_peak_for`, `orchestration.py`, `tech_check.py`, `run_main.py`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `DirtyGitCliTests` connect `DirtyGitCliTests` to `fake_slice`, `DirtyWorktreeError`, `_peak_for`, `load_config`, `run_main.py`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `read_meta()` connect `MockLLMClient` to `write_meta`, `persistence.py`, `config.py`, `run_studies.py`, `common.py`, `load_run_table`, `run.py`, `run_h2`, `orchestration.py`, `load_config`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `execute_run_async()` (e.g. with `AsyncLLMClient` and `RunPaths`) actually correct?**
  _`execute_run_async()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `MockLLMClient` (e.g. with `JsonEnumTests` and `DyadGatherTests`) actually correct?**
  _`MockLLMClient` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_yen_scratch.sh script`, `pack_yen_runs.sh script`, `Cleanup scan — llm-convention-topology` to the rest of the system?**
  _27 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `write_meta` be split into smaller, more focused modules?**
  _Cohesion score 0.07547169811320754 - nodes in this community are weakly interconnected._