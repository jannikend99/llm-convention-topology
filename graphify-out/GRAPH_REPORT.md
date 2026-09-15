# Graph Report - llm-convention-topology  (2026-09-14)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 813 nodes · 2394 edges · 41 communities (22 shown, 19 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 83 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d1fc2a20`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- orchestration.py
- config.py
- dispatch.py
- test_health.py
- MockLLMClient
- common.py
- test_analysis.py
- campaign.py
- run.py
- ParseError
- llm.py
- fake_slice
- TechCheckProbeTests
- DirtyGitCliTests
- test_json.py
- TechCheckCliTests
- prepared.py
- h2.py
- test_run.py
- PrintQueueCliTests
- job_forensics
- DirtyWorktreeError
- fill_r_ladder_eval.py
- fill_r_ladder.sh
- delayed_execute
- simulation.py
- llm-convention-topology
- analysis/__init__.py
- pack_yen_runs.sh
- DataFrame
- Any
- DataFrame
- Path
- DataFrame
- DataFrame
- Path
- Any
- DataFrame
- Path
- Layout
- Table

## God Nodes (most connected - your core abstractions)
1. `execute_run_async()` - 44 edges
2. `MockLLMClient` - 42 edges
3. `load_config()` - 42 edges
4. `resolve_model()` - 38 edges
5. `DirtyGitCliTests` - 34 edges
6. `run_slice_async()` - 33 edges
7. `read_health_snapshot()` - 33 edges
8. `_cfg()` - 31 edges
9. `ConfigError` - 29 edges
10. `read_meta()` - 29 edges

## Surprising Connections (you probably didn't know these)
- `DyadGatherTests` --uses--> `AsyncClientAdapter`  [INFERRED]
  tests/test_run.py → convention_topology/llm.py
- `TechCheckProbeTests` --uses--> `AsyncClientAdapter`  [INFERRED]
  tests/test_tech_check.py → convention_topology/llm.py
- `main()` --uses--> `ConfigError`  [INFERRED]
  run_one.py → convention_topology/config.py
- `ClientTests` --uses--> `ConfigError`  [INFERRED]
  tests/test_json.py → convention_topology/config.py
- `TechCheckProbeTests` --uses--> `LLMResponse`  [INFERRED]
  tests/test_tech_check.py → convention_topology/llm.py

## Import Cycles
- None detected.

## Communities (41 total, 19 thin omitted)

### Community 0 - "orchestration.py"
Cohesion: 0.06
Nodes (66): ArgumentParser, ensure_campaign_files(), load_config(), ModelSpec, resolve_model(), current_commit(), Path, Campaign-writing CLIs fail on a dirty Git worktree. (+58 more)

### Community 1 - "config.py"
Cohesion: 0.06
Nodes (33): apply_cli_protocol_env(), apply_diag_protocol(), apply_diag_tech_interactions(), apply_pilot_bounds(), apply_serve_base_url(), campaign_requires_full_diag_knobs(), check_campaign_name(), config_hash() (+25 more)

### Community 2 - "dispatch.py"
Cohesion: 0.07
Nodes (67): main(), CLI: analysis dispatch for H1-H4 on the locked cell identity., critical_mass(), d1_funnel(), d5_prepared(), prepared_valid_cm(), DataFrame, cross_model_summary() (+59 more)

### Community 3 - "test_health.py"
Cohesion: 0.09
Nodes (70): _assign_verdict(), _cell_key(), _elapsed_label(), format_health_text(), _format_unknown(), HealthSnapshot, _interaction_t(), _is_true() (+62 more)

### Community 4 - "MockLLMClient"
Cohesion: 0.11
Nodes (23): MockLLMClient, read_events(), read_meta(), execute_run(), BaseException, Injected or SIGTERM persistence-boundary stop., StopRequested, _cfg() (+15 more)

### Community 5 - "common.py"
Cohesion: 0.07
Nodes (47): _committed_id_set(), prepared_memory_policy_shares(), Any, Path, Shared run-table loader and gate/critical-mass helpers., Rebuild t=0 memory incumbent share and committed-policy share from inventories.…, _run_dvs(), scan_meta_paths() (+39 more)

### Community 6 - "test_analysis.py"
Cohesion: 0.09
Nodes (25): load_run_table(), empty_sidecar(), EventWriter, load_run_pickle(), PersistenceError, Any, Exception, Path (+17 more)

### Community 7 - "campaign.py"
Cohesion: 0.09
Nodes (41): _atomic_write_json(), _atomic_write_yaml(), build_graphs_payload(), campaign_config_hash(), campaign_identity_config(), CampaignError, Any, Exception (+33 more)

### Community 8 - "run.py"
Cohesion: 0.18
Nodes (25): ensure_run_dirs(), RunPaths, prompt_template_hash(), Canonical Ashery observer prompt with JSON enum instruction., rendered_prompt_hash(), _attempt_row(), _checkpoint(), _decision() (+17 more)

### Community 9 - "ParseError"
Cohesion: 0.17
Nodes (11): json_schema_for_options(), match_option_in_text(), parse_decision(), ParseError, Exception, Strict JSON enum parser for {value, reason}., Raised when the model output is not a valid JSON decision object., Diag-only: map free text onto exactly one pool option. Not the counted parser. (+3 more)

### Community 10 - "llm.py"
Cohesion: 0.15
Nodes (11): AsyncLLMClient, chat_completion_kwargs(), classify_error(), error_raw(), LLMClient, LLMResponse, openai_extra_body(), Any (+3 more)

### Community 12 - "TechCheckProbeTests"
Cohesion: 0.14
Nodes (6): TechCheckProbeTests, wrap_client(), wrap_client(), tracked(), wrap_client(), complete()

### Community 14 - "test_json.py"
Cohesion: 0.24
Nodes (4): OpenAICompatClient, build_user_prompt(), format_history(), ClientTests

### Community 16 - "prepared.py"
Cohesion: 0.24
Nodes (11): assert_prepared(), committed_label(), make_prepared_population(), PreparedInitError, Exception, Prepared Study 2 init: H incumbent matches, then swap k, t_cm_start=0., Raised when prepared-population invariants fail., set_initial_state() (+3 more)

### Community 17 - "h2.py"
Cohesion: 0.29
Nodes (10): cohens_d_unequal_n(), _contrast(), _entropy_descriptives(), h2_analysis(), Any, ndarray, H2: four one-sided Welch contrasts vs mixing, Bonferroni alpha=0.0125., _support_label() (+2 more)

### Community 18 - "test_run.py"
Cohesion: 0.32
Nodes (8): Exception, RunFailedError, _one_interaction(), _pair(), _replay_interactions(), Any, update_dict(), update_tracker()

### Community 20 - "job_forensics"
Cohesion: 0.32
Nodes (5): _gpu_ids_from_env(), job_forensics(), _package_version(), GPU/vLLM sidecar fields from the job environment. Laptop/mock: all None., JobForensicsTests

### Community 21 - "DirtyWorktreeError"
Cohesion: 0.29
Nodes (3): DirtyWorktreeError, Exception, Counted campaign writes require a clean Git worktree.

### Community 22 - "fill_r_ladder_eval.py"
Cohesion: 0.57
Nodes (6): _engine_stats(), main(), Path, Summarize fill-ladder campaigns: JSON-schema share + last Engine 000 lines., _schema_share(), _scratch()

### Community 23 - "fill_r_ladder.sh"
Cohesion: 0.47
Nodes (4): fill_r_ladder.sh script, submit_chain(), resolve_yen_scratch(), _yen_scratch.sh script

### Community 25 - "simulation.py"
Cohesion: 0.67
Nodes (3): Random, Committed-minority swap. Pairing lives in the counted run engine., swap_committed()

### Community 26 - "llm-convention-topology"
Cohesion: 0.50
Nodes (3): Commands, llm-convention-topology, Locks (mirrored in `config.yaml`)

## Knowledge Gaps
- **4 isolated node(s):** `_yen_scratch.sh script`, `Commands`, `Locks (mirrored in `config.yaml`)`, `pack_yen_runs.sh script`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 183 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `orchestration.py` to `config.py`, `test_health.py`, `MockLLMClient`, `test_analysis.py`, `campaign.py`, `test_json.py`, `TechCheckCliTests`, `test_run.py`, `PrintQueueCliTests`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `DirtyGitCliTests` connect `DirtyGitCliTests` to `orchestration.py`, `delayed_execute`, `fake_slice`, `DirtyWorktreeError`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `read_meta()` connect `MockLLMClient` to `orchestration.py`, `common.py`, `test_analysis.py`, `run.py`, `test_run.py`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `execute_run_async()` (e.g. with `AsyncLLMClient` and `RunPaths`) actually correct?**
  _`execute_run_async()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `MockLLMClient` (e.g. with `JsonEnumTests` and `DyadGatherTests`) actually correct?**
  _`MockLLMClient` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_yen_scratch.sh script`, `Commands`, `Locks (mirrored in `config.yaml`)` to the rest of the system?**
  _4 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `orchestration.py` be split into smaller, more focused modules?**
  _Cohesion score 0.056493884682585906 - nodes in this community are weakly interconnected._