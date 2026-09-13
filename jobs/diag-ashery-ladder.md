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

A–B, extra seeds (letters, \(N=24\), \(H=5\)), and the thinking probes are **done**. Do not skip to topologies, CM, or `experiment` while the **lock-cell verification** below is open.

**Wall time:** A–B jobs were **≤ 12 h**. The next Mixing lock-cell jobs use cap 1200; set `-t` from wall-clock after the first seed, not from the old 400-step budget.

## Six models

Thinking off, BF16, 2× A40, `tp: 2`. Registry commit `e4cf196`.

| Shorthand | Checkpoint | Role now |
| --- | --- | --- |
| `gemma4_31b` | `google/gemma-4-31B-it` | **keep** — schema letters \(N=24\) \(H=5\): gate 4/4 seeds |
| `olmo31_32b` | `allenai/Olmo-3.1-32B-Instruct` | **keep** — same cell: gate 4/4 |
| `qwen38_27b` | `Qwen/Qwen3.8-27B` | **keep** — same cell: gate 4/4 |
| `glm4_32b` | `zai-org/GLM-4-32B-0414` | **keep** — same cell: gate 4/4 |
| `nemotron35_lightning` | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16` | **drop for freeze** — gate 2/4 on that cell; late or cap |
| `mistral_small32` | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | **drop for freeze** — gate 1/4; often cap without convention |

## Phase A — done (all six)

### Tech check

vLLM 0.28.0, 2× A40, `HF_HOME=/scratch/shared/jendress/models`. Green: `POST /v1/chat/completions` **200** and `Received request`. `min_frames` / Triton / `EngineDeadError` on shutdown are noise.

| Shorthand | Job | Note |
| --- | --- | --- |
| `nemotron35_lightning` | 593515 | Ampere TP=2 |
| `gemma4_31b` | 593516 | Ampere TP=2 |
| `qwen38_27b` | 593588 | prefetch on yen1; GPU nodes have no HF auth |
| `mistral_small32` | 593591 | mistral tokenizer/config/load; no `chat_template_kwargs` |
| `olmo31_32b` | 593629 | tech green; Phase A–B later completed |
| `glm4_32b` | 593630 | tech green; Phase A–B later completed |

Prefetch: `hf download` (not `huggingface-cli`). Reuse of `diag-tech-*` after a `config.yaml` change → snapshot hash mismatch; new campaign name.

Yen worktree must be clean. `sbatch -G 2`. Do not set `CAMPAIGN` with `DIAG_LADDER`. Do not combine `DIAG_LADDER` with `DIAG_TECH_INTERACTIONS`. Ampere: `NCCL_P2P_DISABLE=1` and `--disable-custom-all-reduce`. GPU cap 4 with `tp: 2`: at most two such jobs at once.

### Phase A decode (Mixing, emergence, seed 0, \(N=24\), \(H=5\), letters, cap 400)

| Cell | Decode | Campaign |
| --- | --- | --- |
| Parse | no `response_format`; match text to options | `diag-ashery-parse-<shorthand>` |
| Schema | JSON enum `value`/`reason` | `diag-ashery-schema-<shorthand>` |

All six: **done**. Do not rerun parse×schema. Pickles: `/scratch/shared/jendress/runs/<CAMPAIGN>/runs/<shorthand>/mixing/*.pkl`.

`scancel` kills the **whole** job (remaining cells too). During Phase A parse, do not scancel if you still want schema on that model.

### Early stop vs Ashery time-to-convention

Abort only if the trajectory is already **comparable in length** to Ashery and still cold. A stop at \(t=80\) is ~7 expected pairings per agent (\(N=24\)) — too short to say the run does not follow Ashery.

Ashery (mixing, \(N=24\), \(W=10\), \(H=5\)): most models reach global consensus by **~15 population rounds**. Taking a round as \(N/2\) pairwise games (each agent once in expectation) that is **~180 interactions**. Gemma/Qwen schema gated in that band (\(t=177\)–\(215\)). Cap 400 is ~2× that horizon — enough to call a run slower than Ashery, not a stub.

Nemotron **parse** took off only after \(t\approx 300\) (last50 = 6 at \(t=150\), 49 at \(t=400\)). A \(t=150\) kill would have dropped a late convention and would not match Ashery’s full rise.

**Do not stop before a full gate window and the Ashery horizon:**

- \(N=24\): no abort before \(t=180\) (except matcher death: zero valid labels, as Mistral parse at \(t=7\)).
- \(N=48\): no abort before \(t=360\) (15 × \(N/2\)), except matcher death.

After that horizon, schema cells may stop if last50 ≤ 12 **and** last50 is not up versus \(t=180\). Otherwise continue to the job cap (400 in A–B; **1200** in lock-cell verification).

That way a “dead” label means: we watched an Ashery-length emergence window and still saw no takeoff — not that we cut at a tiny prefix.

## Phase B — one-factor, **JSON schema only** — done (seed 0, cap 400)

Do not rerun. Historical recipe below. Mistral/Nemotron were included here; they are dropped after Phase C.

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

## Extra seeds (repeat Phase A shape, schema only) — done (indices 1–3)

Do not rerun the letter \(N=24\) \(H=5\) seed sweep. Next multi-seed work is the lock cell in Phase D. Historical note: JSON schema, Mixing, \(N=24\), \(H=5\), letters, cap 400 — was seed 0 luck?

Do **not** rerun parse×schema × six models. Schema only. Start with **seeds 1–3** (`SEED_FROM=1`, `SEED_TO=4`). One job per model if the runner walks the seed range in ≤ 12 h; otherwise one seed per job.

Priority if the queue is tight: Mistral and Nemotron schema first (n=1 fragmentation), then Gemma/Qwen (gate robustness), then Olmo/GLM if their Phase A schema lived.

## Thinking on — probed; not a freeze knob. Do not queue more for the lock cell.

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

## Phase C — readout (2026-09-12)

Source: `diag-readout-pkl-2.gz` / `diag-readout-full-2.gz` (Yen runs on `yen-gpu2` / `yen-gpu3`). Mixing, emergence only. Gate = 0.95 match over window \(3N\).

**Seeds.** The only multi-seed cell is JSON schema, letters, \(N=24\), \(H=5\), thinking off (Phase A seed 0 + extra seeds 1–3). Every other knob is **seed 0**. Treat those as direction, not as an effect size.

**Model.** Large effect. Gemma, Olmo, Qwen, GLM: gate 4/4 on that cell. Nemotron 2/4, Mistral 1/4. Drop the last two for the freeze set.

**Thinking on/off.** No positive emergence effect for models that already gate. Gemma still gated but slower (201 → 295) with 20 retries. Qwen ~unchanged. Nemotron/Olmo think at 2048 tokens died (`attempts_exhausted`); Nemotron at 4096 gated once; Olmo+4096 unfinished. Thinking stays **off**. Not a freeze knob; do not queue more think jobs for the lock cell.

**Parse vs JSON.** JSON is required for **runnability** (Gemma/GLM/Mistral parse died on the matcher). Qwen and Olmo still gated under parse. Nemotron seed 0 almost gated under parse (window 0.94) and did **not** under schema. Schema is not shown to *boost* convention; freeze **JSON schema** so counted runs complete.

**Letters vs strings (Phase B, seed 0, \(N=24\), \(H=5\), schema).** Medium, model-dependent. Qwen/GLM/Olmo still gated (Olmo slower; Qwen faster). **Gemma** did not gate in 400 steps (window 0.85, last 50 at 0.94 — still climbing). Mistral/Nemotron: no gate either way. Strings are the counted pool (Flint letter-bias), not the easier diag cell.

**\(H=5\) vs \(H=12\) (Phase B, seed 0, letters, \(N=24\), schema).** Small to none on whether a convention forms for the four models that already gate. Qwen/GLM: same \(t_\text{gate}\). Gemma: slightly slower. Olmo: clearly slower (200 → 398). H = 12 is the human-analysis lock (Guilbeault \(M=12\)), not a sweep winner.

**\(N=24\) vs \(N=48\) (Phase B, seed 0, letters, \(H=5\), schema, cap 400).** Not a clean causal test. Mixing degree goes 23 → 47 and the gate window 72 → 144, but cap stayed 400. Nobody gated. Gemma was still climbing (last 50 ≈ 0.94). Larger \(N\) needs a **longer** horizon, not a verdict that \(N=48\) blocks emergence.

**Do not use for readout.** `diag-tech-*` (cap 5). `diag-h5-letters` / `diag-h12-letters` / `diag-h5-strings` / `diag-g31-*`: wrong model (Gemma-E2B) or `killed`, config vs meta unclean. Parse/think `attempts_exhausted` is decode death, not “no convention”.

## Phase D — provisional freeze; next runs verify the lock cell

Do **not** edit counted `config.yaml` yet. The cheap cell (letters, \(H=5\), \(N=24\)) is not the freeze. The freeze **candidate** is the existing lock, now that the four models look viable:

| Knob | Provisional | Why |
| --- | --- | --- |
| Models | `gemma4_31b`, `olmo31_32b`, `qwen38_27b`, `glm4_32b` | only 4/4 gate set |
| Thinking | off | no emergence gain |
| Decode | `json_schema` | runs complete |
| Pool | 5-char strings, \(W=10\) | lock (Flint); not because it gated more easily |
| \(H\) | 12 | lock (human \(M=12\)); sweep said small effect on gate among keepers |
| \(N\) | 48 | lock; **unverified** at an honest horizon |
| Topology for this check | Mixing only | still Phase D, not F |
| Seeds (this check) | **4** (indices 0–3) | same count as the letter cell; not counted \(n=32\) |
| Cap / horizon (this check) | **1200** | window 144; Ashery-length floor 360; not 400 and not counted 5000 |

**Next jobs (do this before E–G).** Crossed lock cell, not another one-factor split: Mixing, emergence, JSON schema, strings, \(H=12\), \(N=48\), thinking off, the four keepers.

**Seeds.** First wave: `SEED_FROM=0`, `SEED_TO=4` → indices **0–3**. That matches the letter-cell evidence, so 4/4 vs 2/4 is readable. Do not start at 8: Yen allows only two `tp: 2` jobs at once. If a keeper is mixed (2/4 or 3/4) or Gemma stays just under 0.95, add **only that model** seeds 4–7 (`SEED_FROM=4`, `SEED_TO=8`, new campaign name, e.g. `diag-lockcell-${MODEL}-s47`). Counted \(n=32\) stays for `experiment`.

**Horizon.** Gate window is 144. Do not abort before \(t=360\) except matcher death (Ashery-scale floor: 15 rounds × \(N/2\)). Cap **1200**, not 400 and not 5000. Phase B \(N=48\) letters \(H=5\) still had Gemma climbing at 400 (last 50 ≈ 0.94). Strings × \(H=12\) × larger \(N\) should rise later, not earlier. Olmo already needed \(t=398\) at \(H=12\), \(N=24\). Counted `cap_phase1` 5000 is too expensive for this check. Runs that gate **stop at the gate**; 1200 is paid only by slow or non-gating seeds. After \(t=360\), optional early stop if last50 ≤ 12 **and** last50 is not up versus \(t=180\); otherwise continue to 1200.

**Wall time.** Set `-t` from the first seed, not a 12 h guess. Roughly ~3 h if a seed hits 1200; early gates are shorter. Four models × four seeds, two jobs at a time: about 1–2 days if most gate early, up to ~3 days if many hit the cap.

This is lock **verification**. Gemma-strings seed 0 at \(N=24\) was a near miss under a short cap. If ≥3/4 seeds gate per model in this cell, write that freeze into `config.yaml` and go to Phase E. If Gemma or Olmo stay under 0.95 at 1200, that is a **lock-change discussion** (not a silent return to letters / \(H=5\) / \(N=24\)).

```bash
cd /scratch/shared/jendress/exp/llm-convention-topology
git pull
git status --porcelain
unset CAMPAIGN DIAG_LADDER DIAG_TECH_INTERACTIONS
export PROGRAM=emergence SEED_FROM=0 SEED_TO=4 TOPOLOGY=mixing
export DIAG_N=48 DIAG_H=12 DIAG_POOL=strings DIAG_DECODE=json_schema DIAG_CAP=1200
export NCCL_P2P_DISABLE=1 VLLM_EXTRA_ARGS="--disable-custom-all-reduce"
export HF_HOME=/scratch/shared/jendress/models
for MODEL in gemma4_31b olmo31_32b qwen38_27b glm4_32b; do
  export MODEL
  export CAMPAIGN=diag-lockcell-${MODEL}
  sbatch -G 2 --mem=64G --export=ALL jobs/thesis_vllm.slurm
done
unset CAMPAIGN
```

Two jobs at a time (Yen GPU cap, `tp: 2`). Do not reuse `diag-g31-*` or E2B letter/string campaign names. Do not rerun parse, Phase B one-factor, letter extra-seeds, or thinking for this verification.

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
