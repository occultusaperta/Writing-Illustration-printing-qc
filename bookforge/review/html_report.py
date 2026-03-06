from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image


def _thumb(src: Path, dst: Path, max_w: int = 320) -> None:
    with Image.open(src) as im:
        rgb = im.convert("RGB")
        ratio = max_w / max(1, rgb.width)
        h = max(1, int(rgb.height * ratio))
        rgb.resize((max_w, h), Image.Resampling.LANCZOS).save(dst, "JPEG", quality=85)


def generate_report(out_dir: Path, selected_pages: List[Path], qa_report: Dict[str, Any], production_report: Dict[str, Any], cover_path: Path) -> Path:
    review = out_dir / "review"
    thumbs = review / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)

    _thumb(cover_path, thumbs / "cover.jpg")
    for i, page in enumerate(selected_pages, start=1):
        _thumb(page, thumbs / f"page_{i:03d}.jpg")

    attempts = qa_report.get("attempts", [])
    by_page = {}
    for row in attempts:
        if isinstance(row.get("page"), int):
            by_page[row["page"]] = row.get("best", {})

    worst = production_report.get("drift", {}).get("top_pages", [])
    regen = [k for k, v in production_report.get("regen_counts", {}).items() if int(v) > 1]
    cache_rate = production_report.get("cache_hit_rate", 0.0)

    hook_pack = {}
    dual_address = {}
    artifact_map = []
    companion_links: List[str] = []
    if (review / "hook_pack.json").exists():
        hook_pack = json.loads((review / "hook_pack.json").read_text(encoding="utf-8"))
    if (out_dir / "preprod" / "editorial" / "dual_address.json").exists():
        dual_address = json.loads((out_dir / "preprod" / "editorial" / "dual_address.json").read_text(encoding="utf-8"))
    if (review / "hidden_artifacts_map.json").exists():
        artifact_map = json.loads((review / "hidden_artifacts_map.json").read_text(encoding="utf-8"))
    companion_dir = review / "companion"
    if companion_dir.exists():
        companion_links = [f"companion/{p.name}" for p in sorted(companion_dir.glob("*.md"))]

    fatigue = dual_address.get("read_aloud_fatigue_risk", {})
    rows = []
    for i, page in enumerate(selected_pages, start=1):
        m = by_page.get(i, {})
        rows.append(
            f"<tr><td>{i}</td><td>{html.escape(Path(str(m.get('path',''))).name)}</td><td>{'PASS' if m else 'N/A'}</td>"
            f"<td>{m.get('sharpness','')}</td><td>{m.get('text_likelihood','')}</td><td>{m.get('style_hist_similarity','')}</td>"
            f"<td>{m.get('page_to_page_hist_drift','')}</td><td>{m.get('brightness_mean','')}</td>"
            f"<td><a href='../images/page_{i:03d}.png'>full</a></td></tr>"
        )

    html_text = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>BookForge Proof Dashboard</title>
<style>body{{font-family:Arial,sans-serif;margin:20px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px;font-size:12px}}th{{background:#f3f3f3}}.grid{{display:flex;gap:8px;flex-wrap:wrap}}.tab{{padding:8px;border:1px solid #ddd;border-radius:8px;margin-bottom:12px}}</style>
</head><body>
<h1>BookForge Static Proof Dashboard</h1>
<div class='tab'>
<h2>Editorial</h2>
<ul>
<li>Premise: {html.escape(hook_pack.get('one_sentence_premise', 'n/a'))}</li>
<li>Pitch: {html.escape(hook_pack.get('15_second_pitch', 'n/a'))}</li>
<li>Dual-address signals: child={len(dual_address.get('child_engagement_signals', []))}, adult={len(dual_address.get('adult_gatekeeper_signals', []))}</li>
<li>Read-aloud fatigue: {fatigue.get('score', 'n/a')} ({html.escape(', '.join(fatigue.get('reasons', [])))})</li>
<li>Artifact plan summary: {len(artifact_map)} per-page cues</li>
</ul>
</div>
<h2>Cover</h2><img src='thumbs/cover.jpg' width='220'>
<h2>QA Table</h2>
<table><thead><tr><th>Page</th><th>Variant</th><th>QA</th><th>Sharpness</th><th>Text</th><th>Style Sim</th><th>Drift</th><th>Brightness</th><th>Link</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table>
<h2>Summary</h2>
<ul>
<li>Worst drift pages: {html.escape(json.dumps(worst))}</li>
<li>Regenerated pages: {html.escape(json.dumps(regen))}</li>
<li>Cache hit rate: {cache_rate:.2%}</li>
<li>Companion artifacts: {html.escape(json.dumps(companion_links))}</li>
</ul>
</body></html>"""

    report = review / "report.html"
    report.write_text(html_text, encoding="utf-8")
    return report
