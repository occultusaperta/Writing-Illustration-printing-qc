from __future__ import annotations

import re
from typing import Any, Dict, List


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    count = max(1, len(groups))
    if w.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def audit_rhythm_and_rhyme(text: str) -> Dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        lines = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    syllables = [sum(_syllables(w) for w in re.findall(r"[A-Za-z']+", ln)) for ln in lines]

    endings = [re.findall(r"[A-Za-z']+", ln.lower())[-1] if re.findall(r"[A-Za-z']+", ln.lower()) else "" for ln in lines]
    rhyme_scores = []
    for i in range(1, len(endings)):
        rhyme_scores.append(1.0 if endings[i][-2:] == endings[i - 1][-2:] and endings[i] else 0.0)

    repeats = {}
    for ln in lines:
        repeats[ln.lower()] = repeats.get(ln.lower(), 0) + 1
    chorus = [ln for ln, cnt in repeats.items() if cnt > 1]

    flagged: List[Dict[str, Any]] = []
    if syllables:
        avg = sum(syllables) / len(syllables)
        for idx, val in enumerate(syllables, start=1):
            if abs(val - avg) > 4:
                flagged.append({"line": idx, "reason": "meter break", "syllables": val})
    for idx, ln in enumerate(lines, start=1):
        if len(ln.split()) > 16:
            flagged.append({"line": idx, "reason": "long read-aloud line"})

    meter_consistency = 1.0
    if syllables:
        meter_consistency = max(0.0, 1.0 - (sum(abs(s - (sum(syllables) / len(syllables))) for s in syllables) / (len(syllables) * 10.0)))
    rhyme = sum(rhyme_scores) / len(rhyme_scores) if rhyme_scores else 0.6
    chorus_bonus = min(0.15, 0.05 * len(chorus))
    score = max(0.0, min(100.0, (meter_consistency * 55 + rhyme * 30 + chorus_bonus * 100)))

    return {
        "syllable_estimate_per_line": [{"line": i + 1, "syllables": s} for i, s in enumerate(syllables)],
        "end_rhyme_similarity": round(rhyme, 3),
        "repetition_or_chorus_lines": chorus,
        "predictable_surprise_candidates": flagged,
        "read_aloud_smoothness_score": round(score, 2),
        "flagged_lines": flagged,
    }
