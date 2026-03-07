from __future__ import annotations

import re
from typing import List

from bookforge.typography.types import TypographyDirective


PAGE_TURN_RE = re.compile(r"\[PAGE TURN[^\]]*\]", re.IGNORECASE)
EMPHASIS_RE = re.compile(r"\*\*([^*]+)\*\*|\*([^*]+)\*")
ALL_CAPS_RE = re.compile(r"\b[A-Z]{3,}\b")


def preserve_exact_printed_markdown(markdown_text: str) -> str:
    return str(markdown_text)


def extract_storyweaver_typography_directives(markdown_text: str, illustration_notes: str = "") -> List[TypographyDirective]:
    directives: List[TypographyDirective] = []
    clean = preserve_exact_printed_markdown(markdown_text)
    lines = clean.splitlines()

    for idx, line in enumerate(lines):
        stripped = line.rstrip()
        bare = stripped.strip()
        if not bare:
            continue

        if bare.startswith("#"):
            heading_text = bare.lstrip("#").strip()
            if heading_text:
                directives.append(
                    TypographyDirective(
                        kind="heading",
                        text=heading_text,
                        role="title_dramatic",
                        line_index=idx,
                        strength=0.95,
                        metadata={"markdown_heading": True},
                    )
                )

        for match in EMPHASIS_RE.finditer(stripped):
            token = (match.group(1) or match.group(2) or "").strip()
            if token:
                directives.append(
                    TypographyDirective(
                        kind="markdown_emphasis",
                        text=token,
                        role="emphasis",
                        line_index=idx,
                        strength=0.75,
                    )
                )

        for token in ALL_CAPS_RE.findall(bare):
            directives.append(
                TypographyDirective(
                    kind="all_caps",
                    text=token,
                    role="sound_effect",
                    line_index=idx,
                    strength=0.88,
                )
            )

        if "&nbsp;" in stripped or re.search(r"\w\s{2,}\w", stripped):
            directives.append(
                TypographyDirective(
                    kind="pause_spacing",
                    text=stripped,
                    role="pause_gap",
                    line_index=idx,
                    strength=0.62,
                )
            )

        compact = re.sub(r"[^a-z]", "", bare.lower())
        if idx == len(lines) - 1 and compact and len(compact) <= 8 and bare.lower() == bare:
            directives.append(
                TypographyDirective(
                    kind="tiny_trailing",
                    text=bare,
                    role="whisper",
                    line_index=idx,
                    strength=0.7,
                )
            )

    if PAGE_TURN_RE.search(markdown_text):
        directives.append(
            TypographyDirective(
                kind="page_turn_marker",
                text="PAGE TURN",
                role="directional",
                line_index=max(0, len(lines) - 1),
                strength=0.45,
                metadata={"structural_only": True},
            )
        )

    note = illustration_notes.lower()
    if "typography" in note and "spaced" in note:
        directives.append(
            TypographyDirective(
                kind="note_spacing",
                text=illustration_notes.strip(),
                role="pause_gap",
                line_index=0,
                strength=0.55,
            )
        )
    if "word 'sleep'" in note or 'word "sleep"' in note:
        directives.append(
            TypographyDirective(
                kind="note_micro_word",
                text="sleep",
                role="whisper",
                line_index=max(0, len(lines) - 1),
                strength=0.72,
            )
        )

    return directives
