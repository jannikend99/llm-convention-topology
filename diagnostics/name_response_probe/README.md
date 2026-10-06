# Controlled name-response probe

Small auxiliary diagnostic. It does not run a population, use a topology, or modify
the counted Study 1/2 pipeline. It tests responses to fixed counterfactual histories.

## Questions and budget

For OLMo, Qwen, and Gemma, independently cross:

- Challenger name: `dicfv` or `lwlsi`; the other name is the incumbent.
- Prompt option order: incumbent first or challenger first.
- JSON-schema enum order: incumbent first or challenger first.

Four 12-round histories × eight factorial conditions × three sampling seeds =
**96 requests per model; 288 across three models**. Output cap is 512 tokens,
temperature 0.5, thinking disabled, as in the existing model profiles. No automatic
retries. Calls run sequentially; the Slurm array runs one model at a time.
The GPU allocation is two A40s per model. Model loading may dominate runtime.
The two-hour job limit is a resource bound, not a measured runtime guarantee.

Histories use abstract incumbent `I` and challenger `C` roles:

- `incumbent_control`: 12 successful I/I encounters.
- `mismatch_oldest`: one I/C mismatch, followed by 11 I/I encounters.
- `mismatch_latest`: 11 I/I encounters, followed by one I/C mismatch.
- `repeated_mismatch`: six I/I encounters, followed by six I/C mismatches.

The old/latest pair has identical counts and total score (1050). Only the order of
encounters changes. Moving a mismatch also moves its -50 payoff: this isolates
**episode recency**, not partner-response recency separately from payoff recency.
All own historical choices are I. Own-last-choice effects, changed payoff rules,
other name pairs, and network mechanism sufficiency are deferred.

The runner reuses the canonical prompt, strict parser, and model profiles. It
renders prompt options independently of schema enum options. Same sampling seeds
are paired across conditions; request order is deterministically shuffled.
Seeds do not guarantee identical randomness under changed prompts or GPU kernels.

## Run on Yen

Use the JupyterHub Terminal at <https://yen1.stanford.edu> as `jendress`.
Update the existing private experiment checkout through Git before submission.
An optional upload packet contains this folder only.

```bash
cd /scratch/shared/jendress/exp/llm-convention-topology
git pull --ff-only origin main
mkdir -p /scratch/shared/jendress/vllm

# Offline design check; no GPU inference.
/scratch/shared/jendress/venvs/thesis/bin/python \
  diagnostics/name_response_probe/run.py --model olmo31_32b --dry-run

# Recommended first battery: three models, one allocation at a time.
sbatch --array=0-2%1 diagnostics/name_response_probe/probe.slurm
squeue -u jendress
```

Optional smaller entry point: OLMo only, one seed, **32 requests**. This is a
technical/exploratory check, not enough to interpret unstable differences.

```bash
sbatch diagnostics/name_response_probe/probe.slurm --model olmo31_32b --repeats 1
```

Array task 0 is OLMo, 1 Qwen, 2 Gemma. To rerun only one model with three seeds:

```bash
sbatch diagnostics/name_response_probe/probe.slurm --model qwen38_27b
```

The script requires the existing thesis venv and cached
`/scratch/shared/jendress/images/vllm-openai-v0.28.0.sif`. It uses offline HF mode:
missing pinned checkpoints fail instead of downloading weights. It explicitly
pins both model and tokenizer revision to `config.yaml` and uses context 8192,
BF16, TP=2. Serving capacity is reduced to eight sequences; sampling is unchanged.
Historical jobs did not explicitly pass revision in their launcher. Do not claim
exact historical checkpoint identity without checking their cache provenance.

## Results, resume, and interpretation

Results live under
`/scratch/shared/jendress/runs/name-response-probe/live/<model>/<design-hash>/`.
Mock results use a separate `mock/` tree. Each battery saves:

- `design.json`: exact prompts, histories, enum orders, seeds, profile, source hashes.
- `responses.jsonl`: raw response, choice, reason, token usage, and failures.
- `attempts.jsonl`: durable request reservations for bounded resume.
- `servers.jsonl`: advertised server models on each inference session.
- `summary.csv`: per-condition challenger shares and valid/invalid denominators.
- `paired_contrasts.csv`: complete-pair differences in percentage points.

Contrast signs: challenger `lwlsi minus dicfv`; prompt/schema `C-first minus
I-first`; history `latest minus oldest`. These are balanced descriptive contrasts,
not estimated shares of the cause of a network outcome. Inspect individual cells
for interactions between name, history, and order. Three seeds per cell provide
a screen for large, consistent effects; they do not establish small effects or
their absence. Generated reasons are recorded explanations, not causal evidence.

Changing repeat count creates a separate battery; a one-seed check is not reused
as the first seed of the three-seed battery. Unchanged batteries resume completed
records without resending them. Failed requests consume budget. A request whose
process was interrupted after reservation is marked unknown/invalid on resume and
is never resent. Partial JSONL lines fail visibly rather than being silently
repaired. A writer lock prevents concurrent writes to the same battery. After
three consecutive failures the runner stops; inspect logs before resubmission.
Failed responses produce a nonzero exit code even after remaining cases finish.

Slurm logs: `/scratch/shared/jendress/vllm/name_probe_<array-job>_<task>.out` and
`.err`. Server logs: `/scratch/shared/jendress/vllm/name_probe_<job>_<task>/server.log`.

```bash
sacct -j YOUR_JOB_ID --format=JobID,State,Elapsed,ExitCode
tail -n 60 /scratch/shared/jendress/vllm/name_probe_YOUR_JOB_ID_0.out
```

After completion, download the `name-response-probe` result folder and the Slurm
and server logs. Controlled differences support a mechanism under these fixed
histories. They do not yet show how much that mechanism explains the observed
topology outcomes. That needs a subsequent network sufficiency test.

## Local verification

```bash
python -m unittest discover -s diagnostics/name_response_probe -p 'test_*.py' -v
python diagnostics/name_response_probe/run.py --model olmo31_32b --mock --output /tmp/name-probe
bash -n diagnostics/name_response_probe/probe.slurm
```

Mock chooses the first schema enum option. It must yield +100 pp for schema order
and zero for name assignment, prompt order, and episode recency. Local checks
validate controls, strict response validation, accounting, and resume. They do
not validate GPU serving or measure Yen runtime.
