from __future__ import annotations

from collections import Counter
from typing import Dict, List

from bookforge.color_script.constants import EMOTION_KEYWORDS, NARRATIVE_FUNCTION_KEYWORDS
from bookforge.color_script.types import EmotionType, PageEmotionAnalysis


def _score_emotions(text: str) -> Counter[EmotionType]:
    lowered = text.lower()
    scores: Counter[EmotionType] = Counter()
    for emotion, words in EMOTION_KEYWORDS.items():
        scores[emotion] = sum(lowered.count(w) for w in words)
    return scores


def _narrative_function(text: str, page_idx: int, page_count: int) -> str:
    lowered = text.lower()
    for fn, kws in NARRATIVE_FUNCTION_KEYWORDS.items():
        if any(k in lowered for k in kws):
            return fn
    progress = (page_idx + 1) / max(1, page_count)
    if progress <= 0.2:
        return "opening"
    if progress <= 0.6:
        return "rising_action"
    if progress <= 0.8:
        return "climax"
    if progress <= 0.92:
        return "falling_action"
    return "resolution"


def analyze_page_emotions(pages: List[Dict[str, object]]) -> List[PageEmotionAnalysis]:
    analyses: List[PageEmotionAnalysis] = []
    for i, page in enumerate(pages):
        text = str(page.get("text", "")).strip()
        scores = _score_emotions(text)
        if not scores or max(scores.values()) == 0:
            emotion = EmotionType.NEUTRAL
            intensity = 0.3
            confidence = 0.4
        else:
            emotion = max(scores, key=scores.get)
            peak = float(scores[emotion])
            total = float(sum(scores.values()))
            intensity = min(1.0, 0.25 + peak / 4.0)
            confidence = min(1.0, peak / total) if total else 0.4
        analyses.append(
            PageEmotionAnalysis(
                page_number=int(page.get("page_number", i + 1)),
                emotion=emotion,
                intensity=round(intensity, 4),
                narrative_function=_narrative_function(text, i, len(pages)),
                confidence=round(confidence, 4),
            )
        )
    return analyses
