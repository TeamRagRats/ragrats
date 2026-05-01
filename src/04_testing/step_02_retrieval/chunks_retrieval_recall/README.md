# Test: step_02_chunk_retrieval

Tester at de endelige chunks hentes korrekt og indeholder de forventede kilder.

## Test-forslag

**Unit — filtrering:**
Bekræft at chunks der ikke matcher de givne voyage_keys aldrig returneres, selvom de ellers ville have høj similarity.

**Recall@k mod ground_truth:**
For hvert `(query, expected_source_id)` i ground_truth: kald `retrieve_chunks` med korrekte voyage_keys og tjek at kilden er til stede.

```python
source_ids = {c.source_id for c in chunks}
assert expected_source_id in source_ids
```

**Rankingtest:**
Er det relevante chunk i top 3? Mål MRR (mean reciprocal rank) på tværs af ground_truth.
