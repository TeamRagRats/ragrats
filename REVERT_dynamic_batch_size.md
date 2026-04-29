# Revert: Dynamic phase batch size (TARGET_PHASES = 6)

## Background

The voyage summary pipeline works in two stages: first, emails are grouped
into phases and each phase gets an LLM-generated summary (map step); then
all phase summaries are combined into a single voyage narrative (reduce step).

The original pipeline used a fixed batch size of 10 emails per phase. With
voyages containing 600–1200 emails, this produced 60–120 phase summaries per
voyage. Feeding that many phases into the reduce step created a very long and
highly repetitive input — the same facts (ETAs, discharge ports, LOI requests)
appeared across dozens of consecutive phases — which caused the LLM to enter
a repetition loop, regenerating the same sentences with minor variations.

To diagnose this, we queried the email count distribution across all voyages:
- Median: 621 emails, P90: 1059 emails, Max: 1182 emails

We then replaced the fixed `PHASE_BATCH_SIZE = 10` with a `compute_batch_size()`
function that scales the batch size to the voyage's email count, targeting
approximately 6 phases per voyage regardless of size. For a 621-email voyage
this gives batches of ~104 emails; for a 1182-email voyage, ~197 emails.

This was tested on `CINSPIRATION_1` only. The repetition loops reduced but
did not disappear entirely, which led to a second fix (`repetition_penalty=1.15`
added to the LLM client, commit `82dd7dc`) applied on top of this one.

---

## What was changed

Commit `92015f2` replaced the fixed `PHASE_BATCH_SIZE = 10` constant in the
phase/voyage summary pipeline with a `compute_batch_size()` function that
dynamically targets ~6 phases per voyage regardless of email count.

**Files touched:**
- `src/preprocessing/step_09_summaries/phase/phase_summaries.py`
- `src/preprocessing/step_09_summaries/voyage/voyage_summaries.py`

**Scope of testing:** Only `CINSPIRATION_1` phase and voyage summaries were
regenerated under this change. No other voyages were processed.

---

## How to revert

### Option A — Git revert (recommended)

```bash
git revert 92015f2 --no-edit
git push origin fix_minister
```

This creates a new commit that undoes the change cleanly without rewriting history.

### Option B — Manual rollback

**`phase_summaries.py`** — replace the dynamic constants and function:

```python
# Remove these:
TARGET_PHASES = 6
MIN_BATCH_SIZE = 10

def compute_batch_size(email_count: int) -> int:
    return max(MIN_BATCH_SIZE, math.ceil(email_count / TARGET_PHASES))

# Restore:
PHASE_BATCH_SIZE = 10
```

Revert `_run_phase` signature:
```python
# From:
def _run_phase(voyage_key, phase_index, batch, llm, batch_size):
    first = phase_index * batch_size + 1

# To:
def _run_phase(voyage_key, phase_index, batch, llm):
    first = phase_index * PHASE_BATCH_SIZE + 1
```

Revert `run()` batching:
```python
# From:
batch_size = compute_batch_size(len(emails))
batches = [emails[j:j + batch_size] for j in range(0, len(emails), batch_size)]
# ...
ex.submit(_run_phase, vk, idx, b, llm, batch_size)

# To:
batches = [emails[j:j + PHASE_BATCH_SIZE] for j in range(0, len(emails), PHASE_BATCH_SIZE)]
# ...
ex.submit(_run_phase, vk, idx, b, llm)
```

**`voyage_summaries.py`** — restore the constant and remove the import:

```python
# Remove:
from ..phase.phase_summaries import compute_batch_size

# Restore:
PHASE_BATCH_SIZE = 10  # must match phase/phase_summaries.py

# Revert validation line:
# From:
expected = math.ceil(email_count / compute_batch_size(email_count))
# To:
expected = math.ceil(email_count / PHASE_BATCH_SIZE)
```

---

## After reverting

Clear the CINSPIRATION_1 phase summaries generated under the new batch size
before re-running, otherwise the phase count won't match the old expected value:

```sql
DELETE FROM phase_summaries WHERE voyage_key = 'CINSPIRATION_1';
DELETE FROM voyage_summaries WHERE voyage_key = 'CINSPIRATION_1';
```

Then regenerate:
```bash
python -m src.preprocessing.run_phase_summaries --voyage-key CINSPIRATION_1
python -m src.preprocessing.run_voyage_summaries --voyage-key CINSPIRATION_1
```
