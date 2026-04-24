from __future__ import annotations

# Orchestrates threading for a single voyage: sorts records, calls build_threads,
# and generates a deterministic UUID5 thread_id per cluster (seeded by voyage_key + earliest email).
# Returns a dict mapping email_id → thread_id. Used in run_ingest.py.

from typing import Iterable
from uuid import UUID, uuid5

from step_02_parse.merge_metadata import EmailRecord
from step_04_thread.build_threads import NAMESPACE, build_threads
from step_04_thread.normalize_subject import normalize_subject


def assign_thread_ids(voyage_key: str, records: Iterable[EmailRecord]) -> dict[UUID, UUID]:
    # 1. Sort records to ensure deterministic clustering and seed selection
    # We sort by sent_at, then email_id as a tie-breaker.
    recs = sorted(
        records, 
        key=lambda r: (r.sent_at.timestamp() if r.sent_at else 0, str(r.email_id))
    )
    
    clusters = build_threads(recs)
    email_to_thread: dict[UUID, UUID] = {}
    
    for members in clusters.values():
        # Because recs is sorted, min(members) is the earliest email in the cluster.
        seed_idx = min(members)
        seed = recs[seed_idx]
        
        # Use a stable key for the UUID v5 generation.
        # We include voyage_key to isolate threads between different imports.
        seed_key = normalize_subject(seed.subject) or str(seed.email_id)
        thread_id = uuid5(NAMESPACE, f"{voyage_key}|{seed_key}|{seed.email_id}")
        
        for idx in members:
            email_to_thread[recs[idx].email_id] = thread_id
            
    return email_to_thread
