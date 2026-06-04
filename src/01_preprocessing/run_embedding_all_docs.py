from __future__ import annotations

# Sequential runner for the four *document* embedding strategies.
# Launches each run_embedding_* script as its own subprocess, in order, and
# only starts the next once the previous one exits. Each child script keeps its
# own model-load + retry logic, so this just chains them.
#
# Note: attachment_summary is NOT included — summaries are whole-text
# (chunker='naive') and have no --target-chars knob.
#
# Run:
#   python src/01_preprocessing/run_embedding_all_docs.py --target-chars 3000
#   python src/01_preprocessing/run_embedding_all_docs.py --target-chars 1500 --limit 5 --verbose
#   python src/01_preprocessing/run_embedding_all_docs.py --continue-on-error

import argparse
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# (label, script filename, supports --voyage)
SCRIPTS: list[tuple[str, str, bool]] = [
    ("attachment_context", "run_embedding_attachment_context.py", True),
    ("attachment_late",    "run_embedding_attachment_late.py",    True),
    ("attachment_plain",   "run_embedding_attachment_plain.py",   True),
    ("email_plain",        "run_embedding_email_plain.py",        False),
]


def _build_cmd(script: str, supports_voyage: bool, args: argparse.Namespace) -> list[str]:
    cmd = [sys.executable, str(_HERE / script), "--target-chars", str(args.target_chars)]
    if args.limit is not None:
        cmd += ["--limit", str(args.limit)]
    if args.device is not None:
        cmd += ["--device", args.device]
    if args.verbose:
        cmd += ["--verbose"]
    if args.voyage is not None and supports_voyage:
        cmd += ["--voyage", args.voyage]
    return cmd


def main() -> None:
    p = argparse.ArgumentParser(
        description="Run the four document embedding strategies sequentially "
                    "(context -> late -> plain -> email_plain)."
    )
    p.add_argument("--target-chars", type=int, default=1500, metavar="N",
                   help="Chunk window size forwarded to every script; stored as the "
                        "'chunker' label (default: 1500)")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Forwarded to each script (process only the first N items)")
    p.add_argument("--voyage", default=None, metavar="KEY",
                   help="Forwarded to the attachment scripts only (email_plain has no --voyage)")
    p.add_argument("--device", default=None,
                   help="Torch device forwarded to each script")
    p.add_argument("--verbose", action="store_true",
                   help="Forwarded to each script")
    p.add_argument("--continue-on-error", action="store_true", dest="continue_on_error",
                   help="Keep going to the next script even if one fails "
                        "(default: stop on first failure)")
    args = p.parse_args()

    print(f"Running {len(SCRIPTS)} document embedders | target_chars={args.target_chars} "
          f"(chunker='{args.target_chars}')")

    results: list[tuple[str, int, float]] = []
    t_all = time.monotonic()

    for i, (label, script, supports_voyage) in enumerate(SCRIPTS, 1):
        cmd = _build_cmd(script, supports_voyage, args)
        print("\n" + "=" * 70)
        print(f"[{i}/{len(SCRIPTS)}] {label}")
        print("  " + " ".join(cmd))
        print("=" * 70, flush=True)

        t0 = time.monotonic()
        rc = subprocess.run(cmd).returncode
        dt = time.monotonic() - t0
        results.append((label, rc, dt))

        if rc != 0:
            print(f"\n[{label}] FAILED (exit {rc}) after {dt:.1f}s", flush=True)
            if not args.continue_on_error:
                print("Stopping — pass --continue-on-error to keep going.")
                break
        else:
            print(f"\n[{label}] done in {dt:.1f}s", flush=True)

    print("\n" + "=" * 70)
    print(f"Summary (total {time.monotonic() - t_all:.1f}s):")
    for label, rc, dt in results:
        status = "ok" if rc == 0 else f"FAILED (exit {rc})"
        print(f"  {label:<20} {status:<18} {dt:6.1f}s")

    if any(rc != 0 for _, rc, _ in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
