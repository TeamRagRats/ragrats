"""Plot how the strategies perform: one line per strategy vs k.

Reads the 'total' rows from the latest voyage-key matrix run (or a specific
--matrix-id) and draws one curve per strategy. The y-axis is recall@k or voting
hit-rate depending on what the matrix was run with.

Run on SPARK (requires postgres):
    cd src/04_testing/step_02_retrieval/voyage_key_retrieval/matrix/plots
    python strategies/plot.py
    python strategies/plot.py --matrix-id <uuid>
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    sys.path.insert(0, str(_here.parents[6]))
    sys.path.insert(0, str(_here.parent / "_shared"))

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator

from loader import latest_matrix_id, metric_label, load_total

STRATEGIES = ["plain", "late", "context", "summary"]
# Distinct marker per line so the series are legible without relying on colour
# (colour-blind friendly): circle, square, triangle, diamond.
MARKERS = ["o", "s", "^", "D"]

# Broken x-axis: k=0–20 is stretched out (1 unit per k), k>20 is compressed so
# every 25th k takes up as much space as a 2-step in the low range. Ticks follow
# the same logic: every 2 up to 20, then every 25.
KNEE = 20.0
HI_COMPRESS = 2.0 / 25.0  # 25 k in the high range = 2 units (= one low-tick step)
XTICKS = [1] + list(range(2, 21, 2)) + list(range(50, 501, 25))


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


def plot(curves: dict[str, dict[str, list]], metric: str, matrix_id: str, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, strategy in enumerate(_ordered(curves.keys(), STRATEGIES)):
        c = curves[strategy]
        ax.plot(c["k"], c["recall"], marker=MARKERS[i % len(MARKERS)],
                markersize=3, label=strategy)

    ax.set_xlabel("Top-k", fontsize=16)
    ax.set_ylabel("Recall", fontsize=16)
    ax.set_xscale("function", functions=(_fwd, _inv))
    ax.set_xlim(1, 500)
    ax.xaxis.set_major_locator(FixedLocator(XTICKS))
    ax.set_ylim(0.6, 0.9)
    ax.grid(True, alpha=0.3)
    ax.axvline(KNEE, color="gray", lw=0.8, ls="--", alpha=0.5)
    ax.legend(title="strategy", loc="upper right", fontsize=12)


    fig.text(0.01, 0.01, f"matrix_id={matrix_id}", fontsize=0, color="gray")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot voyage-key strategy curves vs k")
    p.add_argument("--matrix-id", default=None, help="Matrix run (default: latest)")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "strategies.png",
                   help="Output PNG (default: ./strategies.png)")
    args = p.parse_args()

    matrix_id = args.matrix_id or latest_matrix_id()
    if not matrix_id:
        raise SystemExit("No matrix run found. Run run_matrix.py first.")

    curves = load_total(matrix_id)
    if not curves:
        raise SystemExit(f"No 'total' rows for matrix_id={matrix_id}.")

    metric = metric_label(matrix_id)
    for strategy, c in curves.items():
        print(f"{strategy}: {len(c['k'])} k points (k {c['k'][0]}..{c['k'][-1]})")
    plot(curves, metric, matrix_id, args.out)


if __name__ == "__main__":
    main()
