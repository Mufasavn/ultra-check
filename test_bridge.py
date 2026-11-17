import json,threading,time,unittest,urllib.parse
from pathlib import Path
from unittest.mock import patch
import ultra_client as u
from browser_bridge import BrowserBridge

def browser(bridge,answer,seen):
    """Fake Ultra Check page + extension: take one job, answer it."""
    job=bridge.poll('1.0.0',wait=5)
    if job:seen.append(job);bridge.result(job['id'],answer(job))

class BridgeChecks(unittest.TestCase):
    def setUp(self):self.b=BrowserBridge();self.cancel=threading.Event()
    def run_with(self,answer):
        seen=[];t=threading.Thread(target=browser,args=(self.b,answer,seen));t.start()
        try:return self.b.call('SearchService/SearchSuggestions','f.req=%7B%7D',self.cancel,timeout=5),seen
        finally:t.join(5)
    def test_offline_until_polled(self):
        self.assertFalse(self.b.online())
        self.assertIsNone(self.b.poll('1.0.0',wait=0));self.assertTrue(self.b.online());self.assertEqual(self.b.summary()['extensionVersion'],'1.0.0')
        self.b.last_seen-=60;self.assertFalse(self.b.online())
    def test_round_trip(self):
        text,seen=self.run_with(lambda job:{'status':200,'url':'https://adstransparency.google.com/anji/_/rpc/x','text':'{"1":[]}'})
        self.assertEqual(text,'{"1":[]}');self.assertEqual(seen[0]['method'],'SearchService/SearchSuggestions');self.assertEqual(seen[0]['body'],'f.req=%7B%7D')
        self.assertFalse(self.b.jobs);self.assertFalse(self.b.pending)
    def test_verification_is_reported_not_bypassed(self):
        for answer in ({'status':429,'text':''},{'status':403,'text':''},{'status':200,'url':'https://www.google.com/sorry/index','text':'x'},{'status':429,'blocked':True}):
            with self.assertRaises(u.BlockedError):self.run_with(lambda job,a=answer:a)
    def test_errors(self):
        with self.assertRaisesRegex(u.UltraError,'Failed to fetch'):self.run_with(lambda job:{'status':0,'error':'Failed to fetch'})
        with self.assertRaisesRegex(u.UltraError,'HTTP error 500'):self.run_with(lambda job:{'status':500,'text':'x'})
        with self.assertRaises(u.UltraError):self.run_with(lambda job:'not a dict')
        with self.assertRaisesRegex(u.UltraError,'Unsupported'):self.b.call('Other/Method','',self.cancel)
    def test_timeout_and_cancel_clean_up(self):
        with self.assertRaisesRegex(u.UltraError,'did not answer'):self.b.call('SearchService/SearchCreatives','x',self.cancel,timeout=.3)
        self.assertFalse(self.b.jobs);self.assertFalse(self.b.pending)
        self.cancel.set()
        with self.assertRaises(u.CancelledError):self.b.call('SearchService/SearchCreatives','x',self.cancel,timeout=5)
        self.assertFalse(self.b.pending)
    def test_late_or_unknown_result_ignored(self):
        self.assertFalse(self.b.result('nope',{'status':200,'text':'x'}))

class ClientRouting(unittest.TestCase):
    def setUp(self):
        self.c=u.GoogleClient(Path(__file__).parent/'unit-cache',{'2704':'Vietnam'});self.c.bridge=BrowserBridge()
    def tearDown(self):self.c.db.close()
    def test_direct_when_extension_absent(self):
        with patch.object(self.c,'read_url',return_value=b'{"1":[]}') as direct:
            data,_,cached=self.c.rpc('SearchService/SearchSuggestions',{'1':'bridge-absent','2':30,'3':10},fresh=True)
        self.assertEqual(data,{'1':[]});self.assertTrue(direct.called)
    def test_browser_session_when_extension_online(self):
        seen=[];payload={'1':'bridge-online','2':30,'3':10}
        answer=lambda job:{'status':200,'text':'{"1":[{"1":{"1":"Adcore","2":"AR15863532213959131137","3":"IL"}}]}'}
        self.c.bridge.poll('1.0.0',wait=0)
        t=threading.Thread(target=browser,args=(self.c.bridge,answer,seen));t.start()
        with patch.object(self.c,'read_url',side_effect=AssertionError('must not use direct transport')):
            result=self.c.process({'mode':'discover','text':'bridge-online','fresh':True})
        t.join(5)
        self.assertEqual(result['candidates'],[{'id':'AR15863532213959131137','name':'Adcore','country':'IL'}])
        self.assertEqual(json.loads(urllib.parse.parse_qs(seen[0]['body'])['f.req'][0]),payload)
    def test_browser_verification_stops_scan(self):
        self.c.bridge.poll('1.0.0',wait=0)
        t=threading.Thread(target=browser,args=(self.c.bridge,lambda job:{'status':429,'blocked':True},[]));t.start()
        with patch.object(self.c,'read_url',side_effect=AssertionError('no silent fallback after a block')):
            with self.assertRaises(u.BlockedError):self.c.process({'mode':'discover','text':'bridge-blocked','fresh':True})
        t.join(5)

if __name__=='__main__':unittest.main()
