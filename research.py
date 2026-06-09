from __future__ import annotations

import json
import os
import re

from openai import OpenAI

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def deepseek_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured.")
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def research_area(
    area: str,
    *,
    model: str = "deepseek-chat",
    lookback_days: int = 7,
    publication: str = "Writing With AI",
    audience: str = "writers and creators",
) -> str:
    prompt = f"""Research what is timely and article-worthy in this area for {publication}.
Audience: {audience}.

Research area: {area}

Focus on the last {lookback_days} days. Cover:
- trending questions readers are asking
- recent tool updates, debates, or news worth explaining
- practical angles (not hype or prediction fluff)
- gaps where a helpful how-to or explainer would stand out

Be specific. Name real tools, trends, and reader problems where possible."""
    response = deepseek_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"DeepSeek returned empty research for: {area}")
    return content.strip()


def extract_topics_from_research(
    research_text: str,
    *,
    area: str,
    topics_count: int = 3,
    text_client_factory,
    text_model: str,
    publication: str,
    audience: str,
    positioning: str,
) -> list[dict]:
    system = f"""You turn research into newsletter topic ideas for {publication}.
Audience: {audience}
Positioning: {positioning}

Return ONLY valid JSON — an array of objects with keys:
topic, brief, keyword, subtitle, trend_score (1-10), trend_reason, research_snippet

Rules:
- Practical, specific topics — no generic "AI is changing writing" slop
- brief must include angle, 2-3 must-cover points, and what to avoid
- trend_score reflects timeliness + audience fit, not clickbait
- Do not invent author first-person stories"""
    user = f"""Research area: {area}

Research notes:
{research_text}

Propose exactly {topics_count} distinct article topics as JSON array."""

    response = text_client_factory().chat.completions.create(
        model=text_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=4000,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = response.choices[0].message.content or ""
    return _parse_topics_json(content, area=area)


def _parse_topics_json(content: str, *, area: str) -> list[dict]:
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fence:
        content = fence.group(1).strip()
    data = json.loads(content)
    if isinstance(data, dict) and "topics" in data:
        data = data["topics"]
    if not isinstance(data, list):
        raise RuntimeError("Topic extractor did not return a JSON array.")

    items = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        items.append(
            {
                "topic": entry.get("topic", ""),
                "brief": entry.get("brief", ""),
                "keyword": entry.get("keyword", ""),
                "subtitle": entry.get("subtitle", ""),
                "trend_score": entry.get("trend_score", 5),
                "trend_reason": entry.get("trend_reason", ""),
                "research_snippet": entry.get("research_snippet", ""),
                "research_area": area,
                "status": "available",
            }
        )
    return items
