"""Plot voyage-key resultater opdelt på kategori — én subplot pr. strategi.

Samme matrix-kørsel som plot_strategies.py, men i stedet for den samlede
'total'-række tegnes per-kategori-rækkerne (fact_single / summary / reasoning),
så man kan se hvor en strategi kæmper når k stiger.

Kør på SPARK (kræver postgres):
    cd src/04_testing/step_02_retrieval/voyage_key_retrieval/matrix/plots
    python plot_by_category.py
    python plot_by_category.py --matrix-id <uuid> --out by_category.png
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
from matplotlib.ticker import FixedLocator

from loader import latest_matrix_id, metric_label, load_by_category

STRATEGIES = ["plain", "late", "context", "summary"]
CATEGORIES = ["fact_single", "summary", "reasoning"]

# Brudt x-akse: k=0–20 strækkes ud (1 enhed pr. k), k>20 komprimeres så hvert
# 25. k fylder lige så meget som et 2-spring i lav-området. Ticks følger samme
# logik: hvert 2. op til 20, derefter hvert 25.
KNEE = 20.0
HI_COMPRESS = 2.0 / 25.0  # 25 k i høj-området = 2 enheder (= et lav-tick-spring)
XTICKS = [1] + list(range(2, 21, 2)) + list(range(45, 501, 25))


def _fwd(k):
    import numpy as np
    k = np.asarray(k, dtype=float)
    return np.where(k <= KNEE, k, KNEE + (k - KNEE) * HI_COMPRESS)


def _inv(p):
    import numpy as np
    p = np.asarray(p, dtype=float)
    return np.where(p <= KNEE, p, KNEE + (p - KNEE) / HI_COMPRESS)


def _ordered(keys, preferred):
    return [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]


def plot(curves: dict[str, dict[str, dict[str, list]]], metric: str,
         matrix_id: str, out: Path) -> None:
    strategies = _ordered(curves.keys(), STRATEGIES)
    fig, axes = plt.subplots(
        len(strategies), 1, figsize=(12, 4 * len(strategies)),
        sharex=True, squeeze=False,
    )
    for row, strategy in enumerate(strategies):
        ax = axes[row][0]
        by_cat = curves[strategy]
        for category in _ordered(by_cat.keys(), CATEGORIES):
            c = by_cat[category]
            ax.plot(c["k"], c["recall"], marker="o", markersize=3, label=category)
        ax.set_title(f"{strategy} — {metric}")
        ax.set_ylabel(metric)
        ax.set_xscale("function", functions=(_fwd, _inv))
        ax.set_xlim(1, 500)
        ax.xaxis.set_major_locator(FixedLocator(XTICKS))
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.axvline(KNEE, color="gray", lw=0.8, ls="--", alpha=0.5)
        ax.legend(title="kategori", fontsize="small")
        if row == len(strategies) - 1:
            ax.set_xlabel("top-k")

    fig.suptitle(f"Voyage-key {metric} pr. kategori")
    fig.text(0.01, 0.005, f"matrix_id={matrix_id}", fontsize=6, color="gray")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot voyage-key kurver pr. kategori, én række pr. strategi")
    p.add_argument("--matrix-id", default=None, help="Matrix-kørsel (default: seneste)")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "by_category.png",
                   help="Output PNG (default: ./by_category.png)")
    args = p.parse_args()

    matrix_id = args.matrix_id or latest_matrix_id()
    if not matrix_id:
        raise SystemExit("Ingen matrix-kørsel fundet. Kør run_matrix.py først.")

    curves = load_by_category(matrix_id)
    if not curves:
        raise SystemExit(f"Ingen kategori-rækker for matrix_id={matrix_id}.")

    metric = metric_label(matrix_id)
    for strategy, by_cat in curves.items():
        cats = ", ".join(f"{c}({len(v['k'])})" for c, v in by_cat.items())
        print(f"{strategy}: {cats}")
    plot(curves, metric, matrix_id, args.out)


if __name__ == "__main__":
    main()
