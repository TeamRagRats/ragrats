"""k values for the matrix run.

Dense sampling at the bottom where the recall curve is steep (k = 1..20, one at a
time), then coarser steps of 10 up to 500. That gives ~68 k values per category.
"""

from __future__ import annotations


def build_k_values(
    fine_max: int = 20,
    coarse_step: int = 10,
    coarse_max: int = 500,
) -> list[int]:
    fine = list(range(1, fine_max + 1))
    coarse_start = fine_max + coarse_step
    coarse = list(range(coarse_start, coarse_max + 1, coarse_step))
    return fine + coarse


if __name__ == "__main__":
    ks = build_k_values()
    print(f"{len(ks)} k values: {ks}")
