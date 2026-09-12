# Diag ladder: Ashery-like mixing (after tech smokes)

Not confirmatory. Campaign names must start with `diag-`. Counted locks in `config.yaml` stay \(N=48\), \(H=12\), strings, JSON schema. Do not submit `experiment`.

Use only if all four tech jobs (`DIAG_TECH_INTERACTIONS=5`) returned HTTP 200 and schema-valid JSON.

## Cells (one seed, mixing, emergence)

Ashery-like shared knobs: \(N=24\), \(H=5\), letter pool `Q M X Y F J P R C D`, \(T=0.5\), Mixing, one `seed_index=0`.

| Cell | Decode | Campaign pattern |
| --- | --- | --- |
| A | Ashery parse (no `response_format`; match text to options) | `diag-ashery-parse-<shorthand>` |
| B | Thesis structured output (JSON enum `value`/`reason`) | `diag-ashery-schema-<shorthand>` |

Models (after tech green): `nemotron35_lightning`, `gemma4_31b`, `qwen38_27b`, `mistral_small32`.

Cap **400** interactions (~800 LLM calls). Gate window at \(N=24\) is \(3N=72\) (need ≥69 successes in 72). Kill earlier on the tendency rule below. Do not run to 5000.

## Tendency (when to stop)

Same collapse we saw on Gemma 31B showed by \(t\approx 50\)–\(100\). At \(N=24\) the first full gate window is \(t=72\).

- \(t\approx 80\): last50 and trailing-72. If last50 ≤ 10/50 and trailing-72 < 25 → stop that cell.
- \(t\approx 150\): if still fragmented, stop. Do not wait for 400.
- Keep to 400 only if last50 is rising or trailing-72 ≥ 40.

## Commands (after code Go + `git pull`)

Env flags below are live on experiment `main` after pull (`DIAG_N`, `DIAG_DECODE`, `DIAG_H`, `DIAG_POOL`, `DIAG_CAP`). Counted `config.yaml` is unchanged.

```bash
cd /scratch/shared/jendress/exp/llm-convention-topology
git pull
git log -1 --oneline

export PROGRAM=emergence
export SEED_FROM=0
export SEED_TO=1
export TOPOLOGY=mixing
export DIAG_N=24
export DIAG_H=5
export DIAG_POOL=letters
export DIAG_CAP=400
export NCCL_P2P_DISABLE=1
export VLLM_EXTRA_ARGS="--disable-custom-all-reduce"
```

Parse cells:

```bash
export DIAG_DECODE=parse
for MODEL in nemotron35_lightning gemma4_31b qwen38_27b mistral_small32; do
  export MODEL
  export CAMPAIGN="diag-ashery-parse-${MODEL}"
  sbatch -G 2 --mem=64G --export=ALL jobs/thesis_vllm.slurm
done
```

Schema cells (same Ashery knobs, JSON enum):

```bash
export DIAG_DECODE=json_schema
for MODEL in nemotron35_lightning gemma4_31b qwen38_27b mistral_small32; do
  export MODEL
  export CAMPAIGN="diag-ashery-schema-${MODEL}"
  sbatch -G 2 --mem=64G --export=ALL jobs/thesis_vllm.slurm
done
```

GPU cap 4 with `tp: 2`: at most two jobs run; the rest queue. Eight cells overnight is the whole ladder. Do not start WS/BA or \(H=12\)/strings until A vs B is read.

## Readout

Pickle glob:

`/scratch/shared/jendress/runs/<CAMPAIGN>/runs/<shorthand>/mixing/*.pkl`

Tendency script: same as the Gemma diags, but `H=5` and `W, NEED = 72, 69`. Compare parse vs schema **within** model before comparing models.

## Out of scope tonight

One-factor steps toward the thesis lock (\(H=12\), strings, \(N=48\)) after A/B. Study 2 CM. Confirmatory `experiment`.
