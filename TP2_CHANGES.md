# TP2 changes: data sources and evidence

Updated November 14, 2026. These changes are on a separate integration branch and have not been merged into the original MVP branch.

## Workflow

Start `START_APP.cmd`, connect Gemini, choose a data source, and use the single generation button.

- **Team/company data:** expand Data sources, download the CSV column template, fill it with real video records, and upload it. No Bright Data key is needed. TikTok and Instagram Reels may appear in the same file, but topics are grouped separately by platform.
- **Online discovery:** Bright Data searches for TikTok candidates, reusing saved data collected within 24 hours. This is keyword discovery, not an official trending chart.

## Upload format

Accepts UTF-8 CSV or a JSON array, including a wrapper of the form `{"videos": [...]}`. Export Excel files as CSV UTF-8; direct XLSX import is not supported. Maximum: 500 records and 2 MB. All records must pass validation before saving; errors identify the row.

| Required field | Expected value |
| --- | --- |
| platform | `tiktok` or `instagram` |
| source_url | Original public video/Reel HTTPS URL |
| creator | Creator account identifier |
| topic | Topic assigned by your team |
| published_at | ISO timestamp with timezone |
| observed_at | ISO timestamp with timezone |
| duration_seconds | Greater than zero and at most 180 |

Optional fields: `caption`, `plays`, `likes`, `comments`, `shares`, `source_note`. Leave unknown metrics blank rather than inventing zero values. Dates must satisfy publication <= observation <= current time.

Use `source_note` for a manually consulted trend page, region or observation context. Such notes are user-supplied context, not automatic official verification. Sales and inventory files do not fit this video-evidence format.

## Implementation changes

- `wushiland/data_sources.py`: provider-independent import, field validation, URL deduplication and platform/topic grouping. Preserves observation dates and upload provenance.
- `wushiland/app.py`: upload interface, CSV template download, source selection and an analysis path that does not require or call Bright Data.
- `wushiland/trend_review.py`: loads uploaded evidence and counts creator identifiers rather than treating Instagram Reel IDs as creators. Separates candidate inspiration from multi-creator sample evidence.
- `wushiland/llm.py`: platform-aware and source-aware prompts, structured output contracts and bounded format-error recovery.
- `wushiland/web.py`: source descriptions, evidence levels, sampling limitations, provisional drafts and separate evergreen alternatives.

## Evidence levels

1. **Candidate inspiration:** the available sample does not establish a trend.
2. **Multi-creator evidence in this sample:** recent evidence from at least three distinct creators, at least two videos with 10,000 plays, and at least 100,000 combined plays. These are project-specific demonstration thresholds, not an official platform definition or proof of growth. Uploaded metrics and creator identities are not independently verified.

Actual video content still requires review before adoption as a verified trend. A single high-view video or a caption containing "viral" is not proof of platform-wide popularity.

## Not implemented

- Automatic Instagram discovery/collection; Instagram video-record import is supported.
- Automatic official-chart ingestion or platform-wide trend verification.
- Gemini video viewing or visual verification; the model currently reads structured metadata.
- Company sales/inventory integration, arbitrary Excel column mapping or complete raw model-request auditing.

## Testing and deployment

46 offline/mock tests passed, covering CSV/JSON imports, invalid URLs, future timestamps, missing fields, duplicates, platform separation, HTTP upload/CSRF protection and the no-Bright-Data upload path. This development work did not trigger new paid collection or live Gemini requests. Connect your own key to validate the latest behavior with the real model.

Restart the app to load changed code and reconnect the process-memory Gemini key. Existing results are not regenerated automatically. See `START_HERE.md` for startup instructions.

The integration branch does not add live collection records. The tests/fixtures directory contains explicitly labeled synthetic records used only for offline tests.
