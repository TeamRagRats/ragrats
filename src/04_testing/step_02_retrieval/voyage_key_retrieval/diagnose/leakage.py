"""
Data-leakage-tjek:

1) Source-chunk-leakage: hvor ofte er ground_truth_v2.source_chunk_id selv
   blandt de top_k mest similar chunks? Spørgsmålet blev genereret FRA den chunk,
   så hvis embeddingen finder den selv tilbage, er det ikke "generalisering".

2) Verbatim-leakage (stikprøve): står expected voyage_key (eller dele af den)
   ordret i spørgsmålsteksten? Hvis ja, er semantisk søgning trivielt.
"""
from __future__ import annotations

import random


def topk_chunk_ids(conn, query_embedding: list[float], top_k: int) -> list:
    conn.execute(f"SET LOCAL hnsw.ef_search = {int(top_k)}")
    rows = conn.execute("""
        SELECT chunk_id FROM chunks
        ORDER BY embedding <=> %s::halfvec
        LIMIT %s
    """, [query_embedding, top_k]).fetchall()
    return [r[0] for r in rows]


def report_source_chunk_leakage(conn, client, top_k: int, sample_size: int = 50) -> None:
    print("\n" + "=" * 70)
    print(f"SOURCE-CHUNK-LEAKAGE (sample {sample_size}, k={top_k})")
    print("=" * 70)
    print("Hvor ofte ligger ground_truth_v2.source_chunk_id selv i top_k?")
    print("Hvis det er ~100%, måler vi mest 'kan modellen finde sin kilde-chunk tilbage'.\n")

    rows = conn.execute("""
        SELECT category, question, source_chunk_id, voyage_key
        FROM ground_truth_v2
    """).fetchall()
    by_cat: dict[str, list] = {}
    for cat, q, sc, vk in rows:
        by_cat.setdefault(cat, []).append((q, sc, vk))

    print(f"{'category':22s} {'source_in_topk':>16s} {'key_in_topk':>14s}")
    for cat in sorted(by_cat):
        pool = by_cat[cat]
        sample = random.sample(pool, min(sample_size, len(pool)))
        src_hits = 0
        key_hits = 0
        for q, source_chunk_id, expected_key in sample:
            emb = client.embed([q])[0]
            chunk_ids = topk_chunk_ids(conn, emb, top_k)
            if source_chunk_id in chunk_ids:
                src_hits += 1
            keys = conn.execute("""
                SELECT DISTINCT voyage_key FROM chunks WHERE chunk_id = ANY(%s)
            """, [chunk_ids]).fetchall()
            if expected_key in {r[0] for r in keys}:
                key_hits += 1
        n = len(sample)
        print(f"{cat:22s} {src_hits:>3}/{n:<3} ({100.0*src_hits/n:>5.1f}%)   "
              f"{key_hits:>3}/{n:<3} ({100.0*key_hits/n:>5.1f}%)")


def report_verbatim_sample(conn, n: int = 15) -> None:
    print("\n" + "=" * 70)
    print(f"VERBATIM-LEAKAGE STIKPRØVE (n={n})")
    print("=" * 70)
    print("Står expected voyage_key (eller vessel_name) ordret i spørgsmålet?")
    print("Hvis ja for de fleste, er ANN-søgningen ikke nødvendig — keyword-match nok.\n")

    rows = conn.execute("""
        SELECT category, question, voyage_key, vessel_name
        FROM ground_truth_v2
        ORDER BY random() LIMIT %s
    """, [n]).fetchall()

    for cat, q, key, vessel in rows:
        ql = q.lower()
        key_in = key.lower() in ql
        vessel_in = vessel.lower() in ql if vessel else False
        flags = []
        if key_in: flags.append("KEY_VERBATIM")
        if vessel_in: flags.append("VESSEL_VERBATIM")
        flag_str = " ".join(flags) if flags else "(intet trivielt match)"
        print(f"[{cat}] expected_key={key} | vessel={vessel}")
        print(f"  Q: {q[:140]}{'...' if len(q) > 140 else ''}")
        print(f"  -> {flag_str}\n")
