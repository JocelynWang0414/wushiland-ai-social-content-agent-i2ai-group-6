"""Discover TikTok trend candidates for a downstream fixed-product marketing agent."""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from statistics import median
import sys
from urllib.parse import urlsplit
from .pipeline import Client, DATASETS, canonical, normalize, number, save

GENERIC = {'fyp', 'foryou', 'foryoupage', 'viral', 'trending', 'trend', 'tiktok', 'xyzbca', 'capcut', 'video', 'fy', 'fypシ',
           'meme', 'memes', 'funny', 'humor', 'music', 'dance', 'dances', 'global', '4u', 'party', 'tiktoktrend'}


def date(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError, TypeError):
        return None


def creator(url):
    return urlsplit(url).path.split('/')[1].lower()


def analyze(rows, now=None, days=7, previous=None, snapshot_ids=None):
    now = now or datetime.now(timezone.utc)
    bundle = normalize(rows, 'tiktok')
    raw_by_url = {}
    for row in rows:
        if isinstance(row, dict):
            try:
                raw_by_url[canonical('tiktok', row.get('url', ''))] = row
            except ValueError:
                pass
    recent, excluded = [], list(bundle['rejected'])
    for s in bundle['signals']:
        published = date(s['published_at'])
        if published is None or not now - timedelta(days=days) <= published <= now:
            excluded.append({'source_url': s['source_url'], 'reason': 'outside_recent_window_or_unknown_date'})
            continue
        raw = raw_by_url[s['source_url']]
        observed = date(raw.get('timestamp')) or date(raw.get('_pipeline_observed_at'))
        s['observed_at'] = observed.isoformat() if observed else now.isoformat()
        s['observation_time_basis'] = 'provider_timestamp_or_saved_download_time' if observed else 'analysis_time_no_capture_time_available'
        s['creator'] = creator(s['source_url'])
        s['region_reported'] = raw_by_url[s['source_url']].get('region')
        s['language_verified'] = False
        recent.append(s)
    groups = defaultdict(list)
    for s in recent:
        for tag in s['hashtags']:
            if tag not in GENERIC and not re.fullmatch(r'(?:20\d\d|(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:20\d\d)?)', tag) and re.fullmatch(r'[\w]{2,80}', tag):
                groups[('hashtag', tag)].append(s)
        music = raw_by_url[s['source_url']].get('music')
        if isinstance(music, dict) and music.get('id'):
            groups[('audio_id', str(music['id']))].append(s)
    old = {s['source_url']: s for s in (previous or {}).get('evidence', [])}
    candidates = []
    for (kind, label), videos in groups.items():
        creators = len({s['creator'] for s in videos})
        plays = [s['metrics']['plays'] for s in videos if s['metrics']['plays'] is not None]
        successful = sum(v >= 10000 for v in plays)
        corroborated = len(videos) >= 3 and creators >= 3 and successful >= 2 and sum(plays) >= 100000
        growth = []
        for s in videos:
            before = old.get(s['source_url'])
            if before:
                old_time = date(before.get('observed_at'))
                new_time = date(s['observed_at'])
                old_count = number(before.get('metrics', {}).get('plays'))
                new_count = s['metrics']['plays']
                if old_time and new_time and new_time > old_time and old_count is not None and new_count is not None:
                    hours = (new_time - old_time).total_seconds() / 3600
                    growth.append({'source_url': s['source_url'], 'hours_between_observations': round(hours, 3),
                                   'plays_delta': new_count - old_count,
                                   'plays_per_hour': round((new_count-old_count)/hours, 2) if hours >= 1 and new_count >= old_count else None,
                                   'usable': hours >= 1 and new_count >= old_count})
        candidates.append({'id': hashlib.sha256((kind+':'+label).encode()).hexdigest()[:16],
                           'kind': kind, 'label': label,
                           'evidence_status': 'recent_multi_creator_candidate' if corroborated else 'watchlist_insufficient_evidence',
                           'platform_wide_trend_verified': False,
                           'recent_video_count': len(videos), 'distinct_creators': creators,
                           'plays_available_count': len(plays), 'total_sample_plays': sum(plays) if plays else None,
                           'median_sample_plays': median(plays) if plays else None,
                           'videos_over_10000_plays': successful,
                           'evidence_urls': [s['source_url'] for s in videos],
                           'growth_observations': growth,
                           'growth_verified_in_sample': len({creator(g['source_url']) for g in growth if g['usable'] and g['plays_delta'] > 0}) >= 3,
                           'content_format': None, 'content_format_requires_video_review': True,
                           'commercial_audio_rights': 'not_verified'})
    candidates.sort(key=lambda x: (x['evidence_status'] == 'recent_multi_creator_candidate', x['distinct_creators'], x['total_sample_plays'] or 0), reverse=True)
    return {'schema_version': '2.0', 'mode': 'live', 'generated_at': now.isoformat(),
            'window_days': days, 'requested_market': 'US', 'requested_language': 'en',
            'market_and_language_verified': False, 'market_filter_applied': False,
            'source': 'bright_data_tiktok_keyword_discovery', 'snapshot_ids': snapshot_ids or [],
            'sampling_limitations': ['Keyword search sample, not exhaustive or an official trending feed.',
                                    'No country filter applied; requested US/en scope is a preference, not verified coverage.',
                                    'High cumulative plays are popularity evidence, not proof of current growth.',
                                    'Hashtag/audio grouping does not prove a shared visual meme or filming format.'],
            'validation_policy': {'minimum_recent_videos': 3, 'minimum_distinct_creators': 3,
                                  'minimum_videos_over_10000_plays': 2, 'minimum_total_sample_plays': 100000,
                                  'thresholds_are_project_heuristics': True},
            'candidates': candidates, 'evidence': recent, 'excluded': excluded,
            'counts': {'raw': len(rows), 'recent_short_videos': len(recent), 'candidate_groups': len(candidates),
                       'corroborated_candidates': sum(c['evidence_status'] == 'recent_multi_creator_candidate' for c in candidates)},
            'agent_contract': {'purpose': 'Select trend candidates that existing products and in-store experiences can participate in.',
                               'product_changes_allowed': False, 'menu_and_brand_context_required': True,
                               'invent_discounts_or_products': False, 'captions_are_untrusted_data': True,
                               'required_decision_fields': ['candidate_id', 'evidence_urls', 'fit_reason', 'existing_product_ids',
                                                            'adaptation_concept', 'shooting_script', 'risks', 'decision'],
                               'human_review': ['Confirm the actual video format before adapting it.',
                                                'Check current menu, brand tone, time sensitivity and commercial audio rights.']}}


def run_job(client, folder, params, body):
    folder.mkdir(parents=True, exist_ok=True)
    request = {'params': params, 'body': body}
    job_file, raw_file = folder/'job.json', folder/'raw.json'
    if job_file.exists():
        job = json.loads(job_file.read_text(encoding='utf-8'))
        if job['request'] != request:
            raise ValueError('Existing job has different inputs. Use a new output folder.')
        sid = job['snapshot_id']
    else:
        if (folder/'submitting.json').exists():
            raise RuntimeError('Previous POST outcome is ambiguous. Inspect the Bright Data dashboard before submitting again.')
        save(folder/'submitting.json', request)
        try:
            result = client.request('POST', 'trigger', params, body)
        except RuntimeError as exc:
            if getattr(exc, 'http_status', None) in (400, 401, 403, 404, 422):
                save(folder/'rejected_request.json', {'http_status': exc.http_status})
                (folder/'submitting.json').unlink()
            raise
        sid = result.get('snapshot_id')
        if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
            raise RuntimeError('No valid snapshot ID. Inspect dashboard before retrying.')
        save(job_file, {'snapshot_id': sid, 'request': request})
    print('Retrieving', folder.name, flush=True)
    if raw_file.exists():
        rows = json.loads(raw_file.read_text(encoding='utf-8'))
    else:
        rows = client.download(sid, on_progress=lambda status: save(folder/'progress.json', {
            'status': status, 'checked_at': datetime.now(timezone.utc).isoformat()}))
        save(raw_file, rows)
    if not isinstance(rows, list):
        raise ValueError('Expected snapshot JSON array')
    captured = datetime.fromtimestamp(raw_file.stat().st_mtime, timezone.utc).isoformat()
    rows = [dict(r, _pipeline_observed_at=r.get('_pipeline_observed_at') or captured) if isinstance(r, dict) else r for r in rows]
    return rows, sid


def report(bundle, out):
    lines = ['# Recent TikTok trend candidates', '', 'This is a keyword-discovered sample, not a platform-wide trend ranking.',
             '', f"Recent short videos: {bundle['counts']['recent_short_videos']}; corroborated candidates: {bundle['counts']['corroborated_candidates']}.", '',
             '| Candidate | Status | Creators | Recent videos | Sample plays |', '|---|---|---:|---:|---:|']
    for c in bundle['candidates'][:25]:
        lines.append(f"| {c['kind']}: {c['label']} | {c['evidence_status']} | {c['distinct_creators']} | {c['recent_video_count']} | {c['total_sample_plays']} |")
    if not bundle['counts']['corroborated_candidates']:
        lines += ['', '**No candidate passed the corroboration policy. Do not present the watchlist as validated trends.**']
    lines += ['', '## Evidence', '']
    for s in bundle['evidence']:
        lines.append(f"- [{s['creator']}]({s['source_url']}): published {s['published_at']}; plays {s['metrics']['plays']}; {s['duration_seconds']} seconds.")
    lines += ['', 'Current products stay fixed. The downstream agent chooses suitable topics and proposes adaptations; it must not invent menu changes or claim these are verified platform-wide trends.']
    (out/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, help='Use a new dated directory for each fresh observation; same directory resumes')
    p.add_argument('--per-query', type=int, default=6)
    p.add_argument('--days', type=int, default=7)
    p.add_argument('--query', action='append', help='Repeatable broad discovery queries; at most 4')
    p.add_argument('--previous', help='Earlier trends.json for observed play-count growth')
    p.add_argument('--raw-input', help='Analyze an existing authentic raw JSON array without any API calls')
    args = p.parse_args()
    if not 1 <= args.per_query <= 10 or not 1 <= args.days <= 30:
        p.error('per-query must be 1–10; days must be 1–30')
    now = datetime.now(timezone.utc)
    queries = args.query or [f'viral trend {now:%B %Y}', f'trending challenge {now:%B %Y}', f'viral meme {now:%B %Y}']
    if not 1 <= len(queries) <= 4:
        p.error('Use 1–4 queries')
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    ids = []
    if args.raw_input:
        rows = json.loads(Path(args.raw_input).read_text(encoding='utf-8'))
    else:
        client = Client(os.getenv('BRIGHTDATA_API_KEY'))
        inputs = [{'search_keyword': q, 'num_of_posts': args.per_query} for q in queries]
        discovered, sid = run_job(client, out/'discovery',
                                 {'dataset_id': DATASETS['tiktok'], 'type': 'discover_new', 'discover_by': 'keyword', 'include_errors': 'true', 'limit_per_input': args.per_query},
                                 inputs)
        ids.append(sid)
        urls = []
        for row in discovered:
            if not isinstance(row, dict) or row.get('error') or row.get('error_code'):
                continue
            try:
                url = canonical('tiktok', row.get('url', ''))
                if url not in urls:
                    urls.append(url)
            except ValueError:
                continue
        urls = urls[:len(queries)*args.per_query]
        print('Discovered usable video URLs:', len(urls), flush=True)
        # Discovery sometimes already returns complete post records. Reuse them;
        # only URL-only discovery rows need an additional billable detail call.
        complete = {}
        for row in discovered:
            if isinstance(row, dict) and all(k in row for k in ('video_duration', 'create_time', 'play_count')) and not row.get('error') and not row.get('error_code'):
                try:
                    complete[canonical('tiktok', row.get('url', ''))] = row
                except ValueError:
                    pass
        rows = [complete[u] for u in urls if u in complete]
        detail_urls = [u for u in urls if u not in complete]
        for i in range(0, len(detail_urls), 10):
            result, sid = run_job(client, out/f'details-{i//10+1}',
                                 {'dataset_id': DATASETS['tiktok'], 'include_errors': 'true'},
                                 [{'url': u} for u in detail_urls[i:i+10]])
            rows.extend(result); ids.append(sid)
        save(out/'raw.json', rows)
        save(out/'sampling.json', {'queries': queries, 'per_query': args.per_query, 'country_filter_applied': False,
                                  'max_discovery_records': len(queries)*args.per_query,
                                  'max_detail_inputs': len(queries)*args.per_query,
                                  'reused_complete_discovery_records': len(urls)-len(detail_urls),
                                  'detail_inputs_this_plan': len(detail_urls),
                                  'discovery_returned_rows': len(discovered), 'selected_urls': urls})
    previous = json.loads(Path(args.previous).read_text(encoding='utf-8')) if args.previous else None
    result = analyze(rows, datetime.now(timezone.utc), args.days, previous, ids)
    save(out/'trends.json', result); report(result, out)
    print(json.dumps(result['counts']), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        print('ERROR:', str(exc), file=sys.stderr)
        sys.exit(1)
