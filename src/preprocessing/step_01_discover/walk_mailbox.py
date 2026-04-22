from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .derive_voyage_key import derive_voyage_key


@dataclass(frozen=True)
class MailboxItem:
    voyage_folder: Path
    voyage_key: str
    direction: str
    eml_path: Path
    json_path: Path


def walk_mailbox(data_root: Path) -> Iterator[MailboxItem]:
    for voyage_folder in sorted(p for p in data_root.iterdir() if p.is_dir()):
        voyage_key = derive_voyage_key(voyage_folder.name)
        for direction_folder_name, direction in (("IN", "in"), ("OUT", "out")):
            direction_folder = voyage_folder / direction_folder_name
            if not direction_folder.is_dir():
                continue
            for eml_path in sorted(direction_folder.rglob("*.eml")):
                json_path = eml_path.with_suffix(".json")
                yield MailboxItem(
                    voyage_folder=voyage_folder,
                    voyage_key=voyage_key,
                    direction=direction,
                    eml_path=eml_path,
                    json_path=json_path,
                )


if __name__ == "__main__":
    import os
    import sys
    from ..shared.config import load_config

    cfg = load_config()
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else cfg.data_root
    for item in walk_mailbox(root):
        print(item.voyage_key, item.direction, item.eml_path)
