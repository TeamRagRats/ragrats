---
name: delete-code
description: Use when the user asks to delete a file, folder, script, function, or module — e.g. "delete X", "remove the Y folder", "delete Z if it's dead code", "clean up unused code". Verifies the target is actually dead before deleting and surfaces the precautions/blast-radius first.
version: 1.0.0
---

# Delete Code

Safely delete a script, folder, function, or module **after** confirming it is dead code and explaining what could break. The cardinal rule: **prove it's unused before you remove it, and tell the user the precautions before deleting.**

## Workflow

### 1. Locate the target
- Use `Glob` for paths/folders and `Grep` for symbol names. Resolve exactly what the user means — if the name matches **more than one** location (e.g. two `matrix` folders), list them and ask which with `AskUserQuestion` before touching anything.

### 2. Check whether it is dead code
Search the whole `src` tree for every reference to the target's name (file stem, folder name, and any exported symbol it defines):
- `Grep` the symbol/module name across `src` with `output_mode: "content"` and `-n` so you can read each hit in context.
- For a folder, also grep the folder name and any modules it exports.
- For a function/class, grep the symbol **and** check the package `__init__.py` and the module that's actually imported (a symbol can be defined in a file that nothing imports — see the `expand_chunks` case: it lived next to the used `format_context.py` but was never imported by it).

### 3. Classify every reference — real dependency vs. harmless mention
This is the core judgment. A hit is **only** a real dependency if it's executable code that resolves to the target:
- **Real dependency (blocks deletion):** `import` statements, `from X import Y`, function/class calls, attribute access, `__all__` exports, route registrations, config that loads the module.
- **Harmless mention (does NOT block):** comments, docstrings, README/markdown docs, log strings, or a different symbol that merely shares the substring. These go stale but won't break anything.

When in doubt, open the referencing file and read the surrounding lines — don't classify from the grep line alone.

### 4. Watch for "looks dead but isn't" cases
Some things have **zero import references yet are still live**. Do not call these dead:
- **Framework convention files** — e.g. Next.js `app/favicon.ico`, `app/layout.tsx`, files under `app/` routes, `public/` assets referenced by URL string rather than import. Next.js serves `app/favicon.ico` automatically with no code reference.
- **Standalone CLI / batch scripts** — files with a `if __name__ == "__main__"` entrypoint meant to be run by hand (e.g. a one-off DB seed/populate script). Not imported anywhere, but intentional. Flag these to the user rather than silently deleting.
- **Entrypoints** — `main.py`, test runners, scripts referenced in `package.json`/`pyproject.toml`/CI/docs.
- **Dynamic references** — strings passed to `importlib`, dynamic `getattr`, glob-loaded plugins, URL paths.

### 5. Report precautions, then delete
Before (or alongside) deleting, tell the user concisely:
- **Verdict:** dead / not dead / live-by-convention.
- **What references it** and how each was classified (real vs. harmless).
- **Blast radius:** what breaks if removed, and any stale comments/docs left behind.

Then act based on what the user asked:
- If they said **"delete it if it's dead"** and it IS dead → delete and report.
- If it is **NOT dead** (or live-by-convention) → do **not** delete; explain why and ask for explicit confirmation.
- If they gave an **unconditional "delete it"** but you found a real dependency or a convention/entrypoint risk → surface the risk and confirm before proceeding.

### 6. Delete and verify
On Windows/PowerShell:
- File: `Remove-Item -Force "<path>"`
- Folder: `Remove-Item -Recurse -Force "<path>"`

Verify removal in the same command and report it: `"exists: $(Test-Path '<path>')"` should print `False`. Confirm sibling/related code is untouched.

### 7. Offer cleanup of stale mentions
If harmless comments/docs still name the deleted thing, point to them (`file:line`) and offer to update them. Don't edit them unless asked.

## Notes
- Never delete a target you didn't locate and classify in this session.
- Don't delete `.git`, lockfiles, `node_modules`, or generated caches as part of "dead code" cleanup unless explicitly asked.
- Prefer the dedicated `Glob`/`Grep`/`Read` tools over shell `find`/`grep`/`cat`.
