# Final Architecture State (Operator-Facing)

This document is the final operator-focused architecture hardening pass. It does **not** add new pipeline layers; it clarifies what to trust and what is heuristic.

## 1) What is authoritative now

Authoritative artifacts and decisions:

- `preflight_report.json` for print/package hard-gate health.
- `review/qa_report.json` and `review/visual_critic_report.json` for per-page QC pass/fail context.
- `review/book_quality_report.json` as the unified review artifact for sequence and packet diagnostics.
- `LOCK.json` as the generation contract (references, prompts, geometry, profile, endpoint).

Interpretation rule: if an older report conflicts with `review/book_quality_report.json`, trust `review/book_quality_report.json` and use legacy files only for drill-down.

## 2) What remains heuristic

These remain deterministic but heuristic proxies (not ground-truth semantics):

- sequence scoring, layout scoring, camera/hidden-world adherence
- storefront optimization score
- character commercial score
- dual-audience and page-turn tension scores
- typography and saliency-derived proxies

Operator rule: use these signals for **triage and prioritization**, not as proof of literary/artistic correctness.

## 3) What remains deferred / requires live confirmation

Still requires real runtime/operator confirmation:

- rented GPU runtime provisioning/launch status on real provider credentials and reachable hosts
- final commercial/art-direction judgment (storytelling intent, character consistency nuance)
- post-package human checks in storefront and print proofs

Operator rule: “PASS” in verify/QC means pipeline and bounded checks passed; it is not a replacement for final human publication sign-off.

## 4) What should not be expanded further

Do not add:

- additional scoring packets/modules
- additional review artifact files that duplicate existing diagnostics
- alternate “shadow” authoritative reports

Reason: this increases operator ambiguity (“which report matters?”) and weakens trust in existing gates.

## 5) Operator trust-first diagnosis order

Use this order when diagnosing a run:

1. `preflight_report.json` (hard print gates)
2. `review/qa_report.json` and `review/visual_critic_report.json` (page-level failures)
3. `review/book_quality_report.json` (authoritative sequence/summary)
4. `review/production_report.json` (provenance, feature-flag snapshot, provider endpoint)
5. legacy reports only if deeper packet detail is needed

If verify reports that it generated `review/book_quality_report.json` from legacy artifacts, treat the run as compatibility-mode and inspect limitations/warnings before relying on score deltas.

## 6) Final simplifications in this pass

- Feature-flag defaults are centralized in one place in pipeline code and mirrored in operator docs.
- Verify messaging now explicitly labels `review/book_quality_report.json` as authoritative.
- Studio provenance now records:
  - resolved feature-flag snapshot
  - authoritative review artifact path
  - legacy compatibility artifact list

These are clarity improvements only; no scoring/ranking architecture changes were introduced.
