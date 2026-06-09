from __future__ import annotations

import base64
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import markdown
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

from exporters import markdown_to_gutenberg, markdown_to_substack
from substack_publish import create_substack_draft
from topic_queue import (
    add_item,
    delete_item,
    find_next_pending,
    get_item,
    load_queue,
    replace_queue,
    update_item,
)
from voice_library import build_voice_context, library_stats

load_dotenv()

ROOT = Path(__file__).parent
PROFILE_FILE = ROOT / "author_profile.json"
GENERATED_DIR = ROOT / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2")
TEXT_MODEL = os.getenv("TEXT_MODEL", "deepseek-v4-pro")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

app = Flask(__name__)
_openai_client: OpenAI | None = None
_text_client: OpenAI | None = None


def text_client() -> OpenAI:
    global _text_client
    if _text_client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured.")
        _text_client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    return _text_client


def openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Set it or choose 0 images."
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def load_profile() -> dict:
    if not PROFILE_FILE.exists():
        return {}
    return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def build_prompt(data: dict) -> tuple[str, str]:
    profile = load_profile()
    author_name = profile.get("author_name") or "the author"
    publication = profile.get("publication_name") or "the publication"
    voice_notes = profile.get("voice_notes") or "Clear, specific, useful, and human."
    audience = profile.get("audience") or "the publication's readers"
    positioning = profile.get("positioning") or ""
    sample_context = build_voice_context()

    system = f"""You are the editorial writing partner for {publication}.
Write in the voice of {author_name}, using the supplied profile and writing samples.
Do not invent personal stories, credentials, quotes, or experiences. If the library
does not support a first-person claim, write without it.

AUTHOR PROFILE
Audience: {audience}
Positioning: {positioning}
Voice notes: {voice_notes}

WRITING SAMPLES
{sample_context or "(No writing samples have been added yet. Follow the voice notes only.)"}

Return only the finished article in Markdown. Begin with one H1 title. Use H2 and H3
headings, short readable paragraphs, and useful lists where appropriate."""

    topic = (data.get("topic") or "").strip()
    brief = (data.get("brief") or "").strip()
    keyword = (data.get("keyword") or "").strip()
    format_name = (data.get("format") or "blog").strip()
    word_count = max(300, min(5000, int(data.get("word_count") or 1200)))
    image_count = max(0, min(6, int(data.get("image_count") or 0)))

    user = f"""Write an article about: {topic}

Editorial brief:
{brief or "Create the strongest useful article for the stated audience."}

Target length: approximately {word_count} words."""
    if format_name == "newsletter":
        user += (
            "\nFormat: Substack newsletter. Use a strong conversational opening, "
            "a clear central lesson, useful examples, and a concise closing invitation."
        )
    else:
        user += (
            "\nFormat: Search-friendly website article. Answer the core question early, "
            "use descriptive headings, and organize the piece for easy scanning."
        )
    if keyword:
        user += f'\nPrimary SEO phrase: "{keyword}". Use it naturally, without stuffing.'
    if image_count:
        markers = ", ".join(f"[IMAGE_{index}]" for index in range(1, image_count + 1))
        user += (
            f"\nPlace exactly {image_count} image markers in the article: {markers}. "
            "Put each marker on its own line after a complete paragraph, spread them "
            "evenly across the body, and never place one directly after a heading."
        )
    return system, user


def generate_article(data: dict) -> str:
    system, user = build_prompt(data)
    thinking = os.getenv("DEEPSEEK_THINKING", "disabled").strip().lower()
    request_kwargs: dict = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 8000,
    }
    if thinking in {"1", "true", "yes", "enabled"}:
        request_kwargs["reasoning_effort"] = os.getenv("DEEPSEEK_REASONING_EFFORT", "high")
        request_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    else:
        request_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    response = text_client().chat.completions.create(**request_kwargs)
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("DeepSeek returned an empty article.")
    return content.strip()


def _image_context(article_md: str, marker: str) -> str:
    before, _, after = article_md.partition(marker)
    nearby = (before[-900:] + " " + after[:450]).replace("\n", " ")
    return re.sub(r"\s+", " ", nearby).strip()


def ensure_image_markers(article_md: str, image_count: int) -> str:
    """Add any missing image markers after evenly spaced body paragraphs."""
    missing = [
        f"[IMAGE_{index}]"
        for index in range(1, image_count + 1)
        if f"[IMAGE_{index}]" not in article_md
    ]
    if not missing:
        return article_md

    parts = article_md.split("\n\n")
    candidates = [
        index
        for index, part in enumerate(parts)
        if part.strip()
        and not part.lstrip().startswith(("#", "-", "*", ">", "[IMAGE_"))
    ]
    if not candidates:
        return article_md + "\n\n" + "\n\n".join(missing)

    for offset, marker in enumerate(missing, start=1):
        candidate_position = round(offset * (len(candidates) - 1) / (len(missing) + 1))
        part_index = candidates[candidate_position]
        parts[part_index] = parts[part_index].rstrip() + f"\n\n{marker}"
    return "\n\n".join(parts)


def _render_image(prompt: str, index: int) -> dict:
    visual_prompt = (
        "Create a polished editorial illustration for an educational article about "
        "AI and writing. Use the Writing With AI visual language: clean white or soft "
        "gray background, deep teal (#1f3d4d), mint green (#66ccaa), warm yellow "
        "(#ffe666), and restrained dark green (#208664) accents. Modern flat "
        "illustration with subtle depth, "
        "clear focal point, generous negative space, no words, no letters, no logos, "
        f"no watermark. Article context: {prompt}"
    )
    response = openai_client().images.generate(
        model=IMAGE_MODEL,
        prompt=visual_prompt,
        size="1536x1024",
        quality="high",
        n=1,
    )
    image = response.data[0]
    if getattr(image, "b64_json", None):
        image_bytes = base64.b64decode(image.b64_json)
    elif getattr(image, "url", None):
        with urlopen(image.url, timeout=90) as remote:
            image_bytes = remote.read()
    else:
        raise RuntimeError("The image model returned no image data.")

    filename = f"writing-with-ai-{index}-{uuid.uuid4().hex[:8]}.png"
    (GENERATED_DIR / filename).write_bytes(image_bytes)
    return {
        "filename": filename,
        "url": f"/static/generated/{filename}",
        "alt": f"Editorial illustration for article section {index}",
    }


def generate_article_images(article_md: str, image_count: int) -> tuple[str, list[dict]]:
    image_count = max(0, min(6, image_count))
    if not image_count:
        return article_md, []
    article_md = ensure_image_markers(article_md, image_count)

    tasks = []
    for index in range(1, image_count + 1):
        marker = f"[IMAGE_{index}]"
        tasks.append((index, marker, _image_context(article_md, marker)))

    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=min(3, image_count)) as executor:
        futures = {
            executor.submit(_render_image, context, index): (index, marker)
            for index, marker, context in tasks
        }
        for future in as_completed(futures):
            index, _ = futures[future]
            results[index] = future.result()

    for index, marker, _ in tasks:
        image = results[index]
        article_md = article_md.replace(
            marker, f'![{image["alt"]}]({image["url"]})', 1
        )
    article_md = re.sub(r"\[IMAGE_\d+\]", "", article_md)
    return article_md, [results[index] for index in sorted(results)]


def run_generation_job(data: dict, *, push_substack: bool = False) -> dict:
    article_md = generate_article(data)
    article_md, images = generate_article_images(
        article_md, int(data.get("image_count") or 0)
    )
    payload = export_payload(article_md, images)
    if push_substack:
        draft = create_substack_draft(
            article_md,
            subtitle=(data.get("subtitle") or "").strip() or None,
            audience=(data.get("audience") or "everyone").strip(),
        )
        payload["substack"] = draft
    return payload


def export_payload(article_md: str, images: list[dict] | None = None) -> dict:
    article_md = article_md.strip()
    return {
        "article_md": article_md,
        "preview_html": markdown.markdown(
            article_md, extensions=["extra", "sane_lists"]
        ),
        "gutenberg": markdown_to_gutenberg(article_md),
        "substack": markdown_to_substack(article_md),
        "word_count": len(re.findall(r"\b[\w'-]+\b", article_md)),
        "images": images or [],
    }


@app.get("/")
def index():
    return render_template("index.html", profile=load_profile(), stats=library_stats())


@app.post("/api/generate")
def api_generate():
    data = request.get_json(silent=True) or {}
    if not (data.get("topic") or "").strip():
        return jsonify({"error": "Add a topic or working title first."}), 400
    try:
        return jsonify(run_generation_job(data))
    except Exception as exc:
        app.logger.exception("Article generation failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/generate-and-push")
def api_generate_and_push():
    data = request.get_json(silent=True) or {}
    if not (data.get("topic") or "").strip():
        return jsonify({"error": "Add a topic or working title first."}), 400
    try:
        return jsonify(run_generation_job(data, push_substack=True))
    except Exception as exc:
        app.logger.exception("Generate and push failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/queue")
def api_queue_list():
    return jsonify({"items": load_queue()})


@app.post("/api/queue")
def api_queue_add():
    data = request.get_json(silent=True) or {}
    try:
        item = add_item(data)
        return jsonify(item), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.put("/api/queue")
def api_queue_replace():
    data = request.get_json(silent=True) or {}
    items = data.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "Expected an items array."}), 400
    try:
        return jsonify({"items": replace_queue(items)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.delete("/api/queue/<item_id>")
def api_queue_delete(item_id: str):
    try:
        delete_item(item_id)
        return jsonify({"ok": True})
    except KeyError:
        return jsonify({"error": "Queue item not found."}), 404


def _run_queue_item(item: dict) -> dict:
    update_item(item["id"], {"status": "running", "error": None})
    try:
        result = run_generation_job(item, push_substack=True)
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
        result["queue_item_id"] = item["id"]
        return result
    except Exception as exc:
        update_item(item["id"], {"status": "failed", "error": str(exc)})
        raise


@app.post("/api/queue/run-next")
def api_queue_run_next():
    item = find_next_pending()
    if not item:
        return jsonify({"error": "No pending topics in the queue."}), 400
    try:
        return jsonify(_run_queue_item(item))
    except Exception as exc:
        app.logger.exception("Queue run failed")
        return jsonify({"error": str(exc), "queue_item_id": item["id"]}), 500


@app.post("/api/queue/<item_id>/run")
def api_queue_run_item(item_id: str):
    item = get_item(item_id)
    if not item:
        return jsonify({"error": "Queue item not found."}), 404
    if item.get("status") == "running":
        return jsonify({"error": "That topic is already running."}), 409
    try:
        return jsonify(_run_queue_item(item))
    except Exception as exc:
        app.logger.exception("Queue item run failed")
        return jsonify({"error": str(exc), "queue_item_id": item_id}), 500


@app.post("/api/export")
def api_export():
    data = request.get_json(silent=True) or {}
    article_md = data.get("article_md") or ""
    if not article_md.strip():
        return jsonify({"error": "There is no draft to export."}), 400
    return jsonify(export_payload(article_md))


@app.get("/api/agent/status")
def api_agent_status():
    from agent import agent_status

    return jsonify(agent_status())


@app.get("/api/agent/config")
def api_agent_config():
    from agent_config import load_config

    return jsonify(load_config())


@app.put("/api/agent/config")
def api_agent_config_save():
    from agent_config import apply_config_updates, load_config, save_config

    data = request.get_json(silent=True) or {}
    try:
        current = load_config()
        updated = apply_config_updates(current, data)
        save_config(updated)
        return jsonify(updated)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Agent config save failed")
        return jsonify({"error": str(exc)}), 400


@app.post("/api/agent/run")
def api_agent_run():
    from agent import agent_status, cmd_run

    force = (request.get_json(silent=True) or {}).get("force", True)
    try:
        exit_code = cmd_run(force=bool(force))
        return jsonify({"ok": exit_code == 0, "status": agent_status()})
    except Exception as exc:
        app.logger.exception("Agent run failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/substack/draft")
def api_substack_draft():
    data = request.get_json(silent=True) or {}
    article_md = data.get("article_md") or ""
    if not article_md.strip():
        return jsonify({"error": "There is no draft to send to Substack."}), 400
    try:
        draft = create_substack_draft(
            article_md,
            subtitle=(data.get("subtitle") or "").strip() or None,
            audience=(data.get("audience") or "everyone").strip(),
        )
        return jsonify(draft)
    except Exception as exc:
        app.logger.exception("Substack draft creation failed")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
        port=int(os.getenv("PORT", "5000")),
    )
