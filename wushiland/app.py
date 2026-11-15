"""Interactive loopback app: saved-data generation or bounded online refresh."""
from datetime import date, datetime, timezone
from html import escape
from http.server import ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit
from .agent import ET, generate
from .llm import plan, review_trends, MODEL
from .web import Handler as BaseHandler, render
from .data_sources import import_evidence, FIELDS

ROOT = Path(__file__).resolve().parent.parent

class Application:
    def __init__(self, runtime=None):
        self.runtime = Path(runtime or ROOT/'runtime')
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.lock = threading.Lock()
        self.csrf = secrets.token_urlsafe(24)
        for path in self.runtime.glob('*-state.json'):
            try:
                state=json.loads(path.read_text(encoding='utf-8'))
                key=path.name.removesuffix('-state.json')
                if not re.fullmatch(r'[a-f0-9]{20}',key):continue
                if state.get('status')=='running':
                    state.update(status='waiting',message='The local app restarted. Continue the saved task without a new collection.')
                self.jobs[key]=state
                result_path=self.runtime/(key+'-result.json')
                if state.get('status')=='done' and result_path.exists():
                    state['result']=json.loads(result_path.read_text(encoding='utf-8'))
            except (OSError,ValueError):pass

    def persist(self,key):
        state={k:v for k,v in self.jobs[key].items() if k!='result'}
        path=self.runtime/(key+'-state.json')
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state),encoding='utf-8')
        temporary.replace(path)

    def recent_snapshot(self):
        """Reuse only a complete live snapshot collected within 24 hours."""
        try:
            latest=json.loads((self.runtime/'latest.json').read_text(encoding='utf-8'))
            data=json.loads((Path(latest['capture_dir'])/'trends.json').read_text(encoding='utf-8'))
            stamp=datetime.fromisoformat(data['generated_at'].replace('Z','+00:00'))
            age=(datetime.now(timezone.utc)-stamp).total_seconds()
            return (data.get('mode')=='live' and 0 <= age < 86400
                    and isinstance(data.get('evidence'),list) and bool(data['evidence'])
                    and isinstance(data.get('candidates'),list))
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            return False

    def save_upload(self, content, filename):
        data=import_evidence(content,filename)
        with self.lock:
            if any(j['status']=='running' for j in self.jobs.values()):
                raise ValueError('Wait for the current job before replacing uploaded data.')
            folder=self.runtime/('upload-'+secrets.token_hex(8)); folder.mkdir()
            (folder/'trends.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            (self.runtime/'uploaded.json').write_text(json.dumps({'capture_dir':str(folder.resolve()),'records':len(data['evidence']),'snapshot_at':data['generated_at']}),encoding='utf-8')
        return data

    def create(self, start, refresh=None, model=None, resume_key=None, source=None):
        model = (model or os.getenv('WUSHILAND_GEMINI_MODEL',MODEL)).strip().removeprefix('models/')
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}',model):
            raise ValueError('Enter a valid Gemini model ID.')
        week = date.fromisoformat(start)
        from datetime import timedelta
        if week + timedelta(days=6) < datetime.now(ET).date():
            raise ValueError('Choose a week containing today or a future date. Historical replay needs a saved historical snapshot.')
        with self.lock:
            if source not in (None,'uploaded','online'):
                raise ValueError('Choose uploaded data or online TikTok discovery.')
            imported_folder=None
            if source=='uploaded':
                try:
                    imported_folder=Path(json.loads((self.runtime/'uploaded.json').read_text(encoding='utf-8'))['capture_dir'])
                    if not imported_folder.resolve().is_relative_to(self.runtime.resolve()) or not (imported_folder/'trends.json').exists():
                        raise ValueError('Uploaded data is missing. Upload the file again.')
                except (OSError,KeyError,ValueError):
                    raise ValueError('Upload a CSV or JSON video file under Data sources first.') from None
                if not os.getenv('GEMINI_API_KEY'):
                    raise ValueError('Connect Gemini to analyze the uploaded data. Bright Data is not required.')
                for existing_key, existing in self.jobs.items():
                    if existing['status']=='running': return existing_key
                refresh=False
            if refresh is None:
                for existing_key, existing in self.jobs.items():
                    if existing['status']=='running':
                        return existing_key
                waiting=next(((k,j) for k,j in self.jobs.items() if j['status']=='waiting' and j.get('capture_dir')),None)
                if waiting:
                    resume_key=waiting[0]
                    refresh=True
                else:
                    refresh=not self.recent_snapshot()
            if any(j['status']=='running' for j in self.jobs.values()):
                raise ValueError('A job is already running. Open its progress page instead of starting another collection.')
            if refresh and not resume_key and any(j['status']=='waiting' for j in self.jobs.values()):
                raise ValueError('A saved collection is still waiting. Use Continue saved collection below to avoid another paid submission.')
            if refresh and (not os.getenv('BRIGHTDATA_API_KEY') or not os.getenv('GEMINI_API_KEY')):
                raise ValueError('Online discovery needs Bright Data and Gemini. Alternatively upload your own video data; Bright Data is optional for uploads.')
            if resume_key:
                saved=self.jobs.get(resume_key)
                if not saved or saved.get('status') not in ('waiting','failed') or not saved.get('capture_dir'):
                    raise ValueError('No resumable collection was found.')
                folder=Path(saved['capture_dir']).resolve()
                if not folder.is_relative_to(self.runtime.resolve()) or not (folder/'discovery'/'job.json').exists():
                    raise ValueError('The saved collection cannot be resumed safely.')
                key=resume_key
            else:
                key=secrets.token_hex(10)
            os.environ['WUSHILAND_GEMINI_MODEL']=model
            self.jobs[key]={'status':'running','start':start,'refresh':refresh,'model':model,'message':'Preparing the selected week.',
                            'started_at':datetime.now(timezone.utc).isoformat()}
            if resume_key:self.jobs[key]['capture_dir']=str(folder)
            if imported_folder:self.jobs[key]['input_dir']=str(imported_folder.resolve())
            self.jobs[key]['source_kind']='user_upload' if imported_folder else 'bright_data'
            self.persist(key)
        threading.Thread(target=self.work,args=(key,week,refresh),daemon=True).start()
        return key

    def work(self, key, week, refresh):
        job=self.jobs[key]
        previous=os.environ.get('WUSHILAND_BRIGHTDATA_DIR')
        try:
            if refresh:
                folder=Path(job['capture_dir']) if job.get('capture_dir') else self.runtime/('capture-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+key)
                job['message']='Collecting new TikTok candidates online. This can take several minutes; this page updates automatically.'
                job['capture_dir']=str(folder)
                self.persist(key)
                command=[sys.executable,'-m','wushiland.ingest.trends','--out',str(folder),'--per-query','6']
                saved_job=folder/'discovery'/'job.json'
                if saved_job.exists():
                    request=json.loads(saved_job.read_text(encoding='utf-8'))['request']
                    for entry in request['body']:command.extend(['--query',entry['search_keyword']])
                process=subprocess.run(command,
                    cwd=ROOT,env=os.environ.copy(),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1500)
                if process.returncode:
                    if 'Polling timed out' in (process.stderr or ''):
                        job.update(status='waiting',message='The 10-minute local wait ended; the provider job may still be running. Continue the saved collection to check again, without submitting a new job.')
                        return
                    # Only code/error class, never provider bodies, credentials or full stdout.
                    raise ValueError('Collection did not complete. The saved task can be inspected; no old data was substituted for this refresh.')
                if not (folder/'trends.json').exists():
                    raise ValueError('Collection produced no trend report.')
                os.environ['WUSHILAND_BRIGHTDATA_DIR']=str(folder)
                job['message']='New data saved. Gemini is reviewing evidence and drafting recommendations.'
            else:
                latest=self.runtime/'latest.json'
                if job.get('input_dir'):
                    os.environ['WUSHILAND_BRIGHTDATA_DIR']=job['input_dir']
                elif latest.exists():
                    folder=Path(json.loads(latest.read_text())['capture_dir'])
                    os.environ['WUSHILAND_BRIGHTDATA_DIR']=str(folder)
                job['message']='Reading saved evidence and generating recommendations for the selected week.'
            has_key=bool(os.getenv('GEMINI_API_KEY'))
            result=generate(week,planner=plan if has_key else None,reviewer=review_trends if has_key else None)
            result['refresh_requested']=refresh
            result['requested_model']=job.get('model',os.getenv('WUSHILAND_GEMINI_MODEL',MODEL))
            result['data_note']='Collected now, for planning this selected week; not a reconstruction of what was known on the week start.' if refresh else 'Uses the latest saved eligible snapshot; no new collection was requested.'
            if job.get('input_dir'):
                result['data_note']='Analyzed your uploaded video records. No Bright Data call. Dates and metrics are user-supplied, not independently verified.'
            path=self.runtime/(key+'-result.json')
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            if refresh:
                (self.runtime/'latest.json').write_text(json.dumps({'capture_dir':str(folder)}),encoding='utf-8')
            job.update(status='done',result=result,message='Completed.')
        except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
            message=str(exc) if isinstance(exc,ValueError) else 'Job timed out or encountered a local error. Do not repeat a collection blindly; its saved task may still be running.'
            job.update(status='failed',message=message)
        except Exception:
            job.update(status='failed',message='Unexpected processing error. No successful model result is claimed.')
        finally:
            self.persist(key)
            if previous is None:os.environ.pop('WUSHILAND_BRIGHTDATA_DIR',None)
            else:os.environ['WUSHILAND_BRIGHTDATA_DIR']=previous


class Handler(BaseHandler):
    def log_message(self,*args):
        pass

    def page(self, start='', result=None, error=''):
        page=render(start,result,error)
        page=page.replace('<form method="post">','<form method="post" action="/">')
        connected=lambda name:'Connected in this server session' if os.getenv(name) else 'Not connected'
        uploaded=(self.server.app.runtime/'uploaded.json').exists()
        controls=f'''<input type="hidden" name="csrf" value="{self.server.app.csrf}">
<label for="source">Data source</label><select id="source" name="source">
<option value="uploaded" {'selected' if uploaded else ''}>My uploaded video data (TikTok / Instagram)</option>
<option value="online" {'' if uploaded else 'selected'}>Online TikTok discovery (Bright Data)</option></select>
<details><summary>Model settings</summary><label for="model">Gemini model</label><input id="model" name="model" value="{escape(os.getenv('WUSHILAND_GEMINI_MODEL',MODEL),quote=True)}" pattern="[a-zA-Z0-9_.-]+" required>
<small>Enter the exact Gemini model ID used in your other project. Availability and quota depend on your API account. Changing this affects analysis and drafting, not collection speed.</small>
</details><div class="actions"><button type="submit" name="action" value="auto">Generate weekly recommendations</button></div>
<p>Uploads use your file only. Online discovery reuses data from the last 24 hours or collects when needed. Analysis uses Gemini; only online collection needs Bright Data.</p>
<small>The date selects your planning week. Data is observed today, not backdated. A week starting November 11 covers November 11–17.</small>'''
        page=page.replace('<div class="actions"><button type="submit">Generate briefs</button></div>\n<small>Try April 12, 2027 for a Spring Carnival example.</small>',controls)
        keys=f'''<details><summary>API connections</summary><p>Bright Data: {connected('BRIGHTDATA_API_KEY')}<br>Gemini: {connected('GEMINI_API_KEY')}</p>
<form method="post" action="/keys"><input type="hidden" name="csrf" value="{self.server.app.csrf}">
<label>Gemini API key (leave blank to keep current)</label><input type="password" name="gemini" autocomplete="off">
<label>Bright Data API key (leave blank to keep current)</label><input type="password" name="brightdata" autocomplete="off">
<button type="submit">Connect for this session</button><p>Keys stay in server memory. They are not written into result files or sent to the browser again.</p></form></details>'''
        page=page.replace('<h1>Wushiland Weekly Briefs</h1>','<h1>Wushiland Weekly Briefs</h1>'+keys)
        upload_status='No file uploaded yet.'
        if uploaded:
            try:
                info=json.loads((self.server.app.runtime/'uploaded.json').read_text(encoding='utf-8'))
                upload_status=f"Ready: {info['records']} video records. Last observation: {info['snapshot_at']}."
            except (OSError,ValueError,KeyError): upload_status='Please upload your file again.'
        upload_form=f'''<details><summary>Data sources — upload your own data</summary>
<p>{escape(upload_status)}</p><p>Use video links, topics, captions, dates and metrics. No Bright Data key needed. Sales or inventory files are not video trend evidence.</p>
<p><a href="/template.csv">Download CSV column template</a>. Excel: export CSV UTF-8. JSON: array of the same fields. Maximum 500 videos / 2 MB. All records are checked before saving.</p>
<form method="post" action="/upload" enctype="multipart/form-data">
<input type="hidden" name="csrf" value="{self.server.app.csrf}">
<input type="file" name="file" accept=".csv,.json" required><button>Use this file</button></form>
<p>Required: platform, source_url, creator, topic, published_at, observed_at, duration_seconds. Dates need a timezone, e.g. 2026-11-14T00:00:00-05:00. Unknown metrics can be blank. Captions and topics are sent to Gemini when you generate.</p></details>'''
        page=page.replace('<p>Choose a seven-day window',upload_form+'<p>Choose a seven-day window')
        if result:
            page=page.replace('<h2>Briefs for',f"<p>{escape(result.get('data_note',''))}</p><p>Requested model: {escape(result.get('requested_model',MODEL))}</p><h2>Briefs for")
        pending=''
        for key,job in self.server.app.jobs.items():
            if job.get('status')=='waiting':
                pending+='<p>A collection is waiting. Use Generate weekly recommendations to continue it without submitting a new collection.</p>'
        page=page.replace('</main>',pending+'</main>')
        return page

    def do_GET(self):
        if self.path=='/template.csv':
            body=(','.join(FIELDS)+'\r\n').encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8')
            self.send_header('Content-Disposition','attachment; filename="video-evidence-template.csv"')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if self.path=='/':
            self.reply(self.page(str(datetime.now(ET).date())));return
        if self.path.startswith('/jobs/'):
            key=self.path.split('/')[-1]
            job=self.server.app.jobs.get(key)
            if job is None:self.send_error(404);return
            if job['status']=='done':
                self.reply(self.page(job['start'],job['result']));return
            if job['status']=='failed':
                self.reply(self.page(job['start'],error=job['message']));return
            if job['status']=='waiting':
                self.reply(self.page(job['start'],error=job['message']));return
            elapsed=''
            if job.get('started_at'):
                minutes=int((datetime.now(timezone.utc)-datetime.fromisoformat(job['started_at'])).total_seconds()/60)
                elapsed=f' Local wait: {minutes} minute(s).'
            if job.get('capture_dir'):
                progress=Path(job['capture_dir'])/'discovery'/'progress.json'
                try:
                    status=json.loads(progress.read_text())['status']
                    elapsed+=' Provider status: '+str(status)+'.'
                except (OSError,ValueError,KeyError):pass
            self.reply('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="5"><title>Processing</title></head><body style="font:18px system-ui;padding:40px"><h1>Working on your weekly brief</h1><p>'+escape(job['message']+elapsed)+'</p><p>Planning week starts '+escape(job['start'])+'. Do not submit another refresh; this page checks progress automatically.</p></body></html>');return
        self.send_error(404)

    def do_POST(self):
        if self.path not in ('/','/keys','/upload'):
            self.send_error(404);return
        origin=self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            self.send_error(403);return
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:self.send_error(400);return
        if self.path=='/upload':
            if not 0<length<=2_100_000:self.send_error(400,'Upload must be under 2 MB.');return
            from email.parser import BytesParser
            from email.policy import default
            try:
                content_type=self.headers.get('Content-Type','')
                if not content_type.startswith('multipart/form-data'):raise ValueError('Choose a CSV or JSON file.')
                message=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+self.rfile.read(length))
                parts={p.get_param('name',header='content-disposition'):p for p in message.iter_parts()}
                token=parts['csrf'].get_payload(decode=True).decode('utf-8')
                if not secrets.compare_digest(token,self.server.app.csrf):self.send_error(403);return
                part=parts['file']; self.server.app.save_upload(part.get_payload(decode=True),part.get_filename() or '')
            except (ValueError,KeyError,TypeError,UnicodeError) as exc:
                self.reply(self.page(error=str(exc)),400);return
            self.send_response(303);self.send_header('Location','/');self.end_headers();return
        if not 0<length<=16000:self.send_error(400);return
        form=parse_qs(self.rfile.read(length).decode('utf-8'))
        if not secrets.compare_digest(form.get('csrf',[''])[0],self.server.app.csrf):
            self.send_error(403);return
        if self.path=='/keys':
            with self.server.app.lock:
                if any(j['status']=='running' for j in self.server.app.jobs.values()):
                    self.reply(self.page(error='Wait for the current job before changing connections.'),409);return
                for field,name in [('gemini','GEMINI_API_KEY'),('brightdata','BRIGHTDATA_API_KEY')]:
                    value=form.get(field,[''])[0].strip()
                    if value:os.environ[name]=value
            self.send_response(303);self.send_header('Location','/');self.end_headers();return
        start=form.get('start',[''])[0]
        try:
            action=form.get('action',['auto'])[0]
            if action not in ('auto','saved','refresh','resume'):raise ValueError('Unknown action.')
            key=self.server.app.create(start,None if action=='auto' else action in ('refresh','resume'),form.get('model',[None])[0],form.get('resume_key',[None])[0] if action=='resume' else None,source=form.get('source',[None])[0])
        except ValueError as exc:
            self.reply(self.page(start,error=str(exc)),400);return
        self.send_response(303);self.send_header('Location','/jobs/'+key);self.end_headers()

def serve(port=0, open_browser=True):
    import webbrowser
    with ThreadingHTTPServer(('127.0.0.1',port),Handler) as server:
        server.app=Application()
        url=f'http://127.0.0.1:{server.server_port}'
        (server.app.runtime/'server.json').write_text(json.dumps({'url':url}),encoding='utf-8')
        print('Open '+url,flush=True)
        if open_browser:webbrowser.open(url)
        server.serve_forever()

if __name__=='__main__':serve()
