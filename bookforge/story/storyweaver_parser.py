from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

PAGE_HEADER_RE = re.compile(r"^\[Pages?\s+(\d+)(?:\s*[\-\u2013\u2014]\s*(\d+))?\](.*)$", re.IGNORECASE)
BLOCK_HEADER_RE = re.compile(r"^\[(Pages?\s+\d+(?:\s*[\-\u2013\u2014]\s*\d+)?|Back Endpaper)\]\s*(.*)$", re.IGNORECASE)
ILLUSTRATION_RE = re.compile(r"\[ILLUSTRATION NOTE:(.*?)\]", re.IGNORECASE | re.DOTALL)
PAGE_TURN_RE = re.compile(r"(\[PAGE TURN[^\]]*\])", re.IGNORECASE)


@dataclass
class PageSpec:
    page_number: int
    printed_markdown: str = ""
    illustration_notes: str = ""
    page_turn_marker: str | None = None
    typography_directives: List[Dict[str, Any]] = field(default_factory=list)
    required_hidden_details: List[str] = field(default_factory=list)


@dataclass
class ManuscriptBundle:
    title: str
    author: str
    declared_pages: int
    pages: List[PageSpec]
    spreads: List[Tuple[int, int]]
    extras: Dict[str, str]
    tagline_quote: str = ""
    one_sentence_pitch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["pages"] = [asdict(p) for p in self.pages]
        return out


def detect_storyweaver_format(text: str) -> bool:
    return bool(re.search(r"\[Pages?\s+\d+(?:\s*[\-\u2013\u2014]\s*\d+)?\]", text, re.IGNORECASE))


def _extract_typography(printed_markdown: str, illustration_notes: str) -> List[Dict[str, Any]]:
    directives: List[Dict[str, Any]] = []
    for line in printed_markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            directives.append({"type": "display_word", "text": stripped[2:].strip(), "scale": "huge", "placement": "bottom_third_if_spread_else_panel"})
        if "&nbsp;" in line or re.search(r"\b\w\s{2,}\w", line):
            directives.append({"type": "spaced_words", "raw_fragment": line.rstrip()})
    note = illustration_notes.lower()
    if "typography" in note and "spaced across" in note:
        directives.append({"type": "spaced_words", "raw_fragment": illustration_notes.strip()})
    if "word 'sleep'" in note or 'word "sleep"' in note:
        directives.append({"type": "micro_word", "text": "sleep", "style": "tiny_drift_down"})
    return directives


def _extract_hidden_details(note_text: str) -> List[str]:
    found = re.findall(r"Hidden detail:\s*(.*?)(?:\n|$)", note_text, flags=re.IGNORECASE)
    return [x.strip(" .") for x in found if x.strip()]


def _section_text_map(raw: str) -> Dict[str, str]:
    section_re = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)
    hits = list(section_re.finditer(raw))
    out: Dict[str, str] = {}
    for i, hit in enumerate(hits):
        name = hit.group(1).strip()
        start = hit.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(raw)
        out[name.lower()] = raw[start:end].strip()
    return out


def parse_storyweaver_markdown(path_or_text: str | Path) -> ManuscriptBundle:
    if isinstance(path_or_text, Path):
        raw = path_or_text.read_text(encoding="utf-8")
    else:
        candidate = str(path_or_text)
        if "\n" not in candidate and Path(candidate).exists():
            raw = Path(candidate).read_text(encoding="utf-8")
        else:
            raw = candidate
    lines = raw.splitlines()

    title = "Untitled"
    for ln in lines:
        if ln.strip().startswith("# "):
            title = ln.strip()[2:].strip()
            break
    if title == "Untitled":
        for ln in lines:
            if ln.strip() and ln.strip().upper() == ln.strip() and len(ln.strip()) > 3:
                title = ln.strip()
                break

    author = "Internal Studio"
    m_author = re.search(r"^\s*Written by\s+(.+)$", raw, re.IGNORECASE | re.MULTILINE)
    if m_author:
        author = m_author.group(1).strip()

    pages_by_no: Dict[int, PageSpec] = {}
    spreads: set[Tuple[int, int]] = set()
    extras: Dict[str, str] = {"story_data_block": "", "readaloud_notes": "", "parents_companion": "", "developmental_architecture": "", "commercial_architecture_alignment": "", "the_line_that_sells_the_book": "", "back_endpaper": ""}

    marker_idx = [i for i, ln in enumerate(lines) if BLOCK_HEADER_RE.match(ln.strip())]
    marker_idx.append(len(lines))
    for idx in range(len(marker_idx) - 1):
        start, end = marker_idx[idx], marker_idx[idx + 1]
        head = lines[start].strip()
        m_page = PAGE_HEADER_RE.match(head)
        block_text = "\n".join(lines[start + 1 : end]).strip("\n")
        if m_page:
            p1 = int(m_page.group(1))
            p2 = int(m_page.group(2) or p1)
            tail = (m_page.group(3) or "").strip()
            if p2 == p1 + 1 or "FULL DOUBLE-PAGE SPREAD" in tail.upper():
                spreads.add((p1, p1 + 1))
            notes = "\n\n".join(x.strip() for x in ILLUSTRATION_RE.findall(block_text) if x.strip())
            turn_markers = PAGE_TURN_RE.findall(block_text)
            stripped = ILLUSTRATION_RE.sub("", block_text)
            stripped = PAGE_TURN_RE.sub("", stripped).strip()
            directives = _extract_typography(stripped, notes)
            hidden = _extract_hidden_details(notes)
            for pno in range(p1, p2 + 1):
                pages_by_no[pno] = PageSpec(
                    page_number=pno,
                    printed_markdown=stripped,
                    illustration_notes=notes,
                    page_turn_marker=(turn_markers[-1] if turn_markers else None),
                    typography_directives=directives,
                    required_hidden_details=hidden,
                )
        elif "back endpaper" in head.lower():
            extras["back_endpaper"] = block_text

    declared_pages = max(pages_by_no.keys()) if pages_by_no else 0
    pages = [pages_by_no.get(i, PageSpec(page_number=i, printed_markdown="")) for i in range(1, declared_pages + 1)]

    sections = _section_text_map(raw)
    mapping = {
        "story data": "story_data_block",
        "read-aloud notes": "readaloud_notes",
        "parent companion": "parents_companion",
        "parent's companion": "parents_companion",
        "developmental architecture": "developmental_architecture",
        "commercial architecture alignment": "commercial_architecture_alignment",
        "the line that sells the book": "the_line_that_sells_the_book",
    }
    for k, v in mapping.items():
        if k in sections:
            extras[v] = sections[k]

    tagline_quote = ""
    if extras["the_line_that_sells_the_book"]:
        q = re.search(r"^>\s*(.+)$", extras["the_line_that_sells_the_book"], flags=re.MULTILINE)
        if q:
            tagline_quote = q.group(1).strip()
    m_pitch = re.search(r"One-sentence pitch:\s*(.+)$", raw, flags=re.IGNORECASE | re.MULTILINE)
    one_sentence_pitch = m_pitch.group(1).strip() if m_pitch else ""

    return ManuscriptBundle(
        title=title,
        author=author,
        declared_pages=declared_pages,
        pages=pages,
        spreads=sorted(spreads),
        extras=extras,
        tagline_quote=tagline_quote,
        one_sentence_pitch=one_sentence_pitch,
    )
