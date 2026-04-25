# LLM Extraction — System Prompts

## document_restructuring.md

Bruges i **Step 5. LLM extraction** til at omstrukturere rå OCR-markdown fra Docling til et standardiseret dokumentformat.

### Pipeline-step
Step 5 (LLM extraction) — korer efter Step 4 (Docling document extraction).

### Hvad prompten gor
LLM'en modtager raat OCR-output fra Docling (PDF -> markdown) og transformerer det til en fast skabelon med sektioner: Document Type, Purpose, Key Information, Content og Notes. Prompten instruerer modellen i at vaere praecis, bevare alle navne/datoer/tal verbatim, og aldrig tilfoeje indledning eller refleksion.

### Kaldt af
- `Preprocessing/Step 5. LLM extraction/llm_to_db.py`
  - Indlaest via `load_system_prompt(PROMPT_PATH)` ved opstart
  - Sendt som system-besked til vLLM backend (port 8002) via OpenAI-kompatibelt API

### Model backend
- vLLM med Nvidia Nemotron Nano 8B (lokal GPU-server)

### User prompt
User-prompten er selve det raa Docling-output (markdown fra PDF). Ingen builder-funktion — dokumentet sendes direkte.
