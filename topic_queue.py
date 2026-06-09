from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
QUEUE_FILE = ROOT / "topics_queue.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save_queue(items: list[dict]) -> None:
    QUEUE_FILE.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


AGENT_FIELDS = ("source", "pool_id", "trend_score", "trend_reason", "research_area")


def normalize_job(data: dict, *, item_id: str | None = None) -> dict:
    item = {
        "id": item_id or data.get("id") or uuid.uuid4().hex[:12],
        "topic": (data.get("topic") or "").strip(),
        "brief": (data.get("brief") or "").strip(),
        "keyword": (data.get("keyword") or "").strip(),
        "subtitle": (data.get("subtitle") or "").strip(),
        "format": (data.get("format") or "newsletter").strip(),
        "word_count": max(300, min(5000, int(data.get("word_count") or 1200))),
        "image_count": max(0, min(6, int(data.get("image_count") or 2))),
        "audience": (data.get("audience") or "everyone").strip(),
        "status": (data.get("status") or "pending").strip(),
        "created_at": data.get("created_at") or _now(),
        "last_run_at": data.get("last_run_at"),
        "substack_draft_id": data.get("substack_draft_id"),
        "substack_edit_url": data.get("substack_edit_url"),
        "error": data.get("error"),
    }
    for key in AGENT_FIELDS:
        if data.get(key) is not None:
            item[key] = data[key]
    return item


def add_item(data: dict) -> dict:
    item = normalize_job(data)
    if not item["topic"]:
        raise ValueError("Topic is required.")
    items = load_queue()
    items.append(item)
    save_queue(items)
    return item


def replace_queue(items: list[dict]) -> list[dict]:
    normalized = [normalize_job(item, item_id=item.get("id")) for item in items]
    for item in normalized:
        if not item["topic"]:
            raise ValueError("Every queued topic needs a title.")
    save_queue(normalized)
    return normalized


def get_item(item_id: str) -> dict | None:
    return next((item for item in load_queue() if item["id"] == item_id), None)


def update_item(item_id: str, updates: dict) -> dict:
    items = load_queue()
    for index, item in enumerate(items):
        if item["id"] == item_id:
            merged = normalize_job({**item, **updates}, item_id=item_id)
            items[index] = merged
            save_queue(items)
            return merged
    raise KeyError(item_id)


def delete_item(item_id: str) -> None:
    items = load_queue()
    filtered = [item for item in items if item["id"] != item_id]
    if len(filtered) == len(items):
        raise KeyError(item_id)
    save_queue(filtered)


def find_next_pending() -> dict | None:
    return next((item for item in load_queue() if item.get("status") == "pending"), None)
