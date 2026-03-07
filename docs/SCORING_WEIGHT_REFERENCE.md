# Scoring Weight Reference

Five independent weight sets control candidate selection and sequence quality.
They operate at different pipeline stages and serve different objectives.

## 1. Variant Selection Weights (`qc/image_qc.py`)

Used in `choose_best_variant()` to rank candidates within a single page.
Ranking is done via a multi-key tuple so earlier entries dominate later ones.

| Priority | Component | Effective influence |
|----------|-----------|---------------------|
| 1 | pass/fail gate | hard gate |
| 2 | artifact penalties (text −4, watermark −4, logo −3, border −3) | hard gate |
| 3 | color tracking (style_similarity − drift − 0.6 × color_drift) | dominant |
| 4 | visual quality (sharpness + contrast + entropy − dark penalty − gamut risk) | dominant |
| 5 | GPU batch ranking_score | strong |
| 6 | visual_ensemble ensemble_score | strong |
| 7 | page_architecture composite | strong |
| 8 | shot_adherence × 0.15 | moderate |
| 9 | saliency_flow × 0.05 | weak tie-breaker |
| 10 | character_commercial × 0.04 | weak tie-breaker |
| 11 | dual_audience × 0.035 | weak tie-breaker |
| 12 | page_turn_tension × 0.02 | weak tie-breaker |

**Design note:** Because this is a tuple sort, keys 9–12 are effectively
tie-breakers that only matter when higher-priority keys are equal.

## 2. Sequence Report Weights (`review/book_sequence.py`)

Used in `build_book_sequence_report()` to compute the `overall_sequence_score`
that evaluates the entire book as a coherent sequence.

| Weight | Component | Purpose |
|--------|-----------|---------|
| 0.195 | color_flow | Color transition quality across pages |
| 0.175 | architecture_flow | Layout variety and pacing |
| 0.15 | energy_curve | Emotional arc mismatch |
| 0.11 | camera_sequence | Shot type variety |
| 0.10 | saliency_flow | Visual focus flow |
| 0.09 | typography_sequence | Typographic consistency |
| 0.09 | hidden_world | Rereadability elements |
| 0.08 | dual_audience | Child/adult balance |
| 0.01 | page_turn_tension | Directional energy |
| **1.00** | **Total** | |

## 3. Sequence Optimizer Weights (`sequence_optimizer/scoring.py`)

### 3a. Local composite (`local_score_bundle`)

Evaluates a single candidate's quality for swap decisions:

| Weight | Component |
|--------|-----------|
| 0.195 | color |
| 0.175 | ensemble (visual quality) |
| 0.155 | architecture |
| 0.11 | saliency |
| 0.09 | shot (camera) |
| 0.08 | hidden_world |
| 0.07 | character |
| 0.03 | typography proxy |
| 0.08 | dual_audience |
| 0.015 | page_turn_tension |
| **1.00** | **Total** |

### 3b. Composite delta (`composite_delta`)

Evaluates whether a swap is worthwhile:

| Weight | Component |
|--------|-----------|
| 0.14 | saliency_flow_score |
| 0.13 | color_flow_score |
| 0.12 | architecture_flow_score |
| 0.12 | weak_cluster_reduction |
| 0.11 | camera_flow_score |
| 0.08 | character_consistency |
| 0.08 | layout_search_support |
| 0.08 | dual_audience_balance |
| 0.07 | typography_sequence |
| 0.07 | hidden_world_continuity |
| 0.07 | storefront_opening |
| 0.03 | page_turn_tension |
| **1.00** | **Total** |

## 4. Reselection Local Score (`review/reselection.py`)

Used by `_score_local()` (also imported by `targeted_regeneration.py`) to
compare current best against runner-up variants. Simplified to 4 dimensions:

| Weight | Component |
|--------|-----------|
| 0.37 | color |
| 0.33 | ensemble (visual quality) |
| 0.22 | architecture |
| 0.08 | saliency |
| **1.00** | **Total** |

**Note:** This scorer omits shot, hidden_world, character, typography,
dual_audience, and page_turn dimensions present in `local_score_bundle`.
Whether this is intentional simplification or accidental drift is unclear.

## Weight Divergences

The five weight sets intentionally differ because they serve different
evaluation stages:

| Dimension | Variant select | Sequence report | Optimizer local | Optimizer delta | Reselection local |
|-----------|---------------|-----------------|-----------------|-----------------|-------------------|
| Color | dominant (tuple) | 0.195 | 0.195 | 0.13 | 0.37 |
| Ensemble | strong (tuple) | — (energy 0.15) | 0.175 | — (weak_cluster 0.12) | 0.33 |
| Architecture | strong (tuple) | 0.175 | 0.155 | 0.12 | 0.22 |
| Camera/shot | 0.15 | 0.11 | 0.09 | 0.11 | — |
| Saliency | 0.05 | 0.10 | 0.11 | 0.14 | 0.08 |
| Typography | — | 0.09 | 0.03 (proxy) | 0.07 | — |
| Hidden world | — | 0.09 | 0.08 | 0.07 | — |
| Character | 0.04 | — | 0.07 | 0.08 | — |
| Dual audience | 0.035 | 0.08 | 0.08 | 0.08 | — |
| Page turn | 0.02 | 0.01 | 0.015 | 0.03 | — |

**Key observation:** Saliency is underweighted in variant selection (0.05, tuple
position 9) but heavily weighted in the sequence optimizer delta (0.14). This
means a page may be selected with poor saliency flow, then the optimizer will
try to fix it post-hoc. Aligning these would reduce churn.

## Shared Weakness Thresholds

Weakness detection thresholds are defined in `bookforge/utils.py` and shared
by both `reselection.py` and `targeted_regeneration.py`:

| Constant | Value | Used by |
|----------|-------|---------|
| `PREMIUM_QC_WEAK_THRESHOLD` | 0.78 | `_sequence_flagged_pages`, `_is_sequence_flagged` |
| `COLOR_TRANSITION_WEAK_THRESHOLD` | 0.72 | `_sequence_flagged_pages`, `_is_sequence_flagged` |
| `SEVERE_COLOR_THRESHOLD` | 0.68 | `_severe_local_issue`, `_weak_dimensions` |
| `SEVERE_ENSEMBLE_THRESHOLD` | 0.70 | `_severe_local_issue`, `_weak_dimensions` |
| `SEVERE_ARCHITECTURE_THRESHOLD` | 0.65 | `_severe_local_issue`, `_weak_dimensions` |
| `SEVERE_SALIENCY_THRESHOLD` | 0.45 | `_severe_local_issue`, `_weak_dimensions` |
