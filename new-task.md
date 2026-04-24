---
name: new-task
description: Start a new task by entering plan mode, picking a suitable role/expertise lens, interviewing the user about crucial decisions, proposing improvements, and delegating to a subagent when the task is large enough.
---

# /new-task

Kickstart a new task in a structured way: pick the right expertise lens, surface crucial decisions up-front via a short interview, suggest improvements, then produce a plan.

## What to do

Follow these steps in order. Do not skip ahead to implementation — this skill ends at plan approval.

### 1. Enter plan mode

Immediately call `EnterPlanMode`. All subsequent steps happen inside plan mode. No files are edited until the user approves the plan.

### 2. Restate the task in one line

Before anything else, echo back what you understood the task to be in a single sentence, so the user can correct misreadings early.

### 3. Select a role

Pick ONE role that best fits the task and state it explicitly:

- **Software architect** — system design, module boundaries, data flow, non-trivial refactors
- **Backend engineer** — APIs, database schema, pipelines, server-side logic
- **Frontend engineer** — UI, component structure, client-side state
- **Data/ML engineer** — ETL, embeddings, retrieval, model evaluation
- **DevOps / infra** — deployment, CI/CD, containers, observability
- **Security reviewer** — auth, secrets, input handling, threat modeling
- **Debugger** — reproducing and isolating a specific bug
- **Code reviewer** — evaluating existing code for quality/correctness
- **Technical writer** — docs, READMEs, API reference

Format: `**Role:** <role> — <one-line reason this role fits>`

If the task spans multiple roles, pick the primary one and note the secondary lens.

### 4. Quick reconnaissance

Before interviewing, do light exploration (Read/Glob/Grep) to ground your questions in the actual codebase — don't ask questions you could answer yourself in 30 seconds. Keep this tight; this is not full research.

**Check for numbered-step structure.** If the project organises work into sequentially numbered step directories or files (e.g. `step_01_discover/`, `step_02_parse/`, `02-ingest.py`, `phase-03-load/`), this is a strong convention signal. Before planning:

1. List the existing steps in order and identify what each one does (one line each).
2. Decide where the new task fits:
   - **Inside an existing step** — when the task is a natural extension of that step's responsibility (e.g. adding a new parser variant to `step_02_parse`).
   - **Between two steps** — rare; usually means renumbering. Call this out explicitly before doing it.
   - **As a new step at the end** — when the task introduces a new pipeline stage. Propose the next number and a short directory name matching the existing convention (`step_0N_<verb>`).
3. Surface this decision in the plan (step 7) under a dedicated **Step placement** line so the user can veto before any directories are created.

Do **not** silently create a new numbered step — the numbering is a load-bearing convention and renumbering breaks imports, docs, and mental models.

**SQL-logik (kogebogen):** Al DDL (tabeller, views, indeks) hører hjemme i `src/preprocessing/sql_migrations/`. Ny SQL-logik placeres altid som en ny nummereret fil: `0002_<beskrivelse>.sql`. Brug `CREATE OR REPLACE VIEW` til views og `CREATE TABLE IF NOT EXISTS` til tabeller. Kør `python sql_migrations/migrate.py` for at anvende — den springer allerede-kørte filer over automatisk. Redigér **ikke** eksisterende migrationsfiler; tilføj altid en ny.

### 5. Interview about crucial decisions

Use the `AskUserQuestion` tool to ask 1–4 questions covering only **decisions that meaningfully change the implementation** and that you cannot answer from the code. Examples of good interview topics:

- Scope boundaries (in/out of scope)
- Breaking-change tolerance / backwards compatibility
- Performance or scale constraints
- Preferred library / approach when several are viable
- Target environment (dev/prod, runtime versions)
- Data shape or schema decisions
- Error-handling philosophy for this feature

Do **not** ask about:
- Things obvious from the code or CLAUDE.md
- Pure style/formatting
- Implementation minutiae you should decide yourself

Prefer one `AskUserQuestion` call with multiple questions over several sequential calls.

### 6. Suggest improvements

After the interview, present a short **Suggested improvements** section — things the user did not ask for but that you'd recommend given what you found. Each item:

- One line describing the improvement
- One line on why (risk avoided, quality gained, or future pain prevented)
- Marked `[opt-in]` — the user decides whether to include them

Keep this to at most 3–5 items. Do not pad.

### 7. Produce the plan and exit plan mode

Write a concise plan:

```
## Plan

**Role:** <role>
**Goal:** <one sentence>

**Steps:**
1. …
2. …
3. …

**Files likely touched:** <paths>
**Out of scope:** <what this plan will NOT do>
**Opt-in improvements included:** <list, or "none">
```

Then call `ExitPlanMode` to hand control back to the user for approval. Do not start implementing until the plan is approved.

### 8. Decide whether to deploy a subagent

After the plan is approved, judge the size of the work before touching any code:

**Deploy a subagent (via `Agent`) when any of these hold:**
- The task spans 4+ files or multiple distinct areas of the codebase
- It requires extended research/exploration that would blow up main context
- It has independent sub-tasks that can run in parallel (spawn several agents in one message)
- Estimated effort is 30+ minutes of focused work or 10+ tool calls of searching

**Do it inline (no subagent) when:**
- The task is localized to 1–3 files you've already identified
- You already have the context needed to implement it directly
- It's a quick edit, bug fix, or small feature

Pick the right `subagent_type`:
- `Explore` — research / "where does X live" across the codebase
- `Plan` — architectural design for a complex implementation
- `general-purpose` — multi-step implementation work

When deploying, brief the agent as a cold colleague: restate the goal, the approved plan, relevant files/paths you've found, and any interview decisions. Do not delegate understanding — include specifics, not "based on the plan, implement it."

If parallelizable, launch multiple agents in a single message.

## Tone

- Terse. No filler.
- Surface tradeoffs, don't hide them.
- If the task is trivial (< 5 min work, no real decisions), say so and skip the interview — offer to just do it.
