import json
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from wushiland.app import Application, Handler
from wushiland.agent import generate

class OnlineAppTests(unittest.TestCase):
    def test_auto_reuses_recent_snapshot_and_refreshes_expired(self):
        from datetime import datetime, timezone, timedelta
        with TemporaryDirectory() as d,patch.dict(os.environ,{'BRIGHTDATA_API_KEY':'test','GEMINI_API_KEY':'test'}),patch('wushiland.app.threading.Thread'):
            app=Application(d); folder=Path(d)/'capture'; folder.mkdir()
            (Path(d)/'latest.json').write_text(json.dumps({'capture_dir':str(folder)}))
            for hours,expected in [(1,False),(25,True),(-1,True)]:
                app.jobs.clear()
                (folder/'trends.json').write_text(json.dumps({'mode':'live','generated_at':(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(),'evidence':[{}],'candidates':[]}))
                key=app.create('2099-01-01')
                self.assertEqual(app.jobs[key]['refresh'],expected)

    def test_auto_missing_snapshot_and_duplicate_click(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'BRIGHTDATA_API_KEY':'test','GEMINI_API_KEY':'test'}),patch('wushiland.app.threading.Thread') as worker:
            app=Application(d)
            key=app.create('2099-01-01')
            self.assertTrue(app.jobs[key]['refresh'])
            self.assertEqual(app.create('2099-01-01'),key)
            self.assertEqual(worker.call_count,1)

    def test_auto_resumes_waiting_collection(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'BRIGHTDATA_API_KEY':'test','GEMINI_API_KEY':'test'}),patch('wushiland.app.threading.Thread'):
            app=Application(d); folder=Path(d)/'capture'; (folder/'discovery').mkdir(parents=True)
            (folder/'discovery'/'job.json').write_text('{}')
            app.jobs['a'*20]={'status':'waiting','capture_dir':str(folder),'start':'2099-01-01'}
            key=app.create('2099-01-02')
            self.assertEqual(key,'a'*20)
            self.assertEqual(app.jobs[key]['capture_dir'],str(folder.resolve()))
            self.assertEqual(app.jobs[key]['start'],'2099-01-02')

    def test_timeout_is_resumable_and_survives_restart(self):
        with TemporaryDirectory() as d:
            app=Application(d);app.jobs['a'*20]={'status':'running','start':'2026-11-11'}
            with patch('wushiland.app.subprocess.run') as run,patch('wushiland.app.generate') as drafting:
                run.return_value.returncode=1
                run.return_value.stderr='ERROR: Polling timed out. Job may still run.'
                app.work('a'*20,date(2026,11,11),True)
                drafting.assert_not_called()
            self.assertEqual(app.jobs['a'*20]['status'],'waiting')
            restored=Application(d)
            self.assertEqual(restored.jobs['a'*20]['status'],'waiting')

    def test_resume_reuses_capture_folder_and_model(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'BRIGHTDATA_API_KEY':'test','GEMINI_API_KEY':'test'}):
            app=Application(d);folder=Path(d,'capture');(folder/'discovery').mkdir(parents=True)
            (folder/'discovery'/'job.json').write_text('{}')
            app.jobs['a'*20]={'status':'waiting','start':'2099-01-01','capture_dir':str(folder)}
            with patch('wushiland.app.threading.Thread') as thread:
                key=app.create('2099-01-01',True,'gemini-3-flash-preview','a'*20)
                thread.return_value.start.assert_called_once()
            self.assertEqual(key,'a'*20)
            self.assertEqual(app.jobs[key]['capture_dir'],str(folder.resolve()))

    def test_november_11_week_can_be_generated_on_13(self):
        r=generate(date(2026,11,11),as_of=date(2026,11,13))
        self.assertEqual(r['end'],'2026-11-17')
        self.assertEqual(len(r['briefs']),3)
        self.assertTrue(all(b['posting_time'][:10]>='2026-11-13' for b in r['briefs']))

    def test_refresh_uses_new_output_then_model(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'BRIGHTDATA_API_KEY':'test','GEMINI_API_KEY':'test'}):
            app=Application(d);app.jobs['test']={'status':'running'}
            def collect(command,**kwargs):
                folder=Path(command[command.index('--out')+1]);folder.mkdir()
                (folder/'trends.json').write_text('{}')
                self.assertEqual(command[-2:],['--per-query','6'])
                class Result:returncode=0
                return Result()
            def drafting(week,**kwargs):
                self.assertTrue(Path(os.environ['WUSHILAND_BRIGHTDATA_DIR'],'trends.json').exists())
                self.assertIsNotNone(kwargs['reviewer'])
                return {'start':str(week)}
            with patch('wushiland.app.subprocess.run',side_effect=collect),patch('wushiland.app.generate',side_effect=drafting):
                app.work('test',date(2026,11,11),True)
            self.assertEqual(app.jobs['test']['status'],'done')
            self.assertTrue(Path(d,'latest.json').exists())

    def test_refresh_failure_does_not_fall_back_to_old_data(self):
        with TemporaryDirectory() as d:
            app=Application(d);app.jobs['test']={'status':'running'}
            with patch('wushiland.app.subprocess.run') as run,patch('wushiland.app.generate') as generate_mock:
                run.return_value.returncode=1
                app.work('test',date(2026,11,11),True)
                generate_mock.assert_not_called()
            self.assertEqual(app.jobs['test']['status'],'failed')

    def test_missing_keys_and_duplicate_jobs_blocked(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEY':'','BRIGHTDATA_API_KEY':''}):
            app=Application(d)
            with self.assertRaises(ValueError):app.create('2099-01-01',True)
            app.jobs['existing']={'status':'running'}
            with self.assertRaises(ValueError):app.create('2099-01-01',False)

    def test_http_form_routes_back_home_and_keys_not_echoed(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'GEMINI_API_KEY':'','BRIGHTDATA_API_KEY':''}):
            with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
                server.app=Application(d)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base=f'http://127.0.0.1:{server.server_port}'
                try:
                    page=urlopen(base).read().decode()
                    self.assertIn('Generate weekly recommendations',page)
                    self.assertNotIn('Refresh online + generate',page)
                    self.assertNotIn('Generate from saved data',page)
                    self.assertIn('<form method="post" action="/">',page)
                    body=urlencode({'csrf':server.app.csrf,'gemini':'LOCAL_TEST_NOT_A_REAL_KEY'}).encode()
                    response=urlopen(Request(base+'/keys',data=body)).read().decode()
                    self.assertNotIn('LOCAL_TEST_NOT_A_REAL_KEY',response)
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(Request(base+'/keys',data=b'gemini=unauthorized'))
                    self.assertEqual(caught.exception.code,403)
                finally:server.shutdown();thread.join()

if __name__=='__main__':unittest.main()
