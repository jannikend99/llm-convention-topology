# Graph Report - llm-convention-topology  (2026-09-14)

## Corpus Check
- 64 files · ~68,453 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: (none) 3, .ipynb 2, .slurm 1)

## Summary
- 1102 nodes · 2770 edges · 46 communities (39 shown, 4 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 95 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7ba55e1d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run.py
- config.py
- memory_decision.py
- campaign.py
- DashboardState
- common.py
- 7. External dependencies & implementation patterns
- C-05 — OpenRouter real-API smoke (2026-07-20)
- test_health.py
- MockLLMClient
- Provider routing plan — OpenRouter + direct APIs
- Ashery-style split design — emergence ‖ CM on prepared populations
- Together AI switch + Ashery mixing proof log (2026-07-21 → 22)
- llm-convention-topology — Implementation notes
- plot_doug_pilot_preview.py
- 16. Pilot hosting (Hetzner)
- 17. Infra pilot — results & findings (`mistralnemo`, 2026-07-24–26)
- wrap_client
- 15. Async engine (parallelisation)
- 5. Run orchestration
- Status
- 4. Methodology architecture (canonical)
- llm-convention-topology
- 2. Ashery → thesis porting map
- analysis/__init__.py
- test_analysis.py
- ParseError
- fake_slice
- dispatch.py
- 2. Ashery protocol (as implemented in public code + paper)
- Diag ladder and path to `pilot-run`
- 4. Proposed thesis change (Ashery-faithful)
- Ashery mixing baseline — validation plan (2026-07-20)
- orchestration.py
- 2. What we did (procedure)
- 3. Path taken (chronology)
- chat_completion_kwargs
- AsyncClientAdapter
- TechCheckCliTests
- test_json.py
- DirtyGitCliTests
- tech_check.py
- DirtyWorktreeError

## God Nodes (most connected - your core abstractions)
1. `execute_run_async()` - 44 edges
2. `load_config()` - 42 edges
3. `MockLLMClient` - 42 edges
4. `resolve_model()` - 40 edges
5. `run_slice_async()` - 33 edges
6. `DirtyGitCliTests` - 33 edges
7. `read_health_snapshot()` - 31 edges
8. `read_meta()` - 31 edges
9. `_cfg()` - 31 edges
10. `main()` - 29 edges

## Surprising Connections (you probably didn't know these)
- `StreamLoadTests` --uses--> `AnalysisMismatchError`  [INFERRED]
  tests/test_analysis.py → convention_topology/analysis/stream.py
- `ClientTests` --uses--> `ConfigError`  [INFERRED]
  tests/test_json.py → convention_topology/config.py
- `main()` --uses--> `DirtyWorktreeError`  [INFERRED]
  run_main.py → convention_topology/git_guard.py
- `main()` --uses--> `DirtyWorktreeError`  [INFERRED]
  run_one.py → convention_topology/git_guard.py
- `DirtyGitCliTests` --uses--> `DirtyWorktreeError`  [INFERRED]
  tests/test_cli.py → convention_topology/git_guard.py

## Import Cycles
- None detected.

## Communities (46 total, 4 thin omitted)

### Community 0 - "run.py"
Cohesion: 0.06
Nodes (60): AsyncLLMClient, error_raw(), Exception, RunFailedError, ensure_run_dirs(), EventWriter, RunPaths, assert_prepared() (+52 more)

### Community 1 - "config.py"
Cohesion: 0.06
Nodes (30): apply_diag_protocol(), apply_diag_tech_interactions(), apply_pilot_bounds(), apply_serve_base_url(), check_campaign_name(), config_hash(), ConfigError, is_localhost_url() (+22 more)

### Community 2 - "memory_decision.py"
Cohesion: 0.12
Nodes (29): Path, scan_meta_paths(), compare_memory_decision(), decision_rows_for_agent(), extract_decisions(), modal_label(), plot_p_m_by_program(), plot_p_m_compare() (+21 more)

### Community 3 - "campaign.py"
Cohesion: 0.10
Nodes (36): _atomic_write_json(), _atomic_write_yaml(), build_graphs_payload(), campaign_config_hash(), campaign_identity_config(), CampaignError, Any, Exception (+28 more)

### Community 4 - "DashboardState"
Cohesion: 0.09
Nodes (46): cost_summary(), estimate_cost_usd(), DataFrame, Token/cost aggregation from `token_usage` events (WORKING.md §9 cost panel).…, Per-model cumulative token totals and $ estimate from `token_usage` events., _active_runs_table(), _api_health_table(), build_layout() (+38 more)

### Community 5 - "common.py"
Cohesion: 0.06
Nodes (54): _committed_id_set(), prepared_memory_policy_shares(), Any, Shared run-table loader and gate/critical-mass helpers., Rebuild t=0 memory incumbent share and committed-policy share from inventories.…, _run_dvs(), _window(), _mean_ci() (+46 more)

### Community 6 - "7. External dependencies & implementation patterns"
Cohesion: 0.05
Nodes (41): 0. Zero-blocker build contract, 1. Header, 2. Master checklist, 3. Per-phase detail, 4. File creation order, 5. Test matrix, 6. CLI smoke sequence (cumulative — run after each phase), 7.10 Analysis stack — F-05…F-07 (+33 more)

### Community 7 - "C-05 — OpenRouter real-API smoke (2026-07-20)"
Cohesion: 0.18
Nodes (11): 1. Goal, 3.1 Smoke outcomes, 3.2 Routing pin (locked for open-weight models), 3.3 Deferred, 3. Results, 4. Learnings (keep for pilot / Methods), 5. Files touched this session, 6. Reproduce / verify later (+3 more)

### Community 8 - "test_health.py"
Cohesion: 0.10
Nodes (63): _assign_verdict(), _cell_key(), _elapsed_label(), format_health_text(), _format_unknown(), HealthSnapshot, _is_true(), _parse_stamp() (+55 more)

### Community 9 - "MockLLMClient"
Cohesion: 0.11
Nodes (23): MockLLMClient, read_events(), read_meta(), execute_run(), BaseException, Injected or SIGTERM persistence-boundary stop., StopRequested, _cfg() (+15 more)

### Community 10 - "Provider routing plan — OpenRouter + direct APIs"
Cohesion: 0.08
Nodes (26): 10. Risks & mitigations, 11. References, 1. Executive summary, 2.1 Registry (`config.yaml`), 2.2 Client construction, 2.3 Sidecar logging (repro anchor), 2.4 Known gap (pre-existing, not introduced by this plan), 2. Current state (code audit) (+18 more)

### Community 11 - "Ashery-style split design — emergence ‖ CM on prepared populations"
Cohesion: 0.22
Nodes (9): 1. Verdict (one screen), 3.1 Current run unit, 3.2 File-by-file: Ashery vs thesis today, 3.3 Orchestration / analysis coupling to sequential design, 3.4 Config today, 3. Thesis status quo (code cross-check, 2026-07-21), 5. Implementation checklist (for later session), 6. Session log (+1 more)

### Community 12 - "Together AI switch + Ashery mixing proof log (2026-07-21 → 22)"
Cohesion: 0.15
Nodes (13): 1. Goal of this track, 2. Decision log (locked choices), 4. Current config snapshot (emergence proof), 5. Next run — Ashery letters, 8 seeds (manual), 6. Open items after the 8-seed proof, 7.1 Limit-3 proof (A–J pool, Together, `max_tokens=2000`) — done, 7.2 Limit-8 proof (Ashery W=10 letters) — done (2026-07-22/23), 7.3 CM smoke (prepared W=2, mixing) — done (2026-07-23) (+5 more)

### Community 13 - "llm-convention-topology — Implementation notes"
Cohesion: 0.11
Nodes (18): 10. Testing strategy, 11. Configuration and CLI, 12. Reproducibility hooks, 13. Open decisions and blockers, 14. Session log, 1. Target architecture, 3. Implementation phases, 4. LLM API layer (+10 more)

### Community 14 - "plot_doug_pilot_preview.py"
Cohesion: 0.31
Nodes (12): _gate_counts(), main(), package_f1(), plot_f2_emergence_gate(), plot_f3_cm_flip_vs_k(), _preview_dir(), DataFrame, Path (+4 more)

### Community 15 - "16. Pilot hosting (Hetzner)"
Cohesion: 0.20
Nodes (10): 16. Pilot hosting (Hetzner), Access, Background-run options, Guardrails, Monitoring while detached, One-time server setup, Option A — tmux (recommended), Option B — systemd (unattended) (+2 more)

### Community 16 - "17. Infra pilot — results & findings (`mistralnemo`, 2026-07-24–26)"
Cohesion: 0.22
Nodes (9): 17. Infra pilot — results & findings (`mistralnemo`, 2026-07-24–26), CM (36 runs — prepared W=2, Phase 2 horizon 1000), Comparison: Llama mixing proof vs. mistral pilot (mixing only), Emergence (36 runs — organic Phase 1, W=10), Interpretation (locked for thesis planning), Label-pool confound (emergence) — historical note, Label pool — design lock (2026-07-27), Run summary (+1 more)

### Community 17 - "wrap_client"
Cohesion: 0.29
Nodes (4): wrap_client(), wrap_client(), tracked(), wrap_client()

### Community 18 - "15. Async engine (parallelisation)"
Cohesion: 0.25
Nodes (8): 15. Async engine (parallelisation), Concurrency model — two independent knobs, Deferred, Determinism lock (why gathering is statistically neutral), Implementation order (the six steps), Providers later (Step ⑤ extension — config-only), Run recipe, Tests

### Community 19 - "5. Run orchestration"
Cohesion: 0.29
Nodes (7): 5. Run orchestration, CLI (copy-paste ready), Factorial grid, Main study (locked — per model), Main study targets (per model — two programs), Pilot grid (`mistralnemo`), Pilot (locked)

### Community 20 - "Status"
Cohesion: 0.40
Nodes (5): Performance / async optimization (✅ implemented — async engine, §15), Pilot vs. main study (locked 2026-07-24), Scaling & infra (backlog — TODO #16), Sign-off (implementation plan), Status

### Community 21 - "4. Methodology architecture (canonical)"
Cohesion: 0.50
Nodes (4): 4.1 Two studies, not one sequential run, 4.2 Run counts (how N is chosen), 4.3 Alignment map — author intent vs. code vs. docs, 4. Methodology architecture (canonical)

### Community 22 - "llm-convention-topology"
Cohesion: 0.50
Nodes (3): Commands, llm-convention-topology, Locks (mirrored in `config.yaml`)

### Community 23 - "2. Ashery → thesis porting map"
Cohesion: 0.67
Nodes (3): 2. Ashery → thesis porting map, Adopt vs. skip (seed — agent completes), Locked thesis deviations from upstream (cite Methods, not ad hoc)

### Community 26 - "test_analysis.py"
Cohesion: 0.10
Nodes (27): load_run_table(), cohens_d_unequal_n(), _contrast(), _entropy_descriptives(), h2_analysis(), Any, ndarray, H2: four one-sided Welch contrasts vs mixing, Bonferroni alpha=0.0125. (+19 more)

### Community 27 - "ParseError"
Cohesion: 0.18
Nodes (10): match_option_in_text(), parse_decision(), ParseError, Exception, Strict JSON enum parser for {value, reason}., Raised when the model output is not a valid JSON decision object., Diag-only: map free text onto exactly one pool option. Not the counted parser., _reject_duplicates() (+2 more)

### Community 29 - "dispatch.py"
Cohesion: 0.06
Nodes (69): main(), CLI: analysis dispatch for H1-H4 on the locked cell identity., critical_mass(), d1_funnel(), _agg(), d5_prepared(), gate_table(), prepared_valid_cm() (+61 more)

### Community 30 - "2. Ashery protocol (as implemented in public code + paper)"
Cohesion: 0.33
Nodes (6): 2.1 Two runners (`runner.py`), 2.2 Emergence path (`bias_runner` → `population`), 2.3 CM path (`committed_runner` → prepared → `committed`), 2.4 W by experiment (paper vs shipped config), 2.5 What Ashery deliberately does *not* do for CM, 2. Ashery protocol (as implemented in public code + paper)

### Community 31 - "Diag ladder and path to `pilot-run`"
Cohesion: 0.11
Nodes (17): Diag ladder and path to `pilot-run`, Early stop vs Ashery time-to-convention, Extra seeds (repeat Phase A shape, schema only) — done (indices 1–3), Operator notes, Phase A decode (Mixing, emergence, seed 0, \(N=24\), \(H=5\), letters, cap 400), Phase A — done (all six), Phase B — one-factor, **JSON schema only** — done (seed 0, cap 400), Phase C — readout (2026-09-12) (+9 more)

### Community 32 - "4. Proposed thesis change (Ashery-faithful)"
Cohesion: 0.33
Nodes (6): 4.1 Design locks to adopt, 4.2 Suggested W=10 alphabet (to lock later), 4.3 Code changes required (when we implement — not done yet), 4.4 What we keep from current thesis (still valuable), 4.5 Trade-offs (explicit), 4. Proposed thesis change (Ashery-faithful)

### Community 34 - "Ashery mixing baseline — validation plan (2026-07-20)"
Cohesion: 0.14
Nodes (13): 1. Verdict, 2. What we can / cannot match, 3. Staged design (cheap → informative), 4. Success criteria (practical), 5. Sequencing vs Centola-3 pilot, 6. Cost note, Ashery mixing baseline — validation plan (2026-07-20), Do **not** expect 1:1 figure match (+5 more)

### Community 35 - "orchestration.py"
Cohesion: 0.06
Nodes (58): main(), CLI: pilot batch runner — 12 attempted runs/topology per program. `--program…, ArgumentParser, ensure_campaign_files(), load_config(), ModelSpec, resolve_model(), current_commit() (+50 more)

### Community 37 - "2. What we did (procedure)"
Cohesion: 0.29
Nodes (7): 2.1 Environment, 2.2 Provider discovery (probe), 2.3 Failed first smokes (before config fix), 2.4 Root-cause check, 2.5 Config changes applied, 2.6 Successful smokes (after fix), 2. What we did (procedure)

### Community 38 - "3. Path taken (chronology)"
Cohesion: 0.29
Nodes (7): 3.1 Starting point (post C-05), 3.2 Failed path: OpenRouter pilot under load, 3.3 Switch to Together AI, 3.4 First Together proof (`--limit 3`, options still A–J), 3.5 Critical finding: label pool mismatch, 3.6 Ops / tooling lessons, 3. Path taken (chronology)

### Community 39 - "chat_completion_kwargs"
Cohesion: 0.33
Nodes (4): json_schema_for_options(), chat_completion_kwargs(), openai_extra_body(), Any

### Community 43 - "AsyncClientAdapter"
Cohesion: 0.13
Nodes (6): AsyncClientAdapter, LLMClient, LLMResponse, Protocol, TechCheckProbeTests, complete()

### Community 49 - "test_json.py"
Cohesion: 0.24
Nodes (4): OpenAICompatClient, build_user_prompt(), format_history(), ClientTests

### Community 52 - "tech_check.py"
Cohesion: 0.20
Nodes (15): classify_error(), BaseException, draw_pool(), prompt_template_hash(), Canonical Ashery observer prompt with JSON enum instruction., evaluate_pass(), _fixture_options(), _is_serve_startup() (+7 more)

### Community 56 - "DirtyWorktreeError"
Cohesion: 0.29
Nodes (3): DirtyWorktreeError, Exception, Counted campaign writes require a clean Git worktree.

## Knowledge Gaps
- **188 isolated node(s):** `Locks (mirrored in `config.yaml`)`, `Commands`, `Coverage gate (applies at every phase exit)`, `Architecture principles (bindings for all phases)`, `Scaffold snapshot (2026-07-13)` (+183 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 389 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `render_watch_layout()` connect `test_health.py` to `DashboardState`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `load_config()` connect `orchestration.py` to `run.py`, `config.py`, `campaign.py`, `test_health.py`, `MockLLMClient`, `TechCheckCliTests`, `test_json.py`, `tech_check.py`, `test_analysis.py`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `read_meta()` connect `MockLLMClient` to `run.py`, `memory_decision.py`, `orchestration.py`, `common.py`, `test_analysis.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `execute_run_async()` (e.g. with `AsyncLLMClient` and `RunPaths`) actually correct?**
  _`execute_run_async()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `MockLLMClient` (e.g. with `JsonEnumTests` and `DyadGatherTests`) actually correct?**
  _`MockLLMClient` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Locks (mirrored in `config.yaml`)`, `Commands`, `Coverage gate (applies at every phase exit)` to the rest of the system?**
  _188 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `run.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06455696202531645 - nodes in this community are weakly interconnected._