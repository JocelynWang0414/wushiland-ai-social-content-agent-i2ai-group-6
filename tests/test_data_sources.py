import csv
import io
import json
import os
import unittest
from datetime import datetime, timezone, date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from wushiland.app import Handler
from wushiland.data_sources import import_evidence, FIELDS
from wushiland.app import Application
from wushiland.agent import generate
from wushiland.trend_review import load_trend_evidence

NOW=datetime(2026,11,14,12,tzinfo=timezone.utc)

def row(i=1,platform='tiktok'):
    return {'platform':platform,'source_url':f'https://www.tiktok.com/@creator{i}/video/{10000+i}/' if platform=='tiktok' else f'https://www.instagram.com/reel/code{i}/',
            'creator':f'creator{i}','topic':'shared routine','caption':'A staff routine',
            'published_at':'2026-11-13T10:00:00Z','observed_at':'2026-11-14T10:00:00Z',
            'duration_seconds':20,'plays':50000}

class SourceTests(unittest.TestCase):
    def test_browser_multipart_upload_and_csrf(self):
        with TemporaryDirectory() as d,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
            server.app=Application(d)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                template=urlopen(base+'/template.csv').read().decode()
                self.assertIn('observed_at',template)
                for token,accepted in [('wrong',False),(server.app.csrf,True)]:
                    body=(f'--BOUNDARY\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{token}\r\n'
                          '--BOUNDARY\r\nContent-Disposition: form-data; name="file"; filename="videos.json"\r\nContent-Type: application/json\r\n\r\n'
                          +json.dumps([row()])+'\r\n--BOUNDARY--\r\n').encode()
                    request=Request(base+'/upload',data=body,headers={'Content-Type':'multipart/form-data; boundary=BOUNDARY'})
                    with patch('wushiland.app.import_evidence',side_effect=lambda content,name: import_evidence(content,name,NOW)):
                        if accepted:
                            page=urlopen(request).read().decode()
                            self.assertIn('Ready: 1 video records',page)
                            self.assertIn('value="uploaded" selected',page)
                        else:
                            with self.assertRaises(HTTPError) as error:urlopen(request)
                            self.assertEqual(error.exception.code,403)
                            self.assertFalse((Path(d)/'uploaded.json').exists())
            finally:
                server.shutdown();thread.join()

    def test_json_csv_equivalence_and_duplicate_removal(self):
        r=row(); out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=FIELDS);writer.writeheader();writer.writerow(r)
        a=import_evidence(json.dumps([r,r]).encode(),'data.json',NOW)
        b=import_evidence(out.getvalue().encode(),'data.csv',NOW)
        self.assertEqual(a['evidence'],b['evidence'])
        self.assertEqual(len(a['evidence']),1)
        self.assertEqual(a['source_kind'],'user_upload')

    def test_reject_bad_dates_metrics_platform_and_duration(self):
        for update in [{'observed_at':'2099-01-01T00:00:00Z'},{'plays':'NaN'},{'platform':'youtube'},{'source_url':'https://example.com/video/x'},{'duration_seconds':900},{'creator':''}]:
            with self.subTest(update=update),self.assertRaises(ValueError):
                import_evidence(json.dumps([{**row(),**update}]).encode(),'data.json',NOW)

    def test_instagram_creators_not_reel_ids_and_platforms_not_combined(self):
        rows=[row(i,'instagram') for i in range(1,4)]+[row(4)]
        data=import_evidence(json.dumps(rows).encode(),'data.json',NOW)
        self.assertEqual(len(data['candidates']),2)
        with TemporaryDirectory() as d,patch.dict(os.environ,{'WUSHILAND_BRIGHTDATA_DIR':d}):
            Path(d,'trends.json').write_text(json.dumps(data))
            packet=load_trend_evidence(date(2026,11,14),[])
            self.assertEqual(packet['source_kind'],'user_upload')
            self.assertEqual(packet['candidates'][0]['evidence_level'],'multi_creator_sample')
            self.assertIn('instagram',[e['platform'] for e in packet['candidates'][0]['evidence']])
        for r in rows:r['creator']='same_creator'
        data=import_evidence(json.dumps(rows).encode(),'data.json',NOW)
        self.assertTrue(all(c['evidence_status']=='watchlist_insufficient_evidence' for c in data['candidates']))

    def test_import_does_not_freshen_old_observations(self):
        r=row();r.update(published_at='2020-01-01T00:00:00Z',observed_at='2020-01-02T00:00:00Z')
        data=import_evidence(json.dumps([r]).encode(),'data.json',NOW)
        self.assertTrue(data['generated_at'].startswith('2020'))

    def test_upload_job_never_calls_collector(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEY':'TEST_ONLY','BRIGHTDATA_API_KEY':''}),patch('wushiland.app.threading.Thread'):
            app=Application(d)
            with patch('wushiland.app.import_evidence',side_effect=lambda content,name: import_evidence(content,name,NOW)):
                app.save_upload(json.dumps([row()]).encode(),'videos.json')
            key=app.create('2099-01-01',source='uploaded')
            self.assertFalse(app.jobs[key]['refresh'])
            def fake_generate(*args,**kwargs):
                packet=load_trend_evidence(date(2026,11,14),[])
                self.assertEqual(packet['source_kind'],'user_upload')
                return {'trend_evidence':packet}
            with patch('wushiland.app.generate',side_effect=fake_generate),patch('wushiland.app.subprocess.run') as collector:
                app.work(key,date(2099,1,1),False)
                collector.assert_not_called()
            self.assertEqual(app.jobs[key]['status'],'done')
            self.assertIn('No Bright Data call',app.jobs[key]['result']['data_note'])

    def test_missing_upload_is_actionable(self):
        with TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Upload a CSV'):
                Application(d).create('2099-01-01',source='uploaded')
