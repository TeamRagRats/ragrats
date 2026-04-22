from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_json(json_path: Path) -> dict[str, Any]:
    with json_path.open("rb") as f:
        return json.load(f)


if __name__ == "__main__":
    import sys

    data = parse_json(Path(sys.argv[1]))
    print(json.dumps(data, indent=2, default=str)[:2000])
