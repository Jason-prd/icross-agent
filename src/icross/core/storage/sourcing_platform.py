"""Storage for browser extension captures and platform account info.

Each capture represents a product snapshot taken from a sourcing site
(1688 / Pinduoduo / Taobao) via the browser extension.

File: data/sourcing_captures.json
  captures: list[CaptureRecord]
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


def _get_data_path(filename: str) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR / filename


# ── In-memory JSON store (lightweight, no external deps) ─────────────

class _JsonStore:
    """Minimal JSON storage for sourcing captures."""

    _shared_cache: dict[str, list[dict[str, Any]]] = {}

    def __init__(self, filename: str):
        self._path = _get_data_path(filename)
        self._cache_key = str(self._path)

    def _read(self) -> list[dict[str, Any]]:
        cached = self._shared_cache.get(self._cache_key)
        if cached is not None:
            return cached
        if not self._path.exists():
            return []
        import json
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._shared_cache[self._cache_key] = data
                return data
        except (json.JSONDecodeError, IOError):
            return []

    def _write(self, data: list[dict[str, Any]]) -> None:
        self._shared_cache[self._cache_key] = data
        import json
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _find(self, key: str, value: Any) -> dict[str, Any] | None:
        for item in self._read():
            if item.get(key) == value:
                return item
        return None

    def _insert(self, record: dict[str, Any]) -> None:
        data = self._read()
        data.append(record)
        self._write(data)

    def _upsert(self, key: str, value: Any, updates: dict[str, Any]) -> dict[str, Any] | None:
        data = self._read()
        for i, item in enumerate(data):
            if item.get(key) == value:
                data[i].update(updates)
                self._write(data)
                return data[i]
        return None

    def _delete(self, key: str, value: Any) -> bool:
        data = self._read()
        for i, item in enumerate(data):
            if item.get(key) == value:
                data.pop(i)
                self._write(data)
                return True
        return False


# ── Constants ────────────────────────────────────────────────────────

CAPTURE_STATUSES = (
    "captured",      # Raw data received from extension
    "processing",    # Being processed by pipeline
    "parsed",        # SPU/SKU extracted
    "drafted",       # Draft created in iCross
    "error",         # Processing failed
)

PLATFORMS = ("1688", "pinduoduo", "taobao")


# ── Storage ──────────────────────────────────────────────────────────

class SourcingCaptureStorage:
    """Persistent storage for browser extension product captures.

    Each capture represents a product snapshot taken via the extension,
    tracking its journey from raw page scrape → parsing → draft.
    """

    def __init__(self):
        self._store = _JsonStore("sourcing_captures.json")

    # ── CRUD ──────────────────────────────────────────────────────

    def create_capture(
        self,
        platform: str,
        product_url: str,
        raw_data: dict[str, Any],
        shop_id: str = "",
    ) -> dict[str, Any]:
        """Create a new capture record from extension-submitted data."""
        record: dict[str, Any] = {
            "id": f"cap_{uuid.uuid4().hex[:12]}",
            "platform": platform,
            "product_url": product_url,
            "shop_id": shop_id,
            "raw_data": raw_data,
            "parsed_data": None,
            "session_id": None,
            "draft_id": None,
            "status": "captured",
            "error": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._store._insert(record)
        return record

    def get_capture(self, capture_id: str) -> dict[str, Any] | None:
        return self._store._find("id", capture_id)

    def update_capture(self, capture_id: str, **kwargs) -> dict[str, Any] | None:
        kwargs["updated_at"] = datetime.now().isoformat()
        return self._store._upsert("id", capture_id, kwargs)

    def delete_capture(self, capture_id: str) -> bool:
        return self._store._delete("id", capture_id)

    def list_captures(
        self,
        platform: str | None = None,
        status: str | None = None,
        shop_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        records = self._store._read()
        if platform:
            records = [r for r in records if r.get("platform") == platform]
        if status:
            records = [r for r in records if r.get("status") == status]
        if shop_id:
            records = [r for r in records if r.get("shop_id") == shop_id]
        return sorted(records, key=lambda r: r.get("created_at", ""), reverse=True)[:limit]

    def count_by_status(self) -> dict[str, int]:
        records = self._store._read()
        counts: dict[str, int] = {}
        for r in records:
            s = r.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts
