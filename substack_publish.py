from __future__ import annotations

import os
import re
from pathlib import Path

from substack import Api
from substack.post import Post

ROOT = Path(__file__).parent
GENERATED_DIR = ROOT / "static" / "generated"


def _substack_api() -> Api:
    """Authenticate using python-substack's supported methods.

    Env vars (library docs): EMAIL, PASSWORD, PUBLICATION_URL, COOKIES_PATH,
    COOKIES_STRING. Bobby also accepts SUBSTACK_COOKIE and
    SUBSTACK_PUBLICATION_URL as aliases.
    """
    publication_url = (
        os.getenv("PUBLICATION_URL")
        or os.getenv("SUBSTACK_PUBLICATION_URL")
        or "https://writingwithai.substack.com"
    ).strip()

    email = (os.getenv("EMAIL") or "").strip()
    password = (os.getenv("PASSWORD") or "").strip()
    cookies_string = (
        os.getenv("COOKIES_STRING") or os.getenv("SUBSTACK_COOKIE") or ""
    ).strip()
    cookies_path = (os.getenv("COOKIES_PATH") or "").strip()

    if email and password:
        return Api(email=email, password=password, publication_url=publication_url)
    if cookies_string:
        return Api(cookies_string=cookies_string, publication_url=publication_url)
    if cookies_path:
        return Api(cookies_path=cookies_path, publication_url=publication_url)

    raise RuntimeError(
        "Substack auth is not configured. Set EMAIL and PASSWORD in .env "
        "(see python-substack docs), or use COOKIES_STRING / COOKIES_PATH."
    )


def split_title_and_body(article_md: str) -> tuple[str, str, str | None]:
    """Return title, body markdown, and optional subtitle from the first H1."""
    lines = article_md.strip().splitlines()
    title = "Untitled draft"
    subtitle: str | None = None
    body_start = 0

    for index, line in enumerate(lines):
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            title = match.group(1).strip()
            body_start = index + 1
            break

    body_lines = lines[body_start:]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    if body_lines and body_lines[0].strip().startswith(">"):
        subtitle = re.sub(r"^>\s*", "", body_lines[0].strip())
        body_lines = body_lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)

    return title, "\n".join(body_lines).strip(), subtitle


def rewrite_image_paths(article_md: str, generated_dir: Path = GENERATED_DIR) -> str:
    """Convert app image URLs to local paths so Substack can upload them."""

    def replace(match: re.Match[str]) -> str:
        alt = match.group(1)
        src = match.group(2)
        if src.startswith("/static/generated/"):
            local_path = generated_dir / Path(src).name
            if local_path.exists():
                return f"![{alt}]({local_path.as_posix()})"
        return match.group(0)

    return re.sub(r"!\[(.*?)\]\((.*?)\)", replace, article_md)


def create_substack_draft(
    article_md: str,
    *,
    subtitle: str | None = None,
    audience: str = "everyone",
) -> dict:
    article_md = rewrite_image_paths(article_md.strip())
    title, body_md, inferred_subtitle = split_title_and_body(article_md)
    final_subtitle = (subtitle or inferred_subtitle or "").strip()

    api = _substack_api()
    user_id = api.get_user_id()
    post = Post(title=title, subtitle=final_subtitle, user_id=user_id, audience=audience)
    post.from_markdown(body_md, api=api)
    draft = api.post_draft(post.get_draft())

    draft_id = draft.get("id")
    edit_url = None
    publication = (
        os.getenv("PUBLICATION_URL")
        or os.getenv("SUBSTACK_PUBLICATION_URL")
        or ""
    ).strip().rstrip("/")
    if publication and draft_id:
        edit_url = f"{publication}/publish/post/{draft_id}"

    return {
        "draft_id": draft_id,
        "title": title,
        "subtitle": final_subtitle,
        "edit_url": edit_url,
    }
