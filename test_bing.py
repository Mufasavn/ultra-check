import copy
import io
import json
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
from bing_client import BingClient,BASE,COUNTRIES,text_candidate,today_utc
from ultra_client import GoogleClient,UltraError

# A small public Microsoft response captured during integration, not fabricated
# production data. Ad and advertiser IDs deliberately remain strings downstream.
REAL_AD={"AdId":77515820095524,"AdvertiserName":"INMOBI TECHNOLOGY SERVICES PTE. LTD.",
 "AdvertiserId":4295402380,"Title":"Waterdropfilter.com - Advanced Filtration Tech",
 "Description":"Experience the joy of pure water with our advanced filtration system today!.",
 "DisplayUrl":"www.waterdropfilter.com","DestinationUrl":"https://www.waterdropfilter.com/products/example",
 "AssetJson":"","AdDetails":{"StartDate":"2026-10-11","EndDate":"2026-10-14"}}

class BingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.cache=GoogleClient(Path(self.tmp.name),{})
  self.bing=BingClient(self.cache);self.bing.interval=0
 def tearDown(self):self.cache.db.close();self.tmp.cleanup()
 def respond(self,ads=None,count=None):
  def call(path,params=None,**kw):
   if path=='Ads':return {'value':ads if ads is not None else [REAL_AD],**({'@odata.count':count} if count is not None else {})},'2026-11-01T00:00:00+00:00',False
   return REAL_AD,'2026-11-01T00:00:00+00:00',False
  self.bing._request=Mock(side_effect=call)
 def test_real_response_dates_and_domain(self):
  self.respond();r=self.bing.process({'mode':'reverse','domain':'https://www.waterdropfilter.com/'})
  self.assertEqual(len(r['ads']),1);ad=r['ads'][0]
  self.assertEqual(ad['advertiserId'],'4295402380');self.assertEqual(ad['domain'],'waterdropfilter.com')
  self.assertEqual(ad['first'],'2026-10-11T00:00:00+00:00');self.assertEqual(ad['last'],'2026-10-14T00:00:00+00:00')
  self.assertIn('/ad/77515820095524',ad['source']);self.assertFalse(ad['placementVerified'])
  self.assertTrue(r['coverageLimited']);self.assertIn('not all advertisers',r['warning']);self.assertFalse(r['incomplete'])
 def test_domain_lookalikes_are_not_matches(self):
  for host in ['waterdropfilter.com.evil.example','notwaterdropfilter.com','waterdropfilter.company']:
   ad={**REAL_AD,'DestinationUrl':'https://'+host,'DisplayUrl':host}
   self.assertIsNone(self.bing._normalize(ad,'waterdropfilter.com'))
 def test_subdomain_is_verified_but_grouped_under_query(self):
  ad={**REAL_AD,'DestinationUrl':'https://shop.waterdropfilter.com','DisplayUrl':'shop.waterdropfilter.com'}
  self.assertEqual(self.bing._normalize(ad,'waterdropfilter.com')['domain'],'waterdropfilter.com')
 def test_title_mention_does_not_make_url_match(self):
  ad={**REAL_AD,'DestinationUrl':'https://unrelated.example','DisplayUrl':'unrelated.example'}
  self.assertIsNone(self.bing._normalize(ad,'waterdropfilter.com'))
 def test_display_host_match_does_not_claim_destination_match(self):
  ad={**REAL_AD,'DestinationUrl':'https://tracking.example/click'}
  result=self.bing._normalize(ad,'waterdropfilter.com')
  self.assertEqual(result['domain'],'waterdropfilter.com')
  self.assertEqual(result['method'],'bing-display-url')
 def test_media_and_incomplete_text_are_excluded(self):
  self.assertFalse(text_candidate({**REAL_AD,'AssetJson':'https://assets.example/image.json'}))
  self.assertFalse(text_candidate({**REAL_AD,'Title':'','Description':''}))
  self.assertFalse(text_candidate({**REAL_AD,'DisplayUrl':'','DestinationUrl':''}))
 def test_paging_uses_numeric_microsoft_id_and_filters(self):
  self.respond(ads=[{**REAL_AD,"AdId":n} for n in range(1,13)])
  body={'mode':'check','advertiserId':'4295402380','region':'72','start':'2026-10-01','end':'2026-10-20'}
  r=self.bing.process(body);self.assertTrue(r['nextPageToken']);self.assertTrue(r['incomplete'])
  self.bing.process({**body,'pageToken':r['nextPageToken']})
  calls=[c for c in self.bing._request.call_args_list if c.args[0]=='Ads']
  self.assertEqual(calls[-1].args[1],{'top':12,'skip':12,'advertiserId':'4295402380','countryCodes':'72','startDate':'2026-10-01','endDate':'2026-10-20'})
 def test_server_capped_page_with_total_continues(self):
  self.respond(ads=[REAL_AD]*3,count=8)
  r=self.bing.process({'mode':'reverse','domain':'waterdropfilter.com'})
  self.assertTrue(r['nextPageToken'])
 def test_token_cannot_cross_platform_queries(self):
  self.respond(ads=[{**REAL_AD,"AdId":n} for n in range(1,13)])
  r=self.bing.process({'mode':'reverse','domain':'waterdropfilter.com'})
  with self.assertRaises(UltraError):self.bing.process({'mode':'reverse','domain':'other.example','pageToken':r['nextPageToken']})
 def test_missing_detail_cannot_hide_remaining_list_records(self):
  items=[{**REAL_AD,'AdId':n} for n in (11,12,13)]
  def request(path,params=None,**kw):
   if path=='Ads':return {'value':items},'2026-11-01',False
   if path=='Ads/12':raise UltraError('rate limit')
   return {**REAL_AD,'AdId':int(path.split('/')[1])},'2026-11-01',False
  self.bing._request=Mock(side_effect=request)
  r=self.bing.process({'mode':'reverse','domain':'waterdropfilter.com'})
  self.assertEqual([a['id'] for a in r['ads']],['11','12','13']);self.assertFalse(r['incomplete'])
  self.assertEqual(self.bing._request.call_count,1)
 def test_failure_is_not_an_empty_complete_result(self):
  self.bing._request=Mock(side_effect=UltraError('offline'))
  r=self.bing.process({'mode':'reverse','domain':'waterdropfilter.com'})
  self.assertTrue(r['incomplete']);self.assertTrue(r['nextPageToken']);self.assertTrue(r['halt'])
 def test_mismatched_detail_id_is_not_attached(self):
  self.respond();r=self.bing.process({'mode':'dates','records':[{'id':'9','advertiserId':'4295402380'}]})
  self.assertEqual(r['ads'],[]);self.assertTrue(r['incomplete'])
 def test_country_date_ids_and_modes_rejected_before_network(self):
  self.bing._request=Mock(side_effect=AssertionError('network'))
  for body in [{'mode':'check','advertiserId':'AR123'},{'mode':'reverse','domain':'bad'},
   {'mode':'reverse','domain':'test.example','region':'2840'},
   {'mode':'reverse','domain':'test.example','start':'2026-10-02','end':'2026-10-01'},
   {'mode':'reverse','domain':'test.example','start':'2099-01-01','end':'2099-01-02'},
   {'mode':'current','advertiserId':'123'}]:
   with self.assertRaises(UltraError):self.bing.process(body)
 def test_numeric_profile_is_resolved_not_invented(self):
  self.bing._request=Mock(return_value=({'AdvertiserId':123,'AdvertiserName':'Name'},'at',True))
  r=self.bing.process({'mode':'discover','text':'123'})
  self.assertEqual(r['candidates'],[{'id':'123','name':'Name','country':''}])
  self.assertEqual(self.bing._request.call_args.args[0],'Advertisers/123')
 def test_discovery_count_pagination(self):
  self.bing._request=Mock(return_value=({'value':[{'AdvertiserId':123,'AdvertiserName':'Name'}],'@odata.count':2},'at',True))
  r=self.bing.process({'mode':'discover','text':'Name'});self.assertTrue(r['nextPageToken'])
 def test_cache_uses_original_timestamp_and_no_network(self):
  key='bing:v1:'+BASE+'Advertisers/123';self.cache.put_cached(key,{'AdvertiserId':123})
  self.bing.opener=Mock();_,at,cached=self.bing._request('Advertisers/123')
  self.assertTrue(cached);self.bing.opener.open.assert_not_called();self.assertIn('T',at)
 def test_429_cooldown_persists_and_prevents_retries(self):
  self.bing.opener=Mock();self.bing.opener.open.side_effect=urllib.error.HTTPError(BASE,429,'limited',{'Retry-After':'120'},io.BytesIO())
  with self.assertRaises(UltraError):self.bing._request('Ads')
  other=BingClient(self.cache);other.opener=Mock()
  with self.assertRaises(UltraError):other._request('Advertisers')
  other.opener.open.assert_not_called();self.assertEqual(self.bing.opener.open.call_count,1)
 def test_bad_json_is_not_cached(self):
  response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock();response.read.return_value=b'<html>blocked</html>'
  self.bing.opener=Mock();self.bing.opener.open.return_value=response
  with self.assertRaises(UltraError):self.bing._request('Ads')
  self.assertIsNone(self.cache.get_cached('bing:v1:'+BASE+'Ads',3600)[0])
 def test_cancel_retains_downloaded_ads(self):
  self.respond(ads=[REAL_AD]*2)
  original=self.bing._normalize
  def normalize(*args):
   out=original(*args);self.cache.cancel.set();return out
  self.bing._normalize=normalize
  r=self.bing.process({'mode':'reverse','domain':'waterdropfilter.com'})
  self.assertEqual(len(r['ads']),2);self.assertFalse(r['incomplete'])
 def test_unknown_dates_remain_unknown(self):
  ad=self.bing._normalize({**REAL_AD,'AdDetails':{'StartDate':'garbage'}})
  self.assertIsNone(ad['first']);self.assertIsNone(ad['last'])
 def test_metadata_no_global_coverage_claim(self):
  info=self.bing.metadata();self.assertEqual(len(COUNTRIES),30);self.assertNotIn('2840',COUNTRIES)
  self.assertFalse(info['paid']);self.assertIn('EU/EEA',info['scope']);self.assertEqual(info['today'],today_utc())

if __name__=='__main__':unittest.main()
