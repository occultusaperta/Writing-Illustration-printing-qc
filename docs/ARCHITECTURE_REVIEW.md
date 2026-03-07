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

1. **Three weight sets that disagree** — variant selection (tuple sort),
   sequence report (weighted sum), and sequence optimizer (two more weighted
   sums) use different weights for the same dimensions. See
   `docs/SCORING_WEIGHT_REFERENCE.md` for the full divergence table.
2. **`_clamp01` was duplicated 17 times** — now consolidated into
   `bookforge/utils.py`. Symptom of each packet being added independently
   without shared infrastructure.
3. **Verify defaults inconsistent with feature flags** — `page_turn_tension`
   defaulted to False in `verify()` but True in the feature flag. Fixed in
   this review.
4. **Test state leakage** — two test files used direct module assignment instead
   of `monkeypatch.setattr()`, causing FakeIll to leak across test runs. Fixed
   in this review.
5. **Production report is read multiple times in verify()** — lines 1871-1872
   each independently read and parse `production_report.json`. Should read once
   and reuse.

## D. What Is Duplicated / Low-Value / Should Be Merged

| Issue | Location | Recommendation |
|-------|----------|----------------|
| Focal point scoring | `page_architecture.focal_alignment_score` and `saliency_flow.primary_focus_score` both compute "is focal in art zone" independently | Architecture should call saliency_flow for focal point |
| Text fitting estimation | `page_architecture.text_fitting_score` and `layout_search.text_fit_score` use different formulas (word×4.2 vs char/240) | Consolidate or add divergence test |
| Color drift | `image_qc` ranking uses `color_drift_vs_style`, `print_qc` recomputes it | Single source of truth |
| Border quality | `border_bar_score()` and `border_artifact_score()` do similar things | Merge into one composite |
| Composition scoring | `ensemble_visual` (gradient) and `gpu_batch_scoring` (model) both compute composition | Clarify precedence |

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
5. **Scoring is all post-hoc** — every quality signal is evaluated after
   generation. None feed back into the generation prompt to improve the next
   variant.

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

## G. Top 5 Next Implementation Priorities

1. **Consolidate weight constants** — define a single `SCORING_WEIGHTS` dict
   that all three consumers reference, with documented stage-specific overrides.
2. **Add character visual consistency check** — even a simple histogram
   comparison of character regions across pages would catch gross inconsistency.
3. **Feed sequence scores back into regeneration targeting** — the sequence
   optimizer identifies weak pages but targeted regeneration uses a separate
   weakness model. They should share the same weakness definition.
4. **Read production_report.json once in verify()** — eliminate the duplicated
   parsing on lines 1871-1872.
5. **Add integration test for scoring pipeline** — verify that
   variant_selection → sequence_report → optimizer produces monotonically
   improving scores on a synthetic dataset.

## H. What Should NOT Be Built Next

1. **More scoring modules** — the system already has 11. Each new one dilutes
   the influence of existing ones. Focus on making existing scores useful.
2. **More review artifacts** — 20+ JSON reports already. Each one adds verify()
   checks, test fixtures, and maintenance. Add only if it directly gates output.
3. **Real-time UI for scoring** — the Streamlit UI should show results, not
   expose scoring internals as knobs.
4. **Neural scoring without training data** — adding a pretrained aesthetic
   model without children's book training data will add noise, not signal.

## I. Proposed Cleaner Control Hierarchy

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

## J. Reality Check

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
