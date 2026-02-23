import json
import sys
from pathlib import Path

from bookforge.ui.utils import (
    discover_profiles,
    estimate_fal_calls,
    parse_json_stdout,
    read_certification_markdown,
    read_json,
    run_bookforge_command,
    save_story_text,
    scan_run_history,
    write_json,
    write_overrides_json,
)


def test_parse_json_stdout_plain():
    payload = '{"status": "PASS"}'
    assert parse_json_stdout(payload) == {"status": "PASS"}


def test_parse_json_stdout_with_logs():
    stdout = "log line\n{\n  \"status\": \"PASS\",\n  \"stage\": \"preprod\"\n}"
    assert parse_json_stdout(stdout) == {"status": "PASS", "stage": "preprod"}


def test_save_story_text_and_json_roundtrip(tmp_path: Path):
    story = save_story_text("hello", tmp_path)
    assert story.exists()
    assert story.read_text(encoding="utf-8") == "hello"

    config_path = tmp_path / "x" / "config.json"
    write_json(config_path, {"a": 1})
    assert read_json(config_path) == {"a": 1}


def test_discover_profiles():
    profiles = discover_profiles("profiles")
    assert "ultimate_imprint_8p5x8p5_image_heavy" in profiles


def test_estimate_fal_calls_range():
    calls = estimate_fal_calls(pages=24, page_variants=4, num_spreads=6, expected_regen_rate=0.25, avg_regen_rounds=1)
    assert calls["low"] <= calls["likely"] <= calls["high"]
    assert calls["likely"] == 128


def test_scan_run_history(tmp_path: Path):
    run = tmp_path / "dist" / "run1"
    (run / "review").mkdir(parents=True)
    (run / "LOCK.json").write_text("{}", encoding="utf-8")
    (run / "review" / "report.html").write_text("ok", encoding="utf-8")
    (run / "review" / "preflight_report.json").write_text('{"status":"PASS"}', encoding="utf-8")

    rows = scan_run_history(tmp_path / "dist")
    assert len(rows) == 1
    assert rows[0]["run_name"] == "run1"
    assert rows[0]["preflight_status"] == "PASS"


def test_write_overrides_json(tmp_path: Path):
    path = write_overrides_json(tmp_path, {"variant_preference": {"1": 2}})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["variant_preference"]["1"] == 2


def test_read_certification_markdown(tmp_path: Path):
    cert = tmp_path / "CERTIFICATION.md"
    cert.write_text("# Cert", encoding="utf-8")
    assert read_certification_markdown(tmp_path) == "# Cert"


def test_cancellable_run_returns_output():
    result = run_bookforge_command(
        "doctor",
        cancellable=True,
        session_state={},
    )
    assert "command" in result
    assert isinstance(result["stdout"], str)
