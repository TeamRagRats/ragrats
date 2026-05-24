"""k-værdier for matrix-kørslen.

Tæt sampling i bunden hvor recall-kurven er stejl (k = 1..20, ét ad gangen),
derefter grovere skridt på 10 op til 500. Det giver ~68 k-værdier pr. kategori.
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
    print(f"{len(ks)} k-værdier: {ks}")
