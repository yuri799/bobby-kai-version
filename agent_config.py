from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "agent_config.json"
EXAMPLE_FILE = ROOT / "agent_config.example.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "research_areas": [
        "AI writing assistants and workflows for creators",
        "Newsletter and Substack growth tactics for writers",
        "Practical comparisons of leading AI writing tools",
    ],
    "schedule": {
        "timezone": "America/New_York",
        "research_time": "06:00",
        "draft_time": "07:00",
        "articles_per_day": 1,
    },
    "research": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "topics_per_area": 3,
        "lookback_days": 7,
    },
    "selection": {
        "auto_pick": True,
        "min_trend_score": 6,
        "max_pool_age_days": 14,
    },
    "article_defaults": {
        "format": "newsletter",
        "word_count": 1200,
        "image_count": 2,
        "auto_substack_draft": False,
        "audience": "everyone",
    },
    "runtime": {
        "last_research_at": None,
        "last_research_date": None,
        "last_draft_at": None,
        "last_draft_date": None,
        "drafts_created_today": 0,
    },
}


def _merge(default: dict, data: dict) -> dict:
    merged = deepcopy(default)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return _merge(DEFAULT_CONFIG, data)
    if EXAMPLE_FILE.exists():
        data = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))
        return _merge(DEFAULT_CONFIG, data)
    return deepcopy(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def apply_config_updates(current: dict, updates: dict) -> dict:
    """Merge user-editable fields from the UI/API into the saved config."""
    merged = deepcopy(current)

    if "enabled" in updates:
        merged["enabled"] = bool(updates["enabled"])

    if "research_areas" in updates:
        areas = updates["research_areas"]
        if isinstance(areas, str):
            areas = [line.strip() for line in areas.splitlines() if line.strip()]
        if not isinstance(areas, list):
            raise ValueError("research_areas must be a list of strings.")
        cleaned = [str(area).strip() for area in areas if str(area).strip()]
        if not cleaned:
            raise ValueError("Add at least one research area.")
        merged["research_areas"] = cleaned

    if "schedule" in updates:
        schedule = _merge(merged["schedule"], updates["schedule"])
        ZoneInfo(schedule["timezone"])
        _parse_hhmm(schedule["research_time"])
        _parse_hhmm(schedule["draft_time"])
        schedule["articles_per_day"] = max(
            1, min(10, int(schedule.get("articles_per_day", 1)))
        )
        merged["schedule"] = schedule

    if "research" in updates:
        research = _merge(merged["research"], updates["research"])
        research["topics_per_area"] = max(
            1, min(10, int(research.get("topics_per_area", 3)))
        )
        research["lookback_days"] = max(
            1, min(30, int(research.get("lookback_days", 7)))
        )
        research["provider"] = "deepseek"
        research["model"] = str(research.get("model", "deepseek-chat")).strip() or "deepseek-chat"
        merged["research"] = research

    if "selection" in updates:
        selection = _merge(merged["selection"], updates["selection"])
        selection["auto_pick"] = bool(selection.get("auto_pick", True))
        selection["min_trend_score"] = max(
            1, min(10, int(selection.get("min_trend_score", 6)))
        )
        selection["max_pool_age_days"] = max(
            1, min(60, int(selection.get("max_pool_age_days", 14)))
        )
        merged["selection"] = selection

    if "article_defaults" in updates:
        defaults = _merge(merged["article_defaults"], updates["article_defaults"])
        if defaults.get("format") not in {"newsletter", "blog"}:
            defaults["format"] = "newsletter"
        defaults["word_count"] = max(300, min(5000, int(defaults.get("word_count", 1200))))
        defaults["image_count"] = max(0, min(6, int(defaults.get("image_count", 2))))
        defaults["auto_substack_draft"] = bool(defaults.get("auto_substack_draft", False))
        defaults["audience"] = str(defaults.get("audience", "everyone")).strip() or "everyone"
        merged["article_defaults"] = defaults

    return merged


def now_in_tz(config: dict) -> datetime:
    tz = ZoneInfo(config["schedule"]["timezone"])
    return datetime.now(tz)


def today_in_tz(config: dict) -> date:
    return now_in_tz(config).date()


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def is_past_scheduled_time(config: dict, field: str) -> bool:
    now = now_in_tz(config)
    hour, minute = _parse_hhmm(config["schedule"][field])
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now >= scheduled


def reset_daily_counters_if_needed(config: dict) -> dict:
    today = today_in_tz(config).isoformat()
    runtime = config.setdefault("runtime", {})
    if runtime.get("last_draft_date") != today:
        runtime["drafts_created_today"] = 0
    return config


def drafts_remaining_today(config: dict) -> int:
    config = reset_daily_counters_if_needed(config)
    limit = int(config["schedule"]["articles_per_day"])
    used = int(config["runtime"].get("drafts_created_today", 0))
    return max(0, limit - used)


def research_due(config: dict, *, force: bool = False) -> bool:
    if force:
        return True
    if not config.get("enabled"):
        return False
    if not is_past_scheduled_time(config, "research_time"):
        return False
    today = today_in_tz(config).isoformat()
    return config["runtime"].get("last_research_date") != today


def draft_due(config: dict, *, force: bool = False) -> bool:
    if force:
        return True
    if not config.get("enabled"):
        return False
    if drafts_remaining_today(config) <= 0:
        return False
    if not is_past_scheduled_time(config, "draft_time"):
        return False
    return True


def mark_research_run(config: dict) -> dict:
    now = now_in_tz(config)
    config["runtime"]["last_research_at"] = now.isoformat()
    config["runtime"]["last_research_date"] = now.date().isoformat()
    return config


def mark_draft_run(config: dict) -> dict:
    config = reset_daily_counters_if_needed(config)
    now = now_in_tz(config)
    config["runtime"]["last_draft_at"] = now.isoformat()
    config["runtime"]["last_draft_date"] = now.date().isoformat()
    config["runtime"]["drafts_created_today"] = int(
        config["runtime"].get("drafts_created_today", 0)
    ) + 1
    return config
