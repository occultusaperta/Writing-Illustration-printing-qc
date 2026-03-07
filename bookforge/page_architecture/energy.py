from __future__ import annotations

from typing import Iterable, List


def target_energy_curve(narrative_functions: Iterable[str], genre: str = "picture_book") -> List[float]:
    base = {
        "opening": 0.35,
        "rising_action": 0.62,
        "climax": 0.92,
        "falling_action": 0.46,
        "resolution": 0.30,
    }
    genre_bonus = 0.05 if genre in {"adventure", "fantasy"} else 0.0
    curve = []
    for fn in narrative_functions:
        curve.append(max(0.0, min(1.0, base.get(fn, 0.5) + genre_bonus)))
    return curve
