You are generating an unanswerable question for a maritime RAG evaluation set.

DEFINITION (Know Your RAG, COLING 2025):
An unanswerable question has its answer NEITHER present in the context
NOR inferable from it. The question must look plausible — it should be
the kind of question a real maritime operator might ask about this
vessel/voyage — but the chunk genuinely does not contain or imply the
answer.

REQUIREMENTS for this category:
- The question must be plausibly relevant to the entity in the chunk
  (vessel, voyage, port etc.) so a naive RAG might attempt to answer it.
- The chunk must not contain the answer, AND no inference from the chunk
  must yield the answer. Verify both before producing the question.
- The question must mention the specific entity (vessel, voyage, named
  certificate, etc.) so it is unambiguous outside the chunk.
- Set the "answer" field to exactly "NOT_IN_CONTEXT".
- Use "source_hint" to describe what category of information the
  question is asking about (e.g. "next port of call", "fuel consumption
  during voyage", "crew nationality") so reviewers can confirm it is
  genuinely absent from the chunk.

GOOD examples (assuming the chunk does not contain this information):
- "What is the next port of call for African Juniper after Santos on
  voyage AFRICAN_JUNIPER_1?"
- "How much bunker fuel did Corio Bay consume during voyage CORIO_BAY_3?"
- "What is the nationality of Emil Selmer's master?"

BAD examples (do not produce these):
- "What is the IMO number of African Juniper?" — if the chunk states
  the IMO number, this is answerable and belongs to fact_single.
- "What is the capital of France?" — out of domain, not plausibly asked
  by a maritime operator about this entity.
- "What does this exchange say about the next port?" — demonstrative
  reference to the source medium.

Apply all SHARED RULES (source-agnostic phrasing, no banned words, JSON
output with one object). Remember: answer = "NOT_IN_CONTEXT".
