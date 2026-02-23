from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import requests


CHILD_SIGNALS = {
    "humor": ["giggle", "funny", "laugh", "silly", "oops"],
    "trickster_power": ["trick", "sneak", "clever", "outsmart", "secret"],
    "danger_safe_framing": ["almost", "safe", "brave", "careful", "rescued"],
    "participation_cues": ["look", "find", "can you", "say", "count"],
}

ADULT_SIGNALS = {
    "emotional_resolution": ["sorry", "forgive", "learned", "hug", "home"],
    "empathy_modeling": ["kind", "help", "share", "listen", "understand"],
    "utility_cues": ["routine", "bedtime", "school", "practice", "habit"],
    "nostalgia_cues": ["grandma", "old", "once", "remember", "classic"],
}


def _find_signals(text: str, mapping: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for name, words in mapping.items():
        hits = [w for w in words if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)]
        if hits:
            found.append({"signal": name, "evidence": sorted(hits)})
    return found


def _fatigue(text: str) -> Dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    long_sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) > 18]
    tongue_twisters = [ln for ln in lines if re.search(r"\b(\w)\w*\s+\1\w+\s+\1\w+", ln.lower())]
    awkward_breaks = [ln for ln in lines if ln.endswith(",") or ln.endswith(";")]

    reasons = []
    if long_sentences:
        reasons.append(f"{len(long_sentences)} long sentences")
    if tongue_twisters:
        reasons.append(f"{len(tongue_twisters)} tongue-twister-like lines")
    if awkward_breaks:
        reasons.append(f"{len(awkward_breaks)} awkward line breaks")

    score = min(1.0, 0.2 * len(long_sentences) + 0.25 * len(tongue_twisters) + 0.1 * len(awkward_breaks))
    return {"score": round(score, 3), "reasons": reasons or ["low fatigue risk"]}


def _openai_critique(story_text: str, age_band: str) -> Dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        payload = {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Editorial dual-address critique",
                            "age_band": age_band,
                            "story_excerpt": story_text[:7000],
                        }
                    ),
                },
            ],
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        return None


def analyze_dual_address(story_text: str, age_band: str) -> Dict[str, Any]:
    child = _find_signals(story_text, CHILD_SIGNALS)
    adult = _find_signals(story_text, ADULT_SIGNALS)
    fatigue = _fatigue(story_text)
    fallback = {
        "child_engagement_signals": child,
        "adult_gatekeeper_signals": adult,
        "read_aloud_fatigue_risk": fatigue,
        "age_band": age_band,
        "llm_used": False,
    }
    critique = _openai_critique(story_text, age_band)
    if critique is None:
        fallback["fallback"] = fallback.copy()
        return fallback
    fallback["llm_used"] = True
    fallback["llm_critique"] = critique
    fallback["fallback"] = fallback.copy()
    return fallback
