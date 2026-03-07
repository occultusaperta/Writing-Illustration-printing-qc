from __future__ import annotations

from bookforge.color_script.types import EmotionColorProfile, EmotionType, HarmonyType

HUE_RANGES = {
    "warm": (20.0, 70.0),
    "cool": (180.0, 260.0),
    "mystic": (260.0, 320.0),
    "earth": (40.0, 120.0),
}

EMOTION_COLOR_PROFILES = {
    EmotionType.JOY: EmotionColorProfile(EmotionType.JOY, 52.0, 22.0, 52.0, 72.0, 0.8, 0.20),
    EmotionType.WONDER: EmotionColorProfile(EmotionType.WONDER, 292.0, 28.0, 46.0, 66.0, 0.1, 0.22),
    EmotionType.CALM: EmotionColorProfile(EmotionType.CALM, 212.0, 24.0, 30.0, 68.0, -0.5, 0.10),
    EmotionType.TENSION: EmotionColorProfile(EmotionType.TENSION, 8.0, 18.0, 58.0, 44.0, 0.9, 0.26),
    EmotionType.SADNESS: EmotionColorProfile(EmotionType.SADNESS, 232.0, 20.0, 24.0, 40.0, -0.7, 0.08),
    EmotionType.COURAGE: EmotionColorProfile(EmotionType.COURAGE, 24.0, 16.0, 50.0, 58.0, 0.7, 0.18),
    EmotionType.MYSTERY: EmotionColorProfile(EmotionType.MYSTERY, 278.0, 24.0, 42.0, 36.0, -0.2, 0.20),
    EmotionType.NEUTRAL: EmotionColorProfile(EmotionType.NEUTRAL, 90.0, 40.0, 16.0, 62.0, 0.0, 0.05),
}

HARMONY_BY_EMOTION = {
    EmotionType.JOY: HarmonyType.ANALOGOUS,
    EmotionType.WONDER: HarmonyType.SPLIT_COMPLEMENTARY,
    EmotionType.CALM: HarmonyType.MONOCHROMATIC,
    EmotionType.TENSION: HarmonyType.COMPLEMENTARY,
    EmotionType.SADNESS: HarmonyType.MONOCHROMATIC,
    EmotionType.COURAGE: HarmonyType.TRIADIC,
    EmotionType.MYSTERY: HarmonyType.SPLIT_COMPLEMENTARY,
    EmotionType.NEUTRAL: HarmonyType.ANALOGOUS,
}

TARGET_CONFIG = {
    "min_lightness": 18.0,
    "max_lightness": 88.0,
    "min_chroma": 6.0,
    "max_chroma": 72.0,
    "default_page_contrast": 0.48,
    "max_page_contrast": 0.75,
    "min_page_contrast": 0.20,
    "transition_threshold": 0.22,
}

EMOTION_KEYWORDS = {
    EmotionType.JOY: ["laugh", "smile", "giggle", "happy", "play"],
    EmotionType.WONDER: ["magic", "spark", "star", "glow", "wonder"],
    EmotionType.CALM: ["quiet", "soft", "sleep", "gentle", "still"],
    EmotionType.TENSION: ["chase", "storm", "danger", "roar", "panic"],
    EmotionType.SADNESS: ["cry", "alone", "lost", "tears", "sad"],
    EmotionType.COURAGE: ["brave", "stand", "help", "bold", "try"],
    EmotionType.MYSTERY: ["shadow", "secret", "unknown", "fog", "hidden"],
}

NARRATIVE_FUNCTION_KEYWORDS = {
    "opening": ["once", "begin", "morning", "introduce"],
    "rising_action": ["then", "suddenly", "but", "problem"],
    "climax": ["at last", "finally", "biggest", "roar"],
    "falling_action": ["after", "calmed", "rest"],
    "resolution": ["home", "together", "peace", "goodnight", "end"],
}
