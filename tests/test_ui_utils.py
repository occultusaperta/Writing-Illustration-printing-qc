from pathlib import Path

from bookforge.ui.utils import discover_profiles, parse_json_stdout, save_story_text, write_json, read_json


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
