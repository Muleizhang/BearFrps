from __future__ import annotations

import json
from pathlib import Path

from backend.config import ROOT_DIR

_PERSIST_FILE = ROOT_DIR / "config" / "allocatable_range.json"


def load_allocatable_range(default_start: int, default_end: int) -> tuple[int, int]:
    try:
        if _PERSIST_FILE.exists():
            data = json.loads(_PERSIST_FILE.read_text(encoding="utf-8"))
            start = int(data.get("start", default_start))
            end = int(data.get("end", default_end))
            if start > end or start < 1 or end > 65535:
                return default_start, default_end
            return start, end
    except Exception:
        pass
    return default_start, default_end


def save_allocatable_range(start: int, end: int) -> None:
    _PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PERSIST_FILE.write_text(
        json.dumps({"start": start, "end": end}), encoding="utf-8"
    )
