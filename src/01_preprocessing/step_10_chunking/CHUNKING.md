# Chunking-overblik

Model: **Qwen3-Embedding-4B** (2556 dimensioner, kontekstvindue 32.768 tokens)
Database: `chunks`-tabellen med `strategy`-kolonne — samme dokument kan chunkes med flere strategier parallelt.

---

## fixture_summaries
- **Strategi:** Ingen chunking — embed direkte
- **Antal:** 20
- **Median:** 636 tegn = 159 tokens · **P95:** 787 tegn = 197 tokens · **Max:** 838 tegn = 210 tokens

---

## email_attach_summaries
- **Strategi:** Late chunking — `late/`
- **Status:** Ikke implementeret
- **Antal:** 13.191
- **Median:** 736 tegn = 184 tokens · **P95:** 1.497 tegn = 375 tokens · **Max:** 20.413 tegn = 5.112 tokens

Kommentar: Top 5% (> 1.497 tegn, ~660 rækker) indeholder summaries med truncation og repetition fra LLM — rerun anbefales efter fix af attachment-input i summariseringssteget.

---

## thread_summaries
- **Strategi:** Late chunking — `late/`
- **Status:** Ikke implementeret
- **Antal:** 4.578
- **Median:** 934 tegn = 248 tokens · **P95:** 2.762 tegn = 691 tokens · **Max:** 6.977 tegn = 1.752 tokens

---

## phase_summaries
- **Strategi:** Late chunking med overlap — `late_overlap/`
- **Status:** Ikke implementeret
- **Antal:** 1.218
- **Median:** 1.892 tegn = 473 tokens · **P95:** 3.570 tegn = 893 tokens · **Max:** 6.075 tegn = 1.524 tokens

Overlap-logik (per voyage, i kronologisk rækkefølge af `phase_index`):
- Chunk N = fuldt indhold af phase N
- Chunk N+1 = halen af chunk N (fra første punktum efter midten af N) + fuldt indhold af phase N+1
- Giver ~40-60% overlap afhængigt af sætningslængder — bevarer kontekst-kontinuitet på tværs af fase-grænser

---

## Mappestruktur

```
step_10_chunking/
  CHUNKING.md
  db.py
  paragraph/          ← midlertidig placeholder (bruges af run_chunking.py til email)
  late/               ← email_attach + thread
  late_overlap/       ← phase (overlap på forgående chunk)
```

## Database

Migration `0027_chunks_strategy.sql` tilføjede:
- `strategy TEXT NOT NULL` kolonne på `chunks`
- UNIQUE constraint: `(source_type, source_id, strategy, chunk_index)`
- `source_type` check: `email`, `voyage`, `thread`, `phase`
- `strategy` check: `paragraph`, `late`, `late_overlap`
