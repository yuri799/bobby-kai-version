from exporters import markdown_to_gutenberg, markdown_to_substack


SAMPLE = """# A Useful Title

Intro with **bold text** and a [link](https://example.com).

## The list

- First
- Second

> A useful quote
"""


def test_gutenberg_export_uses_native_blocks():
    result = markdown_to_gutenberg(SAMPLE)
    assert "<!-- wp:heading" in result
    assert "<!-- wp:paragraph -->" in result
    assert "<!-- wp:list -->" in result
    assert "<!-- wp:quote -->" in result
    assert "<strong>bold text</strong>" in result


def test_substack_export_is_clean_html():
    result = markdown_to_substack(SAMPLE)
    assert "<h1>A Useful Title</h1>" in result
    assert "<strong>bold text</strong>" in result
    assert "<!-- wp:" not in result
