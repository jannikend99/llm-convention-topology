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
| Phase 1 max | **5000** interactions (pilot observes censoring) |
| Phase 2 horizon | **1000** post-gate interactions |
| CM injection | `swap` mode (Ashery) |
| Flip success (analysis) | `flip = 1` iff ≥95%/3N success **and** modal label = `committed_to`; `flip_resisted` if success but incumbent retained |

Methods sourcebook: `Thesis_Writing/development/03_Methods/WORKING.md` (in thesis-writing submodule).

---

## Planned scope (implementation TBD)

- [ ] Centola-3 graph generators (lattice = thesis build)
- [ ] Gate 0.95 + eligibility logging
- [ ] Config snapshot per run (topology, model, seeds)
- [ ] Pilot + main-study runners
- [ ] Analysis scripts for Phase 1 / Phase 2 DVs
- [ ] **Live analytics** during pilot (success rate, dominant share, gate proximity) — tooling TBD

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

**Scaffold only** — no experiment code yet. First implementation target: lattice generator + gate 0.95 fix before pilot.
