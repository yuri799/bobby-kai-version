import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import agent_config


def test_drafts_remaining_resets_on_new_day():
    config = agent_config.DEFAULT_CONFIG.copy()
    config["runtime"] = {
        "last_draft_date": "2020-01-01",
        "drafts_created_today": 2,
    }
    config = agent_config.reset_daily_counters_if_needed(config)
    assert config["runtime"]["drafts_created_today"] == 0


def test_apply_config_updates_validates_research_areas():
    config = agent_config.DEFAULT_CONFIG.copy()
    with pytest.raises(ValueError):
        agent_config.apply_config_updates(config, {"research_areas": []})


def test_apply_config_updates_merges_schedule():
    config = agent_config.DEFAULT_CONFIG.copy()
    updated = agent_config.apply_config_updates(
        config,
        {"schedule": {"articles_per_day": 3, "timezone": "UTC"}},
    )
    assert updated["schedule"]["articles_per_day"] == 3
    assert updated["schedule"]["timezone"] == "UTC"


def test_research_due_after_scheduled_time(monkeypatch):
    config = agent_config.DEFAULT_CONFIG.copy()
    config["schedule"]["timezone"] = "UTC"
    config["schedule"]["research_time"] = "06:00"
    config["runtime"]["last_research_date"] = None

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 8, 7, 0, tzinfo=tz or ZoneInfo("UTC"))

    monkeypatch.setattr(agent_config, "datetime", FakeDateTime)
    assert agent_config.research_due(config) is True


def test_load_config_migrates_agent_research_to_perplexity(tmp_path, monkeypatch):
    config_file = tmp_path / "agent_config.json"
    config_file.write_text(
        json.dumps({"research": {"provider": "deepseek", "model": "deepseek-chat"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(agent_config, "CONFIG_FILE", config_file)

    config = agent_config.load_config()

    assert config["research"]["provider"] == "perplexity"
    assert config["research"]["model"] == "sonar-pro"
