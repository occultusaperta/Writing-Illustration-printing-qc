from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


def discover_profiles(profiles_dir: str = "profiles") -> List[str]:
    root = Path(profiles_dir)
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.json"))


def _build_cli_command(command: str, **kwargs: Any) -> List[str]:
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
    return cmd


def run_bookforge_command(
    command: str,
    *,
    cancellable: bool = False,
    session_state: Dict[str, Any] | None = None,
    log_callback: Any | None = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    cmd = _build_cli_command(command, **kwargs)
    if not cancellable:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        parsed = parse_json_stdout(proc.stdout)
        return {
            "command": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "json": parsed,
            "ok": proc.returncode == 0,
            "cancelled": False,
        }

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if session_state is not None:
        session_state["active_proc"] = proc
        session_state.setdefault("cancel_requested", False)

    lines: List[str] = []
    cancelled = False
    assert proc.stdout is not None
    while True:
        line = proc.stdout.readline()
        if line:
            lines.append(line)
            if log_callback is not None:
                log_callback("".join(lines))

        cancel_requested = bool(session_state.get("cancel_requested")) if session_state is not None else False
        if cancel_requested and proc.poll() is None:
            cancelled = True
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

        if line == "" and proc.poll() is not None:
            break
        if line == "":
            time.sleep(0.02)

    stdout = "".join(lines)
    returncode = proc.returncode
    if session_state is not None:
        session_state["active_proc"] = None
        session_state["cancel_requested"] = False

    parsed = parse_json_stdout(stdout)
    return {
        "command": cmd,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": "",
        "json": parsed,
        "ok": (returncode == 0) and not cancelled,
        "cancelled": cancelled,
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


def estimate_fal_calls(
    pages: int,
    page_variants: int,
    num_spreads: int,
    expected_regen_rate: float,
    avg_regen_rounds: float,
) -> Dict[str, int]:
    base = pages * page_variants

    def _calc(rate: float) -> int:
        regen = pages * page_variants * rate * avg_regen_rounds
        spreads = num_spreads * (1 + rate * avg_regen_rounds)
        return int(math.ceil(base + regen + spreads))

    low_rate = max(0.0, expected_regen_rate - 0.15)
    high_rate = min(0.8, expected_regen_rate + 0.15)
    likely = _calc(expected_regen_rate)
    return {"low": _calc(low_rate), "likely": likely, "high": _calc(high_rate)}


def scan_run_history(dist_dir: str | Path = "dist") -> List[Dict[str, Any]]:
    root = Path(dist_dir)
    if not root.exists():
        return []

    runs: List[Dict[str, Any]] = []
    for run_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
        lock_path = run_dir / "LOCK.json"
        report_path = run_dir / "review" / "report.html"
        if not (lock_path.exists() and report_path.exists()):
            continue

        preflight_status = "UNKNOWN"
        preflight_path = run_dir / "review" / "preflight_report.json"
        if preflight_path.exists():
            preflight = read_json(preflight_path)
            preflight_status = str(preflight.get("status", "UNKNOWN"))

        runs.append(
            {
                "run_name": run_dir.name,
                "modified_time": run_dir.stat().st_mtime,
                "preflight_status": preflight_status,
                "report": report_path,
                "proof_pack": run_dir / "review" / "proof_pack.pdf",
                "package": run_dir / "bookforge_package.zip",
                "quality_summary": run_dir / "review" / "quality_summary.md",
            }
        )
    return runs


def read_certification_markdown(repo_root: str | Path = ".") -> str | None:
    cert_path = Path(repo_root) / "CERTIFICATION.md"
    if not cert_path.exists():
        return None
    return cert_path.read_text(encoding="utf-8")


def write_overrides_json(out_dir: str | Path, overrides: Dict[str, Any]) -> Path:
    path = Path(out_dir) / "OVERRIDES.json"
    write_json(path, overrides)
    return path


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
