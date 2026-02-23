from __future__ import annotations

from typing import Any, Dict, List


def build_page_turn_map(parsed_story_pages: List[Dict[str, Any]], age_band: str) -> List[Dict[str, Any]]:
    pages = sorted(parsed_story_pages, key=lambda p: int(p.get("page_number", 0)))
    out: List[Dict[str, Any]] = []
    for idx, page in enumerate(pages):
        current_text = str(page.get("text") or page.get("summary") or "").strip()
        next_text = str(pages[idx + 1].get("text") if idx + 1 < len(pages) else "final emotional beat").strip()
        hook = f"What changes next for this moment: {current_text[:80]}" if current_text else "What happens after this beat?"
        payoff = next_text[:110] if next_text else "A gentle reveal on the next page."
        phrase = "...until the page turns." if age_band in {"3-5", "6-8"} else "...but that is only half the story."
        out.append(
            {
                "page_number": int(page.get("page_number", idx + 1)),
                "recto_hook": hook,
                "verso_payoff": payoff,
                "page_turn_phrase": phrase,
            }
        )
    return out
