# Diag ladder and path to `pilot-run`

Not confirmatory. Campaign names for this ladder start with `diag-`. Counted locks in `config.yaml` stay \(N=48\), \(H=12\), strings, JSON schema until a **freeze** (Phase D). Do not submit `experiment` from this file.

Goal of the path: get **emergence** under JSON schema, keep wall time honest, then use the two A40s fully, then widen topology and Study 2, then time a **`pilot-run`**. `pilot-run` is the last campaign before confirmatory `experiment`.

## Recommended order (why)

1. **Mixing + JSON schema first.** Without a convention on mixing, lattice/random and committed minorities have nothing to perturb.
2. **Readout, then freeze knobs.** Do not retune \(H\), \(N\), or the pool after GPU or topology work starts. Otherwise you cannot tell protocol from throughput.
3. **GPU fill next.** Concurrency (`in_flight_limit`, `max_num_seqs`, concurrent runs) only after the protocol is frozen. Filling a protocol that still changes wastes the fit.
4. **All five topologies before Study 2.** Mixing, random-regular, lattice, Watts–Strogatz, Barabási–Albert (locked `network.topologies`). Study 2 needs a pre-perturbation gate.
5. **Study 2 CM size only**, only for models that gated in Study 1.
6. **`pilot-run` last.** Wall-clock per slice, peak memory, JSON-enum ≥200, same frozen protocol. Then `experiment`.

Do not skip to topologies, CM, or `experiment` while Olmo/GLM tech or Phase B is open.

**Wall time:** every `sbatch` in A–B stays **≤ 12 h**. Phase B is one job with all three cells (including \(N=48\)); do not split. Overnight: queue Olmo/GLM Phase A as soon as tech is green, then Phase B for all six.

## Six models

Thinking off, BF16, 2× A40, `tp: 2`. Registry commit `e4cf196`.

| Shorthand | Checkpoint | Role now |
| --- | --- | --- |
| `gemma4_31b` | `google/gemma-4-31B-it` | Phase A schema **gated** |
| `qwen38_27b` | `Qwen/Qwen3.8-27B` | Phase A schema **gated** |
| `nemotron35_lightning` | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16` | Phase A schema **fragmented** (valid JSON); parse almost gated |
| `mistral_small32` | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | Phase A schema **fragmented** (800/800 valid JSON); parse died on the matcher |
| `olmo31_32b` | `allenai/Olmo-3.1-32B-Instruct` | Tech jobs **593629**; Phase A not started |
| `glm4_32b` | `zai-org/GLM-4-32B-0414` | Tech jobs **593630**; Phase A not started |

## Phase A — done for the first four; still open for Olmo and GLM

### Tech check

vLLM 0.28.0, 2× A40, `HF_HOME=/scratch/shared/jendress/models`. Green: `POST /v1/chat/completions` **200** and `Received request`. `min_frames` / Triton / `EngineDeadError` on shutdown are noise.

| Shorthand | Job | Note |
| --- | --- | --- |
| `nemotron35_lightning` | 593515 | Ampere TP=2 |
| `gemma4_31b` | 593516 | Ampere TP=2 |
| `qwen38_27b` | 593588 | prefetch on yen1; GPU nodes have no HF auth |
| `mistral_small32` | 593591 | mistral tokenizer/config/load; no `chat_template_kwargs` |
| `olmo31_32b` | 593629 | in flight (2026-09-12) |
| `glm4_32b` | 593630 | in flight (2026-09-12) |

Prefetch: `hf download` (not `huggingface-cli`). Reuse of `diag-tech-*` after a `config.yaml` change → snapshot hash mismatch; new campaign name.

Yen worktree must be clean. `sbatch -G 2`. Do not set `CAMPAIGN` with `DIAG_LADDER`. Do not combine `DIAG_LADDER` with `DIAG_TECH_INTERACTIONS`. Ampere: `NCCL_P2P_DISABLE=1` and `--disable-custom-all-reduce`. GPU cap 4 with `tp: 2`: at most two such jobs at once.

### Phase A decode (Mixing, emergence, seed 0, \(N=24\), \(H=5\), letters, cap 400)

| Cell | Decode | Campaign |
| --- | --- | --- |
| Parse | no `response_format`; match text to options | `diag-ashery-parse-<shorthand>` |
| Schema | JSON enum `value`/`reason` | `diag-ashery-schema-<shorthand>` |

First four: **done**. Do not rerun.

Olmo and GLM: one job each, parse then schema on the same load. Start only after tech **200**.

```bash
cd /scratch/shared/jendress/exp/llm-convention-topology
git pull
git status --porcelain
unset CAMPAIGN DIAG_TECH_INTERACTIONS
export PROGRAM=emergence SEED_FROM=0 SEED_TO=1 TOPOLOGY=mixing
export DIAG_LADDER=ab DIAG_CAP=400
export NCCL_P2P_DISABLE=1 VLLM_EXTRA_ARGS="--disable-custom-all-reduce" HF_HOME=/scratch/shared/jendress/models
for MODEL in olmo31_32b glm4_32b; do
  export MODEL
  sbatch -G 2 --mem=64G --export=ALL jobs/thesis_vllm.slurm
done
```

Readout: parse vs schema **within** model. Gate window for \(N=24\): need 69/72. Pickles: `/scratch/shared/jendress/runs/<CAMPAIGN>/runs/<shorthand>/mixing/*.pkl`.

`scancel` kills the **whole** job (remaining cells too). During Phase A parse, do not scancel if you still want schema on that model.

### Early stop vs Ashery time-to-convention

Abort only if the trajectory is already **comparable in length** to Ashery and still cold. A stop at \(t=80\) is ~7 expected pairings per agent (\(N=24\)) — too short to say the run does not follow Ashery.

Ashery (mixing, \(N=24\), \(W=10\), \(H=5\)): most models reach global consensus by **~15 population rounds**. Taking a round as \(N/2\) pairwise games (each agent once in expectation) that is **~180 interactions**. Gemma/Qwen schema gated in that band (\(t=177\)–\(215\)). Cap 400 is ~2× that horizon — enough to call a run slower than Ashery, not a stub.

Nemotron **parse** took off only after \(t\approx 300\) (last50 = 6 at \(t=150\), 49 at \(t=400\)). A \(t=150\) kill would have dropped a late convention and would not match Ashery’s full rise.

**Do not stop before a full gate window and the Ashery horizon:**

- \(N=24\): no abort before \(t=180\) (except matcher death: zero valid labels, as Mistral parse at \(t=7\)).
- \(N=48\): no abort before \(t=360\) (15 × \(N/2\)), except matcher death.

After that horizon, schema cells may stop if last50 ≤ 12 **and** last50 is not up versus \(t=180\). Otherwise continue to cap 400.

That way a “dead” label means: we watched an Ashery-length emergence window and still saw no takeoff — not that we cut at a tiny prefix.

## Phase B — one-factor, **JSON schema only**, all six

After Olmo/GLM Phase A readout (schema must at least emit valid JSON; gate is not required — Mistral/Nemotron still go in).

Freeze `DIAG_DECODE=json_schema`. Three cells, one load:

| Cell | Change | Held fixed | Campaign |
| --- | --- | --- | --- |
| H | \(H=12\) | \(N=24\), letters | `diag-h12-schema-<shorthand>` |
| N | \(N=48\) | \(H=5\), letters | `diag-n48-schema-<shorthand>` |
| Strings | 5-char pool | \(N=24\), \(H=5\) | `diag-strings-schema-<shorthand>` |

Still Mixing, emergence, seed 0, cap 400. One job, three cells, **12 h**. Do not split the \(N=48\) cell; Phase A schema at 400 interactions was ~1 h after load.

```bash
unset CAMPAIGN DIAG_TECH_INTERACTIONS
export PROGRAM=emergence SEED_FROM=0 SEED_TO=1 TOPOLOGY=mixing
export DIAG_LADDER=one-factor DIAG_DECODE=json_schema DIAG_CAP=400
export NCCL_P2P_DISABLE=1 VLLM_EXTRA_ARGS="--disable-custom-all-reduce"
export MODEL=<shorthand>
sbatch -G 2 --mem=64G -t 12:00:00 --export=ALL jobs/thesis_vllm.slurm
```

Queue overnight after Olmo/GLM Phase A. Two jobs at a time (GPU cap).

Do **not** cross parse × H/N/strings here.

## Extra seeds (repeat Phase A shape, schema only)

After Phase A for Olmo/GLM and after Phase B is queued or done: more `seed_index` values, **JSON schema**, Mixing, \(N=24\), \(H=5\), letters, cap 400. Question: was seed 0 luck?

Do **not** rerun parse×schema × six models. Schema only. Start with **seeds 1–3** (`SEED_FROM=1`, `SEED_TO=4`). One job per model if the runner walks the seed range in ≤ 12 h; otherwise one seed per job.

Priority if the queue is tight: Mistral and Nemotron schema first (n=1 fragmentation), then Gemma/Qwen (gate robustness), then Olmo/GLM if their Phase A schema lived.

## Thinking on (queue behind A–B and extra seeds)

Not a freeze knob. Same Ashery-base cell as Phase A schema: Mixing, emergence, seed 0, \(N=24\), \(H=5\), letters, JSON schema, cap 400. Compare to thinking-off schema on the same checkpoint (F25). Do not run parse, Phase B, or the counted \(N=48\) / \(H=12\) / strings cell.

Only pairs that exist:

| Shorthand | Checkpoint | Note |
| --- | --- | --- |
| `qwen38_27b_think` | `Qwen/Qwen3.8-27B` | same weights as `qwen38_27b`; `enable_thinking` |
| `gemma4_31b_think` | `google/gemma-4-31B-it` | same weights as `gemma4_31b`; `enable_thinking` |
| `nemotron35_lightning_think` | Lightning 30B-A3B BF16 | same weights; `enable_thinking=true`; parser `nemotron_v3` |
| `olmo31_32b_think` | `allenai/Olmo-3.1-32B-Think` | **other** checkpoint than Instruct; always on; parser `olmo3` |

Mistral Small 3.2 and GLM-4-32B-0414 have no toggle. Magistral / GLM-Z1 are different models; skip them here. Do not add these shorthands to `jobs.models`.

Prefetch Olmo Think on **yen1** before the GPU job (`HF_HOME=/scratch/shared/jendress/models`). Gemma/Qwen/Lightning need no new download.

Thinking is slower. Lightning Think and Olmo Think previously died on empty JSON / client timeout (120 s). Rerun those two only, with a **new** campaign name (config snapshot changed: `max_tokens` 4096, `thinking_token_budget` 2048, client timeout 300 s when `thinking`). Do not reuse `diag-ashery-schema-nemotron35_lightning_think` or `diag-ashery-schema-olmo31_32b_think`. Gemma Think and Qwen Think already gated; do not rerun.

```bash
cd /scratch/shared/jendress/exp/llm-convention-topology
git pull
git log -1 --oneline
git status --porcelain
# worktree must be empty. If graphify-out/ is untracked: rm -rf graphify-out

unset CAMPAIGN DIAG_LADDER DIAG_TECH_INTERACTIONS
export PROGRAM=emergence SEED_FROM=0 SEED_TO=1 TOPOLOGY=mixing
export DIAG_N=24 DIAG_H=5 DIAG_POOL=letters DIAG_DECODE=json_schema DIAG_CAP=400
export NCCL_P2P_DISABLE=1 VLLM_EXTRA_ARGS="--disable-custom-all-reduce"
export HF_HOME=/scratch/shared/jendress/models

export MODEL=nemotron35_lightning_think
export CAMPAIGN=diag-ashery-schema-tok-nemotron35_lightning_think
sbatch -G 2 --mem=64G --export=ALL jobs/thesis_vllm.slurm

export MODEL=olmo31_32b_think
export CAMPAIGN=diag-ashery-schema-tok-olmo31_32b_think
sbatch -G 2 --mem=64G --export=ALL jobs/thesis_vllm.slurm

unset CAMPAIGN
```

Submit two jobs only if two GPU slots are free (Yen cap 4 GPUs, `tp: 2`). Do not `scancel` running A–B/seed jobs. Olmo Think weights should already be in `HF_HOME`; Lightning uses the instruct weights. Registry + timeout/budget live in the commit that adds `thinking_token_budget`.

```bash
export HF_HOME=/scratch/shared/jendress/models
hf download allenai/Olmo-3.1-32B-Think
```

## Phase C — readout (no new jobs)

Compare schema cells: base Phase A vs H vs N vs strings.

Decide, per model or jointly:

- Does JSON schema produce a convention?
- Which one knob (if any) moves last50 / trailing-window?
- Drop a model only if schema never coordinates **and** Phase B does not help.

Write the freeze in chat and then into `config.yaml`. Do not edit counted YAML during B.

## Phase D — freeze protocol

One JSON-schema recipe for the models that stay. Candidates: keep counted \(N=48\), \(H=12\), strings if Phase B shows they still gate (Gemma/Qwen already gated at Ashery-like \(N=24\), \(H=5\), letters). If only letters + \(H=5\) gates, that is a **lock change** (specs + YAML), not a silent diag default.

Output of D: listed models, \(N\), \(H\), pool, decode=`json_schema`, temperature 0.5. That set is used for E–G and `pilot-run`.

## Phase E — GPU fill (Mixing only, frozen protocol)

Not a hypothesis factor. Measure and raise:

- `in_flight_limit`, `max_num_seqs`
- concurrent naming-game runs against **one** vLLM (`max_concurrent_runs`, slice length)
- peak VRAM, tokens/s, time per 400 (or 144-window) interactions

Stay on **2× A40**, `tp: 2`. Do not move counted jobs to H200. Two such jobs are the Yen GPU-cap. The win is a **busy** engine (batch), not a third card.

Stop when GPU util is high and JSON-enum stays valid. Record the numbers in the serve profile. Campaign folder: still `diag-*` or a named fit campaign — **not** `pilot-run` yet if topology/CM are untested.

## Phase F — all topologies (Study 1 shape)

Same frozen protocol, emergence, JSON schema. **All five** locked graphs, one seed first:

`mixing`, `random_regular`, `lattice`, `watts_strogatz`, `barabasi_albert`

Mixing is already known from A–B. Still run it on the freeze so the five share one protocol hash. Then more seeds only on topologies that can still gate.

## Phase G — Study 2 committed-minority size

Only models that passed the Study 1 gate on that topology. Mixing first (human CM benchmark). \(k\) from the locked `k_set`. Placement deferred. Cap/horizon from specs (`phase2_horizon` 1000).

Skip G for a model that never gated in F.

## Phase H — `pilot-run` (last before confirmatory)

Campaign id **`pilot-run`**. Frozen protocol, filled GPU profile, Centola-3 + a small CM smoke if G looked sane.

Measure: JSON-enum ≥200 completions, wall time per slice, peak memory, startup, throughput. Never confirmatory analysis.

After H is green: `experiment` (full \(n=32\) grid). That is **not** this ladder.

## Operator notes

```bash
unset CAMPAIGN DIAG_TECH_INTERACTIONS
```

Logs:

```bash
squeue -u jendress
tail -F jobs/thesis_vllm_<ID>.out /scratch/shared/jendress/vllm/thesis_<ID>.log
```
