from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
POOL_FILE = ROOT / "topic_pool.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_pool() -> list[dict]:
    if not POOL_FILE.exists():
        return []
    data = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save_pool(items: list[dict]) -> None:
    POOL_FILE.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def normalize_pool_item(data: dict, *, item_id: str | None = None) -> dict:
    return {
        "id": item_id or data.get("id") or uuid.uuid4().hex[:12],
        "topic": (data.get("topic") or "").strip(),
        "brief": (data.get("brief") or "").strip(),
        "keyword": (data.get("keyword") or "").strip(),
        "subtitle": (data.get("subtitle") or "").strip(),
        "research_area": (data.get("research_area") or "").strip(),
        "trend_score": max(1, min(10, int(data.get("trend_score") or 5))),
        "trend_reason": (data.get("trend_reason") or "").strip(),
        "research_snippet": (data.get("research_snippet") or "").strip(),
        "status": (data.get("status") or "available").strip(),
        "discovered_at": data.get("discovered_at") or _now(),
        "queued_at": data.get("queued_at"),
        "drafted_at": data.get("drafted_at"),
    }


def add_pool_items(items: list[dict]) -> list[dict]:
    pool = load_pool()
    existing_topics = {item["topic"].lower() for item in pool}
    added: list[dict] = []
    for raw in items:
        item = normalize_pool_item(raw)
        if not item["topic"]:
            continue
        if item["topic"].lower() in existing_topics:
            continue
        pool.append(item)
        existing_topics.add(item["topic"].lower())
        added.append(item)
    save_pool(pool)
    return added


def update_pool_item(item_id: str, updates: dict) -> dict:
    pool = load_pool()
    for index, item in enumerate(pool):
        if item["id"] == item_id:
            merged = normalize_pool_item({**item, **updates}, item_id=item_id)
            pool[index] = merged
            save_pool(pool)
            return merged
    raise KeyError(item_id)


def available_items(*, min_score: int = 1, max_age_days: int = 14) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    results = []
    for item in load_pool():
        if item.get("status") != "available":
            continue
        if int(item.get("trend_score", 0)) < min_score:
            continue
        discovered = datetime.fromisoformat(item["discovered_at"].replace("Z", "+00:00"))
        if discovered < cutoff:
            continue
        results.append(item)
    return sorted(results, key=lambda item: int(item.get("trend_score", 0)), reverse=True)


def recent_topic_titles(days: int = 30) -> set[str]:
    from topic_queue import load_queue

    cutoff = date.today() - timedelta(days=days)
    titles: set[str] = set()
    for item in load_queue():
        titles.add(item["topic"].lower())
        last_run = item.get("last_run_at")
        if not last_run:
            continue
        run_date = datetime.fromisoformat(last_run.replace("Z", "+00:00")).date()
        if run_date >= cutoff:
            titles.add(item["topic"].lower())
    return titles
