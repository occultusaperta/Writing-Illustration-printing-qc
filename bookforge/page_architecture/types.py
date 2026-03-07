from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List


class ArchitectureType(str, Enum):
    FULL_BLEED_SPREAD = "full_bleed_spread"
    FULL_BLEED_SINGLE = "full_bleed_single"
    VIGNETTE = "vignette"
    SPOT_ILLUSTRATION = "spot_illustration"
    PANEL_SEQUENCE = "panel_sequence"
    WORDLESS_SPREAD = "wordless_spread"
    TEXT_DOMINANT = "text_dominant"
    INSET_COMPOSITE = "inset_composite"


class ZoneType(str, Enum):
    ART = "art"
    TEXT = "text"
    CAPTION = "caption"
    INSET = "inset"
    BLEED_GUARD = "bleed_guard"


@dataclass(frozen=True)
class ZoneConstraints:
    min_w: float
    min_h: float
    safe_only: bool
    can_overlap: bool


@dataclass(frozen=True)
class Zone:
    zone_id: str
    zone_type: ZoneType
    x: float
    y: float
    w: float
    h: float
    constraints: ZoneConstraints


@dataclass(frozen=True)
class ArchitectureVariant:
    variant_id: str
    architecture_type: ArchitectureType
    zones: List[Zone]
    suitability_tags: List[str]


@dataclass(frozen=True)
class ArchitecturePlan:
    page_number: int
    narrative_function: str
    target_energy: float
    selected_variant_id: str
    selected_architecture_type: ArchitectureType
    score: float


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
