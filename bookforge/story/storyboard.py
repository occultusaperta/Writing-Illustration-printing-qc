from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import requests

CAMERA_PATTERN = ("wide", "medium", "close")


def _extract_keywords(text: str, options: List[str], default: str) -> str:
    for item in options:
        if re.search(rf"\b{re.escape(item)}\b", text, re.IGNORECASE):
            return item
    return default


def _emotion_from_text(text: str) -> str:
    cues = {
        "joyful": ["smile", "laugh", "happy", "delight"],
        "curious": ["wonder", "curious", "peek", "explore"],
        "nervous": ["worry", "nervous", "afraid", "hesitate"],
        "brave": ["brave", "courage", "bold", "determined"],
        "calm": ["quiet", "calm", "gentle", "soft"],
    }
    for emotion, words in cues.items():
        if any(re.search(rf"\b{w}\w*\b", text, re.IGNORECASE) for w in words):
            return emotion
    return "warm"


def _characters(text: str, fallback_name: str) -> List[str]:
    found = sorted(set(re.findall(r"\b[A-Z][a-z]+\b", text)))
    if fallback_name and fallback_name not in found:
        found.insert(0, fallback_name)
    return found[:4] if found else [fallback_name or "Protagonist"]


def _props(text: str) -> List[str]:
    catalog = ["book", "kite", "lantern", "map", "hat", "boots", "umbrella", "bag", "flower"]
    result = [p for p in catalog if re.search(rf"\b{p}\b", text, re.IGNORECASE)]
    return result[:4] if result else ["signature prop"]


def _continuity_tokens(characters: List[str], wardrobe: str, palette: str) -> List[str]:
    safe_chars = [re.sub(r"[^A-Z0-9]+", "_", c.upper()) for c in characters]
    wardrobe_token = re.sub(r"[^A-Z0-9]+", "_", wardrobe.upper()).strip("_") if wardrobe else "WARDROBE_LOCKED"
    palette_token = re.sub(r"[^A-Z0-9#]+", "_", palette.upper()).strip("_") if palette else "PALETTE_LOCKED"
    tokens = [f"{safe_chars[0]}_{wardrobe_token}", palette_token]
    return [t for t in tokens if t]


def _fallback_storyboard(parsed_story: Dict[str, Any], variants: int) -> Dict[str, Any]:
    meta = parsed_story.get("metadata", {})
    protagonist = meta.get("protagonist_name", "Protagonist")
    wardrobe = meta.get("wardrobe", "")
    palette = meta.get("palette", "")
    pages = []
    settings = ["forest", "town", "meadow", "bedroom", "school", "river"]
    for idx, page in enumerate(parsed_story["pages"]):
        text = page["text"]
        camera = CAMERA_PATTERN[idx % len(CAMERA_PATTERN)]
        setting = _extract_keywords(text, settings, "storybook world")
        chars = _characters(text, protagonist)
        pages.append(
            {
                "page_number": page["page_number"],
                "summary": text[:180],
                "characters_present": chars,
                "emotion": _emotion_from_text(text),
                "props": _props(text),
                "setting": setting,
                "camera": camera,
                "composition": f"{camera} shot, subject inside safe area, balanced negative space",
                "continuity_tokens": _continuity_tokens(chars, wardrobe, palette),
            }
        )
    return {"variant": min(max(1, variants), 1), "pages": pages, "source": "heuristic"}


def _openai_storyboard(parsed_story: Dict[str, Any], variants: int) -> Dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Return strict JSON only. No markdown. Provide deterministic storyboard for every page.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "variants": variants,
                            "story": parsed_story,
                            "schema": {
                                "variant": "int",
                                "pages": [
                                    {
                                        "page_number": "int",
                                        "summary": "string",
                                        "characters_present": ["string"],
                                        "emotion": "string",
                                        "props": ["string"],
                                        "setting": "string",
                                        "camera": "wide|medium|close",
                                        "composition": "string",
                                        "continuity_tokens": ["string"],
                                    }
                                ],
                            },
                        }
                    ),
                },
            ],
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("pages"), list):
            return parsed
    except Exception:
        return None
    return None


def generate_storyboard(parsed_story: Dict[str, Any], variants: int, use_openai_if_available: bool = True) -> Dict[str, Any]:
    if use_openai_if_available:
        model_result = _openai_storyboard(parsed_story, variants)
        if model_result is not None:
            return model_result
    return _fallback_storyboard(parsed_story, variants)
