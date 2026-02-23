from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


def _extract_front_matter(raw: str) -> Tuple[Dict[str, Any], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---", 4)
    if end < 0:
        return {}, raw
    block = raw[4:end].strip()
    body = raw[end + 4 :].lstrip("\n")
    meta: Dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"')
    return meta, body


def _split_never_empty(text: str, pages: int) -> List[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        raise RuntimeError("Story file is empty.")
    result: List[str] = []
    idx = 0
    for p in range(pages):
        remaining_slots = pages - p
        remaining_items = len(sentences) - idx
        take = max(1, math.ceil(remaining_items / remaining_slots))
        chunk = " ".join(sentences[idx : idx + take]).strip()
        if not chunk:
            chunk = sentences[min(idx, len(sentences) - 1)]
        result.append(chunk)
        idx = min(len(sentences), idx + take)
    if idx < len(sentences):
        result[-1] = f"{result[-1]} {' '.join(sentences[idx:])}".strip()
    return result


def _split_with_word_limit(text: str, pages: int, max_words_per_page: int) -> List[str]:
    words = re.findall(r"\S+", text)
    if not words:
        raise RuntimeError("Story file is empty.")
    if len(words) > pages * max_words_per_page:
        raise RuntimeError(f"Story exceeds layout limit: {len(words)} words for {pages} pages at max_words_per_page={max_words_per_page}.")

    result: List[str] = []
    idx = 0
    for page in range(pages):
        remaining_pages = pages - page
        remaining_words = len(words) - idx
        take = max(1, math.ceil(remaining_words / remaining_pages))
        take = min(take, max_words_per_page)
        page_words = words[idx : idx + take]
        if not page_words:
            page_words = [words[-1]]
        result.append(" ".join(page_words))
        idx = min(len(words), idx + take)
    return result


def parse_story(path: str | Path, pages: int, max_words_per_page_override: int | None = None) -> Dict[str, Any]:
    story_path = Path(path)
    raw = story_path.read_text(encoding="utf-8")
    meta, text = _extract_front_matter(raw)

    title = meta.get("title") or story_path.stem.replace("_", " ").title()
    author = meta.get("author") or "Internal Studio"
    meta_limit = int(meta.get("max_words_per_page", "0") or 0)
    max_words_per_page = int(max_words_per_page_override or meta_limit or 0)

    sections = re.split(r"(?:^|\n)##\s*Page\s*\d+[:\-]?", text, flags=re.IGNORECASE)
    explicit = [s.strip() for s in sections if s.strip()]
    if len(explicit) >= pages:
        page_texts = explicit[:pages]
    elif len(explicit) > 1:
        padded = explicit[:]
        while len(padded) < pages:
            padded.append(padded[-1])
        page_texts = padded[:pages]
    else:
        if max_words_per_page > 0:
            page_texts = _split_with_word_limit(text, pages, max_words_per_page)
        else:
            page_texts = _split_never_empty(text, pages)

    return {
        "title": title,
        "author": author,
        "pages": [{"page_number": i + 1, "text": page_texts[i]} for i in range(pages)],
        "metadata": {
            "protagonist_name": meta.get("protagonist_name", ""),
            "wardrobe": meta.get("wardrobe", ""),
            "palette": meta.get("palette", ""),
            "vibe": meta.get("vibe", ""),
            "typography_preset": meta.get("typography_preset", "storybook_large"),
            "interior_layout_preset": meta.get("interior_layout_preset", "cinematic_panel_bottom"),
            "cover_layout_preset": meta.get("cover_layout_preset", "front_title_top_back_blurb"),
            "age_band": meta.get("age_band", "6-8"),
            "max_words_per_page": max_words_per_page if max_words_per_page > 0 else None,
        },
    }


def analyze_story_text(text: str) -> Dict[str, Any]:
    if os.getenv("OPENAI_API_KEY", "").strip():
        try:
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Extract protagonist, setting, tone, props as JSON from this story:\n" + text[:8000]}],
                "temperature": 0,
            }
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"},
                json=payload,
                timeout=45,
            )
            if resp.status_code < 400:
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception:
            pass
    tokens = re.findall(r"\b[A-Z][a-z]+\b", text)
    protagonist = tokens[0] if tokens else "Protagonist"
    tone = "adventurous" if re.search(r"brave|quest|adventure|journey", text, re.I) else "warm"
    setting = "forest" if re.search(r"forest|tree|woods", text, re.I) else "storybook town"
    props = []
    for w in ["lantern", "map", "satchel", "kite", "book"]:
        if re.search(rf"\b{w}\b", text, re.I):
            props.append(w)
    return {"protagonist_cues": protagonist, "setting_cues": setting, "tone_cues": tone, "props": props or ["storybook prop"]}


def build_bible_variants(parsed_story: Dict[str, Any], variants: int = 4) -> List[Dict[str, Any]]:
    full_text = "\n".join(page["text"] for page in parsed_story["pages"])
    cues = analyze_story_text(full_text)
    meta = parsed_story.get("metadata", {})
    protagonist = meta.get("protagonist_name") or cues["protagonist_cues"]
    wardrobe = meta.get("wardrobe") or "storybook outfit with consistent colors"
    palette = meta.get("palette") or "#F2C14E,#3A506B,#5BC0BE"
    vibe = meta.get("vibe") or cues["tone_cues"]
    out: List[Dict[str, Any]] = []
    for i in range(1, variants + 1):
        character = {
            "protagonist_name": protagonist,
            "wardrobe": wardrobe,
            "do_not_change": ["face shape", "age", "wardrobe palette", "hair silhouette"],
            "props": cues["props"],
            "variant_note": f"variant {i} framing and pose diversity",
        }
        style = {
            "visual_mode": f"luxury children's storybook illustration {i}",
            "palette": [p.strip() for p in palette.split(",")],
            "setting": cues["setting_cues"],
            "tone": vibe,
            "composition": "subject centered in safe area, cinematic depth",
        }
        prefix = (
            f"LOCKED CHARACTER: {protagonist}; invariant wardrobe: {wardrobe}; invariant props: {', '.join(cues['props'])}. "
            f"LOCKED STYLE: {style['visual_mode']}; palette {palette}; tone {vibe}; no character drift."
        )
        out.append(
            {
                "variant": i,
                "character_bible": character,
                "style_bible": style,
                "locked_prompt_prefix": prefix,
                "locked_negative_prompt": "NO text, NO watermark, NO logo, NO extra limbs, NO deformed hands, NO cropped faces near trim",
            }
        )
    return out
