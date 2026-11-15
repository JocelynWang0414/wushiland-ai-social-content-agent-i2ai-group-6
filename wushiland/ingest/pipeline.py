"""Wushiland short-video signals. Python 3.10+, standard library only."""
import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

DATASETS = {"instagram": "gd_lyclm20il4r5helnj", "tiktok": "gd_lu702nij2f790tmv9h"}
BASE = "https://api.brightdata.com/datasets/v3/"


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def canonical(platform, url):
    p = urlsplit(str(url))
    host = {"instagram": "instagram.com", "tiktok": "tiktok.com"}[platform]
    pattern = r"/(?:[^/]+/)?reel/[^/]+/?" if platform == "instagram" else r"/@[^/]+/video/\d+/?"
    if p.scheme != "https" or p.hostname not in (host, "www." + host) or not re.fullmatch(pattern, p.path):
        raise ValueError("Expected a public HTTPS Reel or TikTok /@user/video/id URL")
    return urlunsplit(("https", "www." + host, p.path.rstrip("/") + "/", "", ""))


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(str(value).replace(",", ""))
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None


def normalize(rows, platform, fixture=False, snapshot_id=None, max_seconds=180):
    if not isinstance(rows, list):
        raise ValueError("Snapshot must be a JSON array")
    now = datetime.now(timezone.utc).isoformat()
    signals, rejected, seen = [], [], set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("error") or row.get("error_code"):
            rejected.append({"row": i, "reason": "provider_error_or_invalid_row"})
            continue
        try:
            url = canonical(platform, row.get("url", ""))
        except ValueError:
            rejected.append({"row": i, "reason": "not_a_video_url"})
            continue
        duration = number(row.get("length" if platform == "instagram" else "video_duration"))
        if duration is None or duration <= 0 or duration > max_seconds:
            rejected.append({"row": i, "reason": "duration_unknown_or_outside_policy"})
            continue
        if platform == "tiktok" and str(row.get("post_type", "video")).lower() != "video":
            rejected.append({"row": i, "reason": "not_video"})
            continue
        if url in seen:
            rejected.append({"row": i, "reason": "duplicate"})
            continue
        seen.add(url)
        ig = platform == "instagram"
        fields = {"views": "views" if ig else "play_count", "plays": "video_play_count" if ig else "play_count",
                  "likes": "likes" if ig else "digg_count", "comments": "num_comments" if ig else "comment_count",
                  "shares": "share_count", "saves": "collect_count"}
        metrics = {k: number(row.get(v)) for k, v in fields.items()}
        # Instagram schema does not expose shares/saves. Do not infer missing counts.
        if ig:
            metrics.update(shares=None, saves=None)
        caption = str(row.get("description") or "")
        tags = row.get("hashtags") or re.findall(r"#(\w+)", caption)
        tags = sorted({str(t).lstrip("#").lower() for t in tags if isinstance(t, str)}) if isinstance(tags, list) else []
        signals.append({"id": platform + "-" + hashlib.sha256(url.encode()).hexdigest()[:16],
                        "signal_type": "social_trend", "source": platform, "provider": "bright_data",
                        "title": caption[:100] or "Short video", "description": caption,
                        "source_url": url, "observed_at": now, "published_at": row.get("date_posted" if ig else "create_time"),
                        "duration_seconds": duration, "hashtags": tags, "metrics": metrics,
                        "is_fixture": fixture, "evidence_type": "synthetic_fixture" if fixture else "live_scrape",
                        "trend_status": "unverified_single_observation", "snapshot_id": snapshot_id})
    return {"schema_version": "1.0", "mode": "offline_fixture" if fixture else "live",
            "generated_at": now, "dataset_id": DATASETS[platform], "short_video_max_seconds": max_seconds,
            "sampling": "user_selected_urls_not_platform_trending_feed", "signals": signals,
            "rejected": rejected, "counts": {"input": len(rows), "accepted": len(signals), "rejected": len(rejected)}}


class Client:
    def __init__(self, token):
        if not token or not token.strip():
            raise ValueError("Missing BRIGHTDATA_API_KEY; use --prompt-key or offline mode")
        self.token = token.strip()

    def request(self, method, path, params=None, body=None):
        url = BASE + path + ("?" + urlencode(params) if params else "")
        req = Request(url, data=None if body is None else json.dumps(body).encode(), method=method,
                      headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        # Never retry POST: an ambiguous timeout may already have started a billable job.
        for attempt in range(3 if method == "GET" else 1):
            try:
                with urlopen(req, timeout=45) as response:
                    return json.load(response)
            except HTTPError as exc:
                if method == "GET" and (exc.code == 429 or exc.code >= 500) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                detail = ''
                if exc.code == 400:
                    try:
                        payload = json.loads(exc.read())
                        detail = json.dumps(payload, ensure_ascii=True)
                        detail = detail.replace(self.token, '[REDACTED]')[:500]
                    except (ValueError, TypeError, AttributeError):
                        pass
                error = RuntimeError(f"Bright Data HTTP {exc.code}; check key, permissions, credits and dashboard." + (' Validation: ' + detail if detail else ' Response body suppressed.'))
                error.http_status = exc.code
                raise error from None
            except (URLError, TimeoutError):
                raise RuntimeError("Network timeout/error; inspect dashboard before triggering again. POST was not retried.") from None

    def collect(self, platform, urls, job_path):
        if not 1 <= len(urls) <= 10:
            raise ValueError("Use 1–10 URLs per demo job")
        inputs = [{"url": canonical(platform, u)} for u in urls]
        result = self.request("POST", "trigger", {"dataset_id": DATASETS[platform], "include_errors": "true"}, inputs)
        sid = result.get("snapshot_id") if isinstance(result, dict) else None
        if not sid or not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
            raise RuntimeError("Trigger did not return a valid snapshot_id; inspect dashboard")
        save(job_path, {"platform": platform, "snapshot_id": sid, "dataset_id": DATASETS[platform], "inputs": inputs})
        return sid

    def download(self, sid, timeout=600, interval=10, on_progress=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
            raise ValueError("Invalid snapshot ID")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.request("GET", "progress/" + sid).get("status")
            if on_progress:
                on_progress(status)
            if status == "ready":
                return self.request("GET", "snapshot/" + sid, {"format": "json"})
            if status in ("failed", "canceled", "cancelled"):
                raise RuntimeError("Snapshot " + status)
            if status not in ("starting", "running"):
                raise RuntimeError("Unexpected snapshot status; inspect dashboard")
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise TimeoutError("Polling timed out. Job may still run; resume saved job without triggering again.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["offline", "live", "resume"])
    p.add_argument("--platform", choices=DATASETS, default="instagram")
    p.add_argument("--urls", help="JSON array of public video URL strings")
    p.add_argument("--fixture", help="Synthetic raw JSON array; offline only")
    p.add_argument("--job", default="output/job.json")
    p.add_argument("--out", default="output")
    p.add_argument("--prompt-key", action="store_true", help="Hidden terminal prompt, key never written to disk")
    p.add_argument("--max-seconds", type=float, default=180)
    args = p.parse_args()
    if not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        p.error("--max-seconds must be finite and positive")
    sid = None
    if args.mode == "offline":
        fixture = Path(args.fixture) if args.fixture else Path(__file__).parent / "fixtures" / (args.platform + ".json")
        rows = json.loads(fixture.read_text(encoding="utf-8-sig"))
    else:
        client = Client(getpass.getpass("Bright Data API key: ") if args.prompt_key else os.getenv("BRIGHTDATA_API_KEY"))
        if args.mode == "resume":
            job = json.loads(Path(args.job).read_text(encoding="utf-8-sig"))
            args.platform, sid = job["platform"], job["snapshot_id"]
        else:
            if not args.urls:
                p.error("live requires --urls")
            urls = json.loads(Path(args.urls).read_text(encoding="utf-8-sig"))
            if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
                p.error("--urls must contain a JSON array of URL strings")
            sid = client.collect(args.platform, urls, args.job)
            print("Job saved; snapshot:", sid)
        rows = client.download(sid)
    out = Path(args.out)
    save(out / "raw.json", rows)
    bundle = normalize(rows, args.platform, args.mode == "offline", sid, args.max_seconds)
    save(out / "signals.json", bundle)
    print(json.dumps({"mode": bundle["mode"], "counts": bundle["counts"], "output": str(out / "signals.json")}))
    if not bundle["signals"]:
        raise RuntimeError("No eligible short videos; inspect raw.json and rejection reasons")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, TimeoutError, OSError, KeyError) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        sys.exit(1)
