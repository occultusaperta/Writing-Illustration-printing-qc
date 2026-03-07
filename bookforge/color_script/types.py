from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List


class EmotionType(str, Enum):
    JOY = "joy"
    WONDER = "wonder"
    CALM = "calm"
    TENSION = "tension"
    SADNESS = "sadness"
    COURAGE = "courage"
    MYSTERY = "mystery"
    NEUTRAL = "neutral"


class HarmonyType(str, Enum):
    ANALOGOUS = "analogous"
    COMPLEMENTARY = "complementary"
    SPLIT_COMPLEMENTARY = "split_complementary"
    TRIADIC = "triadic"
    MONOCHROMATIC = "monochromatic"


@dataclass(frozen=True)
class EmotionColorProfile:
    emotion: EmotionType
    preferred_hue_center: float
    hue_spread: float
    target_chroma: float
    target_lightness: float
    warm_bias: float
    accent_weight: float


@dataclass(frozen=True)
class PageEmotionAnalysis:
    page_number: int
    emotion: EmotionType
    intensity: float
    narrative_function: str
    confidence: float


@dataclass(frozen=True)
class MasterPalette:
    dominant_emotion: EmotionType
    harmony: HarmonyType
    base_hue: float
    dominant_colors_lab: List[List[float]]
    accent_colors_lab: List[List[float]]
    neutrals_lab: List[List[float]]


@dataclass(frozen=True)
class TransitionSpec:
    from_page: int
    to_page: int
    mode: str
    strength: float


@dataclass(frozen=True)
class PageColorSpec:
    page_number: int
    emotion: EmotionType
    target_lightness: float
    target_chroma: float
    target_temperature: float
    target_contrast: float
    dominant_colors_lab: List[List[float]]
    accent_color_lab: List[float]
    forbidden_colors_lab: List[List[float]]
    background_key_lab: List[float]
    narrative_function: str



def to_primitive(payload: Any) -> Any:
    if isinstance(payload, Enum):
        return payload.value
    if isinstance(payload, list):
        return [to_primitive(i) for i in payload]
    if isinstance(payload, dict):
        return {k: to_primitive(v) for k, v in payload.items()}
    if hasattr(payload, "__dataclass_fields__"):
        return {k: to_primitive(v) for k, v in asdict(payload).items()}
    return payload


def as_jsonable(items: List[Any]) -> List[Dict[str, Any]]:
    return [to_primitive(i) for i in items]
