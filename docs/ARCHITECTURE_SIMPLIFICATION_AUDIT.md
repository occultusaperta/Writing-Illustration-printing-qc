# Architecture Simplification Audit (Packet-Era Modules)

## 1) Root cause summary of why PR #57 removal was insufficient

PR #57 correctly identified sprawl risk, but it over-indexed on code-surface reduction and under-validated real decision paths. The removal of `character`, `dual_audience`, and `page_turn` ranking influence happened without proving that each signal was non-decision-worthy in close candidate sets.

What was missing:

1. **No bounded-effect calibration pass before removal**: weak signals were deleted instead of being calibrated to thresholded, bounded tie-break behavior.
2. **No per-signal pathway audit** across ranking, reselection, optimizer, review, and final quality aggregation.
3. **No explicit demotion contract** for signals that should remain metadata/review only.
4. **No measurable ordering test** showing whether close candidates should or should not move.

## 2) PR #57 components reverted vs retained

### Reverted (premature removal)
- Restored packet-era ranking influence for:
  - `character_commercial_score` (bounded tie-break, confidence-gated)
  - `dual_audience_score` (bounded tie-break)
- Restored registry configuration required for the above ranking behavior.

### Retained
- Shared JSON writer consolidation to `bookforge.io.write_json` remains in place.
- `page_turn_tension_score` remains attached and reported, but intentionally does **not** directly influence image-QC ranking.

## 3) Signal contribution-path audit and decisions

| Signal | Computed in | Attached in QA metadata | Ranking | Reselection | Sequence optimizer | Sequence review/final quality | Decision |
|---|---|---|---|---|---|---|---|
| Character commercial | `bookforge/character_scoring/scoring.py` | `metadata.character_commercial_score` (+ subcomponents) in `qc/image_qc.py` | **Yes** (bounded tie-break with floor + confidence gate) | Indirect via candidate metadata quality | Local + delta (`character`, `character_consistency_score`) | Included in `character_commercial_report` and quality aggregation inputs | **Keep as weak tie-break (calibrated)** |
| Dual audience | `bookforge/dual_audience/scoring.py` | `metadata.dual_audience_score` in `qc/image_qc.py` | **Yes** (bounded tie-break with floor) | Indirect via candidate metadata quality | Local + delta (`dual_audience`, `dual_audience_balance_score`) | Included in dual-audience report and sequence quality synthesis | **Keep as weak tie-break (calibrated)** |
| Page-turn tension | `bookforge/page_turn/scoring.py` | `metadata.page_turn_tension_score` in `qc/image_qc.py` | **No** (metadata-only for image-QC ranking) | Not direct in reselection scoring | Local + delta (`page_turn_tension`, `page_turn_tension_summary_score`) | Included in page-turn report and sequence review | **Demote to metadata/review only for image-QC ranking** |

## 4) Calibration details

### Character commercial (restored + calibrated)
- Added `character_tiebreak_weight`, `character_tiebreak_floor`, and `character_tiebreak_confidence_floor` to registry.
- Ranking influence only activates when:
  - confidence meets floor, and
  - composite score is above floor.
- Influence is normalized within `[floor, 1.0]` and multiplied by weight, keeping effect bounded.

### Dual audience (restored + calibrated)
- Added `dual_audience_tiebreak_weight` and `dual_audience_tiebreak_floor`.
- Influence only activates above floor and is normalized/bounded.

### Page-turn tension (explicit demotion)
- Kept in metadata, sequence optimizer, and review reports.
- Excluded from image-QC variant ranking to avoid overfitting local visual pick decisions to narrative pacing heuristics.

## 5) Files changed

- `bookforge/scoring_registry.py`
- `bookforge/qc/image_qc.py`
- `tests/test_scoring_registry.py`
- `docs/ARCHITECTURE_SIMPLIFICATION_AUDIT.md`

## 6) Risk/debt notes

1. Image-QC ranking still uses tuple-priority ordering, so late tie-breaks only act in close sets by design.
2. Signal calibration is currently static (registry defaults); no per-project calibration profile exists yet.
3. Page-turn remains meaningful at sequence stage but intentionally not at local variant stage, which may invite future pressure to reintroduce it if sequence-local mismatch appears in evidence.
