from __future__ import annotations

import psycopg

from step_02_chunk_retrieval.retrieve_vector import RetrievedChunk

from .fetch_email_summaries import fetch_email_summaries
from .fetch_fixture_summaries import fetch_fixture_summaries


def _voyage_label(idx: int) -> str:
    """0 -> 'A', 1 -> 'B', ..., 25 -> 'Z', 26 -> 'AA', etc."""
    label = ""
    n = idx
    while True:
        label = chr(ord("A") + (n % 26)) + label
        n = n // 26 - 1
        if n < 0:
            break
    return label


def build_context(
    conn: psycopg.Connection,
    chunks: list[RetrievedChunk],
    winning_keys: list[str],
) -> str:
    """Assemble the LLM context: fixture summaries + chunks grouped under their
    email thread summary.

    Layout:
        === VOYAGE FIXTURES ===
        [A] <fixture_summary>
        ...

        === SOURCES ===
        [VOYAGE A | EMAIL e1]
        THREAD SUMMARY: <thread summary>
        CHUNK 1 [email] (similarity 0.8421): <chunk text>
        CHUNK 2 [attachment] (similarity 0.7102): <chunk text>
        ...
    """
    fixture_summaries = fetch_fixture_summaries(conn, winning_keys)
    chunk_email_id, email_summaries = fetch_email_summaries(conn, chunks)

    # Group chunks by (voyage_key, email_id). email_id may be None for chunks
    # we couldn't resolve to a parent email.
    groups: dict[tuple[str, str | None], list[RetrievedChunk]] = {}
    for c in chunks:
        key = (c.voyage_key, chunk_email_id.get(c.chunk_id))
        groups.setdefault(key, []).append(c)

    # Sort groups by their best chunk's similarity, descending — keeps the most
    # relevant source group at the top while preserving the chunk↔summary link.
    sorted_groups = sorted(
        groups.items(),
        key=lambda kv: max(c.similarity for c in kv[1]),
        reverse=True,
    )

    voyage_label_map: dict[str, str] = {}
    email_label_map: dict[str, str] = {}

    def label_voyage(vk: str) -> str:
        if vk not in voyage_label_map:
            voyage_label_map[vk] = _voyage_label(len(voyage_label_map))
        return voyage_label_map[vk]

    def label_email(eid: str) -> str:
        if eid not in email_label_map:
            email_label_map[eid] = f"e{len(email_label_map) + 1}"
        return email_label_map[eid]

    # Assign labels in the order they will appear in the rendered output:
    # fixtures section first (preserves winning_keys order), then sources.
    for vk in winning_keys:
        if vk in fixture_summaries:
            label_voyage(vk)
    for (vk, eid), group in sorted_groups:
        label_voyage(vk)
        if eid is not None:
            label_email(eid)

    parts: list[str] = []

    if fixture_summaries:
        parts.append("=== VOYAGE FIXTURES ===")
        # Render in winning_keys order so the LLM sees them ranked by step_01 vote.
        rendered = set()
        for vk in winning_keys:
            summary = fixture_summaries.get(vk)
            if summary is None or vk in rendered:
                continue
            parts.append(f"[{label_voyage(vk)}]")
            parts.append(summary)
            parts.append("")
            rendered.add(vk)

    parts.append("=== SOURCES ===")
    chunk_counter = 0
    for (vk, eid), group in sorted_groups:
        vlabel = label_voyage(vk)
        if eid is not None:
            header = f"[VOYAGE {vlabel} | EMAIL {label_email(eid)}]"
        else:
            header = f"[VOYAGE {vlabel} | (no email)]"
        parts.append(header)

        if eid is not None and eid in email_summaries:
            parts.append(f"THREAD SUMMARY: {email_summaries[eid]}")

        for c in group:
            chunk_counter += 1
            parts.append(
                f"CHUNK {chunk_counter} [{c.source_type}] "
                f"(similarity {c.similarity:.4f}): {c.text}"
            )
        parts.append("")

    return "\n".join(parts).strip()
