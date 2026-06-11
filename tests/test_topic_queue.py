import json

import topic_queue


def test_add_and_delete_queue_item(tmp_path, monkeypatch):
    queue_file = tmp_path / "topics_queue.json"
    monkeypatch.setattr(topic_queue, "QUEUE_FILE", queue_file)

    item = topic_queue.add_item(
        {
            "topic": "Test topic",
            "brief": "A useful angle",
            "format": "newsletter",
            "word_count": 1200,
            "image_count": 1,
        }
    )
    assert item["status"] == "pending"
    assert topic_queue.find_next_pending()["id"] == item["id"]

    topic_queue.delete_item(item["id"])
    assert topic_queue.load_queue() == []


def test_replace_queue_preserves_order(tmp_path, monkeypatch):
    queue_file = tmp_path / "topics_queue.json"
    monkeypatch.setattr(topic_queue, "QUEUE_FILE", queue_file)

    first = topic_queue.add_item({"topic": "First"})
    second = topic_queue.add_item({"topic": "Second"})
    replaced = topic_queue.replace_queue([second, first])
    assert [item["topic"] for item in replaced] == ["Second", "First"]
    saved = json.loads(queue_file.read_text(encoding="utf-8"))
    assert saved[0]["topic"] == "Second"


def test_add_queue_item_preserves_zero_images(tmp_path, monkeypatch):
    queue_file = tmp_path / "topics_queue.json"
    monkeypatch.setattr(topic_queue, "QUEUE_FILE", queue_file)

    item = topic_queue.add_item({"topic": "No images", "image_count": 0})

    assert item["image_count"] == 0
    assert topic_queue.load_queue()[0]["image_count"] == 0


def test_update_queue_item_preserves_generated_draft(tmp_path, monkeypatch):
    queue_file = tmp_path / "topics_queue.json"
    monkeypatch.setattr(topic_queue, "QUEUE_FILE", queue_file)
    item = topic_queue.add_item({"topic": "Generated article"})

    updated = topic_queue.update_item(
        item["id"],
        {"status": "done", "article_md": "# Draft\n\nBody", "images": []},
    )

    assert updated["article_md"] == "# Draft\n\nBody"
    assert topic_queue.load_queue()[0]["article_md"] == "# Draft\n\nBody"
