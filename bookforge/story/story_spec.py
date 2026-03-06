from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


_STORYWEAVER_PAGE_RE = re.compile(r"^Pages\s*(\d+)\s*[\-–]\s*(\d+)(.*)$", re.IGNORECASE)


def _extract_tagged_blocks(text: str) -> List[Tuple[str, str]]:
    blocks: List[Tuple[str, str]] = []
    current_tag = ""
    current_lines: List[str] = []
    for line in text.splitlines():
        marker = re.match(r"^\[(.+?)\](.*)$", line.strip())
        if marker:
            tag_content = marker.group(1).strip()
            if re.match(r"^(ILLUSTRATION NOTE:|PAGE TURN\s*[—\-])", tag_content, flags=re.IGNORECASE):
                current_lines.append(line.strip())
                continue
            if current_tag or current_lines:
                blocks.append((current_tag, "\n".join(current_lines).strip("\n")))
            current_tag = tag_content
            trailing = marker.group(2).strip()
            current_lines = [trailing] if trailing else []
            continue
        current_lines.append(line)
    if current_tag or current_lines:
        blocks.append((current_tag, "\n".join(current_lines).strip("\n")))
    return blocks


def _parse_storyweaver(text: str, default_pages: int) -> Dict[str, Any] | None:
    blocks = _extract_tagged_blocks(text)
    page_blocks = [(tag, body) for tag, body in blocks if _STORYWEAVER_PAGE_RE.match(tag)]
    if not page_blocks:
        return None

    pages_map: Dict[int, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    spread_pairs: set[Tuple[int, int]] = set()
    declared_pages = 0

    for tag, body in blocks:
        m = _STORYWEAVER_PAGE_RE.match(tag)
        if not m:
            extras.append({"section": tag or "Unlabeled", "content": body})
            continue
        start, end = int(m.group(1)), int(m.group(2))
        declared_pages = max(declared_pages, start, end)
        marker_tail = m.group(3) or ""
        is_spread = (end == start + 1) or ("FULL DOUBLE-PAGE SPREAD" in marker_tail.upper()) or ("FULL DOUBLE-PAGE SPREAD" in body.upper())
        if is_spread:
            spread_pairs.add((start, end))

        illustration_notes = [x.strip() for x in re.findall(r"\[ILLUSTRATION NOTE:\s*(.*?)\]", body, flags=re.IGNORECASE | re.DOTALL) if x.strip()]
        page_turns = [x.strip() for x in re.findall(r"\[PAGE TURN\s*[—\-]\s*(.*?)\]", body, flags=re.IGNORECASE | re.DOTALL) if x.strip()]
        hidden_details = [x.strip() for x in re.findall(r"\b(?:must include|required hidden detail|hidden detail)\s*[:\-]\s*(.+)", "\n".join(illustration_notes), flags=re.IGNORECASE)]

        printed_markdown = re.sub(r"\[ILLUSTRATION NOTE:\s*.*?\]", "", body, flags=re.IGNORECASE | re.DOTALL)
        printed_markdown = re.sub(r"\[PAGE TURN\s*[—\-]\s*.*?\]", "", printed_markdown, flags=re.IGNORECASE | re.DOTALL).strip("\n")
        text_for_prompt = " ".join(line.strip() for line in printed_markdown.splitlines() if line.strip())

        for page_no in range(start, end + 1):
            pages_map[page_no] = {
                "page_number": page_no,
                "text": text_for_prompt,
                "printed_markdown": printed_markdown,
                "illustration_notes": illustration_notes,
                "required_hidden_details": hidden_details,
                "page_turn_markers": page_turns,
            }

    if declared_pages <= 0:
        declared_pages = default_pages
    pages = [
        pages_map.get(
            i,
            {
                "page_number": i,
                "text": "",
                "printed_markdown": "",
                "illustration_notes": [],
                "required_hidden_details": [],
                "page_turn_markers": [],
            },
        )
        for i in range(1, declared_pages + 1)
    ]

    companion = {item["section"]: item["content"] for item in extras if item.get("content")}
    companion_text = "\n\n".join(f"{k}\n{v}" for k, v in companion.items())
    seller_line = ""
    pitch = ""
    quote = re.search(r"THE LINE THAT SELLS THE BOOK\s*[:\-]\s*[\"“]?(.+?)[\"”]?(?:\n|$)", companion_text, flags=re.IGNORECASE)
    if quote:
        seller_line = quote.group(1).strip()
    pitch_m = re.search(r"(?:one[- ]sentence pitch|book pitch)\s*[:\-]\s*(.+?)(?:\n|$)", companion_text, flags=re.IGNORECASE)
    if pitch_m:
        pitch = pitch_m.group(1).strip()

    return {
        "pages": pages,
        "declared_pages": declared_pages,
        "spread_pairs": [list(pair) for pair in sorted(spread_pairs)],
        "extras": extras,
        "companion": companion,
        "cover_copy": {"line_that_sells_the_book": seller_line, "one_sentence_pitch": pitch},
    }


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

    storyweaver = _parse_storyweaver(text, pages)
    parse_warnings: List[str] = []
    if storyweaver:
        declared_pages = int(storyweaver["declared_pages"])
        if declared_pages != int(pages):
            parse_warnings.append(f"Storyweaver declared pages={declared_pages}; ignoring requested pages={pages}.")
        page_payload = storyweaver["pages"]
        page_count = declared_pages
    else:
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
        page_payload = [{"page_number": i + 1, "text": page_texts[i]} for i in range(pages)]
        page_count = pages

    return {
        "title": title,
        "author": author,
        "pages": page_payload,
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
            "storyweaver_detected": bool(storyweaver),
            "declared_pages": storyweaver["declared_pages"] if storyweaver else page_count,
            "storyweaver_spread_pairs": storyweaver["spread_pairs"] if storyweaver else [],
            "cover_copy": storyweaver["cover_copy"] if storyweaver else {},
        },
        "declared_pages": storyweaver["declared_pages"] if storyweaver else page_count,
        "spread_pairs": storyweaver["spread_pairs"] if storyweaver else [],
        "extras": storyweaver["extras"] if storyweaver else [],
        "companion": storyweaver["companion"] if storyweaver else {},
        "parse_warnings": parse_warnings,
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
