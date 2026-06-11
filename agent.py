#!/usr/bin/env python3
"""Editorial agent: research → topic pool → queue → Substack drafts.

Examples:
  python agent.py status
  python agent.py research
  python agent.py pick
  python agent.py draft
  python agent.py run              # daily cycle (respects schedule)
  python agent.py run --force      # run everything now
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from agent_config import (
    draft_due,
    drafts_remaining_today,
    load_config,
    mark_draft_run,
    mark_research_run,
    research_due,
    reset_daily_counters_if_needed,
    save_config,
)
from app import TEXT_MODEL, load_profile, run_generation_job, text_client
from research import extract_topics_from_research, research_area
from topic_pool import add_pool_items, available_items, recent_topic_titles, update_pool_item
from topic_queue import add_item, find_next_pending, load_queue, update_item

ROOT = Path(__file__).parent
LOG_FILE = ROOT / "agent_log.jsonl"


def log_event(event: str, **payload) -> None:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{event}] {payload.get('message', '')}".strip())


def agent_status() -> dict:
    config = reset_daily_counters_if_needed(load_config())
    pool = available_items(
        min_score=int(config["selection"]["min_trend_score"]),
        max_age_days=int(config["selection"]["max_pool_age_days"]),
    )
    queue = load_queue()
    pending = [item for item in queue if item.get("status") == "pending"]
    return {
        "enabled": config.get("enabled"),
        "drafts_remaining_today": drafts_remaining_today(config),
        "research_due": research_due(config),
        "draft_due": draft_due(config),
        "pool_available": len(pool),
        "queue_pending": len(pending),
        "research_areas": config.get("research_areas", []),
        "schedule": config["schedule"],
        "runtime": config["runtime"],
    }


def cmd_status() -> int:
    print(json.dumps(agent_status(), indent=2))
    return 0


def cmd_research(*, force: bool = False) -> int:
    config = load_config()
    if not research_due(config, force=force):
        log_event("research_skip", message="Research not due yet.")
        return 0

    profile = load_profile()
    research_cfg = config["research"]
    all_topics: list[dict] = []

    for area in config["research_areas"]:
        log_event("research_start", message=area)
        notes = research_area(
            area,
            model=research_cfg.get("model", "sonar-pro"),
            lookback_days=int(research_cfg.get("lookback_days", 7)),
            publication=profile.get("publication_name", "Writing With AI"),
            audience=profile.get("audience", "writers"),
        )
        topics = extract_topics_from_research(
            notes,
            area=area,
            topics_count=int(research_cfg.get("topics_per_area", 3)),
            text_client_factory=text_client,
            text_model=TEXT_MODEL,
            publication=profile.get("publication_name", "Writing With AI"),
            audience=profile.get("audience", "writers"),
            positioning=profile.get("positioning", ""),
        )
        all_topics.extend(topics)
        log_event("research_area_done", message=area, topics=len(topics))

    added = add_pool_items(all_topics)
    config = mark_research_run(config)
    save_config(config)
    log_event("research_done", message=f"Added {len(added)} topics to pool.")
    return 0


def cmd_pick(*, force: bool = False) -> int:
    config = reset_daily_counters_if_needed(load_config())
    remaining = drafts_remaining_today(config)
    if force and remaining <= 0:
        remaining = int(config["schedule"]["articles_per_day"])
    if remaining <= 0:
        log_event("pick_skip", message="Daily article limit reached.")
        return 0

    selection = config["selection"]
    candidates = available_items(
        min_score=int(selection["min_trend_score"]),
        max_age_days=int(selection["max_pool_age_days"]),
    )
    recent = recent_topic_titles(days=30)
    defaults = config["article_defaults"]
    picked = 0

    for item in candidates:
        if picked >= remaining:
            break
        if item["topic"].lower() in recent:
            continue

        job = {
            **defaults,
            "topic": item["topic"],
            "brief": item["brief"],
            "keyword": item.get("keyword", ""),
            "subtitle": item.get("subtitle", ""),
            "source": "agent",
            "pool_id": item["id"],
            "trend_score": item.get("trend_score"),
            "trend_reason": item.get("trend_reason"),
            "research_area": item.get("research_area"),
            "status": "pending",
        }
        add_item(job)
        update_pool_item(item["id"], {"status": "queued", "queued_at": datetime.now(timezone.utc).isoformat()})
        recent.add(item["topic"].lower())
        picked += 1
        log_event("pick", message=item["topic"], trend_score=item.get("trend_score"))

    if not picked:
        log_event("pick_none", message="No eligible topics in pool.")
    return 0


def cmd_draft(*, force: bool = False) -> int:
    config = reset_daily_counters_if_needed(load_config())
    push_substack = False
    drafted = 0

    max_drafts = int(config["schedule"]["articles_per_day"])
    while drafted < max_drafts and (force or drafts_remaining_today(config) > 0):
        if not force and not draft_due(config):
            break
        if not force and drafts_remaining_today(config) <= 0:
            break
        item = find_next_pending()
        if not item:
            log_event("draft_skip", message="No pending queue items.")
            break

        update_item(item["id"], {"status": "running", "error": None})
        log_event("draft_start", message=item["topic"], queue_id=item["id"])
        try:
            result = run_generation_job(item, push_substack=push_substack)
            draft = result.get("substack") or {}
            update_item(
                item["id"],
                {
                    "status": "done",
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                    "substack_draft_id": draft.get("draft_id"),
                    "substack_edit_url": draft.get("edit_url"),
                    "error": None,
                },
            )
            pool_id = item.get("pool_id")
            if pool_id:
                update_pool_item(
                    pool_id,
                    {
                        "status": "drafted",
                        "drafted_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            config = mark_draft_run(config)
            save_config(config)
            drafted += 1
            log_event(
                "draft_done",
                message=item["topic"],
                edit_url=draft.get("edit_url"),
            )
        except Exception as exc:
            update_item(item["id"], {"status": "failed", "error": str(exc)})
            log_event("draft_failed", message=str(exc), topic=item["topic"])
            return 1

    if drafted == 0:
        log_event("draft_none", message="Nothing drafted.")
    return 0


def cmd_run(*, force: bool = False) -> int:
    config = load_config()
    if not config.get("enabled") and not force:
        log_event("agent_disabled", message="Agent is disabled in agent_config.json")
        return 0

    if research_due(config, force=force):
        cmd_research(force=force)
    if draft_due(config, force=force) or force:
        if config["selection"].get("auto_pick", True):
            cmd_pick(force=force)
        cmd_draft(force=force)
    else:
        log_event("run_skip", message="Draft step not due yet.")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Writing With AI editorial agent")
    parser.add_argument(
        "command",
        choices=["status", "research", "pick", "draft", "run"],
        help="Agent command",
    )
    parser.add_argument("--force", action="store_true", help="Ignore schedule and limits where safe")
    args = parser.parse_args()

    handlers = {
        "status": cmd_status,
        "research": lambda: cmd_research(force=args.force),
        "pick": lambda: cmd_pick(force=args.force),
        "draft": lambda: cmd_draft(force=args.force),
        "run": lambda: cmd_run(force=args.force),
    }
    try:
        return handlers[args.command]()
    except Exception as exc:
        log_event("error", message=str(exc))
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
