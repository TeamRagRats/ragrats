# Diagnose-rapport: voyage_key recall@k

**Dato:** 2026-05-05
**Test:** `voyage_key_retrieval/run_test.py` (efter fix af hit-definition: `expected_key in vote_counts`)

## TL;DR

Recall@k-tallene (~99% ved k=18) er **ikke fake**, men det de faktisk måler er
**lettere end navnet antyder**. Embedding-modellen gør reelt arbejde
ud over keyword-match, men datasettets struktur (kun 23 voyage_keys, vessel_name
ordret i ~93% af spørgsmål) gør opgaven trivielt løsbar med navne-lookup
i de fleste tilfælde. Anonymiseret retrieval afslører at recall@1 falder
fra ~75% → 18-34% når vessel_name strippes — embeddingen bruger primært
navne-signal, ikke semantisk forståelse af spørgsmålets indhold.

## Datasettets struktur

| Mål | Værdi |
|---|---|
| Total chunks | 19.006 |
| Unikke voyage_keys | **23** |
| Gennemsnit chunks/key | 826 |
| Top-10 keys' andel af chunks | 70,6% |
| Spørgsmål total | 868 (commercial 297, incident 206, logistics 365) |
| Unikke gt expected_keys | 23 (alle keys er repræsenteret) |
| Chunks "in play" (gt-keys) | 19.006 / 19.006 = 100% |

**Implikation:** Det er reelt en 23-klasse klassifikation, ikke open retrieval.
Ved k=18 chunks dækkes typisk 8–13 unikke keys ud af 23.

## Hovedresultater (alle tal er recall@k)

### ANN (efter fix)

| kategori | k=1 | k=10 | k=18 | k=30 |
|---|---|---|---|---|
| commercial_terms | 66,7% | 93,6% | 99,0% | 99,3% |
| incident_decision | 76,7% | 90,8% | 98,1% | 99,0% |
| logistics_cargo | 81,1% | 90,1% | 98,6% | 99,5% |

### Random-baseline (vælg k tilfældige chunks)

| kategori | k=1 | k=10 | k=18 | k=30 |
|---|---|---|---|---|
| commercial_terms | 3,4% | 32,7% | 51,9% | 70,7% |
| incident_decision | 5,3% | 32,5% | 48,5% | 67,0% |
| logistics_cargo | 4,1% | 36,4% | 50,4% | 68,5% |

→ ANN giver +30 til +70 procentpoint over random. **Embedding gør reelt arbejde.**
Ved k=30 nærmer random sig dog 70%, så recall@30 alene er ikke imponerende —
**recall@1 og recall@10 er de meningsfulde tal.**

### BM25-baseline (Postgres `plainto_tsquery` + `ts_rank`)

| kategori | k=1 | k=10 | k=18 | k=30 |
|---|---|---|---|---|
| commercial_terms | 41,4% | 43,4% | 43,4% | 43,4% |
| incident_decision | 50,0% | 51,5% | 51,5% | 51,5% |
| logistics_cargo | 57,0% | 58,9% | 58,9% | 58,9% |

→ Plateau ved k=10 fordi `plainto_tsquery` kræver AND af alle tokens —
~half af spørgsmålene returnerer tomt. Den naive BM25 er en for streng baseline;
en OR-variant ville score højere. **Sammenligning med ANN er ikke 100% fair her.**

### Anonymiseret ANN (vessel_name + voyage_key fjernet før embedding)

| kategori | k=1 | k=10 | k=18 | k=30 |
|---|---|---|---|---|
| commercial_terms | 18,0% | 44,0% | 70,0% | 82,0% |
| incident_decision | 24,0% | 66,0% | 86,0% | 88,0% |
| logistics_cargo | 34,0% | 72,0% | 88,0% | 90,0% |

**Sammenligning ANN normalt vs anonymiseret @ k=1:**

| kategori | normal | anonymiseret | drop |
|---|---|---|---|
| commercial_terms | 66,7% | 18,0% | **−48,7 pp** |
| incident_decision | 76,7% | 24,0% | **−52,7 pp** |
| logistics_cargo | 81,1% | 34,0% | **−47,1 pp** |

→ **Vessel_name er primær drivkraft.** Når navnet fjernes, falder recall@1
med ~50 procentpoint. Embeddingen bruger semantisk indhold sekundært.

## Verbatim-leakage

Stikprøve på 15 spørgsmål: **14/15 (~93%) nævner vessel_name ordret**
i spørgsmålet (typisk "MV NAME" eller "the Name"). 1/15 nævner endda
voyage_key ("ATALANTE_1") direkte.

Eksempler:
- "On what date does **the MV Eastbourne** have its scheduled stop in Valletta?"
- "What demurrage rate applies on the **African Juniper** fixture?"
- "When will the bunker survey be conducted on **MV ATALANTE during Voyage ATALANTE_1**?"

## Source-chunk-leakage

Stikprøve på 50 pr. kategori, k=18:

| kategori | source_chunk_id i top_k | key i top_k |
|---|---|---|
| commercial_terms | 26,0% | 100,0% |
| incident_decision | 38,0% | 98,0% |
| logistics_cargo | 26,0% | 94,0% |

→ Den eksakte kilde-chunk findes kun i 26-38% af tilfældene, men key dækkes
i 94-100%. Det er **et godt tegn** — testen måler ikke kun "find din egen kilde"
men "find ANY chunk fra det rigtige skib".

## Konklusion

1. **Recall@k-tallene er korrekte efter fixet** (`hit = expected_key in vote_counts`).
   Monotonicitet er genoprettet.

2. **Tallene er trivielt høje** fordi opgaven er let:
   - Kun 23 voyage_keys at vælge mellem
   - Vessel_name er ordret i ~93% af spørgsmål
   - Hver key har gennemsnitligt 826 chunks → ANN finder næsten altid mindst én

3. **Embedding gør reelt arbejde** — vist ved gap til random-baseline.
   Men det "arbejde" er primært skibsnavn → embedding-cluster matching,
   ikke semantisk forståelse af spørgsmålets indhold.

4. **Anonymiseret recall er det ærlige tal** for embedding-kvalitet:
   - Recall@1 ~25% (mod ~75% normalt)
   - Recall@10 ~60% (mod ~92% normalt)
   - Recall@18 ~80% (mod ~99% normalt)

5. **Recall@30+ ≈ 99% er ikke en meningsfuld metric** for at sammenligne
   retrieval-kvalitet på dette dataset — random-baseline ligger på 67-70%
   alene, og resten af gappet lukkes hurtigt af enhver semi-fungerende
   retrieval.

## Anbefalinger

- **Brug recall@1 og recall@10 som primære metrics** — ikke recall@18 eller højere.
- **Rapportér både normal og anonymiseret recall** parallelt for at vise
  hvor stor en del der drives af navne-match.
- **Generér nye spørgsmål uden vessel_name** hvis I vil teste semantisk
  retrieval-kvalitet ærligt.
- **Overvej fair BM25-baseline** med `websearch_to_tsquery` + ts_rank på
  alle chunks (uden AND-filter) for ærlig sammenligning. Den naive
  `plainto_tsquery`-version her undervurderer keyword-baseline.

## Kør diagnose-suite igen

```bash
cd src/04_testing/step_02_retrieval/voyage_key_retrieval
python3 diagnose/run.py                  # alt (kræver embed-server)
python3 diagnose/run.py --no-embed       # kun SQL-tjek + random + BM25
python3 diagnose/run.py --sample 200     # større sample til leakage + anonymiseret
```

Filer:
- `diagnose/distribution.py` — chunk/key-fordeling og gt-statistik
- `diagnose/random_baseline.py` — random recall@k
- `diagnose/bm25_baseline.py` — Postgres ts_rank baseline
- `diagnose/leakage.py` — source-chunk + verbatim-stikprøve
- `diagnose/anonymized.py` — recall efter strip af vessel_name + voyage_key
- `diagnose/run.py` — orchestrator
