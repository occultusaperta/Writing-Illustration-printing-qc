from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def discover_profiles(profiles_dir: str = "profiles") -> List[str]:
    root = Path(profiles_dir)
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.json"))


def run_bookforge_command(command: str, **kwargs: Any) -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "bookforge.cli", command]
    for key, value in kwargs.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cmd.append(flag)
            continue
        if value is None:
            continue
        cmd.extend([flag, str(value)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    parsed = parse_json_stdout(proc.stdout)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "json": parsed,
        "ok": proc.returncode == 0,
    }


def parse_json_stdout(stdout: str) -> Dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for idx in range(len(text) - 1, -1, -1):
        if text[idx] != "{":
            continue
        snippet = text[idx:]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue
    return None


def read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_files(path: str | Path, pattern: str) -> List[Path]:
    root = Path(path)
    if not root.exists():
        return []
    return sorted(root.glob(pattern))


def save_story_text(story_text: str, out_dir: str | Path) -> Path:
    destination = Path(out_dir) / "story_input.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(story_text, encoding="utf-8")
    return destination


def open_in_system_viewer(path: str | Path) -> bool:
    path_obj = Path(path)
    if not path_obj.exists():
        return False

    system = platform.system().lower()
    try:
        if system == "darwin":
            subprocess.Popen(["open", str(path_obj)])
        elif system == "windows":
            os.startfile(str(path_obj))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path_obj)])
        return True
    except Exception:
        return False
