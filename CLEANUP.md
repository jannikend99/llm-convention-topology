# Cleanup scan — llm-convention-topology

Completed 2026-09-14. P0–P2 items from the scan are done. Graphify map refreshed.

| Item | Action |
| --- | --- |
| Laptop `runs/` (~54 diag campaigns) | Deleted (gitignored; Yen remains SSOT) |
| `archive/pre-rebuild/` | `git rm` tracked files; local blobs removed |
| `jobs/diag-ashery-ladder.md` | Moved to `archive/ops/diag-ashery-ladder.md` |
| `DIAG_*` for every `diag-*` except `diag-tech*` | `campaign_requires_full_diag_knobs` + slurm |
| `run_one.py` | Applies `DIAG_*` / `PILOT_*`; optional `--campaign` |
| `DIAG_LADDER` | Comment: do not export on counted / `pilot-run` N=48 |
| README | Artifact path, `$USER` scratch, Study 2 horizon, keepers, diag knobs |
| `jobs.models` | Four keepers (Gemma, Qwen, Olmo, GLM). Catalog `models:` unchanged |
| `jobs/_yen_scratch.sh` | Shared scratch resolution |
| `fill_r_ladder_eval.py` | No `jendress` USER fallback |
| `memory_decision.py` + unused helpers | Removed |
| Analysis N=24 | Mixed `gate_window` refused; `dynamics.py` uses row `N` |
| Serve YAML split | Skipped on purpose (jobs read R from the same file) |

Do not copy this untracked file onto Yen while jobs require a clean worktree.
