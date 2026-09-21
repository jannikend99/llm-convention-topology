# llm-convention-topology

Thesis experiment code for network topology × convention emergence and stability under committed-minority perturbation in LLM Naming Game populations.

Counted path: local OpenAI-compatible vLLM (`provider: openai_compat`) or `mock`. Protocol locks live in the thesis specs, mirrored by `config.yaml`.

## Locks (mirrored in `config.yaml`)

| Item | Value |
| --- | --- |
| N | 48 |
| H | 12 |
| Topologies | mixing, random_regular, lattice, watts_strogatz, barabasi_albert |
| Gate | first t≥144 with ≥137/144 successes, or cap 1500 |
| k | {5,10,14} |
| Retry | 5 attempts per player decision |
| Seeds | 32 per cell, `sampling_plan=fixed_attempted` |
| Study 2 | prepared, `t_cm_start=0`, horizon 1500 |

`jobs.models` keepers: `gemma4_31b`, `olmo31_32b`, `qwen38_27b`, `glm4_32b`. Extra entries under `models:` are a catalog (smoke `gemma4_e2b`, think variants). YAML default `run.campaign` is `experiment` with cap 1500. Scout/fit jobs must pass `--campaign` plus `PILOT_*` / `DIAG_*`. A protocol change other than a later increase of `cap_phase1` or `phase2_horizon` needs a new campaign. That increase uses `--extend-bounds` and does not start a new campaign.

## Commands

```bash
python -m pytest tests -q
python run_main.py --print-queue --task emergence:mixing:0-32
python run_main.py --model mock --campaign technical-smoke --artifact-root /tmp/campaign \
  --task emergence:mixing:0-1
python run_one.py --program emergence --model mock --topology mixing --seed-index 0 --artifact-root /tmp/campaign
```

`--print-queue` prints the flattened `--task` list. `--print-jobs` is a deprecation error. Fit/timing jobs use `--campaign pilot-run` so artifacts are not `experiment`. Queue jobs require explicit `--campaign`. Every `diag-*` campaign except `diag-tech*` requires `DIAG_N`, `DIAG_H`, `DIAG_POOL`, `DIAG_DECODE`, and `DIAG_CAP`. Do not export `DIAG_LADDER` on counted or `pilot-run` jobs.

Yen: clone/pull `/scratch/shared/$USER/exp/llm-convention-topology`, then from the repo root in the Jupyter Terminal:

```bash
sbatch --export=ALL jobs/thesis_vllm.slurm -- \
  --campaign technical-smoke --model gemma4_e2b --task emergence:mixing:0-1
```

Operator packet: thesis `specs/yen-configuration.md` and `specs/counted-job-queue.md`. This package does not submit jobs. Ashery ladder notes: `archive/ops/diag-ashery-ladder.md`. Pack downloads: `bash jobs/pack_yen_runs.sh`.

Campaign artifacts: laptop default `data/runs/<campaign>/` (gitignored). Do not use a leftover repo-root `runs/` tree. On Yen pass `--artifact-root /scratch/shared/$USER/runs/<campaign>/` (do not append the campaign name twice).
