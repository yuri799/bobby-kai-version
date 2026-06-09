from __future__ import annotations

import random
import re
from pathlib import Path

ROOT = Path(__file__).parent
LIBRARY_DIR = ROOT / "voice_library"
LIBRARY_DIR.mkdir(exist_ok=True)

CHUNK_WORDS = 900
SAMPLES_PER_REQUEST = 3


def _chunks() -> list[str]:
    chunks: list[str] = []
    for path in sorted(LIBRARY_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        current: list[str] = []
        words = 0
        for paragraph in paragraphs:
            size = len(paragraph.split())
            if current and words + size > CHUNK_WORDS:
                chunks.append("\n\n".join(current))
                current, words = [], 0
            current.append(paragraph)
            words += size
        if current:
            chunks.append("\n\n".join(current))
    return [chunk for chunk in chunks if len(chunk.split()) >= 100]


def build_voice_context() -> str:
    chunks = _chunks()
    if not chunks:
        return ""
    selected = random.sample(chunks, min(SAMPLES_PER_REQUEST, len(chunks)))
    return "\n\n".join(
        f"--- SAMPLE {index} ---\n{sample}"
        for index, sample in enumerate(selected, 1)
    )


def library_stats() -> dict:
    files = list(LIBRARY_DIR.glob("*.txt"))
    return {
        "files": len(files),
        "words": sum(len(path.read_text(encoding="utf-8", errors="ignore").split()) for path in files),
    }
