# llm-convention-topology

Thesis experiment code for network topology × convention emergence and stability under committed-minority perturbation in LLM Naming Game populations.

Counted path: local OpenAI-compatible vLLM (`provider: openai_compat`) or `mock`. Protocol locks live in the thesis specs, mirrored by `config.yaml`.

## Locks (mirrored in `config.yaml`)

| Item | Value |
| --- | --- |
| N | 48 |
| H | 12 |
| Topologies | mixing, random_regular, lattice, watts_strogatz, barabasi_albert |
| Gate | first t≥144 with ≥137/144 successes, or cap 5000 |
| k | {2,4,6,8,10,12} |
| Seeds | 32 per cell, `sampling_plan=fixed_attempted` |
| Study 2 | prepared, `t_cm_start=0` |

## Commands

```bash
python -m pytest tests -q
python run_main.py --print-jobs
python run_main.py --model mock --program emergence --campaign technical-smoke --artifact-root /tmp/campaign --seed-from 0 --seed-to 1
python run_one.py --program emergence --model mock --topology mixing --seed-index 0 --artifact-root /tmp/campaign
```

`--print-jobs` prints the confirmatory grid (shorthand + HF `model_id`). Fit/timing jobs use `--campaign pilot-run` so artifacts are not `experiment`. `config.yaml` `run.campaign: experiment` stays the confirmatory default.

Yen: clone/pull `/scratch/shared/jendress/exp/llm-convention-topology`, then `sbatch jobs/thesis_vllm.slurm` from the repo root in the Jupyter Terminal. First live campaign is `technical-smoke`. Operator packet: thesis `specs/yen-configuration.md`. This package does not submit jobs. `notebooks/yen_jobs.ipynb` is archived.

Campaign artifacts: `data/runs/<campaign>/` on a laptop (gitignored), or `--artifact-root` on scratch (`/scratch/shared/jendress/runs/<campaign>/`; do not append the campaign name twice).
