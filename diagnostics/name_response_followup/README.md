# Controlled response follow-up suite

Separate auxiliary experiments for OLMo, Qwen, Gemma and GLM. The Main runner,
configuration, prompts, adapters and counted datasets are unchanged. This suite
imports their canonical prompt, strict parser and model profiles read-only.
Outputs use `runs/name-response-followup`, not Main or the initial screening
battery. No topology or committed population is simulated here.

## Fixed default plan

| Test | Design | Repetitions | Maximum calls/model | Four-model maximum |
|---|---|---:|---:|---:|
| `replication` | Four histories × two name roles × two prompt orders × two schema orders | 50 | 1,600 | 6,400 |
| `rules` | Three history families × two matched endings × six name-role assignments × two list orientations | 25 | 1,800 | 7,200 |
| `retention` | Eight binary contexts; one shared initial choice, then three branches of twelve further choices | 20 | 5,920 | 23,680 |
| Total | | | 9,320 | 37,280 |

Repetitions are fresh seed blocks starting at 20261008, distinct from the earlier
41000–41002 screen. The same seed is shared across conditions within a block;
analysis therefore treats a block as the uncertainty unit. These sample sizes are
fixed resource/precision choices, not a guarantee of power for small effects.
Do not stop or increase repetitions based on whether p crosses .05. Changing the
repeat count, seed base, source or profile creates a separate battery; do not
silently pool it with an earlier one.

### 1. Replication

Binary `dicfv`/`lwlsi` histories remain exactly the earlier four fixtures:
12 successful incumbent encounters; one oldest mismatch; one latest mismatch;
and six latest mismatches after six successes. Oldest/latest have identical
counts and total payoff. Moving the mismatch moves partner evidence and payoff
together. Prompt and JSON enum order vary independently. Name-role swaps change
both incumbent and challenger identities, not an isolated property of a string.

### 2. Rule discrimination

All ten Main labels are offered. Histories use three labels assigned to I/A/B
in all six permutations of `dicfv`, `lwlsi`, `ptqsu`:

- Partner recency: own choices I twelve times; partner A/B six times each.
- Own recency: own choices A/B six times each; partner I twelve times.
- Frequency versus recency: own choices I twelve times; partner A eight times
  and B four times. A is the partner-frequency leader even when B is latest.

Each family has two matched histories ending in A versus B. Swapping complete
rows preserves name counts and the pair multiset. All twelve payoffs remain -50,
so payoff recency does not vary. Full option lists are deterministically shuffled
and reversed; a matched history pair receives identical lists and sampling seed.
Own-last, partner-last, own/partner/combined unique modes and first-option choices
are recorded as candidate predictions. Their agreements overlap; matching one
prediction does not identify a unique internal algorithm. The matched intervention
changes the order and ending of the history; it does not isolate only the latest
observation. The all-mismatch
fixtures and three historical names are deliberately selected contexts, not a
representative sample of Main agent states.

### 3. Retention under controlled future feedback

Each binary context starts with the latest-single-mismatch fixture and one actual
model choice. Its current partner chooses C. That same initial answer is shared
by three future branches: C on all twelve encounters (`reinforced`), I on all
encounters (`reverted`), or C/I alternation beginning with C (`alternating`).
Every subsequent choice uses the branch's actual prior model answers and legal
payoffs. The stored history accumulates; the canonical prompt displays only the
last twelve encounters with correct advancing round numbers. The current partner
answer is never revealed before the model decides.

Report target production after 1, 3 and 12 further choices, both for all initial
contexts and for initial adopters; also report uninterrupted retention among
adopters. The first further choice sees identical histories in all branches, so
step 1 is a pre-feedback consistency control. Branch-specific feedback first
enters the prompt at step 2. At step 12, eleven branch-specific encounters and
the shared initial encounter are visible. Branches are paired counterfactual environments sharing an initial
answer, not independent agents or network replicates. Invalid ancestors censor
and block descendants. This tests persistence under specified feedback, not
network spread, cognitive mechanisms, or the proportion of a topology effect
explained by adoption.

## Run on Yen

Use the existing JupyterHub Terminal on Yen, from the private experiment checkout.
The Slurm launcher loads each cached, pinned model and tokenizer on two A40s,
uses the existing model temperature/output/thinking profile, and prohibits
unexpected model downloads. Each task has a 24-hour wall-time ceiling; this is
not a runtime estimate. Missing weights or a missing existing venv/SIF fail.

```bash
cd /scratch/shared/jendress/exp/llm-convention-topology
git pull --ff-only origin main
mkdir -p /scratch/shared/jendress/vllm

# CPU-only validation of one plan; no model requests.
/scratch/shared/jendress/venvs/thesis/bin/python \
  diagnostics/name_response_followup/run.py \
  --experiment replication --model glm4_32b --dry-run

# All three tests × four models, one GPU allocation at a time.
sbatch --array=0-11%1 diagnostics/name_response_followup/probe.slurm
squeue -u jendress
```

Array indices 0–3: replication; 4–7: rules; 8–11: retention. Within each group:
OLMo, Qwen, Gemma, GLM. The array may schedule tasks in any order. The `%1` limit
avoids concurrent allocations from this suite. To submit just one group, use
`--array=0-3%1`, `--array=4-7%1`, or `--array=8-11%1` respectively.

Single-task examples:

```bash
sbatch diagnostics/name_response_followup/probe.slurm \
  --experiment retention --model olmo31_32b

# Smaller technical battery; separate results, not confirmatory replication.
sbatch diagnostics/name_response_followup/probe.slurm \
  --experiment rules --model glm4_32b --repeats 1
```

Do not combine `--model`/`--experiment` with an array. Optional `--repeats` (1–200)
and `--seed-base` alter the plan and budget. Resubmit the same indices/arguments
with unchanged sources to resume. Completed choices are not resent. Every request
has a durable reservation; a reserved request with unknown outcome becomes
invalid and is never retried. After three consecutive inference/validation errors
the task stops. Inspect the logs before resubmission; failures are not replaced
with extra draws. A new source fingerprint starts a new battery.

Logs: `/scratch/shared/jendress/vllm/name_followup_<ARRAY_JOB>_<TASK>.out` and
`.err`; serving logs are under `name_followup_<JOB>_<TASK>/server.log`. For a
single task, stdout uses Slurm's non-array task marker and serving logs use
`single`. Model loading and inference runtime have not been measured for this
larger suite. Historical serving/checkpoint identity with Main remains a separate
provenance question; the follow-up records its own profile, source hashes,
server advertisement and raw responses.

## Results and statistical plan

Results: `name-response-followup/live/<model>/<experiment>/<design-hash>/`.
`design.json` specifies the complete bounded plan and source/profile hashes;
`attempts.jsonl` reserves calls; `responses.jsonl` saves exact rendered prompts,
input histories, prompt hashes, raw completions, decisions and validation status;
`completion.json` saves coverage. Mock data use a separate `mock/` tree.

Successful tasks automatically run `analyze.py`. It checks the design, recorded
inputs and parent histories before writing `summary.csv`, `contrasts.csv`,
`rules.csv`, `retention.csv` and `verification.json`. Invalid and missing records
remain explicit. An incomplete/invalid battery makes analysis exit nonzero.

Effect sizes use equal seed-block means with 2,000 whole-block bootstrap samples.
Intervals are pointwise and conditional on this fixed context battery. Single-seed
or degenerate bootstrap intervals are suppressed and marked, not represented as
proof of zero uncertainty. Exact sign tests concern directional consistency of
nonzero seed-block contrasts; they do not test the same estimand as the mean effect.
They assume independent seed blocks. Their sensitivity to effect size and zero
blocks must remain explicit.

Planned Holm families are separate for each model and battery:

- Replication: five contrasts, `lwlsi minus dicfv` challenger-role assignment,
  C-first minus I-first prompt order, C-first minus I-first enum order,
  repeated mismatch minus successful control, and latest minus oldest mismatch.
- Rules: three role-B production contrasts, last-B minus last-A, one per family.
- Retention: six endpoint contrasts, reverted/alternating minus reinforced at
  further-choice steps 1, 3 and 12. Initial answers are counted once.

There is no correction across models or across these three distinct families;
claims of a single omnibus confirmatory result are not supported. The suite is
an auxiliary study motivated by the exploratory screen. Main H1–H4 tests and
population inference remain separate. Generated reasons are not mechanism evidence.

To recheck and export aggregate tables after all tasks finish:

```bash
/scratch/shared/jendress/venvs/thesis/bin/python \
  diagnostics/name_response_followup/analyze.py \
  --results-root /scratch/shared/jendress/runs/name-response-followup/live
```

Aggregate tables keep models and distinct fingerprints separate; they never pool
old and new batteries. Download the entire `name-response-followup` directory,
Slurm logs and this source folder for later local analysis.

## Local checks

```bash
python -m unittest discover -s diagnostics/name_response_followup -p 'test_*.py' -v
bash -n diagnostics/name_response_followup/probe.slurm
python diagnostics/name_response_followup/run.py \
  --experiment retention --model olmo31_32b --repeats 1 \
  --mock --output /tmp/name-response-followup-check
python diagnostics/name_response_followup/analyze.py \
  --results-root /tmp/name-response-followup-check/mock
```

Mock chooses the first enum item. Tests check fixture counts/payoffs, role/order
controls, source/record integrity, shared initial decisions, actual feedback,
rolling visible memory with true rounds, bounded failure/resume behavior and
exclusion accounting. They do not validate GPU serving or statistical power.
