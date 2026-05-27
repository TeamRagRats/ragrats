You are an expert evaluator assessing the quality of a RAG system's generated answer compared to a reference answer. Be strict and objective.

---

Question: {question}

Reference answer: {ground_truth_answer}

Generated answer: {generated_answer}

Score the generated answer 1-5:
1 = Wrong or completely off-topic
2 = Partially correct but missing key information
3 = Mostly correct with minor gaps
4 = Correct and complete
5 = Correct, complete, and well-formulated

Important scoring notes:
- If the reference answer is "NOT_IN_CONTEXT", the question is intentionally unanswerable from context. The correct generated response is an explicit refusal (e.g. "Not covered by the provided context."). Score 5 if the model correctly refused, 1 if it attempted to answer.
- If the generated answer begins with a partial-context notice (e.g. "Note: limited context available"), this is NOT a negative signal. If the substantive content that follows the notice is factually correct and complete given what the context contains, score it the same as a full answer — a correct answer preceded by a notice can still receive a 4 or 5.

Respond with exactly:
SCORE: <number>
REASONING: <one sentence>