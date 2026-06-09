from pathlib import Path

from substack_publish import rewrite_image_paths, split_title_and_body


def test_split_title_and_body_uses_h1_and_optional_quote_subtitle():
    article = """# Main Title

> A short subtitle line

## Section

Body paragraph."""
    title, body, subtitle = split_title_and_body(article)
    assert title == "Main Title"
    assert subtitle == "A short subtitle line"
    assert body.startswith("## Section")
    assert "Main Title" not in body


def test_rewrite_image_paths_points_to_local_generated_files(tmp_path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"png")
    article = "Text\n\n![Alt](/static/generated/sample.png)\n"
    result = rewrite_image_paths(article, generated_dir=tmp_path)
    assert str(tmp_path / "sample.png").replace("\\", "/") in result.replace("\\", "/")
