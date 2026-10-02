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


## Main campaign data backup

The Yen `experiment` campaign snapshot packed on 2026-10-02 is backed up as an
asset of the draft release `main-run-20261002` in this private GitHub repository.
Raw artifacts remain gitignored; cloning the repository does not download them.
The campaign's `config.snapshot.yaml` records the run configuration.

- Archive: `runs_experiment_20261002T174203Z.tar.gz`
- Archive size: 1,091,965,912 bytes
- SHA-256: `99ea2cad05f999856ab562099905882be205b982840dab455600bec7151262ba`
- Contents: 7,712 files, 10,590,595,889 uncompressed bytes
- Local campaign directory: `data/runs/experiment/`

Restore from the repository root with GitHub CLI access to the private release.
Keep at least 12 GB free and check that `data/runs/experiment/` does not already
exist before extracting:

```bash
mkdir -p data/runs
gh release download main-run-20261002 \
  --repo jannikend99/llm-convention-topology \
  --pattern runs_experiment_20261002T174203Z.tar.gz --dir data/runs
shasum -a 256 data/runs/runs_experiment_20261002T174203Z.tar.gz
# Compare the result with the SHA-256 above before extracting.
tar -xzf data/runs/runs_experiment_20261002T174203Z.tar.gz -C data/runs
```
