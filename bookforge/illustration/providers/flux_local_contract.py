from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class FluxQualityPreset:
    name: str
    steps: int
    guidance_scale: float


QUALITY_PRESETS: Dict[str, FluxQualityPreset] = {
    "draft": FluxQualityPreset("draft", steps=4, guidance_scale=2.5),
    "premium": FluxQualityPreset("premium", steps=12, guidance_scale=3.0),
    "ultimate": FluxQualityPreset("ultimate", steps=20, guidance_scale=3.5),
}


@dataclass
class FluxGenerateRequest:
    prompt: str
    width: int
    height: int
    negative_prompt: str = ""
    steps: int = 4
    seed: int | None = None
    guidance: float | None = None
    quality_preset: str = "draft"
    references: List[str] = field(default_factory=list)
    lora_slots: List[Dict[str, Any]] = field(default_factory=list)
    spread: Dict[str, Any] = field(default_factory=dict)
    variant_count: int = 1
    model_name: str | None = None

    def to_payload(self) -> Dict[str, Any]:
        d = asdict(self)
        quality = QUALITY_PRESETS.get(self.quality_preset)
        if quality:
            d["quality"] = asdict(quality)
            if self.guidance is None:
                d["guidance"] = quality.guidance_scale
            if self.steps <= 0:
                d["steps"] = quality.steps
        return d


@dataclass
class FluxGenerateResponse:
    image_b64: str
    image_path: str
    seed: int
    provider: str
    model: str
    elapsed_ms: int
    cache_key: str
    provenance: Dict[str, Any]


def cache_key_for_request(endpoint: str, payload: Dict[str, Any]) -> str:
    stable = json.dumps({"endpoint": endpoint, "payload": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def parse_generate_response(data: Dict[str, Any]) -> FluxGenerateResponse:
    image_b64 = str(data.get("image_b64") or data.get("images", [{}])[0].get("content") or "")
    if not image_b64:
        raise RuntimeError("Flux local provider returned no image payload")
    prov = data.get("provenance", {}) if isinstance(data.get("provenance"), dict) else {}
    return FluxGenerateResponse(
        image_b64=image_b64,
        image_path=str(data.get("image_path", "")),
        seed=int(data.get("seed", 0)),
        provider=str(data.get("provider", "flux_local")),
        model=str(data.get("model", "flux")),
        elapsed_ms=int(data.get("elapsed_ms", 0)),
        cache_key=str(data.get("cache_key", "")),
        provenance=prov,
    )
