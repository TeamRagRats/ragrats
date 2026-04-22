from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from step_02_parse.merge_metadata import EmailRecord
from step_04_thread.normalize_subject import normalize_subject

# Mailbee strips In-Reply-To / References in some cases, which is why we 
# use a hybrid approach: header-chains first, then fallback to 
# normalized-subject + participant-overlap.
NAMESPACE = UUID("b5f5e8e4-6f6a-4b7c-9f1e-7a0d3c2f9a11")


@dataclass
class _UF:
    parent: dict[int, int]

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _participants(rec: EmailRecord) -> frozenset[str]:
    addrs: set[str] = set()
    if rec.from_addr:
        addrs.add(rec.from_addr.lower())
    for a in rec.to_addr:
        addrs.add(a.lower())
    for a in rec.cc_addr:
        addrs.add(a.lower())
    return frozenset(addrs)


def build_threads(records: Iterable[EmailRecord]) -> dict[UUID, list[int]]:
    # NOTE: records should be pre-sorted for deterministic output
    recs = list(records)
    n = len(recs)
    uf = _UF(parent={i: i for i in range(n)})
    
    # 2. Header-based threading
    # Map Message-ID string -> index in recs
    msg_id_to_idx: dict[str, int] = {}
    for i, r in enumerate(recs):
        if r.message_id:
            msg_id_to_idx[r.message_id] = i
            
    for i, r in enumerate(recs):
        # Link via In-Reply-To
        if r.in_reply_to and r.in_reply_to in msg_id_to_idx:
            uf.union(i, msg_id_to_idx[r.in_reply_to])
        
        # Link via References
        for ref in r.references:
            if ref in msg_id_to_idx:
                uf.union(i, msg_id_to_idx[ref])

    # 3. Fallback: Subject + Participant clustering
    by_subject: dict[str, list[int]] = defaultdict(list)
    parts = [_participants(r) for r in recs]
    norms = [normalize_subject(r.subject) for r in recs]
    
    for i, norm in enumerate(norms):
        by_subject[norm].append(i)
        
    for norm, idxs in by_subject.items():
        if not norm or len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                # If they share a participant AND have the same subject, merge
                if parts[idxs[a]] & parts[idxs[b]]:
                    uf.union(idxs[a], idxs[b])
                    
    # 4. Group into clusters
    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        clusters[uf.find(i)].append(i)
        
    # We return the root index as a UUID for the thread key
    return {UUID(int=root): members for root, members in clusters.items()}
