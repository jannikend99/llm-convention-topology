# TypeSafe Jev sidecar

This folder is not part of the counted thesis path. Counted runs stay on localhost vLLM (`run_main.py`, `jobs/thesis_vllm.slurm`). Nothing here changes `config.yaml`, the keeper models, or Yen jobs.

Jev is hosted. There are no weights to serve. Set `TYPESAFE_API_KEY` in the environment. Do not write the key into this repo.

The runner reuses the Naming Game engine: label pool, five topologies, Study 1 (`emergence`), Study 2 (`cm`, k = 5, 10, 14), gate, and artifact writer. Each decision is one TypeSafe Choice over the labels already in the prompt. The client samples one label from Jev's probabilities with the protocol temperature (0.5 sharpens the distribution) and returns the JSON object the existing parser expects. The full distribution is stored in `reason`.

Requests are paced at 1200 per minute, the published account limit. That is 20 requests per second. Concurrent runs exist so the pacer stays full when a single cell is waiting on the network.

Artifacts go to `data/runs/jev-system-one/` inside this experiment repo (gitignored). The campaign name is not `experiment`.

Do not put Jev numbers in the thesis until TypeSafe agrees in writing. The published Master Customer Agreement, section 2.3(f), forbids publishing benchmarks or performance information about the service.

## Run

From the experiment repo root:

```bash
pip install -r typesafe_jev/requirements.txt
export TYPESAFE_API_KEY=...

python typesafe_jev/run_studies.py --dry-run
python typesafe_jev/run_studies.py
```

The default command runs Study 1 and Study 2 on all five topologies and all 32 seeds per cell. A smaller slice:

```bash
python typesafe_jev/run_studies.py --task emergence:mixing:0-1
python typesafe_jev/run_studies.py --studies 1
python typesafe_jev/run_studies.py --studies 2
```

Finished, censored, and failed cells are skipped on a later start. Delete that cell's files under `data/runs/jev-system-one/` to run it again.

`jev-system-one-experiment-fit.md` in this folder is the hosting and fit note. It is not a thesis chapter.
