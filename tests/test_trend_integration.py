import json
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from wushiland.agent import generate, load
from wushiland.trend_review import load_trend_evidence, assess_trends
from wushiland.web import render

DAY=date(2026,11,13)

def proposal(c,decision='watch'):
    return {'candidate_id':c['id'],'decision':decision,'reason':'Metadata suggests a possible topic, but evidence and video review are insufficient.',
            'product':'Boba Milk Tea','adaptation_concept':'Provisional customer reaction idea using the existing drink.',
            'next_step':'Review the original video before choosing a format.','evidence_urls':c['evidence_urls'][:1]}

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"WUSHILAND_BRIGHTDATA_DIR": str(Path(__file__).parent / "fixtures")})
        env.start()
        self.addCleanup(env.stop)

    def packet(self):
        return load_trend_evidence(DAY,[])

    def test_full_evidence_reaches_reviewer_and_planner(self):
        seen=[]
        def reviewer(context):
            p=context['trend_evidence']
            self.assertEqual(p['evidence_count'],12)
            self.assertTrue(any('test-topic' in str(c['label']) for c in p['candidates']))
            for c in p['candidates']:
                self.assertIn('plays',c['evidence'][0]['metrics'])
                self.assertIn('published_at',c['evidence'][0])
            return [proposal(c) for c in p['candidates']]
        def planner(evidence,*args):
            seen.append(evidence)
            self.assertEqual(len(evidence['trend_reviews']),8)
            self.assertEqual(evidence['trend_evidence']['evidence_count'],12)
            return []
        result=generate(DAY,as_of=DAY,reviewer=reviewer,planner=planner)
        self.assertTrue(seen)
        self.assertEqual(len(result['briefs']),3)
        self.assertTrue(all(r['review_mode']=='Gemini recommendation' for r in result['trend_reviews']))

    def test_unsupported_adoption_downgraded(self):
        p=self.packet()
        reviews=assess_trends(p,load('products'),lambda _: [proposal(c,'adapt') for c in p['candidates']],[])
        self.assertTrue(all(r['decision']=='watch' for r in reviews))

    def test_watchlist_can_have_pending_storyboard_without_adoption(self):
        p=self.packet(); r=proposal(p['candidates'][0], 'adapt')
        r['creative_draft']={'source_basis':'Caption topic only; visual joke unknown.',
            'hook':'<script>Tea break</script>', 'script':['Set up','Show drink','React'],
            'shots':['Counter','Cup','Consenting staff']}
        reviews=assess_trends(p,load('products'),lambda _: [r],[])
        item=reviews[0]
        self.assertEqual(item['decision'],'watch')
        self.assertEqual(item['creative_draft']['review_status'],'pending')
        self.assertFalse(item['creative_draft']['video_viewed'])
        self.assertEqual(item['creative_draft']['evidence_urls'],r['evidence_urls'])
        result=generate(DAY,as_of=DAY)
        result['trend_reviews']=reviews
        page=render(str(DAY),result)
        self.assertIn('Evergreen alternatives',page)
        self.assertIn('pending staff review',page)
        self.assertNotIn('<script>Tea break</script>',page)

    def test_bad_storyboard_does_not_discard_valid_review(self):
        p=self.packet(); r=proposal(p['candidates'][0])
        r['creative_draft']={'source_basis':'caption','hook':'Tea','script':['one'],'shots':[]}
        item=assess_trends(p,load('products'),lambda _: [r],[])[0]
        self.assertEqual(item['review_mode'],'Gemini recommendation')
        self.assertIsNone(item['creative_draft'])
        self.assertTrue(any('script' in e for e in item['validation_errors']))

    def test_invalid_source_has_specific_diagnostic_and_no_draft(self):
        p=self.packet(); r=proposal(p['candidates'][0]); r['evidence_urls']=['https://example.com']
        item=assess_trends(p,load('products'),lambda _: [r],[])[0]
        self.assertEqual(item['review_mode'],'Rules fallback')
        self.assertTrue(any('evidence_urls' in e for e in item['validation_errors']))
        self.assertFalse(item.get('creative_draft'))

    def test_rejected_topic_cannot_produce_storyboard(self):
        p=self.packet(); r=proposal(p['candidates'][0],'reject')
        r['creative_draft']={'source_basis':'caption','hook':'Tea','script':['a']*3,'shots':['b']*3}
        item=assess_trends(p,load('products'),lambda _: [r],[])[0]
        self.assertIsNone(item['creative_draft'])

    def test_invented_source_rejected(self):
        p=self.packet();r=proposal(p['candidates'][0]);r['evidence_urls']=['https://example.com/fake']
        reviews=assess_trends(p,load('products'),lambda _: [r],[])
        self.assertEqual(reviews[0]['review_mode'],'Rules fallback')

    def test_invented_or_malformed_product_rejected(self):
        for product in ['Invented drink',{}]:
            p=self.packet();r=proposal(p['candidates'][0]);r['product']=product
            reviews=assess_trends(p,load('products'),lambda _: [r],[])
            self.assertEqual(reviews[0]['review_mode'],'Rules fallback')

    def test_model_outage_visible_as_rules(self):
        def fail(_): raise ValueError('Provider unavailable')
        result=generate(DAY,as_of=DAY,reviewer=fail)
        self.assertTrue(all(r['review_mode']=='Rules fallback' for r in result['trend_reviews']))
        self.assertIn('Provider unavailable',result['trace'])

    def test_future_snapshot_not_used(self):
        self.assertEqual(load_trend_evidence(date(2026,11,12),[])['status'],'missing')

    def test_old_data_cannot_be_adopted(self):
        packet=load_trend_evidence(date(2027,4,12),[])
        self.assertTrue(all(any('older' in b for b in c['blockers']) for c in packet['candidates']))

    def test_incomplete_export_is_explicit(self):
        with TemporaryDirectory() as d,patch.dict(os.environ,{'WUSHILAND_BRIGHTDATA_DIR':d}):
            Path(d,'trends.json').write_text(json.dumps({'mode':'live','generated_at':'2026-11-13T00:00:00Z','candidates':[{'content_format':None}]}))
            self.assertEqual(self.packet()['status'],'no_usable_evidence')

    def test_html_escapes_model_and_source_content(self):
        r=generate(DAY,as_of=DAY)
        r['trend_reviews'][0]['reason']='<script>alert(1)</script>'
        page=render(str(DAY),r)
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertIn('Original videos and metrics',page)

    def test_planner_cannot_cite_watchlist_as_adopted(self):
        c=self.packet()['candidates'][0]
        def planner(*_):
            return [{'product':'Boba Milk Tea','format':'pov','event':None,'hook':'Tea break','concept':'Counter shot',
                     'why':'A local break','script':['a','b','c'],'shots':['a','b','c'],'trend_candidate_id':c['id']}]
        r=generate(DAY,as_of=DAY,planner=planner)
        self.assertTrue(any('eligible adapt' in s for s in r['trace']))
        self.assertEqual(r['mode'],'Templates')

if __name__=='__main__': unittest.main()
