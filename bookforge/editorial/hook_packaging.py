from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import requests


def _first_sentences(text: str, n: int = 2) -> List[str]:
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return sents[:n]


def _fallback(story_text: str, age_band: str) -> Dict[str, Any]:
    words = re.findall(r"[A-Za-z']+", story_text)
    lead = " ".join(words[:14]) or "A curious hero faces a surprising challenge"
    conflict = bool(re.search(r"but|until|except|however|problem|lost|stuck", " ".join(_first_sentences(story_text, 2)), re.I))
    titles = [
        "The Little Turnaround",
        "When the Map Went Missing",
        "The Brave Tiny Surprise",
        "A Whisper Before the Wow",
        "The Secret in the Lantern Glow",
        "One More Page, One Big Reveal",
        "The Sidekick Who Hid in Plain Sight",
        "The Clue Under the Moon",
        "The Small Thing That Changed Everything",
        "Find It Before Bedtime",
    ]
    return {
        "one_sentence_premise": f"{lead}: a comforting world meets a playful twist for ages {age_band}.",
        "two_sentence_opening_check": {
            "opening_sentences": _first_sentences(story_text, 2),
            "conflict_by_sentence_2": conflict,
        },
        "15_second_pitch": "A child-friendly adventure with a clear hook, page-turn tension, and a warm payoff parents will reread.",
        "title_candidates": titles,
        "llm_used": False,
    }


def generate_hook_pack(story_text: str, age_band: str) -> Dict[str, Any]:
    fallback = _fallback(story_text, age_band)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        fallback["fallback"] = fallback.copy()
        return fallback
    try:
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": json.dumps({"age_band": age_band, "task": "Generate hook packaging JSON", "story": story_text[:7000]})}],
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
        fallback["llm_used"] = True
        fallback["llm_hook_pack"] = parsed
    except Exception:
        pass
    fallback["fallback"] = fallback.copy()
    return fallback
