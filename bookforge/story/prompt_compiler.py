from __future__ import annotations

from typing import Any, Dict, Iterable


def compile_prompt(lock: Dict[str, Any], page_text: str, storyboard_fields: Dict[str, Any], addendum: str = "") -> str:
    camera = str(storyboard_fields.get("camera", "medium")).strip().lower()
    emotion = storyboard_fields.get("emotion", "warm")
    setting = storyboard_fields.get("setting", "storybook world")
    props = storyboard_fields.get("props", [])
    props_text = ", ".join(props) if isinstance(props, list) and props else "storybook props"

    templates = {
        "wide": "Environment-first composition, protagonist smaller in frame, strong setting cues and depth.",
        "medium": "Action clarity with props visible, protagonist centered in safe-zone, readable motion.",
        "close": "Expression clarity, clean background, face and hands fully inside safe-zone.",
    }
    camera_line = templates.get(camera, templates["medium"])

    parts = [
        str(lock.get("locked_prompt_prefix", "")).strip(),
        f"Scene text: {page_text.strip()}",
        f"Camera: {camera}. {camera_line}",
        f"Emotion: {emotion}. Setting: {setting}. Props: {props_text}.",
        "Safe-zone composition: keep key subject details inside trim safe area.",
        "NO TEXT / NO WATERMARK / NO LOGO.",
        str(lock.get("locked_negative_prompt", "")).strip(),
    ]

    failed_flags = lock.get("qa_failed_flags", [])
    if _needs_anatomy_guard(failed_flags):
        parts.append("clean hands, five fingers, no extra limbs")
    if addendum.strip():
        parts.append(addendum.strip())
    return " ".join(p for p in parts if p)


def tighten_prompt(prompt: str, reason_flags: Iterable[str]) -> str:
    flags = {str(f).lower() for f in reason_flags}
    out = prompt
    if {"text", "watermark", "logo"} & flags:
        out += " hard ban overlays and marks; plain artwork only"
    if {"anatomy", "extra_limbs", "hands"} & flags:
        out += " clean hands, five fingers, no extra limbs"
    if {"border", "artifact"} & flags:
        out += " no border bars, avoid edge artifacts"
    if "crowd" in flags:
        out += " single main character focus, avoid crowd"
    return out.strip()


def _needs_anatomy_guard(flags: Iterable[str]) -> bool:
    f = {str(x).lower() for x in flags}
    return bool({"anatomy", "extra_limbs", "hands", "face_like_regions"} & f)
