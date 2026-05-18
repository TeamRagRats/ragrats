# Test: step_03_generation

Tester generationskvalitet isoleret fra retrieval — ground_truth-kilder sendes direkte til LLM'en.

## Test-forslag

**Generation accuracy (bypassed retrieval):**
Feed `correct_sources` fra ground_truth direkte til `build_context` + `generate_answer` — ingen retrieval.
Sammenlign output med `correct_answer` via LLM-as-judge eller semantisk lighed.

```python
context = build_context(conn, [chunk], [chunk.voyage_key])
answer, _ = generate_answer(llm, query, context, ...)
score = judge(answer, ground_truth_answer)  # 1–5
```

**End-to-end vs. isolated:**
Kør samme query med og uden retrieval-bypass — stor forskel indikerer retrieval-fejl, ikke generations-fejl.

**Prompt-sensitivitet:**
Test samme query med forskellige system prompts eller temperaturer og mål konsistens i score.
