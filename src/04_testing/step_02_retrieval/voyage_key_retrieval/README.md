# Test: step_01_voyage_key

Tester voting-mekanismen der indsnævrer søgerummet til de mest relevante voyage_keys.

## Test-forslag

**Unit — voting-logik:**
Indsæt mock-chunks med kendte voyage_keys og tjek at `find_winning_voyage_keys` returnerer præcis de keys med flest stemmer — inkl. ties.

```python
# 3 chunks med "key_A", 1 med "key_B" → winner = ["key_A"]
```

**Integration — mod ground_truth:**
For hver `(query, sources)` i ground_truth: kør step 1 og tjek at den forventede voyage_key er blandt vinderne.

**Sensitivitetstest:**
Variér `top_k` (50 → 500) og mål hvor ofte den rigtige voyage_key falder ud — finder tærsklen for stabilt recall.
