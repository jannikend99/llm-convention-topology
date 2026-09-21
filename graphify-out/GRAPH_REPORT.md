# Graph Report - llm-convention-topology  (2026-09-21)

## Corpus Check
- 60 files · ~39,770 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 3, .slurm 1, .ini 1)

## Summary
- 907 nodes · 2676 edges · 35 communities (28 shown, 7 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 91 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f8d071a3`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run_main.py
- config.py
- dispatch.py
- test_health.py
- test_run.py
- persistence.py
- load_run_table
- campaign.py
- run.py
- ParseError
- llm.py
- DirtyGitCliTests
- TechCheckProbeTests
- run_h2
- ClientTests
- TechCheckCliTests
- h3a.py
- h2.py
- Diag ladder and path to `pilot-run`
- test_analysis.py
- typing
- run_one.py
- fill_r_ladder_eval.py
- _yen_scratch.sh
- _peak_for
- orchestration.py
- llm-convention-topology
- analysis/__init__.py
- pack_yen_runs.sh
- load_config
- tech_check.py
- h1.py
- pandas
- _write_heartbeat
- _HttpLimiter

## God Nodes (most connected - your core abstractions)
1. `execute_run_async()` - 44 edges
2. `load_config()` - 43 edges
3. `MockLLMClient` - 43 edges
4. `resolve_model()` - 39 edges
5. `read_meta()` - 34 edges
6. `DirtyGitCliTests` - 34 edges
7. `read_health_snapshot()` - 33 edges
8. `run_slice_async()` - 33 edges
9. `_cfg()` - 33 edges
10. `main()` - 30 edges

## Surprising Connections (you probably didn't know these)
- `Cleanup scan — llm-convention-topology` --references--> `campaign_requires_full_diag_knobs()`  [INFERRED]
  CLEANUP.md → convention_topology/config.py
- `StreamLoadTests` --uses--> `AnalysisMismatchError`  [INFERRED]
  tests/test_analysis.py → convention_topology/analysis/stream.py
- `main()` --uses--> `ConfigError`  [INFERRED]
  run_one.py → convention_topology/config.py
- `ClientTests` --uses--> `ConfigError`  [INFERRED]
  tests/test_json.py → convention_topology/config.py
- `main()` --uses--> `DirtyWorktreeError`  [INFERRED]
  run_main.py → convention_topology/git_guard.py

## Import Cycles
- None detected.

## Communities (35 total, 7 thin omitted)

### Community 0 - "run_main.py"
Cohesion: 0.05
Nodes (39): ArgumentParser, contextlib, _queue_cells(), flatten_tasks(), parse_task(), ValueError, Invalid --task grammar or duplicate cells., seed_slices() (+31 more)

### Community 1 - "config.py"
Cohesion: 0.06
Nodes (35): Cleanup scan — llm-convention-topology, apply_cli_protocol_env(), apply_diag_protocol(), apply_diag_tech_interactions(), apply_pilot_bounds(), apply_serve_base_url(), campaign_requires_full_diag_knobs(), check_campaign_name() (+27 more)

### Community 2 - "dispatch.py"
Cohesion: 0.30
Nodes (19): Analysis dispatch: named spine IDs on the locked grid., plot_d1(), plot_f1(), plot_f13(), plot_f14(), plot_f18(), plot_f24(), plot_f3() (+11 more)

### Community 3 - "test_health.py"
Cohesion: 0.08
Nodes (78): _assign_verdict(), _cell_key(), _elapsed_label(), format_health_text(), _format_unknown(), HealthSnapshot, _interaction_t(), _is_true() (+70 more)

### Community 4 - "test_run.py"
Cohesion: 0.09
Nodes (24): MockLLMClient, Path, read_events(), read_meta(), execute_run(), BaseException, Injected or SIGTERM persistence-boundary stop., StopRequested (+16 more)

### Community 5 - "persistence.py"
Cohesion: 0.06
Nodes (54): ast, _committed_id_set(), prepared_memory_policy_shares(), Any, Shared run-table loader and gate/critical-mass helpers., Rebuild t=0 memory incumbent share and committed-policy share from inventories.…, _run_dvs(), _window() (+46 more)

### Community 6 - "load_run_table"
Cohesion: 0.27
Nodes (11): load_run_table(), Path, scan_meta_paths(), save_run_pickle(), _interactions(), _meta(), Path, StreamLoadTests (+3 more)

### Community 7 - "campaign.py"
Cohesion: 0.09
Nodes (38): _atomic_write_json(), _atomic_write_yaml(), build_graphs_payload(), campaign_config_hash(), campaign_identity_config(), CampaignError, ensure_campaign_files(), Any (+30 more)

### Community 8 - "run.py"
Cohesion: 0.05
Nodes (71): AsyncLLMClient, error_raw(), BaseException, Exception, RunFailedError, ensure_run_dirs(), EventWriter, RunPaths (+63 more)

### Community 9 - "ParseError"
Cohesion: 0.17
Nodes (11): match_option_in_text(), parse_decision(), ParseError, Exception, Strict JSON enum parser for {value, reason}., Raised when the model output is not a valid JSON decision object., Diag-only: map free text onto exactly one pool option. Not the counted parser., _reject_duplicates() (+3 more)

### Community 10 - "llm.py"
Cohesion: 0.16
Nodes (11): collections, json_schema_for_options(), AsyncClientAdapter, chat_completion_kwargs(), LLMClient, LLMResponse, openai_extra_body(), Any (+3 more)

### Community 12 - "TechCheckProbeTests"
Cohesion: 0.15
Nodes (6): TechCheckProbeTests, wrap_client(), wrap_client(), tracked(), wrap_client(), complete()

### Community 13 - "run_h2"
Cohesion: 0.22
Nodes (17): main(), CLI: analysis dispatch for H1-H4 on the locked cell identity., argparse, _load_pool(), Any, DataFrame, Path, run_all() (+9 more)

### Community 16 - "h3a.py"
Cohesion: 0.14
Nodes (17): empirical_flip_rates(), DataFrame, H3a: flip curve over committed-minority size cm_k (WORKING.md §8, locked M04).…, _design_matrices(), h3b_analysis(), _is_confirmatory(), Any, DataFrame (+9 more)

### Community 17 - "h2.py"
Cohesion: 0.26
Nodes (10): cohens_d_unequal_n(), _contrast(), _entropy_descriptives(), h2_analysis(), Any, ndarray, H2: four one-sided Welch contrasts vs mixing, Bonferroni alpha=0.0125., _support_label() (+2 more)

### Community 18 - "Diag ladder and path to `pilot-run`"
Cohesion: 0.11
Nodes (17): Diag ladder and path to `pilot-run`, Early stop vs Ashery time-to-convention, Extra seeds (repeat Phase A shape, schema only) — done (indices 1–3), Operator notes, Phase A decode (Mixing, emergence, seed 0, \(N=24\), \(H=5\), letters, cap 400), Phase A — done (all six), Phase B — one-factor, **JSON schema only** — done (seed 0, cap 400), Phase C — readout (2026-09-12) (+9 more)

### Community 19 - "test_analysis.py"
Cohesion: 0.15
Nodes (12): d1_funnel(), d5_prepared(), prepared_valid_cm(), DataFrame, run_h3a(), h3a_analysis(), Any, 95% vs 50% flip-indicator agreement (mixing, eligible runs). (+4 more)

### Community 20 - "typing"
Cohesion: 0.18
Nodes (12): Campaign 5-character lowercase label pool., build_user_prompt(), format_history(), prompt_template_hash(), Canonical Ashery observer prompt with JSON enum instruction., hashlib, json, random (+4 more)

### Community 21 - "run_one.py"
Cohesion: 0.18
Nodes (12): current_commit(), DirtyWorktreeError, Exception, Path, Campaign-writing CLIs fail on a dirty Git worktree., Counted campaign writes require a clean Git worktree., require_clean_worktree(), options_for_program() (+4 more)

### Community 22 - "fill_r_ladder_eval.py"
Cohesion: 0.43
Nodes (7): _engine_stats(), main(), Path, Summarize fill-ladder campaigns: JSON-schema share + last Engine 000 lines., _schema_share(), _scratch(), os

### Community 23 - "_yen_scratch.sh"
Cohesion: 0.18
Nodes (12): fill_r_ladder_a40_len.sh script, submit_chain(), fill_r_ladder_h200_hi.sh script, submit_chain(), fill_r_ladder_h200_qwen_glm.sh script, submit_chain(), fill_r_ladder_h200.sh script, submit_chain() (+4 more)

### Community 25 - "orchestration.py"
Cohesion: 0.20
Nodes (14): asyncio, ModelSpec, AsyncOpenAICompatClient, request_timeout(), _require_localhost(), build_client(), format_queue_summary(), JobSlice (+6 more)

### Community 26 - "llm-convention-topology"
Cohesion: 0.50
Nodes (3): Commands, llm-convention-topology, Locks (mirrored in `config.yaml`)

### Community 29 - "load_config"
Cohesion: 0.37
Nodes (9): load_config(), Path, allocation_job_id(), run_slice_async(), _one(), build_run_id(), encode_run_key(), run_paths() (+1 more)

### Community 30 - "tech_check.py"
Cohesion: 0.29
Nodes (12): classify_error(), draw_pool(), evaluate_pass(), _fixture_options(), _is_serve_startup(), _probe_async(), Any, BaseException (+4 more)

### Community 31 - "h1.py"
Cohesion: 0.25
Nodes (8): h1_analysis(), h1_per_model(), Any, DataFrame, H1: dominant-share coordination test vs tau=0.90, per model., T-H1 rows: mixing, one row per model, not pooled., numpy, scipy

### Community 32 - "pandas"
Cohesion: 0.33
Nodes (6): critical_mass(), cross_model_summary(), Any, DataFrame, Cross-model robustness comparison — confirmatory models are compared, not…, pandas

### Community 33 - "_write_heartbeat"
Cohesion: 0.29
Nodes (7): heartbeat_path(), Path, _heartbeat_loop(), _heartbeat_payload(), _write_heartbeat(), _utc_stamp(), write_json_atomic()

## Knowledge Gaps
- **19 isolated node(s):** `_yen_scratch.sh script`, `pack_yen_runs.sh script`, `Locks (mirrored in `config.yaml`)`, `Commands`, `Recommended order (why)` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 219 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load_config()` connect `load_config` to `run_main.py`, `config.py`, `test_health.py`, `test_run.py`, `persistence.py`, `campaign.py`, `TechCheckProbeTests`, `ClientTests`, `TechCheckCliTests`, `typing`, `run_one.py`, `_peak_for`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `DirtyGitCliTests` connect `DirtyGitCliTests` to `_peak_for`, `run_main.py`, `run_one.py`, `load_config`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `resolve_model()` connect `config.py` to `run_main.py`, `test_health.py`, `test_run.py`, `ClientTests`, `typing`, `run_one.py`, `_peak_for`, `orchestration.py`, `load_config`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `execute_run_async()` (e.g. with `AsyncLLMClient` and `RunPaths`) actually correct?**
  _`execute_run_async()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `MockLLMClient` (e.g. with `JsonEnumTests` and `DyadGatherTests`) actually correct?**
  _`MockLLMClient` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_yen_scratch.sh script`, `pack_yen_runs.sh script`, `Locks (mirrored in `config.yaml`)` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `run_main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.052429667519181586 - nodes in this community are weakly interconnected._