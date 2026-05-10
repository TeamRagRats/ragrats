# Embedding Strategies

All strategies use **Qwen/Qwen3-Embedding-4B** (2560-dimensional halfvec) and write into the `chunks` table. The `strategy` column distinguishes them — the unique constraint on `(source_type, source_id, strategy, chunk_index)` means the same email or attachment can carry multiple representations simultaneously.

---

## Email strategies

### `plain`

**Runner:** `run_embedding_email_plain.py`  
**Module:** `step_06_embedding/email_plain/`

The simplest baseline. Takes each email's `body_cleaned` field and passes it directly to the embedding model. No thread context, no summary prefix — just the raw cleaned body.

- **Input to model:** `body_cleaned`
- **Stored text:** `body_cleaned`
- **Chunks per email:** 1 (`chunk_index = 0`)
- **DB source:** `emails` — pending = not yet in chunks with `strategy = 'plain'`
- **Use case:** retrieval baseline; establishes a lower bound for comparison against context-aware strategies

---

### `late`

**Runner:** `run_embedding_email_late.py`  
**Module:** `step_06_embedding/email_late/`

The most context-rich email strategy. Works at the **thread level** rather than the individual email level. All emails in a thread are concatenated into one long document (separated by `\n\n---\n\n`) and a single forward pass is run on the entire thread. The model's attention mechanism can therefore see the full conversation history when computing each message's embedding. After the forward pass, per-message embeddings are extracted by mean-pooling the token vectors that fall within each email's character span.

- **Input to model:** full thread text (all emails concatenated)
- **Stored text:** individual `body_cleaned` per email
- **Chunks per email:** 1 (`chunk_index` = position of the email within its thread, 0-based)
- **DB source:** `emails` grouped by `thread_id` — pending = threads with no late-chunked emails yet
- **Truncation risk:** long threads can exceed the 32 768-token limit; later messages in the thread lose full cross-attention context when this happens
- **Use case:** highest-quality email retrieval; captures reply context naturally

---

### `context`

**Runner:** `run_embedding_email_context.py`  
**Module:** `step_06_embedding/email_context/`

Enriches each email's embedding with a thread-level summary without requiring the full thread text in the forward pass. A pre-generated thread summary (from `email_thread_summaries`, status `ok`) is prepended to `body_cleaned` before embedding. The summary is not stored as the chunk's text — only the body is.

- **Input to model:** `thread_summary + "\n\n" + body_cleaned`
- **Stored text:** `body_cleaned` only
- **Chunks per email:** 1 (`chunk_index = 0`)
- **DB source:** `emails` joined with `email_thread_summaries` (status `ok`) — pending = not yet context-chunked
- **Use case:** compact alternative to `late`; cheaper (no full thread forward pass), still gives the model thread context via the summary prefix

---

### `summary`

**Runner:** `run_embedding_email_summary.py`  
**Module:** `step_06_embedding/email_summary/`

Embeds the LLM-generated per-email summary from `email_summaries` directly. The summary is both the embedding input and the stored text. This produces a dense, semantically compressed representation of what the email is about, stripped of formatting noise and tangential content.

- **Input to model:** `email_summaries.summary`
- **Stored text:** the summary itself
- **Chunks per email:** 1 (`chunk_index = 0`)
- **DB source:** `email_summaries` — pending = status `ok`, non-empty summary, not yet summary-chunked
- **`thread_id`:** taken directly from `email_summaries.thread_id`
- **Use case:** high-precision retrieval for queries that match the semantic gist of an email; less useful for exact-phrase or detail lookups

---

## Attachment strategies

Attachments are stored as structured markdown (`llm_structured.structured_md`) produced by Docling + LLM extraction. All attachment strategies apply the fixed-window chunker from `step_05_chunking/attachments/chunker.py` (target ~1 500 chars, 200-char overlap) before embedding — except `attachment_summary`, which bypasses chunking entirely.

### `plain`

**Runner:** `run_embedding_attachment_plain.py`  
**Module:** `step_06_embedding/attachment_plain/`

Baseline. Splits `structured_md` into fixed-window chunks and embeds each chunk independently with no additional context.

- **Input to model:** `chunk.text`
- **Stored text:** `chunk.text`
- **Chunks per attachment:** N (one per fixed-window chunk)
- **Identified by:** `source_type = 'attachment'`, `source_id = sha256`
- **DB source:** `llm_structured` joined with `attachments` — pending = not yet plain-chunked
- **Use case:** retrieval baseline for attachment content; establishes a lower bound

---

### `late`

**Runner:** `run_embedding_attachment_late.py`  
**Module:** `step_06_embedding/attachment_late/`

The richest attachment strategy. Prepends the parent email's summary to the full `structured_md`, then runs a single forward pass on the combined document. Each chunk's embedding is extracted by mean-pooling the token vectors that fall within that chunk's character span — but only the tokens belonging to the document portion are pooled (the email summary portion influences via attention, not by being pooled into the chunk vector).

- **Input to model:** `email_summary + "\n\n---\n\n" + structured_md` (full doc in one pass)
- **Stored text:** `chunk.text`
- **Chunks per attachment:** N
- **Identified by:** `source_type = 'attachment'`, `source_id = sha256`
- **DB source:** `llm_structured` joined with `attachments`; email summary fetched via join
- **Truncation risk:** large documents + long email summaries can exceed 32 768 tokens; later chunks may lose full context
- **Use case:** highest-quality attachment retrieval; the model sees both what the email is about and the full document before producing chunk embeddings

---

### `context`

**Runner:** `run_embedding_attachment_context.py`  
**Module:** `step_06_embedding/attachment_context/`

Splits `structured_md` into chunks first, then embeds each chunk independently with the email summary prepended. Unlike `late`, each chunk gets a separate forward pass — there is no cross-chunk attention. The email summary is not stored as text.

- **Input to model:** `email_summary + "\n\n" + chunk.text` (one forward pass per chunk)
- **Stored text:** `chunk.text`
- **Chunks per attachment:** N
- **Identified by:** `source_type = 'attachment'`, `source_id = sha256`
- **DB source:** `llm_structured` joined with `attachments`; email summary fetched via join
- **Use case:** middle ground between `plain` and `late`; cheaper than `late` (no full-doc forward pass), but each chunk still sees the email context

---

### `summary`

**Runner:** `run_embedding_attachment_summary.py`  
**Module:** `step_06_embedding/attachment_summary/`

Embeds the LLM-generated attachment summary from `email_attach_summaries` directly. Unlike the other attachment strategies, this is keyed by **email_id** rather than sha256 — the summary covers all attachments in an email collectively. No chunking is applied.

- **Input to model:** `email_attach_summaries.summary`
- **Stored text:** the summary itself
- **Chunks per email:** 1 (`chunk_index = 0`)
- **Identified by:** `source_type = 'attachment'`, `source_id = email_id`
- **DB source:** `email_attach_summaries` — pending = status `ok`, non-empty summary, not yet summary-chunked
- **`thread_id`:** fetched via join to `emails`
- **Use case:** high-level retrieval — "what attachments did this email contain?" — rather than specific content within a document; best paired with `late` or `context` for drilling into details

---

## Quick comparison

| Strategy | Source text | Context injected | Forward passes | Chunks out | Keyed by |
|---|---|---|---|---|---|
| `email/plain` | body | none | 1 per email | 1 | email_id |
| `email/late` | full thread | full thread (attention) | 1 per thread | 1 per email | email_id |
| `email/context` | body | thread summary prefix | 1 per email | 1 | email_id |
| `email/summary` | email summary | — | 1 per email | 1 | email_id |
| `attachment/plain` | chunk text | none | 1 per chunk | N | sha256 |
| `attachment/late` | full doc + email summary | email summary (attention) | 1 per doc | N | sha256 |
| `attachment/context` | chunk text | email summary prefix | 1 per chunk | N | sha256 |
| `attachment/summary` | attach summary | — | 1 per email | 1 | email_id |
