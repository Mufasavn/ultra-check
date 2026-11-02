import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from apify_keys import ApifyKeys,ApiError
from apify_client import ApifyClient
from key_vault import KeyVault
from ultra_client import GoogleClient,UltraError
class KeyChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.g=GoogleClient(self.root,{});self.a=ApifyClient(self.g);self.keys=ApifyKeys(self.a,self.root/'keys.dat');self.a.keys=self.keys
 def tearDown(self):self.g.db.close();self.tmp.cleanup()
 def slot(self,i,used=0,limit=10,uid=None):return {'key':'apify_api_TESTKEY00000000'+str(i),'accountId':uid or 'account'+str(i),'quotaKnown':True,'usedUsd':used,'limitUsd':limit,'state':'exhausted' if used>=limit else 'ready','checkedAt':'2026-10-29','fresh':True}
 def test_real_windows_encryption_and_restart(self):
  self.keys.slots[0]=self.slot(1);self.keys.enabled=True;self.keys.persist();raw=(self.root/'keys.dat').read_bytes();self.assertNotIn(self.keys.slots[0]['key'].encode(),raw)
  restored=ApifyKeys(self.a,self.root/'keys.dat');self.assertTrue(restored.enabled);self.assertEqual(restored.slots[0]['key'],self.keys.slots[0]['key']);self.assertFalse(restored.summary()['slots'][0]['stale']==False)
  self.assertNotIn(self.keys.slots[0]['key'],json.dumps(restored.summary()))
 def test_percent_and_shared_accounts(self):
  self.keys.slots[0]=self.slot(1,2.5,10,'same');self.keys.slots[1]=self.slot(2,2.5,10,'same');r=self.keys.summary()['slots'];self.assertEqual(r[0]['usedPercent'],25);self.assertEqual(r[0]['remainingPercent'],75);self.assertEqual(r[1]['sharedWith'],1)
 def test_unknown_is_not_fabricated(self):
  self.keys.slots[0]={'key':'apify_api_TESTKEY00000001','state':'unknown'};r=self.keys.summary()['slots'][0];self.assertIsNone(r['usedPercent']);self.assertIsNone(r['remainingPercent'])
 def test_ordered_quota_failover_before_start(self):
  self.keys.slots=[self.slot(i) for i in range(10)]
  self.keys.refresh=lambda:None
  calls=[]
  def api(path,body=None):
   calls.append(self.a.key)
   if len(calls)<3:raise ApiError('quota',403,'monthly-usage-limit-exceeded')
   return {'id':'accepted','status':'READY'}
  with patch.object(self.a,'api',side_effect=api):result=self.keys.start('acts/example/runs',{})
  self.assertEqual(result['id'],'accepted');self.assertEqual(calls,[self.slot(0)['key'],self.slot(1)['key'],self.slot(2)['key']]);self.assertEqual(self.keys.active,2)
 def test_same_exhausted_account_skipped(self):
  self.keys.slots[0]=self.slot(1,10,10,'same');self.keys.slots[1]=self.slot(2,10,10,'same');self.keys.slots[2]=self.slot(3);self.keys.refresh=lambda:None
  self.assertEqual(self.keys.select(),2)
 def test_start_quota_error_marks_shared_account(self):
  self.keys.slots[0]=self.slot(1,0,10,'same');self.keys.slots[1]=self.slot(2,0,10,'same');self.keys.slots[2]=self.slot(3);self.keys.refresh=lambda:None
  calls=[]
  def api(path,body=None):
   calls.append(self.a.key)
   if len(calls)==1:raise ApiError('balance',402,'not-enough-usage-to-run-paid-actor')
   return {'id':'yes'}
  with patch.object(self.a,'api',side_effect=api):self.keys.start('acts/example/runs',{})
  self.assertEqual(len(calls),2);self.assertEqual(self.keys.active,2);self.assertEqual(self.keys.slots[1]['state'],'exhausted')
 def test_no_rotation_for_network_or_rate_or_paid_actor_requirement(self):
  self.keys.slots=[self.slot(i) for i in range(10)];self.keys.refresh=lambda:None
  for err in [UltraError('network'),ApiError('rate',429,'rate-limit-exceeded'),ApiError('plan',402,'apify-plan-required-to-use-paid-actor')]:
   with patch.object(self.a,'api',side_effect=err) as api:
    with self.assertRaises(UltraError):self.keys.start('acts/example/runs',{})
    self.assertEqual(api.call_count,1);self.assertEqual(self.keys.active,0)
 def test_no_rotation_after_accepted_run(self):
  self.keys.slots=[self.slot(i) for i in range(10)];self.keys.refresh=lambda:None
  calls=[]
  def api(path,body=None):
   calls.append(path)
   if '/runs?' in path:return {'id':'run1','status':'RUNNING'}
   if path.endswith('/abort'):return {}
   raise ApiError('poll quota',403,'monthly-usage-limit-exceeded')
  with patch.object(self.a,'api',side_effect=api):
   with self.assertRaises(UltraError):self.a.run({'mode':'ads'})
  self.assertEqual(len([x for x in calls if '/runs?' in x]),1);self.assertEqual(self.keys.active,0)
 def test_all_full_stops_without_post(self):
  self.keys.slots=[self.slot(i,10,10) for i in range(10)];self.keys.refresh=lambda:None
  with patch.object(self.a,'api') as api:
   with self.assertRaises(UltraError):self.keys.start('acts/example/runs',{})
   api.assert_not_called()
 def test_corrupt_vault_preserved(self):
  p=self.root/'bad.dat';p.write_bytes(b'not encrypted');keys=ApifyKeys(self.a,p);self.assertTrue(keys.error)
  with self.assertRaises(UltraError):keys.save([{}]*10)
  self.assertEqual(p.read_bytes(),b'not encrypted')
 def test_save_atomic_and_blank_keeps_key(self):
  self.keys.slots[0]=self.slot(1);self.keys.persist();old=self.keys.slots[0]['key']
  result=self.keys.save([{}]*10);self.assertTrue(result['slots'][0]['saved']);self.assertEqual(self.keys.slots[0]['key'],old)
  self.keys.save([{'clear':True}]+[{}]*9)
  self.assertFalse(self.keys.slots[0].get('key'));self.assertFalse(self.keys.enabled)
 def test_legacy_five_slot_vault_upgrades_without_losing_keys(self):
  vault=KeyVault(self.root/'legacy.dat');vault.save({'version':1,'slots':[self.slot(i) for i in range(5)],'active':4,'enabled':True})
  keys=ApifyKeys(self.a,self.root/'legacy.dat');self.assertEqual(len(keys.slots),10);self.assertEqual(keys.active,4);self.assertEqual(keys.slots[4]['key'],self.slot(4)['key']);self.assertFalse(keys.slots[9].get('key'))
 def test_failover_reaches_tenth_slot(self):
  self.keys.slots=[self.slot(i) for i in range(10)];self.keys.refresh=lambda:None;calls=[]
  def api(path,body=None):
   calls.append(self.a.key)
   if len(calls)<10:raise ApiError('quota',403,'monthly-usage-limit-exceeded')
   return {'id':'accepted'}
  with patch.object(self.a,'api',side_effect=api):self.keys.start('acts/example/runs',{})
  self.assertEqual(self.keys.active,9);self.assertEqual(len(calls),10)
 def test_limits_endpoint_math(self):
  with patch.object(self.keys,'call_with',side_effect=[{'id':'acct'},{'limits':{'maxMonthlyUsageUsd':10},'current':{'monthlyUsageUsd':.95},'monthlyUsageCycle':{'endAt':'2026-11-13'}}]):
   self.keys.slots[0]=self.keys.inspect('apify_api_TESTKEY00000001')
  self.assertAlmostEqual(self.keys.summary()['slots'][0]['usedPercent'],9.5)
if __name__=='__main__':unittest.main()
