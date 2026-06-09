#!/usr/bin/env python3
"""Generate an article and save it as a Substack draft.

Example:
  python automate.py --topic "How to outline with Claude" --brief "Focus on writers new to AI"
  python automate.py --queue topics_queue.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from app import run_generation_job
from topic_queue import load_queue

ROOT = Path(__file__).parent
DEFAULT_QUEUE = ROOT / "topics_queue.example.json"


def run_job(job: dict) -> dict:
    return run_generation_job(job, push_substack=True)


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate and push a Substack draft.")
    parser.add_argument("--topic", help="Article topic or working title")
    parser.add_argument("--brief", default="", help="Editorial direction")
    parser.add_argument("--keyword", default="", help="Optional SEO phrase")
    parser.add_argument("--subtitle", default="", help="Optional Substack subtitle")
    parser.add_argument("--word-count", type=int, default=1200)
    parser.add_argument("--image-count", type=int, default=2)
    parser.add_argument(
        "--queue",
        help="Path to a JSON file with one job object or a list of jobs",
    )
    args = parser.parse_args()

    if args.queue:
        queue_path = Path(args.queue)
        if queue_path.name == "topics_queue.json" and queue_path.resolve() == (ROOT / "topics_queue.json").resolve():
            jobs = [item for item in load_queue() if item.get("status") == "pending"]
        else:
            queue_data = json.loads(queue_path.read_text(encoding="utf-8"))
            jobs = queue_data if isinstance(queue_data, list) else [queue_data]
    elif args.topic:
        jobs = [
            {
                "topic": args.topic,
                "brief": args.brief,
                "keyword": args.keyword,
                "subtitle": args.subtitle or None,
                "word_count": args.word_count,
                "image_count": args.image_count,
                "format": "newsletter",
            }
        ]
    else:
        parser.error("Provide --topic or --queue.")
        return 2

    results = []
    for job in jobs:
        if not (job.get("topic") or "").strip():
            print("Skipping job with no topic.", file=sys.stderr)
            continue
        print(f"Generating: {job['topic']}")
        result = run_job(job)
        draft = result["substack"]
        print(f"Substack draft created: id={draft['draft_id']}")
        if draft.get("edit_url"):
            print(f"Edit: {draft['edit_url']}")
        results.append(result)

    if not results:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
