from __future__ import annotations

from typing import Any, Dict, List

from bookforge.typography.storyweaver import extract_storyweaver_typography_directives
from bookforge.typography.types import PageTypographyPlan, TypographyDirective, TypographyLinePlan, TypographySpan
from bookforge.utils import clamp01


def _text_zone_from_architecture(page_architecture_context: Dict[str, Any] | None) -> Dict[str, float]:
    arch = page_architecture_context if isinstance(page_architecture_context, dict) else {}
    zone = arch.get("text_zone", {"x": 0.08, "y": 0.06, "w": 0.84, "h": 0.22})
    return {
        "x": float(zone.get("x", 0.08)),
        "y": float(zone.get("y", 0.06)),
        "w": float(zone.get("w", 0.84)),
        "h": float(zone.get("h", 0.22)),
    }


def plan_page_typography(
    *,
    page_number: int,
    printed_markdown: str,
    illustration_notes: str = "",
    page_architecture_context: Dict[str, Any] | None = None,
    camera_context: Dict[str, Any] | None = None,
    saliency_context: Dict[str, Any] | None = None,
    color_context: Dict[str, Any] | None = None,
    age_band: str = "6-8",
) -> PageTypographyPlan:
    directives = extract_storyweaver_typography_directives(printed_markdown, illustration_notes)
    text_zone = _text_zone_from_architecture(page_architecture_context)
    camera_context = camera_context if isinstance(camera_context, dict) else {}
    saliency_context = saliency_context if isinstance(saliency_context, dict) else {}
    color_context = color_context if isinstance(color_context, dict) else {}

    style_roles = sorted({d.role for d in directives} | {"body"})
    lines: List[TypographyLinePlan] = []
    source_lines = printed_markdown.splitlines() or [printed_markdown]
    for idx, line in enumerate(source_lines):
        line_role = "body"
        scale_class = "body"
        weight_class = "regular"
        alignment = "center" if camera_context.get("shot_type") in {"closeup_emotion", "extreme_closeup_detail"} else "left"
        gap = 1.0
        spans: List[TypographySpan] = []
        line_directives = [d for d in directives if d.line_index == idx]

        for directive in line_directives:
            role = directive.role
            drift = "none"
            if role == "title_dramatic":
                line_role = role
                scale_class = "xxl"
                weight_class = "bold"
                alignment = "center"
            elif role == "sound_effect" and line_role != "title_dramatic":
                line_role = role
                scale_class = "xl"
                weight_class = "bold"
            elif role == "whisper":
                line_role = role
                scale_class = "xs"
                weight_class = "light"
                alignment = "right"
            elif role == "pause_gap":
                gap = 1.35
            elif role == "directional":
                line_role = role
                drift = "rightward"
            elif role == "emphasis":
                line_role = role
                scale_class = "lg"
                weight_class = "semibold"

            spans.append(
                TypographySpan(
                    text=directive.text,
                    role=role,
                    emphasis=clamp01(directive.strength),
                    scale_class="lg" if role == "emphasis" else scale_class,
                    weight_class=weight_class,
                    directional_drift=drift,
                    preserve_exact_text=True,
                )
            )

        if not spans:
            spans.append(
                TypographySpan(
                    text=line,
                    role="body",
                    emphasis=0.4,
                    scale_class="body",
                    weight_class="regular",
                    preserve_exact_text=True,
                )
            )

        lines.append(
            TypographyLinePlan(
                line_text=line,
                role=line_role,
                alignment=alignment,
                scale_class=scale_class,
                weight_class=weight_class,
                line_gap_multiplier=gap,
                spans=spans,
            )
        )

    quietness_requirement = 0.65 if any(d.role in {"title_dramatic", "sound_effect"} for d in directives) else 0.5
    contrast_requirement = 0.72 if color_context else 0.65
    special_positioning_mode = "edge_pull_right" if any("page_turn" in d.kind for d in directives) else "anchored"

    warnings: List[str] = []
    if len(lines) > 8:
        warnings.append("High line count may increase typography crowding risk.")
    if text_zone["h"] < 0.14:
        warnings.append("Text zone is shallow; expressive typography options are constrained.")

    notes = [f"Typography planned for age band {age_band}."]
    if saliency_context:
        notes.append("Saliency context present; quietness target weighted.")

    return PageTypographyPlan(
        page_number=page_number,
        source_markdown=printed_markdown,
        text_zone=text_zone,
        alignment=lines[0].alignment if lines else "left",
        preferred_region="lower_safe" if text_zone["y"] < 0.3 else "upper_safe",
        body_scale_class="body",
        style_roles=style_roles,
        lines=lines,
        directives=directives,
        quietness_requirement=quietness_requirement,
        contrast_requirement=contrast_requirement,
        overflow_expected=len(lines) > 8,
        special_positioning_mode=special_positioning_mode,
        warnings=warnings,
        notes=notes,
    )
