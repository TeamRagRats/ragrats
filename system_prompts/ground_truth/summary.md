You are generating a summary question for a maritime RAG evaluation set.

DEFINITION (Know Your RAG, COLING 2025):
A summary question has its answer present in the context but it carries
multiple units of information. Trading completeness for conciseness yields
a partially correct answer — i.e. the answer requires synthesising
several facts spread across the chunk.

REQUIREMENTS for this category:
- The answer must combine at least two distinct facts found in the chunk
  (e.g. damage description + outcome, certificate scope + conditions,
  cargo quantity + delivery schedule + counterparty).
- The question must demand synthesis rather than a single value lookup —
  if it can be answered with a single date or number, it is fact_single,
  not summary.
- The question must reference the specific entity (vessel, voyage, named
  certificate, etc.) so it is unambiguous outside the chunk.

GOOD examples:
- "What damage was reported to African Juniper at Santos and how was the
  situation resolved?"
- "What does Emil Selmer's interim MLC certificate cover and under what
  conditions does it remain valid?"
- "What cargo operations on Corio Bay during voyage CORIO_BAY_3 are
  described, including quantities discharged and remaining balance?"

BAD examples (do not produce these):
- "What does the certificate cover?" — demonstrative, no entity.
- "Summarise this exchange." — references the source medium.
- "When does African Juniper's MLC expire?" — single fact, belongs to
  fact_single.

Apply all SHARED RULES (source-agnostic phrasing, no banned words, JSON
output with one object).
