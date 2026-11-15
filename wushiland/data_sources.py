"""Provider-independent, bounded import of user-supplied short-video evidence."""
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from .brightdata import timestamp

FIELDS = ['platform','source_url','creator','topic','caption','published_at','observed_at','duration_seconds','plays','likes','comments','shares','source_note']

def number(value, required=False):
    if value is None or value == '':
        if required: raise ValueError('duration_seconds is required')
        return None
    if isinstance(value, bool): raise ValueError('metrics must be numbers')
    value=float(value)
    if not math.isfinite(value) or value < 0: raise ValueError('metrics must be finite and nonnegative')
    return value

def import_evidence(content, filename, now=None):
    now=now or datetime.now(timezone.utc)
    if len(content)>2_000_000: raise ValueError('Upload a file smaller than 2 MB.')
    try:
        text=content.decode('utf-8-sig')
        if filename.lower().endswith('.csv'):
            rows=list(csv.DictReader(io.StringIO(text)))
        elif filename.lower().endswith('.json'):
            rows=json.loads(text)
            if isinstance(rows,dict): rows=rows.get('videos')
        else: raise ValueError('Use UTF-8 CSV or JSON; Excel can export CSV UTF-8.')
    except (UnicodeError, json.JSONDecodeError, csv.Error):
        raise ValueError('File could not be read. Use UTF-8 CSV or a JSON videos array.') from None
    if not isinstance(rows,list) or not 1<=len(rows)<=500:
        raise ValueError('Provide 1–500 video records, using the downloadable template.')
    evidence=[]; groups={}; seen=set()
    for index,row in enumerate(rows,1):
        try:
            if not isinstance(row,dict): raise ValueError('expected a video object')
            for name in ('platform','source_url','creator','topic','published_at','observed_at'):
                if not isinstance(row.get(name),str) or not row[name].strip(): raise ValueError(f'{name} is required')
            platform=row['platform'].strip().lower()
            u=urlsplit(row['source_url'].strip())
            if platform=='tiktok':
                valid=u.hostname in ('www.tiktok.com','tiktok.com') and '/video/' in u.path
            elif platform=='instagram':
                valid=u.hostname in ('www.instagram.com','instagram.com') and u.path.startswith('/reel/')
            else: raise ValueError('platform must be tiktok or instagram')
            if not valid or u.scheme!='https' or u.username or u.password or u.port:
                raise ValueError('use a public TikTok video or Instagram Reel HTTPS URL')
            url=urlunsplit(('https',u.hostname,u.path.rstrip('/')+'/', '', ''))
            published=timestamp(row['published_at']); observed=timestamp(row['observed_at'])
            if published>observed or observed>now: raise ValueError('dates must satisfy published <= observed <= now')
            duration=number(row.get('duration_seconds'),True)
            if not 0<duration<=180: raise ValueError('video duration must be 1–180 seconds')
            metrics={k:number(row.get(k)) for k in ('plays','likes','comments','shares')}
            if url in seen: continue
            seen.add(url)
            topic=row['topic'].strip()[:160]
            e={'platform':platform,'source_url':url,'creator':row['creator'].strip()[:160],
               'title':str(row.get('caption') or '')[:200], 'description':str(row.get('caption') or '')[:1200],
               'published_at':published.isoformat(),'observed_at':observed.isoformat(),'duration_seconds':duration,
               'metrics':metrics,'provider':'user_upload','is_fixture':False,
               'source_note':str(row.get('source_note') or '')[:500]}
            evidence.append(e); groups.setdefault((platform,topic),[]).append(e)
        except (ValueError,TypeError,OverflowError) as exc:
            raise ValueError(f'Row {index}: {exc}') from None
    candidates=[]
    for (platform,topic),clips in groups.items():
        creators={e['creator'].lower() for e in clips}
        plays=[e['metrics']['plays'] for e in clips if e['metrics']['plays'] is not None]
        recent=all((now-timestamp(e['published_at'])).total_seconds()<=7*86400 and (now-timestamp(e['observed_at'])).total_seconds()<=7*86400 for e in clips)
        supported=recent and len(creators)>=3 and sum(p>=10000 for p in plays)>=2 and sum(plays)>=100000
        candidates.append({'id':hashlib.sha256((platform+'|'+topic).encode()).hexdigest()[:16],
            'platform':platform,'kind':'supplied_topic','label':topic,'distinct_creators':len(creators),
            'total_sample_plays':sum(plays) if plays else None,'evidence_urls':[e['source_url'] for e in clips],
            'evidence_status':'recent_multi_creator_candidate' if supported else 'watchlist_insufficient_evidence',
            'content_format':None,'content_format_requires_video_review':True,
            'platform_wide_trend_verified':False,'growth_verified_in_sample':False})
    return {'mode':'imported','generated_at':max(timestamp(e['observed_at']) for e in evidence).astimezone(timezone.utc).isoformat(),
            'imported_at':now.isoformat(),'source_kind':'user_upload','discovery_method':'User-supplied topics and video records',
            'evidence':evidence,'candidates':candidates,
            'sampling_limitations':['User-provided metrics, topic grouping and creator identities are not independently verified.',
                'Uploading a file does not refresh its observation dates or establish platform-wide trends.']}
