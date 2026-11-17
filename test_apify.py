import json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
from apify_client import ApifyClient,NoRedirect,BUILD,BudgetRequired
from ultra_client import GoogleClient,UltraError,CancelledError
class ApifyChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.g=GoogleClient(Path(self.tmp.name),{'2704':'Vietnam'});self.g.iso={'2704':'VN'};self.a=ApifyClient(self.g);self.a.key='apify_api_TESTCREDENTIAL00000';self.a.read_log=lambda run_id:'No more ads after page 1'
 def tearDown(self):self.g.db.close();self.tmp.cleanup()
 def row(self,i=1):return {'advertiserId':'AR123','creativeId':'CR'+str(i),'advertiserName':'Example','format':'TEXT','domain':'example.com','firstShown':'2026-01-01T12:00:00Z','lastShown':'2026-10-28T12:00:00Z'}
 def data(self,rows,incomplete=False):return {'rows':rows,'checkedAt':'2026-10-29T03:00:00Z','runId':'run1','datasetId':'dataset1','costUsd':0.003,'incomplete':incomplete}
 def test_region_search_text_dates_and_budget_identity(self):
  mode,region,start,end,body,identity=self.a.context({'mode':'reverse','domain':'https://www.example.com/path','region':'2704','start':'2026-10-01','end':'2026-10-01'})
  self.assertEqual(body['domains'],['example.com']);self.assertEqual(body['region'],'VN');self.assertEqual(body['platform'],'SEARCH');self.assertEqual(body['format'],'TEXT');self.assertEqual(body['dateTo'],'2026-10-01');self.assertEqual(len(identity),64)
 def test_page_does_not_start_paid_run_and_bad_context_rejected(self):
  self.a.max_ads=100;body={'mode':'reverse','domain':'example.com'}
  with patch.object(self.a,'run',return_value=self.data([self.row(i) for i in range(45)])) as run:
   first=self.a.process(body);self.assertEqual(len(first['ads']),40);self.assertTrue(first['nextPageToken'])
   second=self.a.process({**body,'pageToken':first['nextPageToken']});self.assertEqual(len(second['ads']),5);self.assertEqual(run.call_count,1)
   again=self.a.process(body);self.assertTrue(again['cached']);self.assertEqual(run.call_count,1)
   with self.assertRaises(UltraError):self.a.process({'mode':'reverse','domain':'different.com','pageToken':first['nextPageToken']})
 def test_filters_and_domain_mismatch_fail(self):
  for change in [{'format':'VIDEO'},{'advertiserId':'bad'},{'domain':'different.com'}]:
   with self.assertRaises(UltraError):self.a.normalize({**self.row(),**change},{'mode':'reverse','domain':'example.com'},'')
  with self.assertRaises(UltraError):self.a.normalize(self.row(),{'mode':'check','advertiserId':'AR999'},'')
 def test_outside_date_fails(self):
  with self.assertRaises(UltraError):self.a.normalize(self.row(),{'mode':'reverse','domain':'example.com','start':'2025-01-01','end':'2025-01-02'},'')
 def test_cost_limit_flag_and_missing_ocr(self):
  with patch.object(self.a,'run',return_value=self.data([self.row()],True)):
   result=self.a.process({'mode':'reverse','domain':'example.com'});self.assertTrue(result['incomplete']);self.assertTrue(result['warning'])
  row={**self.row(),'domain':None,'imageUrl':'https://tpc.googlesyndication.com/image'}
  with patch.object(self.g,'decode_preview',return_value={'domain':None,'method':'missing','evidence':''}):
   with patch.object(self.a,'run',return_value=self.data([row])):
    result=self.a.process({'mode':'check','advertiserId':'AR123'});self.assertTrue(result['incomplete']);self.assertIsNone(result['ads'][0]['domain'])
 def test_http_error_not_empty_and_redirect_rejected(self):
  self.a.opener=Mock();self.a.opener.open.side_effect=urllib.error.HTTPError('https://api.apify.com',401,'Unauthorized',{},None)
  with self.assertRaises(UltraError):self.a.api('users/me')
  with self.assertRaises(UltraError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')
 def test_failed_run_is_not_empty(self):
  with patch.object(self.a,'api',return_value={'id':'run1','status':'FAILED'}):
   with self.assertRaises(UltraError):self.a.run({'mode':'ads'})
 def test_no_automatic_paid_retry(self):
  with patch.object(self.a,'api',side_effect=UltraError('network')) as api:
   with self.assertRaises(UltraError):self.a.run({'mode':'ads'})
   self.assertEqual(api.call_count,1)
 def test_cancellation_aborts_remote_run(self):
  def api(path,body=None):
   if '/runs?' in path:self.g.cancel.set();return {'id':'run1','status':'RUNNING'}
   return {}
  with patch.object(self.a,'api',side_effect=api) as mocked:
   with self.assertRaises(CancelledError):self.a.run({'mode':'ads'})
   self.assertTrue(any('/abort' in c.args[0] for c in mocked.call_args_list))
 def test_completed_charge_cap_and_build(self):
  with patch.object(self.a,'api',side_effect=[{'id':'run1','status':'SUCCEEDED','defaultDatasetId':'ds1','statusMessage':'Saved 40 ads','usageTotalUsd':0.06},[self.row(i) for i in range(40)]]) as api:
   result=self.a.run({'mode':'ads'});self.assertTrue(result['incomplete']);self.assertIn('build='+BUILD,api.call_args_list[0].args[0]);self.assertIn('maxTotalChargeUsd=0.1',api.call_args_list[0].args[0])
 def test_configuration_failure_preserves_previous_key(self):
  with patch.object(self.a,'api',side_effect=UltraError('unauthorized')):
   old=self.a.key
   with self.assertRaises(UltraError):self.a.configure('apify_api_INVALIDCREDENTIAL000',40,0.1)
   self.assertEqual(self.a.key,old)
 def test_collect_all_lifts_sample_cap_without_raising_dollar_cap(self):
  body={'mode':'reverse','domain':'example.com'}
  self.assertEqual(self.a.context(body)[4]['maxAds'],100000)
  self.assertEqual(self.a.context({**body,'collectAll':False})[4]['maxAds'],40)
  self.assertEqual(self.a.max_charge,.10)
 def test_warning_does_not_hide_remaining_paid_dataset_pages(self):
  body={'mode':'reverse','domain':'example.com'}
  with patch.object(self.a,'run',return_value=self.data([self.row(i) for i in range(85)],True)) as run:
   pages=[];token=None
   while True:
    result=self.a.process({**body,'pageToken':token});pages.append(result);token=result['nextPageToken']
    if not token:break
   self.assertEqual([len(p['ads']) for p in pages],[40,40,5]);self.assertEqual(run.call_count,1)
   self.assertTrue(all(p['sourceIncomplete'] for p in pages));self.assertEqual(len({a['id'] for p in pages for a in p['ads']}),85)
 def test_dataset_reads_beyond_first_thousand(self):
  with patch.object(self.a,'api',side_effect=[{'id':'run1','status':'SUCCEEDED','defaultDatasetId':'ds1'},[self.row(i) for i in range(1000)],[self.row(i) for i in range(1000,1083)]]) as api:
   result=self.a.run({'mode':'ads','maxAds':100000});self.assertEqual(len(result['rows']),1083);self.assertFalse(result['incomplete']);self.assertIn('offset=1000',api.call_args.args[0])
 def test_history_cache_reused_after_twenty_minutes(self):
  body={'mode':'reverse','domain':'example.com'};identity=self.a.context(body)[-1]
  self.g.put_cached('apify-run:'+identity,self.data([]))
  import time
  self.g.db.execute('UPDATE cache SET at=? WHERE key=?',(time.time()-1200,'apify-run:'+identity));self.g.db.commit()
  with patch.object(self.a,'run',side_effect=AssertionError('should reuse 24h history')):
   self.assertTrue(self.a.process(body)['cached'])
 def test_current_cache_expires_after_ten_minutes(self):
  body={'mode':'reverse-current','domain':'example.com'};identity=self.a.context(body)[-1]
  self.g.put_cached('apify-run:'+identity,self.data([]))
  import time
  self.g.db.execute('UPDATE cache SET at=? WHERE key=?',(time.time()-601,'apify-run:'+identity));self.g.db.commit()
  with patch.object(self.a,'run',return_value=self.data([])) as run:
   self.assertFalse(self.a.process(body)['cached']);self.assertEqual(run.call_count,1)
 def test_short_dataset_without_exhaustion_proof_is_incomplete(self):
  self.a.read_log=lambda run_id:''
  with patch.object(self.a,'api',side_effect=[{'id':'run1','status':'SUCCEEDED','defaultDatasetId':'ds1'},[self.row()]]):
   r=self.a.run({'mode':'ads','maxAds':100000});self.assertTrue(r['incomplete']);self.assertEqual(r['incompleteReason'],'unverified')
 def test_budget_stopped_run_preserves_paid_partial_rows(self):
  with patch.object(self.a,'api',side_effect=[{'id':'run1','status':'ABORTED','defaultDatasetId':'ds1'},[self.row()]]):
   r=self.a.run({'mode':'ads','maxAds':100000});self.assertEqual(len(r['rows']),1);self.assertTrue(r['incomplete']);self.assertEqual(r['incompleteReason'],'actor-stopped')
 def managed(self):
  self.a.keys=Mock();self.a.keys.active=0;self.a.keys.slots=[{'accountId':'account1'}]
 def test_full_scan_starts_with_existing_cap_without_preflight(self):
  self.managed()
  with patch.object(self.a,'estimate') as estimate,patch.object(self.a,'run',return_value=self.data([self.row()])) as run:
   result=self.a.process({'mode':'reverse','domain':'example.com'})
   estimate.assert_not_called();self.assertEqual(run.call_count,1);self.assertEqual(self.a.max_charge,.1);self.assertFalse(result['incomplete'])
 def test_complete_cached_result_skips_preview_and_scan(self):
  self.managed();body={'mode':'reverse','domain':'example.com'};identity=self.a.context(body)[-1];self.g.put_cached('apify-run:'+identity,self.data([self.row()]))
  with patch.object(self.a,'estimate') as estimate,patch.object(self.a,'run') as run:
   r=self.a.process(body);self.assertEqual(len(r['ads']),1);estimate.assert_not_called();run.assert_not_called()
 def test_partial_cache_reused_without_silent_paid_rerun(self):
  self.managed();body={'mode':'reverse','domain':'example.com'};identity=self.a.context(body)[-1];self.g.put_cached('apify-run:'+identity,self.data([self.row()],True))
  with patch.object(self.a,'estimate') as estimate,patch.object(self.a,'run') as run:
   result=self.a.process(body);self.assertTrue(result['incomplete']);estimate.assert_not_called();run.assert_not_called()
 def test_unknown_estimate_never_blocks_search(self):
  self.managed()
  with patch.object(self.a,'estimate',return_value={'suggestedBudgetUsd':None}) as estimate,patch.object(self.a,'run',return_value=self.data([self.row()],True)) as run:
   result=self.a.process({'mode':'reverse','domain':'example.com'});estimate.assert_not_called();self.assertEqual(run.call_count,1);self.assertTrue(result['incomplete'])
 def test_estimate_is_overview_and_cached(self):
  with patch.object(self.a,'run',return_value={'rows':[{'type':'overview','estimatedCostUsd':1.35,'approximateTotalAds':900}],'runId':'preview'}) as run:
   inputs=self.a.context({'mode':'reverse','domain':'example.com'})[4];r=self.a.estimate(inputs);again=self.a.estimate(inputs)
   self.assertEqual(r['suggestedBudgetUsd'],1.36);self.assertEqual(r,again);self.assertEqual(run.call_count,1);self.assertTrue(run.call_args.args[0]['overviewOnly'])
 def import_meta(self):return {'id':'RunABCDE123456789','actId':'6gAFfuqX4Chhom1FY','status':'SUCCEEDED','defaultKeyValueStoreId':'store1','defaultDatasetId':'ds1'}
 def import_input(self):return {'mode':'ads','domains':['example.com'],'region':'','format':'TEXT','platform':'SEARCH','maxAds':100000}
 def test_import_existing_dataset_never_starts_actor(self):
  with patch.object(self.a,'api',side_effect=[self.import_meta(),self.import_input(),[self.row()]]) as api,patch.object(self.a,'run') as run:
   r=self.a.import_run({'mode':'reverse','domain':'example.com'},'RunABCDE123456789');self.assertEqual(len(r['ads']),1);self.assertTrue(r['cached']);self.assertFalse(r['incomplete']);run.assert_not_called();self.assertTrue(all(len(c.args)==1 for c in api.call_args_list))
 def test_import_rejects_different_domain_filters_and_actor(self):
  for input_change in [{'domains':['other.com']},{'platform':'YOUTUBE'},{'region':'VN'},{'dateFrom':'2026-01-01'},{'onlyNewSinceLastRun':True}]:
   with patch.object(self.a,'api',side_effect=[self.import_meta(),{**self.import_input(),**input_change}]),patch.object(self.a,'run') as run:
    with self.assertRaises(UltraError):self.a.import_run({'mode':'reverse','domain':'example.com'},'RunABCDE123456789')
    run.assert_not_called()
  with patch.object(self.a,'api',return_value={**self.import_meta(),'actId':'different'}):
   with self.assertRaises(UltraError):self.a.import_run({'mode':'reverse','domain':'example.com'},'RunABCDE123456789')
if __name__=='__main__':unittest.main()
