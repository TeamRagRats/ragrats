# Test: step_03_generation

Tester generationskvalitet med realistisk kontekst fra retrieval-systemet.

Joiner `ground_truth` med `test_retrieval_chunk_logging` og tager kun spørgsmål hvor `hit=true` (korrekte chunks blev returneret). Grupperer per K-værdi og evaluerer generation for hvert K separat. Scorer hvert svar med cosine similarity + LLM-as-judge (1–5). Rapporterer per K og per kategori: `fact_single`, `summary`, `reasoning`.

```bash
# Kræver at chunk-retrieval testen er kørt først
python run_test.py --retrieval-run-id <UUID>
```

**Flags:**
- `--retrieval-run-id` (påkrævet) — UUID fra en kørsel i `test_retrieval_chunk_logging`; sikrer at generation kun evalueres på én strategi/konfiguration ad gangen
- `--embed-url` — embed-server base URL (default: `http://localhost:8003/v1`)
- `--llm-url` — LLM-server base URL (default: `http://localhost:8002/v1`)
- `--temperature` — generations-temperatur (default: `0.3`)
- `--max-tokens` — max tokens i svar (default: `2500`)
