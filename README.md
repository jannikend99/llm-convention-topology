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
python run_one.py --program emergence --model mock --topology mixing --seed-index 0 --artifact-root /tmp/campaign
```

Yen submit uses `jobs/thesis_vllm.slurm` from JupyterHub. This package does not submit jobs.

Campaign artifacts: `data/runs/<campaign>/` on a laptop (gitignored), or `--artifact-root` on scratch.
