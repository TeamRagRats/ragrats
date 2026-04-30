from __future__ import annotations

# Validates that each MailboxItem from walk_mailbox has both a .eml and a .json sidecar on disk.
# Returns (valid_items, orphan_errors). Used in run_ingest.py before the import loop.

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from step_01_discover.walk_mailbox import MailboxItem


@dataclass(frozen=True)
class PairError:
    voyage_key: str
    eml_path: Path
    missing: str


def validate_pairs(items: Iterable[MailboxItem]) -> tuple[list[MailboxItem], list[PairError]]:
    ok: list[MailboxItem] = []
    errors: list[PairError] = []
    for item in items:
        if not item.eml_path.is_file():
            errors.append(PairError(item.voyage_key, item.eml_path, "eml"))
            continue
        if not item.json_path.is_file():
            errors.append(PairError(item.voyage_key, item.eml_path, "json"))
            continue
        ok.append(item)
    return ok, errors


if __name__ == "__main__":
    from core.config import load_config
    from step_01_discover.walk_mailbox import walk_mailbox

    cfg = load_config()
    ok, errs = validate_pairs(walk_mailbox(cfg.data_root))
    print(f"paired={len(ok)} orphans={len(errs)}")
    for e in errs[:20]:
        print("orphan", e)
