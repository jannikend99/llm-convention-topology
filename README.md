# llm-convention-topology

**Thesis experiment codebase** — LLM Naming Game with **Centola-3** network topologies, committed-minority perturbation, and eligibility logging.

Extends [Ashery et al. (2025)](https://github.com/Ariel-Flint-Ashery/AI-norms) (`ashery-ai-norms`) as a **controlled extension**, not a fork of the canonical upstream.

**Meta-repo path:** `Master Thesis/02_Topic/Experiment_Code/llm-convention-topology/` (git submodule of [master-thesis](https://github.com/jannikend99/master-thesis))

---

## Role in the multi-repo layout

| Repo | Path (in meta-repo) | Role |
| --- | --- | --- |
| **master-thesis** | `Master Thesis/` | Project context, literature, org |
| **thesis-writing** | `02_Topic/Thesis_Writing/` | LaTeX manuscript |
| **ashery-ai-norms** | `02_Topic/Experiment_Code/ashery-ai-norms/` | Read-only Ashery reference |
| **ai-convention-formation** | `02_Topic/Experiment_Code/ai-convention-formation/` | Collaborator reproduction (Guilbeault group) |
| **llm-convention-topology** *(this repo)* | `02_Topic/Experiment_Code/llm-convention-topology/` | **Thesis-specific experiment implementation** |

**Rule:** Do not edit `ashery-ai-norms/` in place. Copy/adapt patterns here; pin Ashery submodule commit in Methods reproducibility.

---

## Design locks (2026-07-10)

| Parameter | Lock |
| --- | --- |
| Population **N** | 24 |
| Topologies | Centola-3: **mixing** (`complete`), **random regular** deg 4, **1D ring lattice** deg 4 |
| Lattice | Nearest + next-nearest on ring — Centola & Baronchelli (2015) |
| Stability gate | **≥95%** dyadic success over trailing **3N = 72** interactions (`convergence_threshold: 0.95`) |
| Phase 1 max | **5000** interactions (emergence program; pilot observes censoring) |
| CM horizon | **1000** interactions on prepared populations |
| Programs | **emergence** (W=10, organic) ‖ **cm** (W=2, prepared) — Ashery split |
| CM injection | `swap` mode (Ashery) |
| Flip success (analysis) | `flip = 1` iff ≥95%/3N success **and** modal label = `committed_to`; non-flip = single censored category at horizon 1000 (no separate `flip_resisted` code — see Methods/Theory Fix Pack R2, 2026-07-13) |

Methods sourcebook: `Thesis_Writing/development/03_Methods/WORKING.md` (in thesis-writing submodule).

**Implementation SSOT:** [`WORKING.md`](WORKING.md) — charter · [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — execution checklist + **§7 dependency/API patterns** (rev. 3).

---

## Implementation status

**Execution checklist:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — day-to-day todo list (phases A–G, 45 items) decomposed from `WORKING.md` §3.

| Component | Status |
| --- | --- |
| `config.yaml` thesis locks (`convergence_threshold: 0.95`, `max_phase1_interactions: 5000`) | ✅ |
| Stability gate (`convention_topology/gate.py`) | ✅ |
| Phase 1 loop with hard cap (`convention_topology/simulation.py`) | ✅ |
| Centola-3 networks incl. 1D ring lattice deg 4 (`convention_topology/networks.py`) | ✅ |
| Unit tests (`tests/test_gate.py`) | ✅ |
| **Implementation plan** — [`WORKING.md`](WORKING.md) §1–§13 fully specified (milestone 0) | ✅ |
| Mock LLM layer + prompting port (`convention_topology/llm.py`, `prompting.py`) — WORKING §3 Phase A | ✅ |
| Full run unit: Phase 1→2, persistence, metadata sidecar (`run.py`, `persistence.py`) — Phase B | ✅ |
| LLM API layer, OpenAI-compatible + 3× retry (`llm.py`, `run_one.py`) — Phase C; **C-05 real-API smoke done 2026-07-20** ([session log](docs/sessions/2026-07-20_C05_openrouter_smoke.md); DeepInfra pin + `max_tokens` 512) | ✅ |
| Pilot / main-study orchestration (`run_pilot.py`, `run_main.py`, dispatch logic in `convention_topology/orchestration.py`) — Phases D, G | ✅ |
| Analysis scripts H1–H3b + H4, per model (`analysis/`, `analysis/dispatch.py`, `analyze.py`, `dvs.py`) — Phase F | ✅ |
| **Code review remediation (2026-07-14)** — H3a GAM-vs-linear primary test, real `code_commit` sidecar, Phase 2 shared option shuffle, unified incumbent tie-break, H3b full-grid confirmatory check, thin-CLI extraction (`orchestration.py`/`analysis/dispatch.py`), persistence write/delete helpers, typed analysis exceptions — see [`CODE_REVIEW_REPORT.md`](CODE_REVIEW_REPORT.md) remediation table | ✅ |
| **Live analytics** — Rich (`live/monitor.py`) + **Streamlit** (`live/web.py`) + notebook (`notebooks/pilot_dashboard.ipynb`) — Phase E | ✅ |

**One-shot offline build complete (2026-07-14):** all 43 non-deferred todos in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) are ✅; full suite (121 tests) green; coverage 92% (≥85% gate). Deferred (⏸, need real API keys/model strings or real data): C-05 (paid manual smoke), G-03/G-04 (dependency freeze + repro pins at analysis freeze).

### Gate fix (vs. Ashery public default)

Ashery `config.yaml` sets `convergence_threshold: 1` (100% success in trailing 3N).
The thesis build uses **0.95**, matching Ashery et al. (2025) Methods and the locked
Methods chapter spec.

```bash
python -m unittest discover -s tests -v
```

---

## Ashery alignment

When adopting Ashery design choices, Methods prose must **flag + cite**, explain comparability, or invoke Ashery's stated rationale. Deviations (e.g. gate threshold, Centola-3 topologies) must be **explicit**.

Reference: `Experiment_Code/ashery-ai-norms/` · Zenodo [10.5281/zenodo.14937173](https://doi.org/10.5281/zenodo.14937173)

---

## Clone

From a fresh meta-repo clone:

```bash
cd "Master Thesis"
git submodule update --init --recursive
```

Or this repo only:

```bash
git clone git@github.com:jannikend99/llm-convention-topology.git
```

---

## Status

| **Provider routing (OpenRouter + direct APIs)** — [`PROVIDER_ROUTING_PLAN.md`](PROVIDER_ROUTING_PLAN.md) | ✅ |

**One-shot offline build + provider routing complete (2026-07-14):** mock LLM layer, full run unit, OpenRouter/direct API client, pilot + main-study orchestration, live analytics (Rich + Streamlit + notebook), and H1–H4 analysis pipeline — **153 tests**, 91% coverage. Next: C-05 real-API smoke + pin `openrouter_provider.only`; commit implementation; pilot run.
