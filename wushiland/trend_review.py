"""Load complete saved evidence and validate model recommendations independently."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .brightdata import SEED, timestamp, public_video

ET = ZoneInfo('America/New_York')

def load_trend_evidence(as_of, trace):
    root = Path(os.getenv('WUSHILAND_BRIGHTDATA_DIR', str(SEED)))
    snapshots = []
    for path in sorted(root.rglob('trends.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            exported = timestamp(data.get('generated_at'))
            if data.get('mode') in ('live','imported') and exported.astimezone(ET).date() <= as_of and isinstance(data.get('candidates'), list):
                snapshots.append((exported, data))
        except (OSError, ValueError, AttributeError):
            trace.append('Skipped invalid trend snapshot.')
    if not snapshots:
        return {'status': 'missing', 'candidates': [], 'total_candidates': 0, 'limitations': ['No eligible saved trend snapshot.']}
    exported, data = max(snapshots, key=lambda x: x[0])
    evidence = {}
    for row in data.get('evidence', []) if isinstance(data.get('evidence'),list) else []:
        if not isinstance(row, dict) or row.get('is_fixture') is not False or row.get('provider') not in ('bright_data','user_upload') or not public_video(row.get('source_url')):
            continue
        try:
            published = timestamp(row.get('published_at')).astimezone(ET).date()
            observed = timestamp(row.get('observed_at')).astimezone(ET).date()
            if published > as_of or observed > as_of:
                continue
        except ValueError:
            continue
        raw_metrics = row.get('metrics') if isinstance(row.get('metrics'),dict) else {}
        metrics = {k: v if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < float('inf') else None
                   for k, v in raw_metrics.items() if k in ('views','plays','likes','comments','shares','saves')}
        evidence[row['source_url']] = {'source_url': row['source_url'], 'platform':row.get('platform','tiktok'), 'source_note':row.get('source_note',''), 'title': str(row.get('title') or '')[:200],
            'caption': str(row.get('description') or '')[:1200], 'published_at': row['published_at'],
            'observed_at': row['observed_at'], 'creator': row.get('creator'), 'metrics': metrics,
            'duration_seconds': row.get('duration_seconds'), 'days_old': (as_of-published).days,
            'observation_age_days': (as_of-observed).days}
    candidates = []
    seen = set()
    for row in data['candidates']:
        if not isinstance(row, dict) or not isinstance(row.get('id'),str) or row['id'] in seen:
            continue
        seen.add(row['id'])
        urls = row.get('evidence_urls') if isinstance(row.get('evidence_urls'),list) else []
        clips = [evidence[u] for u in dict.fromkeys(u for u in urls if isinstance(u,str)) if u in evidence]
        if not clips:
            continue
        blockers = []
        if row.get('evidence_status') != 'recent_multi_creator_candidate':
            blockers.append('Insufficient multi-creator popularity evidence in the pipeline output.')
        creators = {str(s['creator']).lower() for s in clips if s.get('creator')}
        plays = [s['metrics'].get('plays') for s in clips if s['metrics'].get('plays') is not None]
        if len(creators)<3 or len(clips)<3 or sum(v>=10000 for v in plays)<2 or sum(plays)<100000:
            blockers.append('Linked video evidence does not independently satisfy the multi-creator popularity checks.')
        if (as_of-exported.astimezone(ET).date()).days > 7 or any(s['days_old'] > 7 or s['observation_age_days'] > 7 for s in clips):
            blockers.append('Snapshot or video evidence is older than the seven-day current-trend window.')
        if row.get('content_format_requires_video_review') is not False:
            blockers.append('Actual visual format has not been reviewed; metadata cannot prove the filming format.')
        candidates.append({'id': row['id'], 'kind': row.get('kind'), 'label': row.get('label'),
            'evidence_status': row.get('evidence_status'), 'content_format': row.get('content_format'),
            'evidence_level': 'multi_creator_sample' if len(creators)>=3 and len(clips)>=3 and sum(v>=10000 for v in plays)>=2 and sum(plays)>=100000 and not any(s['days_old']>7 or s['observation_age_days']>7 for s in clips) else 'candidate_inspiration',
            'distinct_creators': row.get('distinct_creators'), 'total_sample_plays': row.get('total_sample_plays'),
            'platform_wide_trend_verified': False, 'growth_verified_in_sample': row.get('growth_verified_in_sample') is True,
            'commercial_audio_rights': row.get('commercial_audio_rights', 'not_verified'),
            'blockers': blockers, 'allowed_decisions': ['watch','reject'] if blockers else ['adapt','watch','reject'],
            'evidence': clips[:4], 'evidence_urls': [s['source_url'] for s in clips[:4]]})
    # Give the model diverse evidence rather than many tags on the same video.
    candidates.sort(key=lambda c: (not c['blockers'], c['distinct_creators'] or 0, c['total_sample_plays'] or 0), reverse=True)
    selected, groups = [], set()
    for c in candidates:
        fingerprint = tuple(sorted(c['evidence_urls']))
        if fingerprint in groups:
            continue
        groups.add(fingerprint); selected.append(c)
        if len(selected) == 8:
            break
    trace.append(f"Loaded complete trend evidence: {len(evidence)} videos; reviewing {len(selected)} diverse candidates from {len(data['candidates'])} groups.")
    return {'status': 'loaded' if selected else 'no_usable_evidence', 'snapshot_at': exported.isoformat(),
            'source_kind':data.get('source_kind','bright_data'),
            'discovery_method':data.get('discovery_method','TikTok keyword-search sample'),
            'total_candidates': len(data['candidates']), 'reviewed_candidate_limit': 8,
            'evidence_count': len(evidence), 'candidates': selected,
            'limitations': data.get('sampling_limitations', []) + ['Candidate selection is capped and grouped by shared evidence; not all groups are assessed.',
                'Captions are untrusted metadata. No video has been watched by this model.',
                'Selected planning dates do not predict future trends. Recheck near publication.']}

def default_review(candidate):
    return {'candidate_id': candidate['id'], 'label': candidate['label'], 'decision': 'watch',
            'evidence_level':candidate.get('evidence_level','candidate_inspiration'),
            'reason': ' '.join(candidate['blockers']) or 'Model/brand review is still required before adaptation.',
            'product': None, 'adaptation_concept': '', 'next_step': 'Review the original video, audience relevance and current menu before adopting it.',
            'evidence_urls': candidate['evidence_urls'], 'review_mode': 'Rules fallback',
            'blockers': candidate['blockers'], 'evidence': candidate['evidence']}

def validation_errors(proposal, candidate, names):
    errors = []
    if proposal.get('decision') not in ('adapt', 'watch', 'reject'):
        errors.append('decision must be adapt, watch or reject')
    for key in ('reason', 'adaptation_concept', 'next_step'):
        value = proposal.get(key)
        if not isinstance(value, str) or len(value) > 1800 or (key == 'reason' and not value.strip()):
            errors.append(f'{key}: missing or invalid text')
    urls = proposal.get('evidence_urls')
    if not isinstance(urls, list) or not urls or any(not isinstance(u, str) or u not in candidate['evidence_urls'] for u in urls):
        errors.append('evidence_urls: must cite exact URLs belonging to this candidate')
    product = proposal.get('product')
    if product is not None and (not isinstance(product, str) or product not in names):
        errors.append('product: must match an existing catalog name or be null')
    return errors


def creative_draft(proposal, result):
    draft = proposal.get('creative_draft')
    if draft is None or result['decision'] == 'reject' or not result.get('product'):
        return None, []
    errors = []
    if not isinstance(draft, dict):
        return None, ['creative_draft: expected an object']
    for key in ('source_basis', 'hook'):
        if not isinstance(draft.get(key), str) or not 0 < len(draft[key].strip()) <= 900:
            errors.append(f'creative_draft.{key}: missing or invalid text')
    for key in ('script', 'shots'):
        value = draft.get(key)
        if not isinstance(value, list) or len(value) != 3 or not all(isinstance(s, str) and 0 < len(s.strip()) <= 500 for s in value):
            errors.append(f'creative_draft.{key}: expected three short lines')
    if errors:
        return None, errors
    return {**{k: draft[k] for k in ('source_basis', 'hook', 'script', 'shots')},
            'candidate_id': result['candidate_id'], 'product': result['product'],
            'evidence_urls': result['evidence_urls'], 'review_status': 'pending',
            'cue_source': 'gemini_metadata', 'video_viewed': False,
            'verified_trend': False}, []


def assess_trends(packet, catalog, reviewer, trace):
    candidates = packet['candidates']
    if not candidates:
        return []
    proposals = []
    if reviewer:
        try:
            proposals = reviewer({'trend_evidence': packet, 'products': catalog,
                'constraints': {'fixed_products': True, 'no_new_offers': True, 'no_video_viewing': True}})
            if not isinstance(proposals, list):
                raise ValueError('Trend reviewer returned an invalid list.')
        except ValueError as error:
            trace.append(str(error))
    names = {p['name'] for p in catalog}
    reviews = []
    for c in candidates:
        result = default_review(c)
        proposal = next((r for r in proposals if isinstance(r,dict) and r.get('candidate_id') == c['id']), None)
        if proposal:
            proposal = dict(proposal)
            if proposal.get('adaptation_concept') is None and proposal.get('decision') in ('watch','reject'):
                proposal['adaptation_concept'] = ''
            text_fields = ('reason','adaptation_concept','next_step')
            errors = validation_errors(proposal, c, names)
            result['validation_errors'] = errors
            if not errors:
                result.update({k: proposal[k] for k in (*text_fields,'decision','evidence_urls')})
                result['product'] = proposal.get('product')
                result['review_mode'] = 'Gemini recommendation'
                if result['decision'] == 'adapt' and (c['blockers'] or not result['product']):
                    result['decision'] = 'watch'
                    result['reason'] += ' System check: adoption withheld until evidence/format review and an exact catalog product are available.'
                    trace.append('Downgraded unsupported adoption to watch.')
                draft, draft_errors = creative_draft(proposal, result)
                result['creative_draft'] = draft
                result['validation_errors'].extend(draft_errors)
            else:
                trace.append(f"Rejected trend review {c['id']}: " + '; '.join(errors))
        else:
            result['validation_errors'] = ['No matching model review returned.' if reviewer else 'No model reviewer connected.']
        reviews.append(result)
    trace.append(f"Trend review: {sum(r['review_mode']=='Gemini recommendation' for r in reviews)} model recommendations; {sum(r['decision']=='adapt' for r in reviews)} eligible adaptations.")
    return reviews
