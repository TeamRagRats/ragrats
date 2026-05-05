from clients.rerank_client import RerankClient

c = RerankClient("http://localhost:8004/v1")
print("Model:", c.model)

resp = c._client.chat.completions.create(
    model=c.model,
    messages=[
        {"role": "system", "content": 'Judge whether the Document meets the requirements based on the Query and the Instruct provided. Note only output a single token "yes" or "no".'},
        {"role": "user", "content": "<Instruct>: Given a shipping operations query, retrieve relevant passages that answer the query\n<Query>: What is the freight rate?\n<Document>: The freight rate is USD 25 per tonne."},
    ],
    max_tokens=1,
    logprobs=True,
    top_logprobs=20,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)

print("Raw token:", resp.choices[0].logprobs.content[0].token)
print("Top logprobs:")
for lp in resp.choices[0].logprobs.content[0].top_logprobs:
    print(f"  '{lp.token}' -> {lp.logprob:.3f}")

score = c._score_one("What is the freight rate?", "The freight rate is USD 25 per tonne.")
print("Score:", score)
