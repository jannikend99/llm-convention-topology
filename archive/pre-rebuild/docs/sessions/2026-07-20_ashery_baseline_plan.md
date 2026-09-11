# Ashery mixing baseline — validation plan (2026-07-20)

**Status:** in progress — **model lock: `llama31` only** (2026-07-20)  
**Goal:** Check that the thesis stack on **mixing + Llama-3.1 + W=2** produces Ashery-like dynamics before spending budget on Centola-3 lattice/random.  
**Related:** Doug email (open-source first) · C-05 smoke log · Methods Ashery alignment protocol

### Model lock (Ashery open models on OpenRouter)

| Ashery paper model | OpenRouter | Baseline use |
| --- | --- | --- |
| **Llama-3.1-70B-Instruct** | `meta-llama/llama-3.1-70b-instruct` (`llama31`) | **Yes — sole model** |
| Llama-3-70B-Instruct | no live endpoints (404) | skip |
| Llama-2-70b-Chat | not listed | skip |
| Claude-3.5-Sonnet | proprietary | skip (Doug: open-source first) |

No second-model arm for this baseline.

---

## 1. Verdict

| Question | Answer |
| --- | --- |
| Is the Ashery protocol already in our code? | **Yes** — prompts, N=24, H=5, W=2, gate 0.95, swap-CM, Phase2=1000, `complete` topology, `llama31` |
| Dedicated “reproduce Ashery” script? | **No** — use mixing-only CLI subset |
| Same as Centola-3 pilot? | **No** — pilot spends 2/3 runs on lattice/random; baseline = **`complete` only** |

---

## 2. What we can / cannot match

### Target (Ashery paper, W=2 CM / bias populations)

- Full mixing (`complete`), Llama-3.1-70B-Instruct  
- Spontaneous consensus → CM swap → 1000 interactions  
- Qualitative: high gate rate on mixing; flip rate rises with k; strong vs weak incumbent asymmetry  

### Do **not** expect 1:1 figure match

| Ashery | Thesis | Implication |
| --- | --- | --- |
| Fig. 1 often **W=10** emergence | Locked **W=2** sequential | Compare to **binary/CM** figures, not W=10 curves |
| Strong CM tipping ~**42%** for Llama-3.1 | Our k only **1…6** (~4–25%) | Many non-flips at k≤6 on strong incumbents can still be **consistent** |
| HF serverless, `max_new_tokens` 12–15 | OpenRouter/DeepInfra, `max_tokens` 512 | Stack difference — document, don’t force HF |
| Prepared baselines for some CM runs | Sequential Phase1→2, incumbent = modal @ gate | Closer to paper sequential story; slight protocol difference |

Gate **0.95** matches the **paper** (not Ashery repo default 1.0) — keep it.

---

## 3. Staged design (cheap → informative)

### Stage B1 — Mechanics (1–2 full runs)

Confirm end-to-end: Phase1 gates, CM short-circuit (no API for committed), Phase2 finishes, sidecars clean.

```bash
cd llm-convention-topology
python run_one.py --model llama31 --topology complete --k 1 --seed 0
python run_one.py --model llama31 --topology complete --k 6 --seed 1
```

**Pass:** both `run_status` completed or censored with sensible metadata; parse-fail rate low; CM agents show 0 LLM calls.

### Stage B2 — Emergence sample (~8–12 mixing Phase-1 attempts)

Enough to see eligibility + dominant-share regime on mixing.

Practical path: mixing-only main with temporarily lowered eligible targets, **or** a short loop of `run_one` over seeds — prefer documented config copy if lowering targets:

```bash
python run_main.py --model llama31 --topology complete --dry-run
# then run with a baseline config that sets complete targets to ~[2,3] (optional)
python run_main.py --model llama31 --topology complete
```

**Pass:** most mixing runs gate before 5000; high dominant share (H1-style).

### Stage B3 — CM sketch (optional, after B1/B2 look good)

≥2 eligible per k∈{1…6} on complete only → flip-vs-k sketch for Doug share.

```bash
python analyze.py --h1 --h3a --h4 --eligibility --model llama31
```

---

## 4. Success criteria (practical)

1. Mixing almost always **eligible** (gate ≥95%/3N).  
2. **Dominant share** high after Phase 1 (order, not perpetual disorder).  
3. **Flip rate non-decreasing in k** (direction); exact Ashery tipping point not required inside k≤6.  
4. Low **failed** rate from parse errors (else revisit before Centola-3).  
5. Write results into `docs/sessions/YYYY-MM-DD_ashery_baseline_results.md` for Doug share.

---

## 5. Sequencing vs Centola-3 pilot

Recommended order (aligned with Doug open-source-first):

1. Commit C-05 config  
2. **Ashery baseline B1 → B2** (this plan)  
3. If OK → Centola-3 **pilot** (`run_pilot.py --model llama31`)  
4. Share baseline + pilot summary with Doug  

If B1 fails mechanically → fix stack before burning pilot budget on lattice/random.

---

## 6. Cost note

Each full mixing run ≈ O(t_gate + 1000) interactions × 2 agent calls (minus CM short-circuit in Phase 2). Start with **B1 only**; scale B2/B3 after B1 looks clean.
