from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_profile(name_or_path: str) -> Dict[str, Any]:
    profile_path = Path(name_or_path)
    if not profile_path.exists():
        profile_path = PROFILE_DIR / f"{name_or_path}.json"
    if not profile_path.exists():
        raise RuntimeError(f"Unknown profile: {name_or_path}")
    return json.loads(profile_path.read_text(encoding="utf-8"))


def apply_profile(approval_dict: Dict[str, Any], profile_dict: Dict[str, Any]) -> Dict[str, Any]:
    return _deep_merge(approval_dict, profile_dict)
