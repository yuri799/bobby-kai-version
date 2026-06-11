import app


def test_run_queue_item_stores_draft_without_substack(monkeypatch):
    updates = []
    push_values = []
    item = {"id": "queue-1", "topic": "Test article", "image_count": 0}

    def fake_update_item(item_id, values):
        updates.append((item_id, values))

    def fake_run_generation_job(data, *, push_substack=False):
        push_values.append(push_substack)
        return {"article_md": "# Draft\n\nBody", "images": []}

    monkeypatch.setattr(app, "update_item", fake_update_item)
    monkeypatch.setattr(app, "run_generation_job", fake_run_generation_job)

    result = app._run_queue_item(item)

    assert push_values == [False]
    assert result["article_md"] == "# Draft\n\nBody"
    assert updates[-1][1]["status"] == "done"
    assert updates[-1][1]["article_md"] == "# Draft\n\nBody"
