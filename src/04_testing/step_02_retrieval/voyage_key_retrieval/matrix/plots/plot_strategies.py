"""Plot hvordan strategierne klarer sig: én linje pr. strategi vs. k.

Læser 'total'-rækkerne fra den seneste voyage-key matrix-kørsel (eller en
specifik --matrix-id) og tegner én kurve pr. strategi. Y-aksen er recall@k eller
voting hit-rate afhængigt af hvad matrixen blev kørt med.

Kør på SPARK (kræver postgres):
    cd src/04_testing/step_02_retrieval/voyage_key_retrieval/matrix/plots
    python plot_strategies.py
    python plot_strategies.py --matrix-id <uuid> --out strategies.png
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    sys.path.insert(0, str(_here))
    sys.path.insert(0, str(_here.parents[5]))

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from loader import latest_matrix_id, metric_label, load_total

STRATEGIES = ["plain", "late", "context", "summary"]


def _ordered(keys, preferred):
    return [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]


def plot(curves: dict[str, dict[str, list]], metric: str, matrix_id: str, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    for strategy in _ordered(curves.keys(), STRATEGIES):
        c = curves[strategy]
        ax.plot(c["k"], c["recall"], marker="o", markersize=3, label=strategy)

    ax.set_title(f"Voyage-key — {metric} vs top-k (alle kategorier samlet)")
    ax.set_xlabel("top-k")
    ax.set_ylabel(metric)
    ax.set_xlim(left=0)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend(title="strategi")

    fig.text(0.01, 0.01, f"matrix_id={matrix_id}", fontsize=6, color="gray")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot voyage-key strategi-kurver vs k")
    p.add_argument("--matrix-id", default=None, help="Matrix-kørsel (default: seneste)")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "strategies.png",
                   help="Output PNG (default: ./strategies.png)")
    args = p.parse_args()

    matrix_id = args.matrix_id or latest_matrix_id()
    if not matrix_id:
        raise SystemExit("Ingen matrix-kørsel fundet. Kør run_matrix.py først.")

    curves = load_total(matrix_id)
    if not curves:
        raise SystemExit(f"Ingen 'total'-rækker for matrix_id={matrix_id}.")

    metric = metric_label(matrix_id)
    for strategy, c in curves.items():
        print(f"{strategy}: {len(c['k']) - 1} k-punkter (k {c['k'][1]}..{c['k'][-1]})")
    plot(curves, metric, matrix_id, args.out)


if __name__ == "__main__":
    main()
