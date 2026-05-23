"""
Diagnose-suite for voyage_key recall-tallene.

Kører:
  1) Distribution af chunks/voyage_keys og ground truth (rent SQL, hurtigt)
  2) Random-baseline recall@k for k ∈ {1, 10, 18, 30}
  3) Source-chunk-leakage (kræver embed-server) — sample
  4) Verbatim-stikprøve (rent SQL)

Kør på SPARK hvor postgres + embed-server er nået:
    python -m diagnose.run
    python -m diagnose.run --no-embed         # spring leakage-delen over (ingen embed-server nødvendig)
    python -m diagnose.run --sample 100       # større leakage-sample
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
_repo_root = _here.parents[4]
_retrieval = _repo_root / "src" / "02_retrieval"
sys.path.insert(0, str(_here))
sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_retrieval))

import argparse

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL

from distribution import (
    report_chunk_distribution,
    report_ground_truth_distribution,
    report_key_coverage_in_chunks,
)
from random_baseline import report_random_baseline
from leakage import report_source_chunk_leakage, report_verbatim_sample
from tsrank_baseline import report_tsrank_baseline
from anonymized import report_anonymized_recall


def main() -> None:
    p = argparse.ArgumentParser(description="Diagnose voyage_key recall-tal")
    p.add_argument("--no-embed", action="store_true",
                   help="Spring leakage-checks over (ingen embed-server)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL)
    p.add_argument("--top-k", type=int, default=18,
                   help="k til source-chunk-leakage (default: 18)")
    p.add_argument("--sample", type=int, default=50,
                   help="Stikprøve-størrelse til leakage-tjek (default: 50)")
    p.add_argument("--ks", type=int, nargs="+", default=[1, 10, 18, 30],
                   help="k-værdier til random- og ts_rank-baseline + anonymiseret")
    args = p.parse_args()

    with connect() as conn:
        report_chunk_distribution(conn)
        report_ground_truth_distribution(conn)
        report_key_coverage_in_chunks(conn)
        report_random_baseline(conn, args.ks)
        report_tsrank_baseline(conn, args.ks)
        report_verbatim_sample(conn, n=15)

    if not args.no_embed:
        client = EmbedClient(base_url=args.embed_url)
        with connect() as conn:
            report_source_chunk_leakage(conn, client, top_k=args.top_k,
                                        sample_size=args.sample)
            report_anonymized_recall(conn, client, args.ks,
                                     sample_size=args.sample)
    else:
        print("\n[--no-embed: source-chunk-leakage + anonymiseret sprunget over]")


if __name__ == "__main__":
    main()
