from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import requests


def generate_blurb_options(parsed_story: Dict[str, Any], n: int = 5, allow_generated: bool = False) -> Dict[str, List[str]]:
    cover_copy = parsed_story.get("metadata", {}).get("cover_copy", {}) if isinstance(parsed_story, dict) else {}
    seller_line = str(cover_copy.get("line_that_sells_the_book", "")).strip()
    pitch = str(cover_copy.get("one_sentence_pitch", "")).strip()
    if seller_line or pitch:
        blurbs = [x for x in [seller_line, pitch] if x]
        subtitles = [pitch] if pitch else ["A richly illustrated storybook adventure"]
        return {"blurbs": (blurbs or _fallback_blurbs(parsed_story, n)["blurbs"])[:n], "subtitles": subtitles[:3]}

    if not allow_generated:
        return _fallback_blurbs(parsed_story, n)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        try:
            return _generate_with_openai(parsed_story, n, api_key)
        except Exception:
            pass
    return _fallback_blurbs(parsed_story, n)


def _generate_with_openai(parsed_story: Dict[str, Any], n: int, api_key: str) -> Dict[str, List[str]]:
    pages = "\n".join(f"Page {p['page_number']}: {p['text']}" for p in parsed_story.get("pages", []))
    prompt = (
        "Generate strict JSON with keys blurbs and subtitles. "
        f"blurbs: {n} entries, each 60-110 words. subtitles: 3 entries, each 6-10 words. "
        "No markdown.\n"
        f"Title: {parsed_story.get('title','')}\nAuthor: {parsed_story.get('author','')}\nStory:\n{pages[:10000]}"
    )
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    blurbs = [str(x).strip() for x in data.get("blurbs", [])][:n]
    subtitles = [str(x).strip() for x in data.get("subtitles", [])][:3]
    if not blurbs:
        raise RuntimeError("No blurbs generated")
    if not subtitles:
        subtitles = ["A heartfelt journey through wonder and courage"]
    return {"blurbs": blurbs, "subtitles": subtitles}


def _fallback_blurbs(parsed_story: Dict[str, Any], n: int) -> Dict[str, List[str]]:
    page_lines = [p.get("text", "").strip() for p in parsed_story.get("pages", []) if p.get("text", "").strip()]
    core = " ".join(page_lines[:4])
    if not core:
        core = "A warm story of friendship, courage, and imagination."
    base = (
        f"{parsed_story.get('title','This story')} follows a young hero through moments of challenge and wonder. "
        f"{core[:260]} "
        "With gentle pacing and vivid scenes, this tale invites families to read aloud and revisit each page. "
        "A final spark of hope makes it perfect for bedtime and classroom sharing."
    )
    blurbs = [base for _ in range(max(1, n))]
    subtitles = [
        "A gentle adventure for curious young hearts",
        "A story of courage friendship and wonder",
        "Bedtime magic with bright emotional storytelling",
    ]
    return {"blurbs": blurbs[:n], "subtitles": subtitles}
