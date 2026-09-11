# Ashery-style split design — emergence ‖ CM on prepared populations

**Status:** code implemented (2026-07-21) — Theory/Methods prose sync deferred until after pilot  
**Date:** 2026-07-21  
**Tracks:** TODO #10 · Doug revisit after baseline/pilot  
**Decision intent:** Match Ashery’s **split protocol** (separate emergence vs CM programs; CM on **prepared** populations; W=10 vs W=2), not keep sequential Phase 1→2 as the main run unit.

**Related:**
- Ashery code: `../ashery-ai-norms/` (`runner.py`, `utils.py`, `simulation_module.py`, `config.yaml`)
- Thesis code: `convention_topology/run.py`, `simulation.py`, `orchestration.py`, `config.yaml`
- Methods hub risk note: `02_Topic/Thesis_Writing/development/03_Methods/WORKING.md` § Design risk — label pool W
- TODO: `TODO.md` § Deferred #10

---

## 1. Verdict (one screen)

| Question | Answer |
| --- | --- |
| How does Ashery split runs? | **Two programs:** `bias_runner` (emergence) vs `committed_runner` (CM). CM does **not** continue an organic Phase-1 trajectory. |
| How does Ashery start CM? | **Prepared population:** fill each agent’s memory (`H`) with the incumbent label; set `committed_to = options[1]`; then `swap`/`inject` → `committed()` for 1000 interactions. |
| W in the paper? | Emergence / Fig. 1 often **W = 10**; bias + critical-mass typically **W = 2**. |
| What does thesis code do today? | **One sequential run:** empty init → Phase 1 → gate → modal incumbent → `swap_committed(k)` → Phase 2; **W = 2** throughout. Prepared init explicitly **skipped** (M03). |
| Target change? | Adopt Ashery split as default: Emergence program (W=10, organic) **and** CM program (W=2, prepared). Drop sequential P1→P2 as the main study run unit. |

---

## 2. Ashery protocol (as implemented in public code + paper)

### 2.1 Two runners (`runner.py`)

Entry loop (simplified):

```text
for cm in minority_size_set:
    if cm == 0:  bias_runner()
    else:        committed_runner()
```

| Program | When | What runs |
| --- | --- | --- |
| **`bias_runner`** | `cm == 0` | Individual bias tests + **collective emergence** |
| **`committed_runner`** | `cm > 0` | Critical-mass / flip experiments |

These write **different pickle families** (different filename patterns). They are not one continuous trajectory per seed.

### 2.2 Emergence path (`bias_runner` → `population`)

When `params.initial == 'None'` (organic start):

1. `get_empty_population` — empty histories, graph from `network_type`
2. `simulation_module.population(...)` — loop until `has_tracker_converged` (Ashery repo default threshold **1.0** over trailing `convergence_time = 3N`)
3. Store `convergence = {converged_index: t, committed_to: None}`
4. Options come from `params.options_set` (repo default `[['Q','M']]`; **paper Fig. 1 uses W = 10**)

When `initial != 'None'`, the same runner can instead start from a prepared state and call `committed()` (“continue evolution”) — that is a separate stability/evolution mode, not the main Fig. 1 empty-start emergence.

### 2.3 CM path (`committed_runner` → prepared → `committed`)

Critical detail: **CM does not load organically converged baselines from `bias_runner`.**

```text
if initial != 'None':
    mainframe = get_prepared_population(...)
else:
    raise ValueError("baseline does not exist")
→ swap_committed / add_committed
→ committed(..., total_interactions=1000)
```

So the public CM protocol is:

| Step | Ashery behavior | Code |
| --- | --- | --- |
| 1. Build graph | `get_interaction_network(..., minority_size=0)` | `utils.py` |
| 2. Synthesize consensus | `set_initial_state`: for each of `memory_size` slots, append `(options[initial], options[initial], +100)` to every non-committed agent | `utils.set_initial_state` (`initial` is an **int** index) |
| 3. Sanity check | Every agent’s first `H` own-answers == `options[initial]` | `test_if_initialisation_worked` |
| 4. Mark “already converged” | `convergence = {converged_index: 0, committed_to: options[1]}` | `get_prepared_population` |
| 5. Inject CM | `swap` (retag k agents) or `inject` (grow N) | `swap_committed` / `add_committed` |
| 6. Run horizon | Fixed **1000** interactions; CM agents always emit `committed_to` (no LLM call) | `simulation_module.committed` |

**Incumbent / CM labels (prepared):**

- Incumbent = `options[initial]` (e.g. `initial: 0` → first label)
- Committed push = `options[1]` (**hard-coded** as second option in prepared setup)
- Paper often pairs this with **W = 2** (`Q`/`M`) and studies strong vs weak convention by which label is incumbent

### 2.4 W by experiment (paper vs shipped config)

| Experiment | Typical W (paper) | Shipped `config.yaml` default |
| --- | --- | --- |
| Spontaneous emergence (Fig. 1 style) | **W = 10** | `options_set: [['Q','M']]` (W=2) — config is **per-batch**, not paper-complete |
| Collective / individual bias | **W = 2** | W=2 |
| Committed minority / critical mass | **W = 2** | W=2 |

Implication for us: matching Ashery’s **design** means **different option pools per program**, not one global `options_set: [[Q, M]]`.

### 2.5 What Ashery deliberately does *not* do for CM

- Does **not** require organic Phase-1 eligibility before CM
- Does **not** derive incumbent as modal label in trailing 3N of a live trajectory (prepared path)
- Does **not** keep W=10 through CM (paper CM is W=2)

Organic → CM continuity exists in human Centola (2018) and in our **current** thesis sequential design — but **not** in Ashery’s public CM runner.

---

## 3. Thesis status quo (code cross-check, 2026-07-21)

### 3.1 Current run unit

`convention_topology/run.py::execute_run` (docstring + body):

```text
init empty network
→ Phase 1 loop until gate (0.95 / 3N) or cap 5000
→ if censored: stop (no Phase 2)
→ incumbent = modal_label_in_window(tracker, 3N)
→ committed_to = the other W=2 label
→ swap_committed(k)
→ Phase 2 for 1000 interactions
```

Locked in `WORKING.md` as **M03 sequential Phase 1→2**; prepared helpers explicitly **skipped**.

### 3.2 File-by-file: Ashery vs thesis today

| Ashery | Thesis today | Match? |
| --- | --- | --- |
| `bias_runner` / `committed_runner` | Single `execute_run` + pilot/main grids that always pass `cm_k` into the same sequential unit | **No** — one program |
| `population()` empty start | Phase 1 in `execute_run` / `run_phase1` | **Yes** (organic half) |
| `get_prepared_population` + `set_initial_state` | Not ported (`WORKING.md` §2: skip) | **No** |
| CM on prepared | CM only after organic gate | **No** |
| `committed_to = options[1]` by construction | `committed_to` = non-modal at gate | **Different** |
| `swap_committed` | `simulation.swap_committed` (rng-injected) | **Yes** |
| `committed()` CM short-circuit | `make_interaction_step(..., committed_to=...)` | **Yes** |
| Phase 2 horizon 1000 | `params.total_interactions: 1000` | **Yes** |
| Gate threshold paper 0.95 / repo 1.0 | Thesis **0.95** + cap 5000 | Thesis follows **paper** gate |
| W per program | `options_set: [[Q, M]]` only | **No** W=10 emergence |
| Prompt / H=5 / payoffs | Ported | **Yes** |
| Centola-3 topologies | Thesis extension | N/A (Ashery mixing-only) |

### 3.3 Orchestration / analysis coupling to sequential design

These pieces **assume** sequential P1→P2 + eligibility:

| Component | Assumption today | Impact if we split |
| --- | --- | --- |
| `run_pilot.py` / `pilot_grid` | 36 cells = topology × seed with **cyclic k**; each cell is full P1→P2 | Need **two grids** (emergence without k; CM with k on prepared) |
| `run_main.py` | Eligible-count targeting after Phase-1 gate | Emergence: eligibility stays; CM: eligibility gate **goes away** (prepared always “ready”) |
| `build_run_id` / meta | `…_k{cm_k}_s…` even for runs whose scientific interest is Phase 1 | Separate ID schemes or `program=emergence|cm` in meta |
| `analysis` H1/H2 | Slice tracker to Phase-1 end (`t_gate`); include censored | Unchanged in spirit (emergence-only artifacts) |
| `analysis` H3 / flip | Phase 2 after organic gate; `eligibility==1` filter | Flip DVs still apply; filter becomes “completed CM run”, not organic eligibility |
| Methods LaTeX | “sequential design”, W=2 both phases | Must be revised when lock flips |

### 3.4 Config today

```yaml
# llm-convention-topology/config.yaml (excerpt)
params:
  max_phase1_interactions: 5000
  convergence_threshold: 0.95
  memory_size_set: [5]
  options_set: [[Q, M]]          # W=2 only
  total_interactions: 1000       # Phase 2 horizon
```

No `params.initial`, no separate emergence options, no `run_mode` / program flag.

---

## 4. Proposed thesis change (Ashery-faithful)

### 4.1 Design locks to adopt

| Lock | New value |
| --- | --- |
| Run architecture | **Split programs** (emergence ‖ CM), not sequential P1→P2 |
| Emergence | Empty init → Phase 1 to gate/cap; **W = 10**; Centola-3; no CM |
| CM | **Prepared** init (Ashery `set_initial_state` semantics) → swap → 1000 interactions; **W = 2** |
| Incumbent (CM) | By construction: `options[incumbent_index]` (default 0) |
| CM label | `options[1 − incumbent_index]` or explicit `committed_to` (Ashery uses `options[1]`) |
| Swap mode | Keep **swap** (no inject) |
| Gate (emergence only) | Keep thesis **0.95** + **5000** cap |
| H, N, payoffs, prompts | Unchanged |

### 4.2 Suggested W=10 alphabet (to lock later)

Ashery uses letters from the English alphabet. Concrete thesis default TBD (e.g. first 10 letters or Ashery’s published set). Placeholder until Methods lock:

```text
options_emergence: 10 distinct letters (exact set: author lock)
options_cm: [Q, M]   # match Ashery CM / current thesis labels
```

### 4.3 Code changes required (when we implement — not done yet)

Ordered by dependency:

1. **`simulation.py` / new `prepared.py`**
   - Port `set_initial_state` (int incumbent index), `get_prepared_population`, `test_if_initialisation_worked`
   - Keep rng-injected (no module-level `random`)
   - Prepared players: empty tracker; `convergence.converged_index = 0`; `committed_to` set; histories length = `H`

2. **`run.py`**
   - Split `execute_run` into:
     - `execute_emergence_run(...)` — today’s Phase 1 path only; persist; no swap/Phase 2
     - `execute_cm_run(...)` — prepared init → swap → Phase 2 only
   - Optionally keep `execute_run` sequential behind a deprecated/`legacy` flag for old fixtures — or delete after test migration

3. **`config.yaml` + `config.py`**
   - `params.options_emergence` (W=10) and `params.options_cm` (W=2), **or** program-scoped `options_set`
   - `params.initial` / `incumbent_index` for prepared CM (Ashery int)
   - `run.program` or CLI `--program {emergence,cm}`

4. **`orchestration.py` + CLIs**
   - `emergence_grid` / `cm_grid` (replace single `pilot_grid` that mixes k into Phase 1)
   - `run_pilot.py` / `run_main.py` / `run_one.py`: `--program` (+ `--k` only for CM)
   - Run-ID: e.g. `{model}_{topology}_emerg_s{seed}` vs `{model}_{topology}_k{k}_s{seed}`

5. **Persistence / meta**
   - Add `program`, `options`, `incumbent_index`, `init_mode: organic|prepared`
   - Emergence: `cm_k=0` or omit; `eligibility` from gate
   - CM: `eligibility=1` always (or drop field); `t_gate=0` / `init_mode=prepared`

6. **Analysis**
   - H1/H2: read emergence artifacts only
   - H3/flip: read CM artifacts only; remove dependence on organic Phase-1 eligibility
   - Cross-check: no script assumes Phase-2 tracker continues after a live `t_gate > 0` unless legacy

7. **Tests**
   - Prepared init invariant (all agents’ first H answers = incumbent)
   - CM short-circuit still zero API for committed agents
   - Emergence never tags committed agents
   - Update integration tests that currently expect sequential completion

8. **Docs / Methods (after code lock)**
   - `WORKING.md` M03 unlock + deviation table
   - Methods LaTeX: sequential → split; W=10 emergence / W=2 CM; prepared CM
   - TODO #10 → done when code + Methods synced; Doug note

### 4.4 What we keep from current thesis (still valuable)

- Centola-3 topologies on **both** programs (Ashery was mixing-only)
- Gate 0.95 + Phase-1 cap 5000 (emergence)
- Swap-only CM, horizon 1000
- Prompt/parse/retry stack, OpenRouter routing
- Live analytics / analysis scaffolding (re-point inputs)

### 4.5 Trade-offs (explicit)

| Benefit | Cost |
| --- | --- |
| Ashery Fig. 1 comparability (W=10 emergence) | Loses sequential “same population then shocked” narrative |
| Ashery CM protocol fidelity (prepared + W=2) | Weaker ecological continuity; Centola-2018 human CM was organic |
| Cheaper / clearer CM (no failed Phase-1 waste before k) | Eligibility contingency (D4/D5) reframes: only emergence-relevant |
| Clean H1/H2 vs H3 separation | Methods + WORKING + analysis rewrite; pilot grid redesign |

**Benchmark framing after change:**

- Phase 1 / RQ1: Centola (2015) + Ashery Fig. 1 (W=10 mixing)
- Phase 2 / RQ2–RQ3: Ashery CM protocol (prepared, W=2) × Centola-3 topology; Centola (2018) remains **pattern** benchmark with documented init mismatch (organic human vs prepared LLM)

---

## 5. Implementation checklist (for later session)

- [ ] Author-lock exact W=10 letter set
- [ ] Author-lock strong/weak CM arms (incumbent_index ∈ {0,1} vs single incumbent)
- [ ] Implement prepared init + split executors
- [ ] Rewire pilot/main grids + run IDs + meta
- [ ] Migrate tests; keep or drop sequential legacy path
- [ ] Update `WORKING.md` / Methods / TODO #10
- [ ] Revisit baseline plan (`2026-07-20_ashery_baseline_plan.md`): mixing emergence may need **W=10** arm for Fig. 1; CM baseline stays W=2 prepared

**Out of scope for first code pass:** changing LaTeX before code works offline; Doug email (can share this note).

---

## 6. Session log

| Date | Note |
| --- | --- |
| 2026-07-21 | Design doc written from Ashery `runner.py`/`utils.py` audit + thesis `run.py`/`WORKING.md` cross-check. |
| 2026-07-21 | **Code implemented:** prepared init, `execute_emergence_run` / `execute_cm_run`, dual pilot/main grids, analysis program filters, tests. No sequential residue. Theory/Methods sync still open (TODO #10). |
