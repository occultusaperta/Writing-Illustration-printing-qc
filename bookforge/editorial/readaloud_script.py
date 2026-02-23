from __future__ import annotations

from typing import Any, Dict, List


def generate_readaloud_script(pages: List[Dict[str, Any]], rhythm_report: Dict[str, Any], page_turn_map: List[Dict[str, Any]]) -> str:
    turn_by_page = {int(x["page_number"]): x for x in page_turn_map}
    flagged = {int(x.get("line", -1)): x for x in rhythm_report.get("flagged_lines", []) if isinstance(x.get("line"), int)}

    lines = ["# Read-Aloud Performance Script", ""]
    for page in pages:
        pno = int(page.get("page_number", 0))
        txt = str(page.get("text", "")).strip()
        turn = turn_by_page.get(pno, {})
        lines.append(f"## Page {pno}")
        lines.append(f"Text: {txt}")
        lines.append("Direction: pause after the first sentence; stress the last five words.")
        if pno in flagged:
            lines.append("Fatigue note: slow pacing and add breath pause.")
        lines.append(f"Turn cue: whisper '{turn.get('page_turn_phrase', '...until the next page.')}'")
        lines.append("Participation: repeat catchphrase once and invite child response.")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
