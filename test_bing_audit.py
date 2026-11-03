"""Regression checks for the meshy.ai missing-records report."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from bing_client import BingClient,BASE,text_candidate
from ultra_client import GoogleClient,UltraError

class BingAuditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.cache=GoogleClient(Path(self.tmp.name),{})
  self.client=BingClient(self.cache);self.client.interval=0
  self.fixture=json.loads((Path(__file__).parent/'fixtures/bing-meshy-2026-11-03.json').read_text(encoding='utf-8'))
  self.items=self.fixture['value'];self.calls=[]
  self.query={'mode':'reverse','domain':'meshy.ai','start':'2025-11-03','end':'2026-11-03'}
  def source(path,params=None,**kw):
   self.calls.append((path,params))
   self.assertEqual(path,'Ads','Listing must not fetch individual date details')
   skip=params['skip'];return {'value':self.items[skip:skip+params['top']],'@odata.count':len(self.items)},'2026-11-03T00:00:00Z',False
  self.source=source;self.client._request=Mock(side_effect=source)
 def tearDown(self):self.cache.db.close();self.tmp.cleanup()
 def collect(self,token=None,client=None):
  client=client or self.client;ads=[]
  for _ in range(20):
   r=client.process({**self.query,'pageToken':token});ads+=r['ads'];token=r['nextPageToken']
   if not token or r.get('halt'):return ads,r
  self.fail('Paging did not finish')
 def test_all_85_source_records_80_matching_text_ads_two_advertisers(self):
  ads,r=self.collect()
  self.assertEqual(len(ads),80);self.assertEqual(len({a['id'] for a in ads}),80)
  self.assertEqual(len({a['advertiserId'] for a in ads}),2)
  self.assertEqual(r['sourceStats']['sourceTotal'],85);self.assertEqual(r['sourceStats']['sourceRead'],85)
  self.assertEqual(r['sourceStats']['accepted'],80);self.assertEqual(r['sourceStats']['excludedDifferentDomain'],3);self.assertEqual(r['sourceStats']['excludedMedia'],2)
  self.assertEqual(r['sourceStats']['pagesRead'],8);self.assertTrue(r['sourceStats']['sourceComplete']);self.assertFalse(r['incomplete'])
  self.assertEqual([params['skip'] for _,params in self.calls],[0,12,24,36,48,60,72,84])
  self.assertEqual(sum(not a['Description'] for a in self.items if text_candidate(a)),7)
  self.assertTrue(all(a['dateStatus']=='pending' for a in ads))
 def test_title_only_and_empty_asset_array_remain_visible(self):
  item={**self.items[0],'Description':'','AssetJson':'[]'}
  self.assertTrue(text_candidate(item));self.assertIsNotNone(self.client._normalize(item,'meshy.ai'))
 def test_rate_limit_keeps_ledger_and_resume_after_new_client(self):
  first=self.client.process(self.query);token=first['nextPageToken']
  self.client._request=Mock(side_effect=UltraError('Microsoft HTTP 429'))
  failed=self.client.process({**self.query,'pageToken':token})
  self.assertTrue(failed['halt']);self.assertEqual(failed['sourceStats']['sourceRead'],12)
  other=BingClient(self.cache);other._request=Mock(side_effect=self.source)
  rest,last=self.collect(failed['nextPageToken'],other)
  self.assertEqual(len(first['ads']+rest),80);self.assertTrue(last['sourceStats']['sourceComplete'])
 def test_cached_dates_are_attached_without_detail_request(self):
  item=self.items[0]
  self.cache.put_cached('bing:v1:'+BASE+'Ads/'+str(item['AdId'])+'?expand=AdDetails',{
   **item,'AdDetails':{'StartDate':'2026-10-01','EndDate':'2026-11-01'}})
  r=self.client.process(self.query)
  ad=next(a for a in r['ads'] if a['id']==str(item['AdId']))
  self.assertTrue(ad['first'].startswith('2026-10-01'));self.assertEqual(ad['dateStatus'],'reported')
  self.assertEqual(self.client._request.call_count,1)
 def test_unrelated_cached_ad_is_never_used_for_dates(self):
  item=self.items[0]
  self.cache.put_cached('bing:v1:'+BASE+'Ads/'+str(item['AdId'])+'?expand=AdDetails',{
   **item,'AdvertiserId':999,'AdDetails':{'StartDate':'2026-01-01'}})
  r=self.client.process(self.query);ad=next(a for a in r['ads'] if a['id']==str(item['AdId']))
  self.assertIsNone(ad['first']);self.assertEqual(ad['dateStatus'],'pending')
 def test_refresh_lists_does_not_attach_old_cached_dates(self):
  item=self.items[0]
  self.cache.put_cached('bing:v1:'+BASE+'Ads/'+str(item['AdId'])+'?expand=AdDetails',{
   **item,'AdDetails':{'StartDate':'2026-01-01'}})
  r=self.client.process({**self.query,'fresh':True});ad=next(a for a in r['ads'] if a['id']==str(item['AdId']))
  self.assertIsNone(ad['first']);self.assertEqual(ad['dateStatus'],'pending')
 def test_date_failure_retains_dates_already_read(self):
  ads=[a for a in self.items if text_candidate(a)][:3]
  def detail(path,params=None,**kw):
   if path!='Ads/'+str(ads[0]['AdId']):raise UltraError('Microsoft HTTP 429')
   return {**ads[0],'AdDetails':{'StartDate':'2026-10-01','EndDate':'2026-11-01'}},'2026-11-03',False
  self.client._request=Mock(side_effect=detail)
  r=self.client.process({'mode':'dates','domain':'meshy.ai','records':[{'id':a['AdId'],'advertiserId':a['AdvertiserId']} for a in ads]})
  self.assertEqual(len(r['ads']),1);self.assertTrue(r['halt']);self.assertEqual(self.client._request.call_count,2)
  self.assertEqual(r['ads'][0]['dateStatus'],'reported')
 def test_dates_batch_validated_before_source_access(self):
  for records in [[],[{}],[{'id':1,'advertiserId':1}]*4]:
   with self.assertRaises(UltraError):self.client.process({'mode':'dates','records':records})
  self.assertEqual(self.client._request.call_count,0)
 def test_exact_full_page_does_not_make_extra_request(self):
  self.items=self.items[:12];r=self.client.process(self.query)
  self.assertIsNone(r['nextPageToken']);self.assertTrue(r['sourceStats']['sourceComplete'])
  self.assertEqual(self.client._request.call_count,1)
 def test_domain_mismatch_is_counted_and_not_inferred_from_title(self):
  self.items=[{**self.items[0],'DestinationUrl':'https://notmeshy.ai/','DisplayUrl':'notmeshy.ai'}]
  r=self.client.process(self.query);self.assertEqual(r['ads'],[])
  self.assertEqual(r['sourceStats']['excludedDifferentDomain'],1);self.assertTrue(r['sourceStats']['sourceComplete'])
 def test_duplicate_source_records_cannot_claim_complete_coverage(self):
  self.items=[self.items[0]]*12;r=self.client.process(self.query)
  self.assertEqual(r['sourceStats']['sourceRead'],1);self.assertFalse(r['sourceStats']['sourceComplete'])
  self.assertTrue(r['incomplete'])
 def test_empty_source_is_complete_only_for_zero_count(self):
  self.items=[];r=self.client.process(self.query)
  self.assertEqual(r['sourceStats']['sourceTotal'],0);self.assertTrue(r['sourceStats']['sourceComplete'])
 def test_invalid_records_are_accounted_for(self):
  self.items=[{'AdId':'bad'}];r=self.client.process(self.query)
  self.assertEqual(r['ads'],[]);self.assertEqual(r['sourceStats']['invalid'],1)

if __name__=='__main__':unittest.main()
