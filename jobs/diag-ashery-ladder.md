# Diag ladder: Ashery mixing, then one-factor steps

Not confirmatory. Campaign names must start with `diag-`. Counted locks in `config.yaml` stay \(N=48\), \(H=12\), strings, JSON schema. Do not submit `experiment`.

Use only if all four tech jobs (`DIAG_TECH_INTERACTIONS=5`) returned HTTP 200 and schema-valid JSON.

Yen worktree must be clean (`git status --porcelain` empty) or `run_main.py` exits 2. Submit with `sbatch -G 2`; the script default is `-G 1`. Do not set `CAMPAIGN` when using `DIAG_LADDER` (the job sets one campaign per cell). Do not combine `DIAG_LADDER` with `DIAG_TECH_INTERACTIONS`.

The job script always sets `NCCL_P2P_DISABLE=1`, passes it into Apptainer, and appends `--disable-custom-all-reduce`. It prints those extras in the Slurm `.out`. If the vLLM log only repeats engine wait / `shm_broadcast` for 7 minutes with no `startup complete`, the job exits instead of waiting 30 minutes. `scancel` a current tech job that already matches that pattern; resubmit after pull.

One Slurm job loads **one model once**, then runs several cells against the same vLLM. GPU cap 4 with `tp: 2`: at most two such jobs run; the rest queue.

`scancel` stops the **whole job**, including cells that have not started. During Phase 1 parse, do not scancel if you still want schema on that model. Let a dead cell hit cap 400, then the next cell starts. Parse still uses the JSON-enum prompt; A vs B only changes `response_format` and the parser.

Before submit, clear leftovers that would fail the job:

```bash
unset CAMPAIGN DIAG_TECH_INTERACTIONS
```

## Shared knobs

Mixing, emergence, one seed (`SEED_FROM=0`, `SEED_TO=1`), \(T=0.5\), cap **400**. Do not run to 5000. Do not start WS/BA.

Tendency (when to `scancel` a cell / the job):

- \(N=24\): at \(t\approx 80\), last50 and trailing-72. If last50 ≤ 10/50 and trailing-72 < 25 → stop that cell.
- \(t\approx 150\): if still fragmented, stop. Do not wait for 400.
- Keep to 400 only if last50 is rising or trailing-72 ≥ 40.
- \(N=48\): gate window is 144 (need ≥137). Same last50 rule at \(t\approx 80\) / 150; do not wait for a full 144-window if last50 is already dead.

## Phase 1 — A vs B (decode)

Ashery-like base: \(N=24\), \(H=5\), letters `Q M X Y F J P R C D`.

| Cell | Decode | Campaign |
| --- | --- | --- |
| A | Parse (no `response_format`; match text to options) | `diag-ashery-parse-<shorthand>` |
| B | JSON enum `value`/`reason` | `diag-ashery-schema-<shorthand>` |

Models: `nemotron35_lightning`, `gemma4_31b`, `qwen38_27b`, `mistral_small32`.

Four jobs (not eight). Each job: parse, then schema, same loaded weights.

```bash
cd /scratch/shared/jendress/exp/llm-convention-topology
git pull
git log -1 --oneline
git status --porcelain

unset CAMPAIGN DIAG_TECH_INTERACTIONS

export PROGRAM=emergence
export SEED_FROM=0
export SEED_TO=1
export TOPOLOGY=mixing
export DIAG_LADDER=ab
export DIAG_CAP=400
export NCCL_P2P_DISABLE=1
export VLLM_EXTRA_ARGS="--disable-custom-all-reduce"

for MODEL in nemotron35_lightning gemma4_31b qwen38_27b mistral_small32; do
  export MODEL
  sbatch -G 2 --mem=64G --export=ALL jobs/thesis_vllm.slurm
done
```

Readout: compare parse vs schema **within** model. Tendency: `H=5` and `W, NEED = 72, 69`.

Pickle glob: `/scratch/shared/jendress/runs/<CAMPAIGN>/runs/<shorthand>/mixing/*.pkl`

Do not start Phase 2 until this readout.

## Phase 2 — one knob at a time

Freeze `DIAG_DECODE` per model (`parse` or `json_schema`) from Phase 1. Skip a model if both A and B were dead.

Three cells, still one load per model:

| Cell | Change | Held fixed | Campaign |
| --- | --- | --- | --- |
| H | \(H=12\) | \(N=24\), letters, frozen decode | `diag-h12-<parse\|schema>-<shorthand>` |
| N | \(N=48\) | \(H=5\), letters, frozen decode | `diag-n48-<parse\|schema>-<shorthand>` |
| Strings | 5-char pool | \(N=24\), \(H=5\), frozen decode | `diag-strings-<parse\|schema>-<shorthand>` |

Same stop rule. For the N=48 cell use last50; trailing window is 144.

Walltime: default script is 12h. Phase 2 is three cells (one is \(N=48\)) → submit `-t 24:00:00`.

```bash
unset CAMPAIGN DIAG_TECH_INTERACTIONS

export PROGRAM=emergence
export SEED_FROM=0
export SEED_TO=1
export TOPOLOGY=mixing
export DIAG_LADDER=one-factor
export DIAG_CAP=400
export NCCL_P2P_DISABLE=1
export VLLM_EXTRA_ARGS="--disable-custom-all-reduce"

# Example: Gemma parse survived Phase 1. Repeat per living model with that model's decode.
export MODEL=gemma4_31b
export DIAG_DECODE=parse
sbatch -G 2 --mem=64G -t 24:00:00 --export=ALL jobs/thesis_vllm.slurm
```

Campaign tag is `schema` when `DIAG_DECODE=json_schema`.

## Later (not this ladder)

Combined knobs (H and N and strings together). Study 2 CM. Confirmatory `experiment`.
