"""
BM25-lignende baseline via Postgres full-text search (ts_rank).
Hvis BM25 scorer tæt på ANN, så måler ANN-testen ikke embedding-kvalitet —
keyword-match (skibsnavn, havn, dato) er nok.
"""
from __future__ import annotations


def bm25_topk_keys(conn, question: str, top_k: int) -> set[str]:
    rows = conn.execute("""
        WITH q AS (SELECT plainto_tsquery('english', %s) AS query)
        SELECT DISTINCT voyage_key FROM (
            SELECT voyage_key
            FROM chunks, q
            WHERE to_tsvector('english', text) @@ q.query
            ORDER BY ts_rank(to_tsvector('english', text), q.query) DESC
            LIMIT %s
        ) s
    """, [question, top_k]).fetchall()
    return {r[0] for r in rows}


def report_bm25_baseline(conn, ks: list[int]) -> None:
    print("\n" + "=" * 70)
    print("BM25/FULL-TEXT BASELINE RECALL@k (ts_rank)")
    print("=" * 70)
    print("Postgres full-text search uden embedding. Hvis tallene ligner ANN,")
    print("så er ANN'en ikke det der løfter recall — ren keyword-match er nok.\n")

    rows = conn.execute("""
        SELECT category, question, voyage_key FROM ground_truth_v2
    """).fetchall()
    by_cat: dict[str, list] = {}
    for cat, q, key in rows:
        by_cat.setdefault(cat, []).append((q, key))

    header = f"{'category':22s}" + "".join(f"{'k=' + str(k):>12s}" for k in ks)
    print(header)
    print("-" * len(header))

    for cat in sorted(by_cat):
        pairs = by_cat[cat]
        cells = []
        for k in ks:
            hits = 0
            for q, expected in pairs:
                keys = bm25_topk_keys(conn, q, k)
                if expected in keys:
                    hits += 1
            cells.append(f"{100.0*hits/len(pairs):>10.1f}%")
        print(f"{cat:22s}" + "".join(f"{c:>12s}" for c in cells))
