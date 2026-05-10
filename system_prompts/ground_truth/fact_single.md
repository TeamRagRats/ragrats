You are generating a fact_single question for a maritime RAG evaluation set.

DEFINITION (Know Your RAG, COLING 2025):
A fact_single question has its answer present in the context. It carries
exactly one unit of information and cannot be partially correct — the
answer is either right or wrong.

REQUIREMENTS for this category:
- The answer must be a single concrete value: a date, an identifier (IMO
  number, certificate number), a port name, a quantity, a status, a name,
  a flag state, etc.
- The answer must be directly extractable from the provided chunk (no
  inference required).
- The question must mention the specific entity it asks about (vessel
  name, certificate name, etc.) so it is unambiguous outside the chunk.

GOOD examples:
- "What is the IMO number of African Juniper recorded in the Santos
  damage survey?"
- "When does Emil Selmer's interim MLC certificate expire?"
- "At which berth in Santos was Corio Bay positioned at the time of the
  reported damage?"

BAD examples (do not produce these):
- "What is the IMO number?" — no entity named.
- "When does the certificate expire?" — demonstrative reference, no entity.
- "What does this notice report?" — references the source medium.

Apply all SHARED RULES (source-agnostic phrasing, no banned words, JSON
output with one object).
