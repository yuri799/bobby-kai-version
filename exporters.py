from __future__ import annotations

import html
import re

import markdown


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[(.+?)\]\((https?://.+?)\)", r'<a href="\2">\1</a>', text)
    return text


def markdown_to_gutenberg(article_md: str) -> str:
    blocks: list[str] = []
    lines = article_md.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            text = _inline(heading.group(2))
            attrs = "" if level == 2 else f' {{"level":{level}}}'
            blocks.append(
                f'<!-- wp:heading{attrs} -->\n'
                f'<h{level} class="wp-block-heading">{text}</h{level}>\n'
                f'<!-- /wp:heading -->'
            )
            i += 1
            continue

        image = re.match(r"^!\[(.*?)\]\((.*?)\)$", line)
        if image:
            alt, src = map(html.escape, image.groups())
            blocks.append(
                '<!-- wp:image {"sizeSlug":"large","linkDestination":"none"} -->\n'
                f'<figure class="wp-block-image size-large"><img src="{src}" alt="{alt}"/></figure>\n'
                '<!-- /wp:image -->'
            )
            i += 1
            continue

        if re.match(r"^[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                item_text = re.sub(r"^[-*]\s+", "", lines[i].strip())
                items.append(f"<li>{_inline(item_text)}</li>")
                i += 1
            blocks.append(
                '<!-- wp:list -->\n<ul class="wp-block-list">'
                + "".join(items)
                + "</ul>\n<!-- /wp:list -->"
            )
            continue

        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(f"<li>{_inline(item_text)}</li>")
                i += 1
            blocks.append(
                '<!-- wp:list {"ordered":true} -->\n<ol class="wp-block-list">'
                + "".join(items)
                + "</ol>\n<!-- /wp:list -->"
            )
            continue

        if line.startswith("> "):
            quote = _inline(line[2:])
            blocks.append(
                '<!-- wp:quote -->\n<blockquote class="wp-block-quote">'
                f"<p>{quote}</p></blockquote>\n<!-- /wp:quote -->"
            )
            i += 1
            continue

        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            next_line = lines[i].strip()
            if re.match(r"^(#{1,3})\s+|^[-*]\s+|^\d+\.\s+|^>\s+|^!\[", next_line):
                break
            paragraph.append(next_line)
            i += 1
        text = _inline(" ".join(paragraph))
        blocks.append(f"<!-- wp:paragraph -->\n<p>{text}</p>\n<!-- /wp:paragraph -->")

    return "\n\n".join(blocks)


def markdown_to_substack(article_md: str) -> str:
    """Clean HTML that can be pasted into Substack's editor."""
    return markdown.markdown(article_md, extensions=["extra", "sane_lists"])
