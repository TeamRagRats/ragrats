"""Ground-truth loader for chunk_retrieval/run_test.py."""
from __future__ import annotations


def load_ground_truth(conn, voyage: str | None = None) -> dict[str, list[tuple]]:
    """Returns rows_by_category. Row tuple: (question_id, question, voyage_key,
    source_type, source_id, strategy). source_type is currently always 'email'
    and strategy always 'plain' — kept in the tuple so downstream code stays
    agnostic if/when ground_truth grows attachment/strategy variation."""
    voyage_filter_sql = "WHERE voyage_key = %(voyage)s" if voyage else ""
    voyage_params = {"voyage": voyage} if voyage else {}
    all_rows = conn.execute(f"""
        SELECT question_id::text, question, voyage_key,
               'email' AS source_type, source_id::text, category,
               'plain' AS strategy
        FROM ground_truth
        {voyage_filter_sql}
        ORDER BY category, question_id::text
    """, voyage_params).fetchall()

    rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, source_type, source_id, category, strategy in all_rows:
        rows_by_category.setdefault(category, []).append(
            (question_id, question, voyage_key, source_type, source_id, strategy)
        )
    return rows_by_category
