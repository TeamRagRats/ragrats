"""
Anonymiseret retrieval: strip vessel_name + voyage_key (og MV-prefix) ud af
spørgsmålet før embedding. Så testes om embedding faktisk forstår semantisk
indhold (datoer, havne, fragtrater) frem for at gen-genkende skibsnavne.

Hvis recall falder dramatisk (fx 99% -> 30%), bekræfter det at det meste
af "succesen" var trivielt skibsnavn-match.
"""
from __future__ import annotations

import re


def anonymize(question: str, vessel_name: str, voyage_key: str) -> str:
    q = question
    # Voyage_key (fx ATALANTE_1) — ordret, case-insensitive
    q = re.sub(re.escape(voyage_key), "the voyage", q, flags=re.IGNORECASE)
    # Vessel_name som hele ord — håndter både "Eastbourne" og "MV EASTBOURNE"
    if vessel_name:
        pattern = r"(?:MV\s+)?\b" + re.escape(vessel_name) + r"\b"
        q = re.sub(pattern, "the vessel", q, flags=re.IGNORECASE)
    # Fjern dobbelt-mellemrum
    q = re.sub(r"\s+", " ", q).strip()
    return q


def topk_keys_via_embedding(conn, embedding: list[float], top_k: int) -> set[str]:
    conn.execute(f"SET LOCAL hnsw.ef_search = {int(top_k)}")
    rows = conn.execute("""
        SELECT DISTINCT voyage_key FROM (
            SELECT voyage_key FROM chunks
            ORDER BY embedding <=> %s::halfvec
            LIMIT %s
        ) s
    """, [embedding, top_k]).fetchall()
    return {r[0] for r in rows}


def report_anonymized_recall(conn, client, ks: list[int], sample_size: int = 100) -> None:
    print("\n" + "=" * 70)
    print(f"ANONYMISERET RECALL@k (sample {sample_size} pr. kategori)")
    print("=" * 70)
    print("Vessel_name + voyage_key fjernes fra spørgsmålet før embedding.")
    print("Falder recall dramatisk her, var skibsnavn-match drivkraften.\n")

    import random
    rows = conn.execute("""
        SELECT category, question, vessel_name, voyage_key FROM ground_truth_v2
    """).fetchall()
    by_cat: dict[str, list] = {}
    for cat, q, v, k in rows:
        by_cat.setdefault(cat, []).append((q, v, k))

    print("Eksempler på anonymisering:")
    sample_pool = [r for r in rows[:5]]
    for cat, q, v, k in sample_pool:
        anon = anonymize(q, v, k)
        print(f"  [{cat}] '{q[:80]}'")
        print(f"     -> '{anon[:80]}'")

    header = f"\n{'category':22s}" + "".join(f"{'k=' + str(k):>12s}" for k in ks)
    print(header)
    print("-" * len(header))

    for cat in sorted(by_cat):
        triples = by_cat[cat]
        sample = random.sample(triples, min(sample_size, len(triples)))
        cells = []
        for k in ks:
            hits = 0
            for q, vessel, vkey in sample:
                anon_q = anonymize(q, vessel, vkey)
                emb = client.embed([anon_q])[0]
                keys = topk_keys_via_embedding(conn, emb, k)
                if vkey in keys:
                    hits += 1
            cells.append(f"{100.0*hits/len(sample):>10.1f}%")
        print(f"{cat:22s}" + "".join(f"{c:>12s}" for c in cells))
