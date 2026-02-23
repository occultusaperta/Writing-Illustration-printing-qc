from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from bookforge.ui.utils import (
    discover_profiles,
    list_files,
    open_in_system_viewer,
    read_json,
    run_bookforge_command,
    save_story_text,
    write_json,
)

ROOT = Path.cwd()
CSS_PATH = Path(__file__).with_name("style.css")


def _init_state() -> None:
    defaults = {
        "project_name": "run",
        "size": "8.5x8.5",
        "pages": 24,
        "variants": 4,
        "profile": "ultimate_imprint_8p5x8p5_image_heavy",
        "out_dir": "dist/run",
        "story_path": "",
        "story_text": "",
        "last_logs": "",
        "last_result": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _inject_css() -> None:
    if CSS_PATH.exists():
        st.markdown(f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _path_link(path: Path) -> None:
    st.markdown(f"[{path}](file://{path.resolve()})")


def _open_button(path: Path, label: str) -> None:
    col1, col2 = st.columns([4, 1])
    with col1:
        _path_link(path)
    with col2:
        if st.button(label, key=f"open-{path}-{label}"):
            ok = open_in_system_viewer(path)
            st.toast("Opened" if ok else "Could not open", icon="✅" if ok else "⚠️")


def _show_command_output(result: Dict[str, Any]) -> None:
    st.code(" ".join(result["command"]), language="bash")
    if result["stdout"]:
        st.text_area("stdout", value=result["stdout"], height=160)
    if result["stderr"]:
        st.text_area("stderr", value=result["stderr"], height=100)
    if result["json"]:
        st.json(result["json"])


def _preprod_paths(out_dir: Path) -> Dict[str, Path]:
    preprod = out_dir / "preprod"
    return {
        "preprod": preprod,
        "approval": preprod / "APPROVAL.json",
        "layout_options": preprod / "layout_options.json",
        "lock": out_dir / "LOCK.json",
        "checkpoint": out_dir / "CHECKPOINT.json",
    }


def _apply_uploaded_reference(upload, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(upload.getbuffer())


def _render_setup() -> None:
    st.header("1) Setup")
    st.session_state["project_name"] = st.text_input("Project name", value=st.session_state["project_name"])
    st.session_state["out_dir"] = f"dist/{st.session_state['project_name']}"
    out_dir = Path(st.session_state["out_dir"])
    st.caption(f"Output folder: {out_dir}")

    upload = st.file_uploader("Upload story (.md/.txt)", type=["md", "txt"])
    story_text = st.text_area("Or paste story text", value=st.session_state["story_text"], height=200)
    st.session_state["story_text"] = story_text

    if upload is not None:
        story_path = out_dir / "story_input.md"
        story_path.parent.mkdir(parents=True, exist_ok=True)
        story_path.write_bytes(upload.getbuffer())
        st.session_state["story_path"] = str(story_path)
        st.success(f"Saved uploaded story to {story_path}")

    if st.button("Save pasted text to story_input.md") and story_text.strip():
        story_path = save_story_text(story_text, out_dir)
        st.session_state["story_path"] = str(story_path)
        st.success(f"Saved story to {story_path}")

    profiles = discover_profiles()
    selected_profile = st.selectbox(
        "Profile",
        options=profiles or [st.session_state["profile"]],
        index=(profiles.index(st.session_state["profile"]) if st.session_state["profile"] in profiles else 0),
    )
    st.session_state["profile"] = selected_profile

    c1, c2, c3 = st.columns(3)
    st.session_state["size"] = c1.text_input("Trim size", value=st.session_state["size"])
    st.session_state["pages"] = c2.number_input("Pages", min_value=8, step=2, value=int(st.session_state["pages"]))
    st.session_state["variants"] = c3.number_input("Variants", min_value=1, max_value=8, value=int(st.session_state["variants"]))

    if st.button("Run Doctor (strict)"):
        result = run_bookforge_command("doctor", strict=True)
        st.session_state["last_result"] = result
        _show_command_output(result)


def _render_preprod() -> None:
    st.header("2) Preprod")
    out_dir = Path(st.session_state["out_dir"])
    story_path = st.session_state.get("story_path")

    if st.button("Run Preprod"):
        if not story_path:
            st.error("Provide a story first.")
        else:
            result = run_bookforge_command(
                "preprod",
                story=story_path,
                out=str(out_dir),
                size=st.session_state["size"],
                pages=int(st.session_state["pages"]),
                variants=int(st.session_state["variants"]),
                profile=st.session_state["profile"],
            )
            st.session_state["last_result"] = result
            _show_command_output(result)

    preprod = out_dir / "preprod"
    if not preprod.exists():
        return

    options_pdf = preprod / "options_contact_sheet.pdf"
    if options_pdf.exists():
        _open_button(options_pdf, "Open")

    for folder_name in ["layout_previews", "cover_previews"]:
        folder = preprod / folder_name
        if folder.exists():
            st.subheader(folder_name)
            for pdf in sorted(folder.glob("*.pdf")):
                _open_button(pdf, "Open")

    st.subheader("Option image grids")
    cols = st.columns(3)
    image_patterns = [
        ("character_options", "character_turnaround_v*.png"),
        ("style_options", "style_frame_v*.png"),
        ("cover_options", "cover_concept_v*.png"),
    ]
    for idx, (folder, pattern) in enumerate(image_patterns):
        files = list_files(preprod / folder, pattern)
        with cols[idx]:
            st.caption(folder)
            for image in files:
                st.image(str(image), caption=image.name, use_container_width=True)

    st.subheader("Bring your own references (optional)")
    char_upload = st.file_uploader("Character reference", type=["png", "jpg", "jpeg"], key="char_up")
    style_upload = st.file_uploader("Style reference", type=["png", "jpg", "jpeg"], key="style_up")
    cover_upload = st.file_uploader("Cover reference", type=["png", "jpg", "jpeg"], key="cover_up")

    if st.button("Save uploaded references"):
        if char_upload is not None:
            _apply_uploaded_reference(char_upload, preprod / "character_options" / f"uploaded_{char_upload.name}")
        if style_upload is not None:
            _apply_uploaded_reference(style_upload, preprod / "style_options" / f"uploaded_{style_upload.name}")
        if cover_upload is not None:
            _apply_uploaded_reference(cover_upload, preprod / "cover_options" / f"uploaded_{cover_upload.name}")
        st.success("Uploaded references copied into preprod option folders.")


def _render_approval_gate() -> None:
    st.header("3) Human Approval Gate")
    out_dir = Path(st.session_state["out_dir"])
    paths = _preprod_paths(out_dir)
    if not paths["approval"].exists():
        st.info("Run preprod first.")
        return

    approval = read_json(paths["approval"])
    layout_options = read_json(paths["layout_options"]) if paths["layout_options"].exists() else {}

    st.json(approval)
    variants = sorted([int(p.name[1:]) for p in (paths["preprod"] / "bible_variants").glob("v*") if p.name[1:].isdigit()])
    approval["approved_variant"] = st.selectbox("approved_variant", options=variants or [1], index=max(0, (variants.index(int(approval.get("approved_variant", 1))) if variants else 0)))

    char_files = [p.name for p in list_files(paths["preprod"] / "character_options", "*.png")]
    style_files = [p.name for p in list_files(paths["preprod"] / "style_options", "*.png")]
    cover_files = [p.name for p in list_files(paths["preprod"] / "cover_options", "*.png")]

    def _pick(label: str, options: List[str], current: str) -> str:
        if not options:
            return current
        idx = options.index(current) if current in options else 0
        return st.selectbox(label, options=options, index=idx)

    approval["approved_character"] = _pick("approved_character", char_files, approval.get("approved_character", ""))
    approval["approved_style"] = _pick("approved_style", style_files, approval.get("approved_style", ""))
    approval["approved_cover"] = _pick("approved_cover", cover_files, approval.get("approved_cover", ""))

    for key, section in [
        ("interior_layout_preset", "interior_layout_presets"),
        ("typography_preset", "typography_presets"),
        ("cover_layout_preset", "cover_layout_presets"),
    ]:
        options = [item.get("id") for item in layout_options.get(section, []) if item.get("id")]
        if options:
            approval[key] = _pick(key, options, str(approval.get(key, options[0])))

    for k in ["page_variants", "image_steps", "max_regen_rounds", "checkpoint_pages", "spread_mode", "crop_mode", "pdf_image_embed", "pdf_jpeg_quality", "director_grade_enabled"]:
        if k not in approval:
            continue
        v = approval[k]
        if isinstance(v, bool):
            approval[k] = st.checkbox(k, value=v)
        elif isinstance(v, int):
            approval[k] = st.number_input(k, value=v)
        elif isinstance(v, float):
            approval[k] = st.number_input(k, value=float(v), format="%.4f")
        else:
            approval[k] = st.text_input(k, value=str(v))

    if st.button("Save APPROVAL.json"):
        write_json(paths["approval"], approval)
        st.success("Saved APPROVAL.json")

    if st.button("Approve + Run Lock"):
        approval["approved"] = True
        write_json(paths["approval"], approval)
        result = run_bookforge_command("lock", out=str(out_dir), size=st.session_state["size"], pages=int(st.session_state["pages"]))
        _show_command_output(result)
        if result.get("ok") and paths["lock"].exists():
            _open_button(paths["lock"], "Open")


def _render_studio() -> None:
    st.header("4) Studio")
    out_dir = Path(st.session_state["out_dir"])
    story_path = st.session_state.get("story_path")

    if st.button("Run Studio"):
        result = run_bookforge_command(
            "studio",
            story=story_path,
            out=str(out_dir),
            size=st.session_state["size"],
            pages=int(st.session_state["pages"]),
            illustrator="fal",
            require_lock=True,
        )
        st.session_state["studio_result"] = result
        _show_command_output(result)

    result = st.session_state.get("studio_result")
    if result and result.get("json", {}).get("status") == "STOPPED_CHECKPOINT":
        checkpoint_pdf = out_dir / "checkpoint" / "first_pages_contact_sheet.pdf"
        if checkpoint_pdf.exists():
            _open_button(checkpoint_pdf, "Open")

        checkpoint_file = out_dir / "CHECKPOINT.json"
        checkpoint = read_json(checkpoint_file) if checkpoint_file.exists() else {"approved": False, "notes": "", "overrides": {}}

        checkpoint["approved"] = st.checkbox("checkpoint.approved", value=bool(checkpoint.get("approved", False)))
        checkpoint["notes"] = st.text_area("checkpoint.notes", value=str(checkpoint.get("notes", "")))
        raw_overrides = st.text_area("checkpoint.overrides (JSON)", value=json.dumps(checkpoint.get("overrides", {}), indent=2), height=120)
        try:
            checkpoint["overrides"] = json.loads(raw_overrides)
        except json.JSONDecodeError:
            st.error("checkpoint.overrides must be valid JSON")

        if st.button("Save CHECKPOINT.json"):
            write_json(checkpoint_file, checkpoint)
            st.success("Saved CHECKPOINT.json")

        if st.button("Approve checkpoint and Continue Studio"):
            checkpoint["approved"] = True
            write_json(checkpoint_file, checkpoint)
            rerun = run_bookforge_command(
                "studio",
                story=story_path,
                out=str(out_dir),
                size=st.session_state["size"],
                pages=int(st.session_state["pages"]),
                illustrator="fal",
                require_lock=True,
            )
            st.session_state["studio_result"] = rerun
            _show_command_output(rerun)


def _render_verify() -> None:
    st.header("5) Verify + Outputs")
    out_dir = Path(st.session_state["out_dir"])
    if st.button("Run Verify"):
        result = run_bookforge_command("verify", out=str(out_dir))
        st.session_state["verify_result"] = result
        _show_command_output(result)

    verify_result = st.session_state.get("verify_result", {})
    parsed = verify_result.get("json") or {}
    if parsed:
        st.subheader(f"Status: {parsed.get('status', 'UNKNOWN')}")
        if parsed.get("remediation"):
            st.warning(parsed.get("remediation"))

    for rel in ["review/report.html", "review/proof_pack.pdf", "review/quality_summary.md", "bookforge_package.zip"]:
        path = out_dir / rel
        if path.exists():
            _open_button(path, "Open")


def main() -> None:
    st.set_page_config(page_title="BookForge Local UI", layout="wide")
    _init_state()
    _inject_css()
    st.title("BookForge Pipeline UI")
    st.caption("Local-only control plane for doctor → preprod → approval → lock → studio → checkpoint → verify")

    _render_setup()
    _render_preprod()
    _render_approval_gate()
    _render_studio()
    _render_verify()


if __name__ == "__main__":
    main()
