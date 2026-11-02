import io,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch,MagicMock
from proxy_client import ProxySettings,ProxyGoogleClient
from ultra_client import GoogleClient,UltraError,BlockedError,CancelledError

class Response:
    def __init__(self,data):self.stream=io.BytesIO(data)
    def read(self,n):return self.stream.read(n)
    def __enter__(self):return self
    def __exit__(self,*args):pass

class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.settings=ProxySettings(self.root)
        self.shared=GoogleClient(self.root/'direct',{})
        self.client=ProxyGoogleClient(self.root/'proxy',{},self.settings,self.shared)
    def tearDown(self):self.client.db.close();self.shared.db.close();self.temp.cleanup()
    def configure(self):return self.settings.save({'username':'test-user','password':'dummy-test-secret','enabled':True,'totalGb':5,'baselineMb':51.2})
    def test_encrypted_persistent_and_masked(self):
        self.configure();raw=self.settings.path.read_bytes();self.assertNotIn(b'dummy-test-secret',raw)
        self.settings.add(10,90,True);restored=ProxySettings(self.root)
        self.assertTrue(restored.config['enabled']);self.assertEqual(restored.config['password'],'dummy-test-secret')
        result=restored.summary();self.assertNotIn('password',result);self.assertEqual(result['measuredBytes'],100);self.assertAlmostEqual(result['usedBytes'],51_200_100)
        self.assertAlmostEqual(result['usedPercent'],51_200_100/5e9*100)
        restored.save({'password':''});self.assertEqual(restored.config['password'],'dummy-test-secret')
    def test_invalid_values(self):
        self.configure()
        for change in ({'totalGb':float('nan')},{'baselineMb':-1},{'port':0},{'host':'http://bad'},{'password':'x_session-123_ttl-10'}):
            with self.assertRaises(UltraError):self.settings.save(change)
        self.assertEqual(self.settings.config['password'],'dummy-test-secret')
    def test_explicit_reset(self):
        self.configure();self.settings.add(10,90,True);self.settings.reset(75)
        self.assertEqual(self.settings.summary()['measuredBytes'],0);self.assertEqual(self.settings.summary()['usedBytes'],75e6)
    def test_corrupt_meter_not_silently_zeroed(self):
        self.settings.meter_path.write_text('bad');restored=ProxySettings(self.root)
        self.assertTrue(restored.error)
        with self.assertRaises(UltraError):restored.add(1)
        self.assertEqual(self.settings.meter_path.read_text(),'bad')
    def transport(self,opener):
        return patch('proxy_client.urllib.request.build_opener',return_value=opener)
    def test_meter_cache_and_filters(self):
        self.configure();row={'1':'AR123','2':'CR123','4':1,'14':'waterdropfilter.com','12':'Test'}
        opener=MagicMock();opener.open.return_value=Response(json.dumps({'1':[row]}).encode())
        with self.transport(opener):
            result=self.client.process({'mode':'reverse','domain':'waterdropfilter.com'})
            self.assertEqual(result['ads'][0]['advertiserId'],'AR123');first=self.settings.summary()['measuredBytes']
            again=self.client.process({'mode':'reverse','domain':'waterdropfilter.com'})
            self.assertTrue(again['cached']);self.assertEqual(self.settings.summary()['measuredBytes'],first);self.assertEqual(opener.open.call_count,1)
    def test_retry_proxy_timeout_same_page(self):
        self.configure();opener=MagicMock();opener.open.side_effect=[urllib.error.URLError(OSError('Tunnel connection failed: 504 Gateway Timeout')),Response(b'{}')]
        with self.transport(opener),patch.object(self.client.cancel,'wait',return_value=False):self.assertEqual(self.client.read_url('https://adstransparency.google.com/x',b'abc'),b'{}')
        self.assertEqual(opener.open.call_count,2);self.assertIs(opener.open.call_args_list[0].args[0],opener.open.call_args_list[1].args[0]);self.assertEqual(self.settings.summary()['measuredBytes'],8)
    def test_gateway_502_503_retried_same_request(self):
        self.configure();opener=MagicMock();opener.open.side_effect=[urllib.error.URLError(OSError('Tunnel connection failed: 502 Bad Gateway')),urllib.error.URLError(OSError('Tunnel connection failed: 503 Service Unavailable')),Response(b'{}')]
        with self.transport(opener),patch.object(self.client.cancel,'wait',return_value=False):self.assertEqual(self.client.read_url('https://adstransparency.google.com/x'),b'{}')
        self.assertEqual(opener.open.call_count,3);self.assertTrue(all(call.args[0] is opener.open.call_args_list[0].args[0] for call in opener.open.call_args_list))
    def test_persistent_502_bounded_and_actionable(self):
        self.configure();opener=MagicMock();opener.open.side_effect=urllib.error.URLError(OSError('Tunnel connection failed: 502 Bad Gateway'))
        with self.transport(opener),patch.object(self.client.cancel,'wait',return_value=False):
            with self.assertRaises(UltraError) as error:self.client.read_url('https://adstransparency.google.com/x')
        self.assertIn('HTTP 502',str(error.exception));self.assertIn('3 attempts',str(error.exception));self.assertEqual(opener.open.call_count,3)
    def test_tunnel_auth_failure_not_retried(self):
        self.configure();opener=MagicMock();opener.open.side_effect=urllib.error.URLError(OSError('Tunnel connection failed: 407 Proxy Authentication Required'))
        with self.transport(opener):
            with self.assertRaises(UltraError) as error:self.client.read_url('https://adstransparency.google.com/x')
        self.assertIn('407',str(error.exception));self.assertEqual(opener.open.call_count,1)
    def test_upstream_502_retried(self):
        self.configure();opener=MagicMock();opener.open.side_effect=[urllib.error.HTTPError('https://adstransparency.google.com/x',502,'bad gateway',{},None),Response(b'{}')]
        with self.transport(opener),patch.object(self.client.cancel,'wait',return_value=False):self.assertEqual(self.client.read_url('https://adstransparency.google.com/x'),b'{}')
        self.assertEqual(opener.open.call_count,2)
    def test_google_block_never_retry_or_change_session(self):
        self.configure();opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError('https://adstransparency.google.com/x',429,'limit',{},None)
        with self.transport(opener):
            with self.assertRaises(BlockedError):self.client.process({'mode':'reverse','domain':'waterdropfilter.com'})
            before=dict(self.client.sessions)
            with self.assertRaises(BlockedError):self.client.process({'mode':'reverse','domain':'example.com'})
            self.assertEqual(before,self.client.sessions);self.assertEqual(opener.open.call_count,1)
    def test_captcha_in_200_stops(self):
        self.configure();opener=MagicMock();opener.open.return_value=Response(b'<html>captcha</html>')
        with self.transport(opener):
            with self.assertRaises(BlockedError):self.client.process({'mode':'reverse','domain':'waterdropfilter.com'})
        self.assertTrue(self.client.blocked)
    def test_credentials_not_in_error(self):
        self.configure();opener=MagicMock();opener.open.side_effect=urllib.error.URLError('dummy-test-secret proxy failure')
        with self.transport(opener):
            with self.assertRaises(UltraError) as error:self.client.read_url('https://adstransparency.google.com/x')
        self.assertNotIn('dummy-test-secret',str(error.exception));self.assertEqual(opener.open.call_count,1)
    def test_session_continuation_and_expiry(self):
        self.configure()
        with patch.object(GoogleClient,'process',return_value={}):
            self.client.process({'mode':'reverse','domain':'example.com'})
            first=self.client.session_id
            self.client.process({'mode':'reverse','domain':'example.com','pageToken':'next'})
            self.assertEqual(first,self.client.session_id)
            for key,(sid,created) in self.client.sessions.items():self.client.sessions[key]=(sid,created-600)
            with self.assertRaises(UltraError):self.client.process({'mode':'reverse','domain':'example.com','pageToken':'next'})
    def test_cancel_no_network(self):
        self.configure();self.client.cancel.set()
        with patch('proxy_client.urllib.request.build_opener') as op:
            with self.assertRaises(CancelledError):self.client.read_url('https://adstransparency.google.com/x')
            op.assert_not_called()
    def test_allowlist(self):
        self.configure()
        with self.assertRaises(UltraError):self.client.read_url('https://example.com/')

if __name__=='__main__':unittest.main()
