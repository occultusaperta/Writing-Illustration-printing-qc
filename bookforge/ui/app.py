from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from bookforge.ui.utils import (
    discover_profiles,
    estimate_fal_calls,
    list_files,
    open_in_system_viewer,
    read_certification_markdown,
    read_json,
    run_bookforge_command,
    save_story_text,
    scan_run_history,
    write_json,
    write_overrides_json,
)

ROOT = Path.cwd()
CSS_PATH = Path(__file__).with_name("style.css")
MAX_PROFILE = "ultimate_imprint_8p5x8p5_image_heavy_MAX"


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
        "max_quality": False,
        "assume_spreads": False,
        "expected_regen_rate": 0.25,
        "avg_regen_rounds": 1,
        "active_proc": None,
        "cancel_requested": False,
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


def _download_button(path: Path, label: str) -> None:
    if path.exists():
        st.download_button(label, data=path.read_bytes(), file_name=path.name, key=f"dl-{path}")


def _show_command_output(result: Dict[str, Any]) -> None:
    st.code(" ".join(result["command"]), language="bash")
    if result.get("cancelled"):
        st.warning("Run cancelled by user.")
    if result["stdout"]:
        st.text_area("stdout", value=result["stdout"], height=180)
    if result["stderr"]:
        st.text_area("stderr", value=result["stderr"], height=100)
    if result["json"]:
        st.json(result["json"])


def _run_command(command: str, **kwargs: Any) -> Dict[str, Any]:
    logs = st.empty()

    def _update_logs(output: str) -> None:
        logs.text_area("Live logs", value=output[-12000:], height=180)

    return run_bookforge_command(command, cancellable=True, session_state=st.session_state, log_callback=_update_logs, **kwargs)


def _preprod_paths(out_dir: Path) -> Dict[str, Path]:
    preprod = out_dir / "preprod"
    return {
        "preprod": preprod,
        "approval": preprod / "APPROVAL.json",
        "layout_options": preprod / "layout_options.json",
        "lock": out_dir / "LOCK.json",
        "checkpoint": out_dir / "CHECKPOINT.json",
        "editorial_dir": preprod / "editorial",
        "artifact_options": preprod / "editorial" / "artifact_plan_options.json",
        "editorial_report": preprod / "editorial" / "editorial_report.md",
        "readaloud": preprod / "editorial" / "readaloud_script.md",
        "hook_pack": preprod / "editorial" / "hook_pack.json",
        "dual_address": preprod / "editorial" / "dual_address.json",
    }


def _render_cancel_button() -> None:
    active = st.session_state.get("active_proc")
    if active is not None and active.poll() is None:
        if st.button("Cancel current run"):
            st.session_state["cancel_requested"] = True
            st.warning("Cancellation requested. Waiting for process to terminate...")


def _render_setup() -> None:
    st.header("1) Setup")
    st.session_state["project_name"] = st.text_input("Project name", value=st.session_state["project_name"])
    st.session_state["out_dir"] = f"dist/{st.session_state['project_name']}"
    out_dir = Path(st.session_state["out_dir"])
    st.caption(f"Output folder: {out_dir}")

    upload = st.file_uploader("Upload story (.md/.txt)", type=["md", "txt"])
    st.session_state["story_text"] = st.text_area("Or paste story text", value=st.session_state["story_text"], height=180)

    if upload is not None:
        story_path = out_dir / "story_input.md"
        story_path.parent.mkdir(parents=True, exist_ok=True)
        story_path.write_bytes(upload.getbuffer())
        st.session_state["story_path"] = str(story_path)
        st.success(f"Saved uploaded story to {story_path}")

    if st.button("Save pasted text to story_input.md") and st.session_state["story_text"].strip():
        story_path = save_story_text(st.session_state["story_text"], out_dir)
        st.session_state["story_path"] = str(story_path)
        st.success(f"Saved story to {story_path}")

    profiles = discover_profiles()
    max_quality = st.checkbox("Max Quality (slower)", value=st.session_state["max_quality"])
    st.session_state["max_quality"] = max_quality
    if max_quality:
        st.warning("MAX increases Fal calls (cost/time). Use estimator.")

    if max_quality and MAX_PROFILE in profiles:
        st.session_state["profile"] = MAX_PROFILE

    options = profiles or [st.session_state["profile"]]
    idx = options.index(st.session_state["profile"]) if st.session_state["profile"] in options else 0
    st.session_state["profile"] = st.selectbox("Profile", options=options, index=idx)

    c1, c2, c3 = st.columns(3)
    st.session_state["size"] = c1.text_input("Trim size", value=st.session_state["size"])
    st.session_state["pages"] = c2.number_input("Pages", min_value=8, step=2, value=int(st.session_state["pages"]))
    st.session_state["variants"] = c3.number_input("Variants", min_value=1, max_value=8, value=int(st.session_state["variants"]))

    if st.button("Run Doctor (strict)"):
        result = _run_command("doctor", strict=True)
        st.session_state["doctor_result"] = result
        _show_command_output(result)


def _apply_max_fallback_if_needed(approval: Dict[str, Any]) -> Dict[str, Any]:
    if not st.session_state.get("max_quality"):
        return approval
    if st.session_state.get("profile") == MAX_PROFILE:
        return approval

    approval["page_variants"] = 4
    approval["image_steps"] = 12
    approval["max_regen_rounds"] = 4
    approval["checkpoint_pages"] = 2
    approval["spread_mode"] = "every_4"
    approval["crop_mode"] = "smart"
    if isinstance(approval.get("metadata"), dict):
        approval["metadata"]["max_words_per_page"] = 24
    return approval


def _render_checklist(where: str) -> None:
    st.subheader(f"Publisher Checklist ({where})")
    cert_text = read_certification_markdown(ROOT)
    with st.expander("CERTIFICATION.md"):
        if cert_text is None:
            st.warning("CERTIFICATION.md missing at repository root.")
        else:
            st.markdown(cert_text)

    items = [
        "Doctor strict PASS",
        "Preprod reviewed",
        "Approval selected (approved=true)",
        "Lock created",
        "Checkpoint approved (if used)",
        "Studio completed",
        "Verify PASS/WARN (not FAIL)",
        "Reviewed: report.html, proof_pack.pdf, quality_summary.md",
    ]
    for item in items:
        key = f"checklist::{where}::{item}"
        st.checkbox(item, key=key)


def _render_run_history() -> None:
    st.subheader("Run History")
    runs = scan_run_history("dist")
    if not runs:
        st.caption("No prior completed runs found in dist/*")
        return

    for run in runs:
        card = st.container(border=True)
        with card:
            st.markdown(f"**{run['run_name']}** · preflight: `{run['preflight_status']}`")
            for key, label in [("report", "Open report.html"), ("proof_pack", "Open proof_pack.pdf"), ("package", "Open bookforge_package.zip"), ("quality_summary", "Open quality_summary.md")]:
                p = Path(run[key])
                if p.exists():
                    _open_button(p, label)


def _render_estimator(approval: Dict[str, Any], out_dir: Path) -> None:
    st.subheader("Estimator")
    max_rounds = int(approval.get("max_regen_rounds", 4))
    st.session_state["expected_regen_rate"] = st.slider("expected_regen_rate", 0.0, 0.8, float(st.session_state["expected_regen_rate"]), 0.01)
    st.session_state["avg_regen_rounds"] = st.slider("avg_regen_rounds", 0, max_rounds, int(st.session_state["avg_regen_rounds"]), 1)
    st.session_state["assume_spreads"] = st.checkbox("assume spreads", value=bool(st.session_state["assume_spreads"]))

    spread_mode = str(approval.get("spread_mode", "none"))
    pages = int(st.session_state["pages"])
    num_spreads = pages // 4 if (st.session_state["assume_spreads"] or spread_mode != "none") else 0

    estimate = estimate_fal_calls(
        pages=pages,
        page_variants=int(approval.get("page_variants", st.session_state["variants"])),
        num_spreads=num_spreads,
        expected_regen_rate=float(st.session_state["expected_regen_rate"]),
        avg_regen_rounds=float(st.session_state["avg_regen_rounds"]),
    )
    st.info(f"Approx Fal calls — low: {estimate['low']} · likely: {estimate['likely']} · high: {estimate['high']}")


def _render_preprod() -> None:
    st.header("2) Preprod")
    out_dir = Path(st.session_state["out_dir"])
    story_path = st.session_state.get("story_path")
    _render_cancel_button()

    if st.button("Run Preprod"):
        if not story_path:
            st.error("Provide a story first.")
        else:
            result = _run_command(
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

    _render_run_history()
    if (out_dir / "preprod").exists():
        _render_checklist("post-preprod")


def _render_approval_gate() -> None:
    st.header("3) Human Approval Gate")
    out_dir = Path(st.session_state["out_dir"])
    paths = _preprod_paths(out_dir)
    if not paths["approval"].exists():
        st.info("Run preprod first.")
        return

    approval = _apply_max_fallback_if_needed(read_json(paths["approval"]))
    layout_options = read_json(paths["layout_options"]) if paths["layout_options"].exists() else {}

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

    approval["age_band"] = st.selectbox("age_band", options=["3-5", "6-8", "7-12", "custom"], index=["3-5", "6-8", "7-12", "custom"].index(str(approval.get("age_band", "6-8")) if str(approval.get("age_band", "6-8")) in {"3-5", "6-8", "7-12", "custom"} else "6-8"))
    approval["editorial_mode"] = st.checkbox("editorial_mode", value=bool(approval.get("editorial_mode", True)))
    approval["artifact_intensity"] = st.selectbox("artifact_intensity", options=["light", "medium", "high"], index=["light", "medium", "high"].index(str(approval.get("artifact_intensity", "light")) if str(approval.get("artifact_intensity", "light")) in {"light", "medium", "high"} else "light"))
    approval["readaloud_script_enabled"] = st.checkbox("readaloud_script_enabled", value=bool(approval.get("readaloud_script_enabled", True)))
    approval["trade_dress_lock_enabled"] = st.checkbox("trade_dress_lock_enabled", value=bool(approval.get("trade_dress_lock_enabled", True)))
    artifact_options_path = paths.get("artifact_options")
    if artifact_options_path and artifact_options_path.exists():
        plans = read_json(artifact_options_path).get("plans", [])
        ids = [p.get("plan_id") for p in plans if p.get("plan_id")]
        if ids:
            cur = str(approval.get("artifact_plan_id", ids[0]))
            approval["artifact_plan_id"] = st.selectbox("artifact_plan_id", options=ids, index=ids.index(cur) if cur in ids else 0)

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

    _render_estimator(approval, out_dir)

    if paths.get("editorial_report") and paths["editorial_report"].exists():
        _open_button(paths["editorial_report"], "Open editorial_report.md")
    if paths.get("readaloud") and paths["readaloud"].exists():
        _open_button(paths["readaloud"], "Open readaloud_script.md")
    if paths.get("hook_pack") and paths["hook_pack"].exists():
        hp = read_json(paths["hook_pack"])
        st.info(f"Premise: {hp.get('one_sentence_premise','n/a')}\n\nPitch: {hp.get('15_second_pitch','n/a')}")
    if paths.get("dual_address") and paths["dual_address"].exists():
        da = read_json(paths["dual_address"])
        risk = float(da.get("read_aloud_fatigue_risk", {}).get("score", 0.0) or 0.0)
        if risk >= 0.6:
            st.warning("High read-aloud fatigue risk detected in editorial analysis.")

    if st.button("Save APPROVAL.json"):
        write_json(paths["approval"], approval)
        st.success("Saved APPROVAL.json")

    if st.button("Approve + Run Lock"):
        approval["approved"] = True
        write_json(paths["approval"], approval)
        result = _run_command("lock", out=str(out_dir), size=st.session_state["size"], pages=int(st.session_state["pages"]))
        st.session_state["lock_result"] = result
        _show_command_output(result)


def _render_worst_pages(out_dir: Path) -> None:
    qa_path = out_dir / "review" / "qa_report.json"
    if not qa_path.exists():
        return
    qa = read_json(qa_path)
    pages = qa.get("pages", [])
    if not isinstance(pages, list) or not pages:
        return
    sorted_pages = sorted(pages, key=lambda p: float(p.get("score", 999.0)))[:10]
    st.subheader("Worst Pages")
    rows = []
    for page in sorted_pages:
        reasons = []
        for key in ["integrity_flags", "drift", "contrast_warning", "brightness_warning", "focus_overlap"]:
            value = page.get(key)
            if value:
                reasons.append(f"{key}:{value}")
        rows.append({"page": page.get("page"), "score": page.get("score"), "passes": page.get("passes"), "main_reasons": "; ".join(reasons)})
    st.dataframe(rows, use_container_width=True)

    overrides: Dict[str, Any] = {"variant_preference": {}}
    variants = list(range(1, int(st.session_state["variants"]) + 1))
    for row in rows:
        page_num = str(row["page"])
        overrides["variant_preference"][page_num] = st.selectbox(f"Preferred variant for page {page_num}", options=variants, key=f"ovr-{page_num}")

    if st.button("Save OVERRIDES.json"):
        write_overrides_json(out_dir, overrides)
        st.success("OVERRIDES.json saved")

    if st.button("Re-run Studio using OVERRIDES"):
        write_overrides_json(out_dir, overrides)
        result = _run_command(
            "studio",
            story=st.session_state.get("story_path"),
            out=str(out_dir),
            size=st.session_state["size"],
            pages=int(st.session_state["pages"]),
            illustrator="fal",
            require_lock=True,
        )
        st.session_state["studio_result"] = result
        _show_command_output(result)


def _render_checkpoint_ui(out_dir: Path) -> None:
    st.error("Checkpoint gate reached")
    checkpoint_pdf = out_dir / "checkpoint" / "first_pages_contact_sheet.pdf"
    if checkpoint_pdf.exists():
        _open_button(checkpoint_pdf, "Open first_pages_contact_sheet.pdf")

    checkpoint_file = out_dir / "CHECKPOINT.json"
    checkpoint = read_json(checkpoint_file) if checkpoint_file.exists() else {"approved": False, "notes": "", "overrides": {}}
    overrides = checkpoint.get("overrides", {})

    checkpoint["approved"] = st.checkbox("checkpoint.approved", value=bool(checkpoint.get("approved", False)))
    checkpoint["notes"] = st.text_area("checkpoint.notes", value=str(checkpoint.get("notes", "")))

    fields = {
        "page_prompt_addendum": overrides.get("page_prompt_addendum", {}),
        "force_regen": overrides.get("force_regen", []),
        "variant_preference": overrides.get("variant_preference", {}),
    }
    parsed: Dict[str, Any] = {}
    for key, value in fields.items():
        raw = st.text_area(f"checkpoint.overrides.{key} (JSON)", value=json.dumps(value, indent=2), height=120)
        try:
            parsed[key] = json.loads(raw)
        except json.JSONDecodeError:
            st.error(f"{key} must be valid JSON")
            return

    checkpoint["overrides"] = parsed
    if st.button("Save CHECKPOINT.json"):
        write_json(checkpoint_file, checkpoint)
        st.success("Saved CHECKPOINT.json")

    if st.button("Approve checkpoint and Continue Studio"):
        checkpoint["approved"] = True
        write_json(checkpoint_file, checkpoint)
        rerun = _run_command(
            "studio",
            story=st.session_state.get("story_path"),
            out=str(out_dir),
            size=st.session_state["size"],
            pages=int(st.session_state["pages"]),
            illustrator="fal",
            require_lock=True,
        )
        st.session_state["studio_result"] = rerun
        _show_command_output(rerun)


def _render_studio() -> None:
    st.header("4) Studio")
    out_dir = Path(st.session_state["out_dir"])
    _render_cancel_button()

    if st.button("Run Studio"):
        result = _run_command(
            "studio",
            story=st.session_state.get("story_path"),
            out=str(out_dir),
            size=st.session_state["size"],
            pages=int(st.session_state["pages"]),
            illustrator="fal",
            require_lock=True,
        )
        st.session_state["studio_result"] = result
        _show_command_output(result)

    result = st.session_state.get("studio_result") or {}
    if result.get("json", {}).get("status") == "STOPPED_CHECKPOINT":
        _render_checkpoint_ui(out_dir)

    _render_worst_pages(out_dir)


def _render_verify() -> None:
    st.header("5) Verify + Outputs")
    out_dir = Path(st.session_state["out_dir"])
    _render_checklist("pre-verify")
    if st.button("Run Verify"):
        result = _run_command("verify", out=str(out_dir))
        st.session_state["verify_result"] = result
        _show_command_output(result)

    verify_result = st.session_state.get("verify_result", {})
    parsed = verify_result.get("json") or {}
    if parsed:
        st.subheader(f"Status: {parsed.get('status', 'UNKNOWN')}")
        if parsed.get("status") in {"WARN", "FAIL"} and parsed.get("remediation"):
            st.warning(parsed.get("remediation"))

    if st.button("Open output folder"):
        open_in_system_viewer(out_dir)

    artifacts = ["review/report.html", "review/proof_pack.pdf", "review/quality_summary.md", "review/production_report.json", "bookforge_package.zip"]
    for rel in artifacts:
        path = out_dir / rel
        if path.exists():
            _open_button(path, "Open")
            if path.name == "bookforge_package.zip":
                _download_button(path, "Download bookforge_package.zip")


def main() -> None:
    st.set_page_config(page_title="BookForge Local UI", layout="wide")
    _init_state()
    _inject_css()
    st.title("BookForge Pipeline UI")
    st.caption("Local-only control plane for doctor → preprod → approval → lock → studio → checkpoint → verify")
    st.info("OpenAI image provider disabled; Fal/Flux only.")

    _render_setup()
    _render_preprod()
    _render_approval_gate()
    _render_studio()
    _render_verify()


if __name__ == "__main__":
    main()
