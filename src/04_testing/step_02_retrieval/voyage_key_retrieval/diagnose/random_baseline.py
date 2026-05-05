"""
Random-baseline: for hver gt-row, vælg k tilfældige chunks og tjek om
expected_key er blandt deres voyage_keys. Hvis dette tal ligger tæt på den
"rigtige" recall, måler vi key-distributions-skævhed, ikke retrieval.
"""
from __future__ import annotations


def random_recall(conn, top_k: int) -> dict[str, tuple[int, int]]:
    rows = conn.execute("""
        SELECT category, voyage_key FROM ground_truth_v2
    """).fetchall()

    by_cat: dict[str, list[str]] = {}
    for cat, key in rows:
        by_cat.setdefault(cat, []).append(key)

    results: dict[str, tuple[int, int]] = {}
    for cat in sorted(by_cat):
        expected_keys = by_cat[cat]
        hits = 0
        for expected in expected_keys:
            sampled = conn.execute("""
                SELECT DISTINCT voyage_key FROM (
                    SELECT voyage_key FROM chunks ORDER BY random() LIMIT %s
                ) s
            """, [top_k]).fetchall()
            sampled_set = {r[0] for r in sampled}
            if expected in sampled_set:
                hits += 1
        results[cat] = (hits, len(expected_keys))
    return results


def report_random_baseline(conn, ks: list[int]) -> None:
    print("\n" + "=" * 70)
    print("RANDOM-BASELINE RECALL@k")
    print("=" * 70)
    print("For hver gt-row: vælg k tilfældige chunks. Recall = expected_key i deres keys.")
    print("Hvis dette ligner den ANN-baserede recall, er retrieval ikke det der løfter tallet.\n")

    header = f"{'category':22s}" + "".join(f"{'k=' + str(k):>12s}" for k in ks)
    print(header)
    print("-" * len(header))

    cat_rows: dict[str, list[str]] = {}
    for k in ks:
        results = random_recall(conn, k)
        for cat, (h, t) in results.items():
            cat_rows.setdefault(cat, []).append(f"{100.0*h/max(t,1):>10.1f}%")
    for cat in sorted(cat_rows):
        print(f"{cat:22s}" + "".join(f"{v:>12s}" for v in cat_rows[cat]))
