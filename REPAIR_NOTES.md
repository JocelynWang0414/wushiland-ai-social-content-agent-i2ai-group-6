# Output repairs, November 14, 2026

- Added generateContent responseSchema contracts for assessments and briefs. Exact source/product validators remain authoritative.
- Accept absent/null creative concepts for watch/reject, without manufacturing an idea or discarding the valid assessment.
- Distinguish incomplete model output from auth/quota/network failures. Retry malformed drafting once; do not automatically retry provider errors. Accept a complete fenced JSON object, never salvage truncated JSON.
- Prioritize creative drafts in presentation. Collapse candidates whose video URLs are already represented and candidates without drafts; retain full assessments in JSON. This is evidence-overlap suppression, not semantic clustering of unrelated videos.
- Replace bare numeric audio headings, explicitly label keyword-search sampling and metadata uncertainty, and prominently disclose fallback weekly scripts.
- Reinforce that captions cannot establish actual choreography, tempo or time signature. This prompt reduces risk but is not a factual guarantee; no video understanding was added.

Validation: 39 offline/mock tests passed. No new paid collection or live Gemini request was made. Old saved results are not regenerated. Restart the application to load this code; process-memory Gemini keys must be entered again. Generate on recent saved data to validate with the real model.

Scope: current online discovery remains TikTok keyword search. Instagram discovery, company-data upload, independent trend-source ingestion and video review are not implemented in this repair. Bright Data should be a replaceable acquisition adapter, not the definition of a trend.
