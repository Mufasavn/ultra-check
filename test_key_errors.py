import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from apify_keys import ApifyKeys,ApiError
from apify_client import ApifyClient
from ultra_client import GoogleClient,UltraError
class KeyErrorReasons(unittest.TestCase):
    """A rejected key, an empty quota and a network failure must be reported differently."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);self.g=GoogleClient(root,{});self.a=ApifyClient(self.g)
        self.keys=ApifyKeys(self.a,root/'keys.dat');self.a.keys=self.keys;self.keys.persist=lambda:None
        self.keys.slots=[{'key':f'apify_api_TESTKEY00000000{i}','accountId':f'acc{i}','state':'ready'} for i in range(3)]+[{} for _ in range(7)];self.keys.enabled=True
    def tearDown(self):self.g.db.close();self.tmp.cleanup()
    def refresh_with(self,errors):
        def inspect(key):
            e=errors[key[-1]]
            if e:raise e
            return {'key':key,'accountId':'acc'+key[-1],'state':'ready','fresh':True}
        with patch.object(self.keys,'inspect',side_effect=inspect):self.keys.refresh()
        return [s.get('state') for s in self.keys.slots[:3]]
    def test_401_token_not_found_is_invalid_not_unavailable(self):
        states=self.refresh_with({'0':ApiError('Invalid or expired Apify key.',401,'user-or-token-not-found'),'1':ApiError('x',401,''),'2':ApiError('x',403,'')})
        self.assertEqual(states,['invalid','invalid','invalid'])
        self.assertIn('user-or-token-not-found',self.keys.slots[0]['message']);self.assertIn('new API token',self.keys.slots[0]['message'])
        with patch.object(self.keys,'refresh',lambda:None),self.assertRaises(UltraError) as cm:self.keys.select()
        msg=str(cm.exception);self.assertIn('3 rejected by Apify',msg);self.assertNotIn('out of quota',msg)
    def test_network_error_is_unavailable_with_reason(self):
        states=self.refresh_with({'0':UltraError('Could not connect to Apify.'),'1':None,'2':ApiError('Apify rate limit reached.',429,'')})
        self.assertEqual(states,['unavailable','ready','unavailable'])
        self.assertIn('Could not reach Apify',self.keys.slots[0]['message']);self.assertIn('rate limit',self.keys.slots[2]['message'])
        with patch.object(self.keys,'refresh',lambda:None):self.assertEqual(self.keys.select(),1)   # the working key is still used
    def test_mixed_reasons_summarised(self):
        self.refresh_with({'0':ApiError('x',401,'user-or-token-not-found'),'1':UltraError('net'),'2':None})
        self.keys.slots[2]['state']='exhausted'
        with patch.object(self.keys,'refresh',lambda:None),self.assertRaises(UltraError) as cm:self.keys.select()
        msg=str(cm.exception);self.assertIn('1 rejected by Apify',msg);self.assertIn('1 out of quota',msg);self.assertIn('1 could not be checked',msg)
if __name__=='__main__':unittest.main(verbosity=2)
