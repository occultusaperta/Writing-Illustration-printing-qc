from __future__ import annotations

from typing import Dict, List

from bookforge.camera_language.types import ShotType

SHOT_PRIORITY_BY_FUNCTION: Dict[str, List[ShotType]] = {
    "opening": [ShotType.ESTABLISHING_WIDE, ShotType.BIRDS_EYE, ShotType.MEDIUM_INTERACTION],
    "setup": [ShotType.ESTABLISHING_WIDE, ShotType.MEDIUM_INTERACTION, ShotType.OVER_SHOULDER],
    "rising_action": [ShotType.MEDIUM_INTERACTION, ShotType.OVER_SHOULDER, ShotType.CLOSEUP_EMOTION],
    "conflict": [ShotType.WORMS_EYE, ShotType.DUTCH_TILT, ShotType.CLOSEUP_EMOTION],
    "tension": [ShotType.CLOSEUP_EMOTION, ShotType.DUTCH_TILT, ShotType.OVER_SHOULDER],
    "reveal": [ShotType.BIRDS_EYE, ShotType.ESTABLISHING_WIDE, ShotType.EXTREME_CLOSEUP_DETAIL],
    "climax": [ShotType.WORMS_EYE, ShotType.BIRDS_EYE, ShotType.CLOSEUP_EMOTION],
    "resolution": [ShotType.MEDIUM_INTERACTION, ShotType.ESTABLISHING_WIDE, ShotType.CLOSEUP_EMOTION],
    "ending": [ShotType.ESTABLISHING_WIDE, ShotType.MEDIUM_INTERACTION, ShotType.CLOSEUP_EMOTION],
}

SHOT_DISTANCE_CLASS = {
    ShotType.ESTABLISHING_WIDE: "wide",
    ShotType.MEDIUM_INTERACTION: "medium",
    ShotType.CLOSEUP_EMOTION: "close",
    ShotType.EXTREME_CLOSEUP_DETAIL: "extreme_close",
    ShotType.BIRDS_EYE: "wide",
    ShotType.WORMS_EYE: "medium",
    ShotType.OVER_SHOULDER: "medium",
    ShotType.DUTCH_TILT: "medium",
}

SHOT_ANGLE_CLASS = {
    ShotType.ESTABLISHING_WIDE: "level",
    ShotType.MEDIUM_INTERACTION: "level",
    ShotType.CLOSEUP_EMOTION: "level",
    ShotType.EXTREME_CLOSEUP_DETAIL: "level",
    ShotType.BIRDS_EYE: "high_angle",
    ShotType.WORMS_EYE: "low_angle",
    ShotType.OVER_SHOULDER: "over_shoulder",
    ShotType.DUTCH_TILT: "tilted",
}

SHOT_PROMPT_LINES = {
    ShotType.ESTABLISHING_WIDE: "wide establishing view with clear spatial context",
    ShotType.MEDIUM_INTERACTION: "medium interaction framing with readable character blocking",
    ShotType.CLOSEUP_EMOTION: "close emotional reaction shot focused on the primary character",
    ShotType.EXTREME_CLOSEUP_DETAIL: "extreme close-up detail shot emphasizing tactile story clue",
    ShotType.BIRDS_EYE: "bird's-eye view to map scene geometry and movement",
    ShotType.WORMS_EYE: "worm's-eye view making environment forms loom",
    ShotType.OVER_SHOULDER: "over-the-shoulder framing toward the narrative target",
    ShotType.DUTCH_TILT: "slight dutch tilt to suggest instability without disorientation",
}
