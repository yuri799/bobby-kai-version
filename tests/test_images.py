import app


def test_missing_image_markers_are_added_to_body():
    article = """# Title

Opening paragraph.

## First section

First useful paragraph.

Second useful paragraph.

## Final section

Closing paragraph."""
    result = app.ensure_image_markers(article, 2)
    assert result.count("[IMAGE_1]") == 1
    assert result.count("[IMAGE_2]") == 1
    assert "## First section\n\n[IMAGE_" not in result


def test_generate_article_images_replaces_markers(monkeypatch):
    def fake_render(prompt, index):
        return {
            "filename": f"image-{index}.png",
            "url": f"/static/generated/image-{index}.png",
            "alt": f"Image {index}",
        }

    monkeypatch.setattr(app, "_render_image", fake_render)
    article, images = app.generate_article_images("# Title\n\nA paragraph.", 2)

    assert len(images) == 2
    assert "[IMAGE_" not in article
    assert "![Image 1](/static/generated/image-1.png)" in article
    assert "![Image 2](/static/generated/image-2.png)" in article
