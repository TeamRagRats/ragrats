# Retrieval-strategi × top-k sweep — resultater

**Dato:** 2026-05-12
**Datagrundlag:** 4 084 ground_truth_v3 spørgsmål (15 per kategori × 4 kategorier × 20 voyages × 4 strategier — minus filter-frafald).
**Metric:** source recall — træf hvis retrieval returnerer en chunk fra samme email-tråd som det spørgsmålet blev genereret fra.
**Test:** isoleret `chunk_retrieval` (step 2 alene, perfekt voyage_key gives fra GT).

## Hovedresultat — averages over alle 16 (kategori × gt-strategi) celler

| Retrieval | k=20 | k=30 | k=50 | k=100 |
|---|---:|---:|---:|---:|
| **plain** | 55.7% | 62.4% | 72.6% | **81.1%** |
| context | 52.4% | 58.0% | 64.3% | 73.7% |
| late | 40.0% | 51.5% | 58.9% | 69.6% |
| summary | 47.8% | 52.7% | 58.3% | 65.5% |

**Plain er den robuste generalist på tværs af alle k. Late catcher op efterhånden som k stiger (var sidst ved k=20, kun 4pp efter plain ved k=100).**

---

## Detaljerede tabeller

### k=20 (default i prod)

#### retrieval = plain
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 53.4 | 53.1 | 52.0 | 46.7 |
| reasoning | 65.3 | 67.1 | 73.8 | 56.9 |
| summary | 63.6 | 68.5 | 69.6 | 58.1 |
| unanswerable | 48.0 | 41.2 | 39.5 | 33.7 |

#### retrieval = late
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 34.2 | 44.8 | 40.6 | 27.8 |
| reasoning | 41.0 | 52.1 | 48.6 | 40.6 |
| summary | 42.0 | 50.4 | 48.6 | 40.4 |
| unanswerable | 34.3 | 34.0 | 34.8 | 26.4 |

#### retrieval = context
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 39.1 | 51.5 | 53.9 | 41.6 |
| reasoning | 54.0 | 68.0 | 72.9 | 57.9 |
| summary | 50.5 | 65.9 | 72.7 | 57.3 |
| unanswerable | 37.7 | 38.1 | 44.3 | 32.9 |

#### retrieval = summary
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 42.1 | 30.3 | 31.9 | **78.8** |
| reasoning | 54.0 | 38.4 | 32.7 | **87.3** |
| summary | 58.0 | 34.8 | 30.8 | **87.3** |
| unanswerable | 45.3 | 24.1 | 26.4 | 62.2 |

### k=30

#### retrieval = plain
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 60.5 | 58.9 | 61.4 | 52.5 |
| reasoning | 70.3 | 73.5 | 80.8 | 64.0 |
| summary | 71.4 | 74.8 | 74.3 | 64.2 |
| unanswerable | 54.0 | 50.2 | 47.6 | 40.2 |

#### retrieval = late
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 43.6 | 54.8 | 55.1 | 40.4 |
| reasoning | 52.7 | 66.7 | 68.2 | 48.2 |
| summary | 52.7 | 67.0 | 61.3 | 52.7 |
| unanswerable | 41.7 | 42.3 | 43.2 | 33.7 |

#### retrieval = context
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 46.2 | 58.1 | 58.7 | 47.8 |
| reasoning | 60.3 | 74.4 | 75.2 | 62.9 |
| summary | 54.4 | 71.9 | 77.9 | 64.6 |
| unanswerable | 43.3 | 45.7 | 48.6 | 37.8 |

#### retrieval = summary
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 48.9 | 34.4 | 37.0 | 84.7 |
| reasoning | 58.2 | 42.9 | 36.9 | 91.4 |
| summary | 62.9 | 37.8 | 35.6 | 90.4 |
| unanswerable | 51.3 | 28.5 | 31.1 | 71.5 |

### k=50

#### retrieval = plain
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 68.4 | 69.3 | 71.7 | 65.1 |
| reasoning | 80.8 | 83.1 | 86.9 | 77.2 |
| summary | 79.2 | 83.7 | 83.4 | 75.4 |
| unanswerable | 67.7 | 59.5 | 58.1 | 52.8 |

#### retrieval = late
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 52.6 | 58.5 | 63.8 | 46.7 |
| reasoning | 61.1 | 74.0 | 74.3 | 57.4 |
| summary | 59.0 | 74.1 | 70.0 | 60.4 |
| unanswerable | 52.0 | 49.5 | 50.0 | 39.0 |

#### retrieval = context
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 52.3 | 65.1 | 67.3 | 52.9 |
| reasoning | 64.4 | 80.8 | 80.8 | 69.5 |
| summary | 60.1 | 75.2 | 81.8 | 69.2 |
| unanswerable | 52.3 | 56.0 | 56.4 | 45.5 |

#### retrieval = summary
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 56.4 | 38.6 | 42.9 | 91.4 |
| reasoning | 61.9 | 47.5 | 43.0 | 94.9 |
| summary | 67.1 | 41.1 | 39.9 | 95.0 |
| unanswerable | 56.7 | 35.4 | 37.2 | 83.7 |

### k=100

#### retrieval = plain
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 75.2 | 78.8 | 82.3 | 74.9 |
| reasoning | 87.9 | 90.4 | 91.6 | 85.3 |
| summary | 87.3 | 88.5 | 89.7 | 85.4 |
| unanswerable | 77.0 | 71.1 | 67.2 | 65.4 |

#### retrieval = late
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 60.9 | 72.2 | 74.4 | 59.6 |
| reasoning | 72.4 | 87.2 | 81.8 | 66.5 |
| summary | 68.6 | 81.5 | 80.2 | 70.4 |
| unanswerable | 62.0 | 63.2 | 62.5 | 50.8 |

#### retrieval = context
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 61.3 | 75.9 | 77.6 | 63.1 |
| reasoning | 77.0 | 87.2 | 88.3 | 77.7 |
| summary | 71.4 | 82.6 | 87.0 | 75.8 |
| unanswerable | 62.0 | 69.4 | 67.2 | 56.1 |

#### retrieval = summary
| kategori | →plain | →late | →ctx | →summ |
|---|---:|---:|---:|---:|
| fact_single | 66.2 | 47.3 | 48.8 | **97.6** |
| reasoning | 69.0 | 54.3 | 46.3 | **99.0** |
| summary | 73.5 | 48.5 | 46.6 | **98.1** |
| unanswerable | 68.7 | 44.3 | 45.3 | 93.9 |

---

## Key takeaways

1. **`plain` retrieval er den robuste generalist** — bedst eller næstbedst i alle 16 felter på nær summary→summary-diagonalen. Mindst varians.
2. **`summary` retrieval er bimodal** — fantastisk på sin egen GT (97-99% ved k=100), kollapser mod fremmede GT-strategier.
3. **`late` er svageste** ved k=20 (40%), men løfter sig mest når k stiger — den henter relevante chunks netop i 20-100-området.
4. **Diagonalen vinder altid** — retrieval-strategi og spørgsmåls-strategi matcher bedst.
5. **`unanswerable` er strukturelt sværeste kategori** — ikke noget kanonisk "rigtig" chunk at finde. Plain ved k=100 topper ved 65-77%.
6. **Knækpunkt på recall-kurven nås ikke ved k=100** for de fleste felter — kurven har stadig hovedrum opefter.

## Anbefaling for produktion

- **Default = `plain` retrieval, k=30-50.** Sweet spot på recall (~62-73% gennemsnit) uden context-eksplosion.
- k=100 giver +8pp recall, men 2× kontekst → 2× LLM-cost og -latency. Brug kun hvis budget tillader.
- **Nuværende default `late` er klart suboptimal** — bør udskiftes med `plain` i `filter_args.py:11`.

## Næste skridt at overveje

- **Hybrid plain+summary med RRF** — udnyt at de to fanger forskellige signaler. Forventet +5-10pp oveni.
- **BM25 + vector hybrid** — sparse retrieval rammer eksakt-match (IMO-nummer, datoer) bedre. Forventet +5-15pp på fact_single.
- **Cross-encoder rerank** — fra top-100 plain ned til top-20. Forbedrer MRR markant.
- **Knæk-punkt-test** ved k=200/500 — ser om recall fortsætter med at stige eller flader ud.

## Filplaceringer (rådata)

- `~/Desktop/ragrats/log/test_matrix/` — k=20 rådata (chunk_retrieval + e2e_retrieval)
- `~/Desktop/ragrats/log/test_matrix_k30/`
- `~/Desktop/ragrats/log/test_matrix_k50/`
- `~/Desktop/ragrats/log/test_matrix_k100/`
