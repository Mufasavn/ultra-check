import json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from ultra_client import GoogleClient,UltraError
from apify_client import ApifyClient
from run_history import RunHistory

class HistoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.g=GoogleClient(self.path,{})
 def tearDown(self):self.g.db.close();self.tmp.cleanup()
 def inputs(self):return {'mode':'ads','domains':['getdex.com'],'region':'','format':'TEXT','platform':'SEARCH'}
 def test_immediate_id_survives_poll_failure(self):
  a=ApifyClient(self.g);a.history=RunHistory(self.g);a.key='dummy-test-key'
  with patch.object(a,'api',side_effect=[{'id':'RunABCDE123456789','status':'RUNNING'},UltraError('poll failure'),{}]),patch.object(self.g.cancel,'wait',return_value=False):
   with self.assertRaises(UltraError):a.run(self.inputs())
  rows=a.history.list()['runs'];self.assertEqual(rows[0]['id'],'RunABCDE123456789');self.assertEqual(rows[0]['status'],'RUNNING');self.assertEqual(rows[0]['query']['domain'],'getdex.com')
 def test_cache_migration_persistent_and_deduplicated(self):
  self.g.put_cached('apify-run:old',{'runId':'RunABCDE123456789','input':self.inputs(),'rows':[{}],'checkedAt':'2026-10-29T01:00:00Z','incomplete':True})
  h=RunHistory(self.g);self.assertEqual(len(h.list()['runs']),1);self.assertTrue(h.list()['runs'][0]['importable'])
  h.record({'id':'RunABCDE123456789','status':'SUCCEEDED'},self.inputs(),{'rows':[{},{}],'incomplete':False})
  self.g.db.close();self.g=GoogleClient(self.path,{});restored=RunHistory(self.g)
  self.assertEqual(len(restored.list()['runs']),1);self.assertEqual(restored.list()['runs'][0]['status'],'SUCCEEDED');self.assertEqual(restored.list()['runs'][0]['ads'],2)
 def test_metadata_allowlist_and_overview_not_importable(self):
  h=RunHistory(self.g);h.record({'id':'RunABCDE123456789','status':'SUCCEEDED','token':'do-not-save'},dict(self.inputs(),overviewOnly=True,password='do-not-save'))
  row=h.list()['runs'][0];self.assertFalse(row['importable']);self.assertNotIn('do-not-save',json.dumps(row))
 def test_advertiser_query_and_country_dates(self):
  self.g.iso={'2840':'US'};h=RunHistory(self.g);h.record({'id':'RunABCDE123456789'},{'mode':'ads','advertiserIds':['AR123'],'region':'US','dateFrom':'2026-10-01','dateTo':'2026-10-20','format':'TEXT','platform':'SEARCH'})
  row=h.list()['runs'][0];self.assertEqual(row['query'],{'mode':'check','advertiserId':'AR123','region':'2840','start':'2026-10-01','end':'2026-10-20'})
 def test_malformed_legacy_cache_skipped(self):
  self.g.put_cached('apify-run:bad',{'rows':[]});h=RunHistory(self.g);self.assertEqual(h.list()['runs'],[])

if __name__=='__main__':unittest.main()
