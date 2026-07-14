# Agent prompt — Execute `IMPLEMENTATION_PLAN.md` (todo-by-todo)

## Task

**Implement the thesis experiment codebase** by working through [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) **one todo at a time**, in dependency order. After each todo: run its **Verify** command, mark it **done in the plan**, then proceed to the next unchecked item.

Do not skip ahead, batch unrelated todos, or re-plan. Charter: [`WORKING.md`](../WORKING.md). On conflict, WORKING wins.

**Scope of one agent run:** complete as many todos as possible until context limits or a hard blocker — then stop with a resume pointer (next todo ID).

---

## Startup (every session)

1. Read `IMPLEMENTATION_PLAN.md` §0 (zero-blocker contract, coverage gate, architecture principles) and **§7** (dependency pins + API patterns) before any C/E/F todo.
2. Scan §2 master checklist — find the **first row** where the ✔ column is `☐` (not `✅`, not `⏸`).
3. Confirm **Depends on** IDs for that row are already `✅`. If not, do the earliest unmet dependency first.
4. Skim the todo's **Files** + **Acceptance**; read only the Ashery sources needed for this todo (WORKING §2 / plan §3 watch-outs).

```bash
cd "Master Thesis/02_Topic/Experiment_Code/llm-convention-topology"
python -m unittest discover -s tests -v   # baseline must be green before changing anything
```

If baseline is red, fix regressions before new work.

---

## Per-todo loop (repeat until no `☐` rows remain except ⏸)

For todo **`{ID}`** (e.g. `A-03`):

### 1. Implement

- Touch **only** the files listed in that row (+ tests the row implies).
- Follow §0 architecture principles (pure core, DI, single-writer `persistence.py`, typed errors, thin CLIs).
- **Do not rewrite** `gate.py` or `networks.py`.
- **Do not edit** `../ashery-ai-norms/`.
- Port Ashery logic per WORKING §2 when the todo says so — deviations are already locked (0.95 gate, 144 denominator, no `flip_resisted`, CM skips API).

### 2. Verify

Run the row's **Verify** command exactly. On failure: fix before marking done.

Then always run the phase baseline:

```bash
python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests && coverage report --include="convention_topology/*,live/*" --fail-under=85
```

If this is the **last todo in a phase** (see §3 exit gate in the plan), also run that phase's cumulative commands from §6 CLI smoke sequence.

### 3. Mark done in `IMPLEMENTATION_PLAN.md`

In §2 master checklist, change **only that row's** ✔ cell:

```diff
-| ☐ | A-03 |
+| ✅ | A-03 |
```

Do not reorder rows or edit other todos' text.

### 4. Secondary bookkeeping (same todo, before moving on)

| When | Action |
| --- | --- |
| Last todo of phase A–G | Append one line to `WORKING.md` §14 session log: `{date} — Phase {X} complete ({IDs})` |
| Milestone boundary (plan §8) | Update WORKING § Status sign-off table (☐ → ✅ + date) |
| New public entrypoint | One-line note in `README.md` Implementation status if status changed |

### 5. Next

Return to **Startup step 2** for the next `☐` row.

---

## Deferred items (⏸) — do not execute unless user explicitly asks

| ID | Trigger |
| --- | --- |
| C-05 | Real API keys + provider + model strings available |
| G-03 | Analysis freeze after real data |
| G-04 | After G-03 |

Skip these in the normal loop. When user requests one, run it like any other todo and mark `✅`.

---

## Execution order (when multiple `☐` are ready)

Default: **phase letter A→G**, then **numeric ID** within phase (A-01 before A-02).

Within a phase, respect **Depends on** strictly. Plan §3 **Order** lines override if ambiguous.

Phases **E** and **F** may run after **B** (parallel with C/D in separate sessions) — but in a **single sequential run**, still follow A→B→C→D→E→F→G unless the user says "skip to Phase F".

---

## Quality gates (non-negotiable)

- Every todo gets its own verify + full suite + coverage before `✅`.
- No committed secrets — `git grep -iE "sk-|api[_-]?key.*=" -- ':!*.md' ':!IMPLEMENTATION_PLAN.md'` must stay empty after C-03.
- Branch-critical paths (parser, retry, flip taxonomy, resume, CM zero-API) need explicit tests even if coverage % passes.
- **Definition of done** for the full build: all non-⏸ todos `✅`, §6 final CLI smoke green (plan §0).

---

## Anti-patterns

- Marking `✅` without a green Verify command
- Implementing multiple checklist IDs in one blob without per-ID verify + checkbox
- Re-litigating design locks from WORKING / Methods
- Adding scope (scale-free, meta-prompting, extra topologies, Mehdizadeh graphs)
- `git commit` / `git push` unless the user asks
- Creating files outside the plan's file-creation order without a plan reason

---

## Stop / resume protocol

**Stop when:** all non-⏸ todos are `✅`, or a hard blocker outside §7 (e.g. missing tool, ambiguous spec).

**End-of-session message must include:**

1. Last completed ID (`✅`)
2. Next ID to run (`☐`)
3. Verify command for next ID
4. Any failing test output (if stopped mid-fix)

**Resume next session:** paste this prompt + *"Resume from {next ID}"*.

---

## Post-run self-check (when stopping)

- [ ] Every completed ID is `✅` in §2 and was verified individually
- [ ] `python -m unittest discover -s tests -v` green
- [ ] Coverage gate green (if any code landed this session)
- [ ] No edits to `gate.py` / `networks.py` / `ashery-ai-norms/`
- [ ] WORKING §14 updated if a full phase finished
