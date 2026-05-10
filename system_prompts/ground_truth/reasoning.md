You are generating a reasoning question for a maritime RAG evaluation set.

DEFINITION (Know Your RAG, COLING 2025):
A reasoning question has its answer NOT explicitly present in the context,
but the answer can be inferred from it via simple, single-step reasoning.

REQUIREMENTS for this category:
- The answer must require one logical inference step beyond what the chunk
  literally states (e.g. comparing a recorded date to a stated validity
  period, comparing measured wind speed to a stated operating limit,
  combining two facts to draw a conclusion).
- The inference must be clear and grounded — anyone reading the chunk
  should reach the same conclusion. Avoid speculative or open-ended
  questions.
- The chunk must contain enough information to make the inference
  possible. Do not require external knowledge beyond elementary maritime
  domain understanding.
- The question must reference the specific entity (vessel, voyage, named
  certificate, etc.) so it is unambiguous outside the chunk.

GOOD examples:
- "Was Emil Selmer's interim MLC certificate still valid on the date of
  the African Juniper damage survey at Santos?" (compares two dates)
- "Given the wind speeds recorded for Corio Bay's departure on voyage
  CORIO_BAY_3, were conditions within the operating limits stated for
  the manoeuvre?" (compares measurement to limit)
- "Based on the Santos stevedore findings for African Juniper, did the
  surveyors attribute fault to the loading crew?" (inference from
  reported observations)

BAD examples (do not produce these):
- "When does African Juniper's MLC certificate expire?" — direct lookup,
  belongs to fact_single.
- "What does the certificate cover?" — demonstrative, no entity, no
  inference.
- "Will African Juniper be profitable next quarter?" — speculative, not
  grounded in the chunk.

Apply all SHARED RULES (source-agnostic phrasing, no banned words, JSON
output with one object).
