"""Read saved Bright Data exports without making platform requests."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SEED = Path(__file__).parent / "data" / "brightdata"


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing export timestamp.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Expected a timestamp with timezone.")
    return parsed


def public_video(url):
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.netloc in
            {"www.tiktok.com", "www.instagram.com", "tiktok.com", "instagram.com"}
            and not parsed.query and not parsed.fragment
            and ("/video/" in parsed.path or parsed.path.startswith("/reel/")))


def load_creative_signals(as_of, trace):
    root = Path(os.getenv("WUSHILAND_BRIGHTDATA_DIR", str(SEED)))
    exports = {}
    for kind, filename in (("signals", "signals.json"), ("candidates", "trends.json")):
        snapshots = []
        for path in sorted(root.rglob(filename)):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                exported = timestamp(data.get("generated_at")).astimezone(timezone.utc)
                if data.get("mode") == "live" and exported.date() <= as_of and isinstance(data.get(kind), list):
                    snapshots.append((exported, data[kind]))
            except (OSError, ValueError, AttributeError):
                trace.append(f"Skipped unreadable Bright Data {filename}.")
        if snapshots:
            exports[kind] = max(snapshots, key=lambda entry: entry[0])
    signals = []
    for kind, (exported, records) in exports.items():
        trace.append(f"Read saved Bright Data {kind} export from {exported.date()}.")
        for row in records:
            if not isinstance(row, dict):
                continue
            try:
                if kind == "signals":
                    if row.get("is_fixture") is not False or row.get("provider") != "bright_data":
                        continue
                    published = timestamp(row.get("published_at")).date()
                    if published > as_of:
                        continue
                    tags = row.get("hashtags", [])
                    words = str(row.get("title", "")).lower() + " " + str(tags).lower()
                    url = row.get("source_url")
                    if not any(term in words for term in ("milk tea", "milktea", "boba", "bubbletea", "jasmine")):
                        continue
                    if "which" in words:
                        format_name, cue = "choice", "Ask viewers which angle or first sip they would pick."
                    elif "recipe" in words or "batching" in words:
                        format_name, cue = "pour", "Start with an ingredient or pour close-up and reveal the finished cup."
                    else:
                        continue
                    label = "Saved video reference; its visual format was inferred from metadata."
                else:
                    # Discovery groups do not establish a visual format without manual review.
                    format_name = row.get("content_format")
                    if row.get("content_format_requires_video_review") is not False or format_name not in (
                        "routine", "pour", "choice", "pov", "checklist"
                    ):
                        continue
                    urls = row.get("evidence_urls")
                    url = urls[0] if isinstance(urls, list) and urls else None
                    cue = "Adapt the reviewed creative format using the selected catalog product."
                    label = "Saved discovery reference."
                    published = exported.date()
                if not public_video(url) or any(item["url"] == url for item in signals):
                    continue
                signals.append({"id": f"video-{len(signals) + 1}", "format": format_name,
                                "cue": cue, "url": url, "label": label,
                                "published": str(published), "snapshot": str(exported.date()),
                                "historical": (as_of - published).days > 30})
            except ValueError:
                continue
    trace.append(f"Found {len(signals)} creative references in saved exports." if signals
                 else "No usable saved Bright Data references. Used local creative formats.")
    return signals[:8]
