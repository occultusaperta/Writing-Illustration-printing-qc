# Architecture Review

Technical review of the bookforge pipeline as of the current codebase.

## A. Executive Verdict

The system is **architecturally coherent at the macro level** but **additive at
the scoring micro-level**. The pipeline stages (preprod → lock → studio → verify)
are well-separated. Each packet adds a genuine quality dimension. However the
accumulation of 11+ scoring modules, three independent weight sets, and 20+
review artifacts means the system's actual influence on output quality is
increasingly diffuse. The biggest risk is not missing features — it is that too
many weak signals compete with the few signals that actually drive visual
quality.

## B. What Is Genuinely Strong

1. **Pipeline stage separation** — preprod/lock/studio/verify is clean and each
   stage has a clear contract.
2. **Feature flag gating** — every subsystem can be toggled independently via
   env vars, with safe no-op defaults.
3. **Color script engine** — CIEΔE2000 LAB scoring against planned emotional
   palettes is the right technical choice. Color is the single most important
   visual dimension for children's books.
4. **QA loop with regeneration** — the sharpness/artifact/watermark pass/fail
   gates are genuine hard gates that prevent bad output.
5. **Page architecture sequencer** — zone-based layout planning with gutter
   safety is structurally sound.
6. **Bounded reselection + targeted regeneration** — the hierarchy (reselection
   first, then regeneration, then sequence optimization) is correctly ordered
   from cheapest to most expensive operation.
7. **Test coverage** — 218 tests covering all major modules with proper
   monkeypatch patterns.

## C. What Is Structurally Weak

1. **Four weight sets that disagree** — variant selection (tuple sort in
   `qc/image_qc.py`), sequence report (weighted sum in
   `review/book_sequence.py`), and sequence optimizer (two more weighted sums
   in `sequence_optimizer/scoring.py`) use different weights for the same
   dimensions. Saliency ranges from 0.05 (variant selection) to 0.14 (optimizer
   delta). Page turn tension has four different values (0.01, 0.015, 0.02,
   0.03) across the four systems. See `docs/SCORING_WEIGHT_REFERENCE.md`.
2. **`clamp01` consolidation incomplete** — consolidated into
   `bookforge/utils.py` but `hidden_world/sequence.py` and
   `storefront/scoring.py` were still using inline `max(0, min(1, x))`.
   Fixed in this review.
3. **Test state leakage** — two test files used direct module assignment instead
   of `monkeypatch.setattr()`, causing FakeIll to leak across test runs. Fixed
   in a prior review.
4. **Production report was read multiple times in verify()** — dual_audience,
   page_turn_tension, and readaloud_script feature checks each independently
   parsed `production_report.json`. Fixed in this review: now parsed once into
   `prod_data`.
5. **Ensemble score computed but unused in variant selection** — `image_qc.py`
   computes `evaluate_visual_ensemble()` (composition 0.25, clarity 0.20,
   artifact 0.20, perceptual 0.20, texture 0.15) and stores it in metadata,
   but the variant selection tuple sort ignores it, falling back to raw
   `sharpness + contrast + entropy`. The curated ensemble is wasted.

## D. What Is Duplicated / Low-Value / Should Be Merged

| Issue | Location | Recommendation |
|-------|----------|----------------|
| Focal point scoring | `page_architecture/scoring.py` `focal_alignment_score` and `saliency_flow/scoring.py` `primary_focus_score` both compute "is focal in art zone" independently | Architecture should call saliency_flow for focal point |
| Text fitting estimation | `page_architecture/scoring.py` `text_fitting_score` and `layout_search/scoring.py` `text_fit_score` use different formulas (word×4.2 vs char/240) | Consolidate or add divergence test |
| Color drift | `image_qc.py` ranking uses `color_drift_vs_style`, `print_qc.py` recomputes it | Single source of truth |
| Border quality | `border_bar_score()` and `border_artifact_score()` in `image_qc.py` do overlapping things | Merge into one composite |
| Composition scoring | `ensemble_visual.py` (gradient-based) and `gpu_batch_scoring.py` (model-based) both compute composition | Clarify precedence; deduplicate or document split |
| Summary score pattern | `dual_audience/sequence.py`, `page_turn/sequence.py`, `character_scoring/sequence.py` all implement identical mean-based aggregation | Extract to shared utility |
| Typography proxy | `sequence_optimizer/scoring.py` line 17 uses `1.0 - focus_bleed_overlap` as a typography stand-in (weight 0.03) | Replace with actual typography score or remove |

## E. What Still Blocks Top-Tier Output

1. **No neural perception model** — all scoring is heuristic (gradient energy,
   Laplacian, FFT). A fine-tuned aesthetic model would outperform the current
   11-metric weighted sum.
2. **No character consistency enforcement** — character bible exists but there
   is no visual character matching across pages (no face embedding, no pose
   consistency check).
3. **No layout-aware image generation** — prompt guidance is text-only. The
   pipeline cannot tell the image generator "put character on left third, leave
   right side for text."
4. **No spread composition** — double-page spreads are split and QC'd
   individually; there is no cross-page visual balance check.
5. **Post-hoc scoring mistaken for art direction** — color script, page
   architecture, camera language, and hidden world planning are computed in
   preprod and feed prompt guidance. But 8 of the 11 scoring systems
   (page turn tension, dual audience, character commercial, storefront,
   typography, saliency flow, hidden world report, sequence optimization) only
   evaluate the output after generation. They produce reports but do not
   influence the next generation attempt. This is measurement, not direction.

## F. Module Classification

### Hard Gates (must pass or regenerate)
- `image_qc` pass/fail: sharpness, artifact detection, watermark, text
- `kdp_preflight`: PDF dimensions, DPI, barcode placement
- Color drift thresholds: style similarity, page-to-page drift

### Strong Rankers (directly influence selection)
- Color script adherence
- Page architecture composite
- Visual ensemble score
- GPU batch ranking score

### Weak Tie-Breakers (only matter when strong signals tie)
- Shot adherence (0.15 weight in tuple position 7)
- Saliency flow (0.05 in position 8)
- Character commercial (0.04 in position 9)
- Dual audience (0.035 in position 10)
- Page turn tension (0.02 in position 11)

### Review-Only (produce reports but don't influence selection)
- Book sequence report (overall_sequence_score)
- Storefront optimization
- Editorial analysis (rhythm, hook, trade dress)
- Companion materials

### Candidates for Deprecation
- `border_bar_score` (redundant with `border_artifact_score`)
- Typography "proxy" in sequence optimizer (uses focus_bleed_overlap as stand-in)

## G. Top 5 Changes That Would Most Improve Output Quality

1. **Use the ensemble score in variant selection** — `evaluate_visual_ensemble()`
   already computes a curated 5-component quality score (composition 0.25,
   clarity 0.20, artifact 0.20, perceptual 0.20, texture 0.15) but variant
   selection ignores it, using raw `sharpness + contrast + entropy` instead.
   Replace tuple key 4 with the ensemble score. File: `qc/image_qc.py:271`.
2. **Align saliency weight in variant selection** — saliency is 0.05 in variant
   selection but 0.14 in the optimizer delta. Pages selected with poor saliency
   flow are then expensively swapped by the optimizer. Raise the variant
   selection weight to ~0.10. File: `qc/image_qc.py:275`.
3. **Feed sequence weakness back into regeneration targeting** — the sequence
   optimizer (`sequence_optimizer/search.py`) identifies weak pages by composite
   delta, but targeted regeneration (`review/targeted_regeneration.py`) uses a
   separate weakness model. They should share the same weakness definition.
4. **Freeze page turn tension scoring** — four different weight values across
   four systems (0.01, 0.015, 0.02, 0.03) contribute negligible signal. Either
   raise to a meaningful level (≥0.05) everywhere or freeze at 0.0 and remove
   the feature flag. The current state is decorative complexity.
5. **Consolidate weight constants into a single source** — define a shared
   `SCORING_WEIGHTS` dict in `bookforge/scoring_weights.py` that all four
   consumers reference, with documented stage-specific overrides for the
   dimensions that genuinely need to differ (e.g., ensemble weight absent
   from delta scoring because it's per-page, not per-sequence).

## H. What Should NOT Be Built Next

1. **More scoring modules** — the system already has 11. Each new one dilutes
   the influence of existing ones. Focus on making existing scores useful.
2. **More review artifacts** — 25 required JSON reports, 40+ total JSON files.
   Each one adds verify() field checks, test fixture schemas, and maintenance.
   Six feature-gated reports are currently listed as required in
   `_expected_package_artifacts()` even though they produce stubs when disabled.
   Do not add more; consider making feature-gated reports conditional in the
   required list.
3. **Real-time UI for scoring** — the Streamlit UI should show results, not
   expose scoring internals as knobs.
4. **Neural scoring without training data** — adding a pretrained aesthetic
   model without children's book training data will add noise, not signal.

## I. Feature-Flag and Artifact Sprawl

### Feature Flags (12 unique, all in `pipeline.py`)

| Flag | Default | Category |
|------|---------|----------|
| BOOKFORGE_COLOR_SCRIPT | true | pre-generation planning |
| BOOKFORGE_PAGE_ARCHITECTURE | true | pre-generation planning |
| BOOKFORGE_CAMERA_LANGUAGE | true | pre-generation planning |
| BOOKFORGE_HIDDEN_WORLD | true | pre-generation planning |
| BOOKFORGE_DYNAMIC_TYPOGRAPHY | true | post-generation scoring |
| BOOKFORGE_STOREFRONT_OPTIMIZATION | true | post-generation scoring |
| BOOKFORGE_CHARACTER_COMMERCIAL_SCORING | true | post-generation scoring |
| BOOKFORGE_DUAL_AUDIENCE | true | post-generation scoring |
| BOOKFORGE_MONTE_CARLO_LAYOUT | true | post-generation scoring |
| BOOKFORGE_PAGE_TURN_TENSION | true | post-generation scoring |
| BOOKFORGE_RESELECTION | false | repair loop |
| BOOKFORGE_TARGETED_REGENERATION | false | repair loop |

The first four flags influence prompt generation. These are real art direction.
The next six flags only produce reports — disabling them changes nothing about
the output PDFs. They are measurement, not control. Flag 11 and 12 (repair
loops) are correctly defaulted to false.

### Artifact Sprawl

`_expected_package_artifacts()` requires 25 files including 14 review JSON
reports. Six of these reports (storefront, character commercial, dual audience,
page turn tension, hidden world, layout search) are feature-gated but always
required. When disabled they emit stubs (`enabled: false, summary_score: 0.0`).
This means the required list is unconditional but the content is conditional —
verify() has to handle both cases, and every test must construct full stub
payloads for all 14 reports.

### verify() Complexity

verify() is 199 lines and validates 18 different artifact types with different
field schemas. It reads and parses up to 15 JSON files. Each new packet adds
~15 lines of field checks to verify(), a new entry to
`_expected_package_artifacts()`, and a new test fixture schema. This grows
linearly with feature count.

## J. Proposed Cleaner Control Hierarchy

```
HARD GATES (must pass):
  └─ image_qc pass/fail (artifacts, sharpness, watermark)
  └─ kdp_preflight (PDF specs)
  └─ color drift thresholds

VARIANT SELECTION (weighted composite, not tuple):
  └─ 0.30 × color_adherence
  └─ 0.25 × visual_quality (sharpness + contrast + ensemble)
  └─ 0.20 × architecture_composite
  └─ 0.10 × camera_adherence
  └─ 0.10 × saliency_flow
  └─ 0.05 × remaining (character, dual_audience, page_turn)

SEQUENCE EVALUATION (same weights as above):
  └─ overall_sequence_score using identical weight proportions

OPTIMIZER (delta-based using same weight vector):
  └─ accept swap if weighted_delta > threshold

REVIEW-ONLY (no selection influence):
  └─ storefront_optimization
  └─ editorial_analysis
  └─ companion_materials
```

## K. Reality Check

This system will not match a top illustration studio because:

1. **No human art direction** — the highest-quality picture books are made by
   illustrators who compose each spread as a unique painting. AI generation
   with post-hoc QC cannot replicate compositional intent.
2. **No visual storytelling feedback** — a human art director looks at a spread
   and says "the character's expression doesn't match the text's emotion."
   No scoring heuristic can do this reliably.
3. **Scoring granularity exceeds signal** — with 11 scoring modules producing
   50+ metrics per page, the effective information content per metric is very
   low. A single experienced art director's gut check carries more signal.
4. **Color is not style** — the color script engine measures palette adherence
   but not illustration style consistency (brushwork, line weight, character
   proportions).
5. **The gap is in generation, not QC** — current AI image generators cannot
   reliably produce publication-quality children's book illustrations with
   consistent characters. Better QC cannot fix what the generator cannot
   produce.

The system's actual value is as a **production pipeline** that scales volume
while maintaining minimum quality floors — not as a replacement for human
creative direction.
