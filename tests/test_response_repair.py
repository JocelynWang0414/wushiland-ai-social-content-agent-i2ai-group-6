from pathlib import Path
import io
import json
import os
import unittest
from datetime import date
from unittest.mock import patch
from wushiland.llm import request_json, output_schema, ResponseFormatError
from wushiland.agent import generate, load
from wushiland.trend_review import assess_trends, load_trend_evidence
from wushiland.web import render_trend_reviews


class RepairTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"WUSHILAND_BRIGHTDATA_DIR": str(Path(__file__).parent / "fixtures")})
        env.start()
        self.addCleanup(env.stop)

    def test_schema_and_fenced_json(self):
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'```json\n{"briefs": []}\n```'}]}}]}
        with patch.dict(os.environ,{'GEMINI_API_KEY':'TEST_ONLY'}), patch('wushiland.llm.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as call:
            self.assertEqual(request_json('test',{},output_schema()),{'briefs':[]})
            body=json.loads(call.call_args.args[0].data)
            self.assertIn('responseSchema',body['generationConfig'])

    def test_truncated_output_not_accepted_even_if_json_is_valid(self):
        response={'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]}
        with patch.dict(os.environ,{'GEMINI_API_KEY':'TEST_ONLY'}), patch('wushiland.llm.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaisesRegex(ResponseFormatError,'MAX_TOKENS'):
                request_json('test',{})

    def test_null_idea_preserves_valid_assessment(self):
        packet=load_trend_evidence(date(2026,11,13),[]); c=packet['candidates'][0]
        proposal={'candidate_id':c['id'],'decision':'watch','reason':'Insufficient evidence.',
                  'product':None,'adaptation_concept':None,'next_step':'Review source.', 'evidence_urls':c['evidence_urls']}
        review=assess_trends(packet,load('products'),lambda _: [proposal],[])[0]
        self.assertEqual(review['review_mode'],'Gemini recommendation')
        self.assertEqual(review['adaptation_concept'],'')

    def test_format_error_retried_once(self):
        with patch('wushiland.llm.plan',side_effect=ResponseFormatError('Malformed JSON')) as planner:
            result=generate(date(2026,11,13),as_of=date(2026,11,13),planner=planner)
            self.assertEqual(planner.call_count,2)
            self.assertEqual(result['mode'],'Templates')
            self.assertTrue(any('Retrying malformed' in t for t in result['trace']))

    def test_duplicate_evidence_collapsed_and_fallback_explicit(self):
        result=generate(date(2026,11,13),as_of=date(2026,11,13))
        item=result['trend_reviews'][0]
        result['trend_reviews']=[item,dict(item,label='1234567')]
        page=render_trend_reviews(result)
        self.assertIn('shared video evidence',page)
        self.assertIn('Audio-based candidate',page)
        self.assertIn('keyword-search sample',page)
