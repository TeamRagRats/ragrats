"""
Distribution-stats: hvor mange unikke voyage_keys, hvor skæv er fordelingen?
Hvis fordelingen er meget skæv, og ground truth peger på de hyppigste keys,
bliver høj recall trivielt — uanset embedding-kvalitet.
"""
from __future__ import annotations


def report_chunk_distribution(conn) -> None:
    print("=" * 70)
    print("CHUNK & VOYAGE_KEY FORDELING")
    print("=" * 70)

    total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    total_keys = conn.execute("SELECT COUNT(DISTINCT voyage_key) FROM chunks").fetchone()[0]
    print(f"Total chunks:             {total_chunks:,}")
    print(f"Unikke voyage_keys:       {total_keys:,}")
    print(f"Gennemsnit chunks/key:    {total_chunks / max(total_keys, 1):.1f}")

    print("\nTop 15 voyage_keys efter chunk-antal:")
    rows = conn.execute("""
        SELECT voyage_key, COUNT(*) AS n
        FROM chunks GROUP BY voyage_key ORDER BY n DESC LIMIT 15
    """).fetchall()
    for key, n in rows:
        pct = 100.0 * n / total_chunks
        print(f"  {key:40s} {n:6,}  ({pct:5.2f}%)")

    cum_top10 = sum(r[1] for r in rows[:10])
    print(f"\nTop 10 keys dækker {cum_top10:,}/{total_chunks:,} chunks "
          f"({100.0*cum_top10/total_chunks:.1f}%)")


def report_ground_truth_distribution(conn) -> None:
    print("\n" + "=" * 70)
    print("GROUND TRUTH PER KATEGORI")
    print("=" * 70)

    rows = conn.execute("""
        SELECT category,
               COUNT(*)                       AS questions,
               COUNT(DISTINCT voyage_key)     AS unique_keys
        FROM ground_truth_v2 GROUP BY category ORDER BY category
    """).fetchall()
    print(f"{'category':22s} {'questions':>10s} {'unique_keys':>14s} {'q/key':>8s}")
    for cat, q, k in rows:
        print(f"{cat:22s} {q:>10,} {k:>14,} {q/max(k,1):>8.1f}")

    print("\nFor hver kategori: top 5 expected_keys (hvor mange spørgsmål peger på samme key):")
    cats = [r[0] for r in rows]
    for cat in cats:
        top = conn.execute("""
            SELECT voyage_key, COUNT(*) AS n
            FROM ground_truth_v2 WHERE category = %s
            GROUP BY voyage_key ORDER BY n DESC LIMIT 5
        """, [cat]).fetchall()
        print(f"\n  [{cat}]")
        for key, n in top:
            print(f"    {key:40s} {n:>4} spørgsmål")


def report_key_coverage_in_chunks(conn) -> None:
    """
    Hvor mange chunks tilhører de keys der overhovedet optræder som expected_key?
    Hvis kun et lille subset af chunks-tabellen er 'i spil', er recall@k højere
    end den ville være på en større population.
    """
    print("\n" + "=" * 70)
    print("DÆKNING: HVOR STOR DEL AF CHUNKS-TABELLEN ER 'I SPIL'?")
    print("=" * 70)
    row = conn.execute("""
        WITH gt_keys AS (SELECT DISTINCT voyage_key FROM ground_truth_v2)
        SELECT
            (SELECT COUNT(*) FROM chunks) AS total,
            (SELECT COUNT(*) FROM chunks WHERE voyage_key IN (SELECT voyage_key FROM gt_keys)) AS in_play
    """).fetchone()
    total, in_play = row
    print(f"Chunks i alt:                       {total:,}")
    print(f"Chunks tilhørende en gt voyage_key: {in_play:,} ({100.0*in_play/max(total,1):.1f}%)")
    print("(Hvis 'in_play' er en lille brøkdel, er recall trivielt højere — ANN'en")
    print(" har let ved at undgå chunks som alligevel ikke matcher en gt-key.)")
