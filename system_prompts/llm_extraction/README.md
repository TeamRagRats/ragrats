# LLM Extraction — System Prompts

## document_restructuring.md

Used in **Step 5. LLM extraction** to restructure raw OCR markdown from Docling into a standardized document format.

### Pipeline step
Step 5 (LLM extraction) — runs after Step 4 (Docling document extraction).

### What the prompt does
The LLM receives raw OCR output from Docling (PDF -> markdown) and transforms it into a fixed template with the sections: Document Type, Purpose, Key Information, Content and Notes. The prompt instructs the model to be precise, preserve all names/dates/numbers verbatim, and never add a preamble or reflection.

### Called by
- `Preprocessing/Step 5. LLM extraction/llm_to_db.py`
  - Loaded via `load_system_prompt(PROMPT_PATH)` at startup
  - Sent as the system message to the vLLM backend (port 8002) via the OpenAI-compatible API

### Model backend
- vLLM with Nvidia Nemotron Nano 8B (local GPU server)

### User prompt
The user prompt is the raw Docling output itself (markdown from PDF). No builder function — the document is sent directly.
