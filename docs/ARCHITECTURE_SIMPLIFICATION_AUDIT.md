# Architecture Simplification Audit (Packet-Era Modules)

## 1) Root cause summary of complexity creep

The packet-era stack accumulated complexity through additive scoring and reporting layers that were each safe in isolation but collectively caused sprawl:

1. **Weak tie-break accretion** in variant ranking (`character`, `dual_audience`, `page_turn`) added maintenance surface while barely changing ordering versus stronger metrics (pass/fail gates, artifact penalties, style drift, core quality).
2. **Repeated JSON report writer helpers** proliferated across packet modules, duplicating the same `mkdir + json.dumps + write_text` pattern.
3. **Compatibility-oriented reporting** preserved many legacy report artifacts; this remains useful for migration safety but can obscure the canonical source of truth.
4. **Feature-flagged optional layers** were added conservatively, but several contributed mostly as metadata side channels rather than robust decision drivers.

## 2) Candidate decisions (keep/remove/inline/defer)

| Area | Candidate | Decision | Reason |
|---|---|---|---|
| Variant ranking | `character_tiebreak_weight` | **remove** | Ultra-weak tie-break with low leverage and ongoing config/maintenance overhead. |
| Variant ranking | `dual_audience_tiebreak_weight` | **remove** | Same: low decision value relative to stronger earlier ranking terms. |
| Variant ranking | `page_turn_tiebreak_weight` | **remove** | Same: weak late-stage signal that rarely changes winner selection. |
| Variant ranking | `architecture/shot/saliency` tie-breaks | **keep** | Still materially connected to visual planning and readability objectives. |
| Report serialization | Per-module duplicate JSON write helpers | **inline** (into shared utility) | Consolidated repetitive logic to `bookforge.io.write_json` and kept public writer function names stable. |
| Legacy compatibility semantics | `book_quality` legacy artifact ingestion/migration hints | **defer** | Retained for compatibility safety; removing now risks migration/verification regressions. |
| Core safeguards | lock/checkpoint/approval flow | **keep** | Explicitly preserved; not modified. |
| Core pipeline and optimization flow | reselection/targeted regen/sequence optimization execution | **keep** | Still a meaningful quality and planning backbone. |

## 3) Exact files changed

### Added
- `bookforge/io/__init__.py`
- `bookforge/io/json_io.py`

### Changed
- `bookforge/scoring_registry.py`
- `bookforge/qc/image_qc.py`
- `bookforge/review/proof_pack.py`
- `bookforge/review/targeted_regeneration.py`
- `bookforge/review/book_sequence.py`
- `bookforge/review/reselection.py`
- `bookforge/sequence_optimizer/apply.py`
- `bookforge/dual_audience/sequence.py`
- `bookforge/page_turn/sequence.py`
- `bookforge/storefront/scoring.py`
- `bookforge/hidden_world/sequence.py`
- `bookforge/review/book_quality.py`
- `tests/test_scoring_registry.py`
- `docs/ARCHITECTURE_SIMPLIFICATION_AUDIT.md`

### Removed
- No files removed in this pass.

## 4) Tests/commands run

- `python -m compileall -q bookforge`
- `pytest -q tests/test_scoring_registry.py tests/test_book_sequence_review.py tests/test_bounded_reselection.py tests/test_targeted_regeneration.py tests/test_sequence_optimizer_packet18.py tests/test_storefront_optimization.py tests/test_book_quality_report.py`

## 5) Risk notes

1. **Ranking behavior shift risk**: removing three weak tie-break signals may alter winner choice in extremely close candidate sets. Mitigation: kept stronger tie-break layers and all pass/fail gates.
2. **Serialization centralization risk**: shared writer utility becomes a single point for JSON report writing. Mitigation: utility intentionally minimal and deterministic.
3. **Deferred compatibility cleanup risk**: legacy artifact compatibility remains, so conceptual sprawl is reduced but not fully eliminated. This is intentional for safety.

## 6) Branch / commit / PR metadata

To be filled after commit:
- Branch name: `<pending>`
- Commit hash: `<pending>`
- PR title: `<pending>`
- PR description: `<pending>`
