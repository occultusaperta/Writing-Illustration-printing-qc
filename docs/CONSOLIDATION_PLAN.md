# Scoring & Review Consolidation Plan

## 1. Architecture Review Assessment

The architecture review (docs/ARCHITECTURE_REVIEW.md) is **mostly correct but incomplete**.

### Correct findings

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Macro architecture is coherent | **Correct** | Pipeline stages (preprod → lock → studio → verify) are clean and well-separated. |
| Micro scoring is too additive and diffuse | **Correct** | 11 scoring dimensions in variant selection; the bottom four (shot 0.15, saliency 0.05, character 0.04, dual 0.035, page_turn 0.02) collectively move the sort key less than a single color-drift point. |
| Ensemble score is computed but not used in variant selection | **Correct** | `ensemble_visual.evaluate_visual_ensemble()` is called at `image_qc.py:192` and stored in metadata, but the sort key at lines 265-281 never references it. GPU batch `ranking_score` is used instead. |
| Weakness logic diverges between optimizer and targeted regeneration | **Correct** | `reselection._sequence_flagged_pages` uses thresholds `premium_qc < 0.78, color_transition < 0.72`. `targeted_regeneration._is_sequence_flagged` uses `premium_qc < 0.76, color_transition < 0.70`. Same concept, different numbers, no shared constant. |
| Verify/artifact sprawl is growing | **Correct** | 24 expected package artifacts; `production_report.json` parsed three separate times in `verify()` (lines 1784, 1871, 1872); plus a fourth at line 1942. |

### Incomplete or understated findings

| Gap | Detail |
|-----|--------|
| **Five weight sets, not three** | The review counts three; `SCORING_WEIGHT_REFERENCE.md` documents four. There is a fifth: `reselection._score_local` (37/33/22/8 over 4 dimensions only — color, ensemble, arch, saliency). This set is also used by `targeted_regeneration` via import. |
| **reselection._score_local diverges from scoring.local_score_bundle** | `_score_local` uses 4 dimensions with weights summing to 1.0. `local_score_bundle` uses 10 dimensions with weights summing to 1.0. Both claim to produce a "local quality composite". Reselection ignores shot, hidden_world, character, typography, dual_audience, page_turn entirely. |
| **production_report.json still parsed 3× in verify()** | A previous memory claims this was fixed. The code shows it is not fixed. Lines 1871 and 1872 each call `json.loads(…read_text(…))` independently, and the `production` dict from line 1784 is not reused. |
| **storefront_opening_score hardcoded to 0.0** | `sequence_summary_from_report()` at `scoring.py:70` always returns `storefront_opening_score: 0.0` regardless of report content. This dimension is dead weight in `composite_delta`. |

### One thing the review gets wrong

The review says "scoring is all post-hoc." This is partially wrong: color script guidance, camera language guidance, hidden world guidance, and architecture guidance are all injected into prompts *before* generation. The scoring is post-hoc, but the planning is pre-hoc. The review conflates measurement with influence.

---

## 2. Concrete Consolidation Plan

### Merge

| What | Into | Reason |
|------|------|--------|
| `reselection._score_local` | `sequence_optimizer.scoring.local_score_bundle` | One local-quality scorer, used by both reselection and targeted regeneration. The 4-dimension version drops 6 signals that the optimizer already computes. |
| `reselection._score_sequence_support` | `sequence_optimizer.scoring.transition_fit` + ensemble/arch blend | Reselection's sequence support (50/30/20 transition/ensemble/arch) is a simplified version of what `move_component_deltas` already computes. |
| Weakness thresholds | Shared constants in `bookforge/qc/thresholds.py` | `_severe_local_issue`, `_weak_dimensions`, `_sequence_flagged_pages`, and `_is_sequence_flagged` use the same concept with drifting numbers. One source of truth. |

### Freeze (do not add more weight sets)

| What | Reason |
|------|--------|
| `image_qc.py` sort-key tuple structure | Already 11 keys. Adding more weak tie-breakers will not change selection outcomes. Instead, fix the ensemble gap (below). |
| `composite_delta` weight dict | 12 dimensions is already at the limit of interpretability. |
| `book_sequence.py` overall formula | Report-only; no code path reads it for decisions. Changing it produces no output-quality effect. |

### Delete (or deprecate)

| What | Reason |
|------|--------|
| `storefront_opening_score` in `composite_delta` | Hardcoded to 0.0 in `sequence_summary_from_report`. Dead weight; carries a 7% allocation that does nothing. |
| `typography_report.json` as separate artifact | Already a slice of `book_sequence_report.json` (line 1661: `sequence_report.to_dict().get("typography_sequence", {})`). Duplicate. |

### Move earlier in control flow

| What | From | To | Impact |
|------|------|----|--------|
| `ensemble_score` into variant selection | Computed but ignored in sort key | Add to `image_qc.py` sort tuple between GPU batch and architecture | **Highest single output-quality gain.** Ensemble captures composition, clarity, texture, artifacts, and perceptual quality — none of which are in the current sort key directly. |

### Remain review-only (no decision authority)

| What | Reason |
|------|--------|
| `book_sequence_report.json` overall_sequence_score | Useful diagnostic; no code path gates on it. |
| `storefront_optimization_report.json` | Measurement of opening-page commercial strength. Not actionable without storefront-aware generation. |
| `character_commercial_report.json` | Measurement; character consistency enforcement requires model-level work. |
| `editorial_report.md`, `readaloud_script.md` | Human review artifacts. |

---

## 3. Ranked Implementation Tasks (by expected output-quality gain)

### Task 1: Add ensemble_score to variant selection (HIGH impact)

**File:** `bookforge/qc/image_qc.py` lines 265-281

**Problem:** The sort key includes `gpu_batch_scores.ranking_score` but not `visual_ensemble.ensemble_score`. The ensemble score (composition 25%, clarity 20%, texture 15%, artifact 20%, perceptual quality 20%) measures exactly the visual properties that determine whether a generated image looks good. It is computed for every variant but then discarded at selection time.

**Fix:** Insert `ensemble_score` into the sort tuple between GPU batch ranking and page architecture. This gives it higher priority than architecture-specific scoring but lower priority than the model-level GPU ranker.

**Expected gain:** Directly improves which variant is selected for every page. This is the single highest-leverage change in the pipeline.

### Task 2: Align weakness thresholds and unify local scoring (MEDIUM impact)

**Files:** `bookforge/review/reselection.py`, `bookforge/review/targeted_regeneration.py`

**Problem:** Two modules that perform the same conceptual task (identify weak pages, score candidates) use different thresholds and different scoring functions. Reselection uses 4-dimension `_score_local`; targeted regeneration imports it. Reselection flags at `premium_qc < 0.78, color < 0.72`; targeted regeneration flags at `premium_qc < 0.76, color < 0.70`. A page can be considered "fine" by one module and "weak" by the other.

**Fix:** Extract thresholds to shared constants. Make reselection use `local_score_bundle` from `sequence_optimizer.scoring` instead of its own 4-dimension scorer.

**Expected gain:** Prevents reselection from ignoring shot/hidden_world/character/typography/dual_audience/page_turn signals. Eliminates cases where the two modules disagree on which pages need intervention.

### Task 3: Consolidate verify() production_report.json reads (LOW-MEDIUM impact)

**File:** `bookforge/pipeline.py` lines 1784, 1871, 1872, 1942

**Problem:** `production_report.json` is parsed from disk 3-4 times in `verify()`. Each parse is independent and could return different data if the file changes between reads (unlikely but fragile). More importantly, it's a maintenance trap — each new feature flag check adds another parse.

**Fix:** Read once at line 1784 into `production` dict and reuse for all subsequent checks.

**Expected gain:** No direct output-quality gain, but prevents verify() from becoming the next source of subtle bugs as more feature flags are added.

---

## 4. Summary of Changes Made in This PR

### What changed

1. **`bookforge/qc/image_qc.py`**: Added `ensemble_score` to the variant selection sort tuple, positioned after GPU batch ranking and before page architecture.
2. **`bookforge/pipeline.py`**: Consolidated `verify()` to read `production_report.json` once and reuse the parsed dict for `dual_audience_enabled` and `page_turn_tension_enabled` checks.
3. **`bookforge/review/reselection.py` and `bookforge/review/targeted_regeneration.py`**: Aligned sequence-flagging thresholds to shared values (`PREMIUM_QC_WEAK_THRESHOLD = 0.78`, `COLOR_TRANSITION_WEAK_THRESHOLD = 0.72`).
4. **`docs/SCORING_WEIGHT_REFERENCE.md`**: Documented the fifth weight set (`reselection._score_local`).
5. **This document** (`docs/CONSOLIDATION_PLAN.md`).

### What broke or is still wrong

- `reselection._score_local` still uses only 4 dimensions instead of calling `local_score_bundle`. Full unification requires updating test expectations and validating that the 10-dimension scorer doesn't change reselection acceptance rates too aggressively. This is deferred to Task 2 full implementation.
- `storefront_opening_score` is still dead (hardcoded 0.0) in `composite_delta`. Removing it requires updating test fixtures. Deferred.
- `typography_report.json` is still a duplicate artifact. Removing it requires updating `_expected_package_artifacts` and all test payloads that include it.

### One thing I am unsure about

Whether `reselection._score_local` (4 dimensions, simple) was *intentionally* kept simpler than `local_score_bundle` (10 dimensions) as a "fast approximation" for runner-up comparison, or whether it simply never got updated as new scoring dimensions were added. The code gives no indication either way. If intentional, merging them would change reselection behavior. If accidental drift, the 4-dimension version is strictly inferior. The threshold alignment (Task 2) is safe regardless; the scorer unification needs validation.
