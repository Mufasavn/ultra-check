import json,unittest,urllib.error,threading
from pathlib import Path
from unittest.mock import Mock,patch
import ultra_client as u
class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.c=u.GoogleClient(Path(__file__).parent/'unit-cache',{'2704':'Vietnam','2250':'France'})
    def test_filters(self):
        p=self.c.search_payload('AR123','2704','2024-02-29','2024-02-29','token')
        self.assertEqual(p['3']['4'],1);self.assertEqual(p['3']['14'],[3]);self.assertEqual(p['3']['8'],[2704]);self.assertEqual(p['3']['6'],20240229);self.assertEqual(p['3']['7'],20240301);self.assertEqual(p['4'],'token')
    def test_all_countries_and_all_dates(self):
        p=self.c.search_payload('AR123');self.assertNotIn('8',p['3']);self.assertNotIn('6',p['3']);self.assertNotIn('7',p['3'])
    def test_current_query_uses_today(self):
        with patch.object(self.c,'rpc',return_value=({},u.now_iso(),False)) as rpc:self.c.process({'mode':'current','advertiserId':'AR123','start':'2024-01-01','end':'2024-01-01'});self.assertEqual(rpc.call_args.args[1]['3']['6'],u.day_number(u.today()))
    def test_validation(self):
        for body in [{'mode':'check','advertiserId':'not-an-id'},{'mode':'check','advertiserId':'AR1','region':'unknown'},{'mode':'check','advertiserId':'AR1','start':'2025-02-29','end':'2025-02-29'},{'mode':'check','advertiserId':'AR1','start':'2099-01-01','end':'2099-01-01'}]:
            with self.assertRaises(u.UltraError):self.c.validate(body)
    def test_domains(self):
        self.assertEqual(u.domain('https://www.snapwidget.com/path'),'snapwidget.com');self.assertEqual(u.domain('cloud.vmoscloud.com'),'cloud.vmoscloud.com');self.assertIsNone(u.domain('javascript:alert(1)'));self.assertIsNone(u.domain('https://user:pw@example.com'))
    def test_ocr_no_description_mining(self):
        self.assertEqual(u.ocr_domain(['SnapWidget','www.snapwidget.com/','Help']),'snapwidget.com');self.assertIsNone(u.ocr_domain(['Brand','Headline','Description: example.com']));self.assertIsNone(u.ocr_domain(['one.example two.example']));self.assertIsNone(u.ocr_domain(['https://']))
    def test_cache_keeps_timestamp(self):
        payload={'1':'unit'};self.c.put_cached('rpc:unit:'+json.dumps(payload,sort_keys=True),{'1':[]})
        with patch.object(self.c,'read_url',side_effect=AssertionError('cache should not fetch')):
            data,when,cached=self.c.rpc('unit',payload);self.assertTrue(cached);self.assertEqual(data,{'1':[]});self.assertTrue(when)
    def test_block_is_not_empty(self):
        fake=Mock();fake.open.side_effect=urllib.error.HTTPError(u.GOOGLE,429,'Limited',{},None)
        with patch.object(self.c,'opener',fake):
            with self.assertRaises(u.BlockedError):self.c.read_url(u.GOOGLE)
    def test_schema_change_is_not_empty(self):
        with patch.object(self.c,'rpc',return_value=({'unexpected':'value'},u.now_iso(),False)):
            with self.assertRaises(u.UltraError):self.c.process({'mode':'check','advertiserId':'AR1'})
    def test_does_not_request_advertiser_sites(self):
        with self.assertRaises(u.UltraError):self.c.read_url('https://snapwidget.com')
    def test_cancellation(self):
        self.c.cancel.set()
        try:
            with self.assertRaises(u.CancelledError):self.c.read_url(u.GOOGLE)
        finally:self.c.cancel.clear()
    def test_reverse_query_filters_and_paging(self):
        with patch.object(self.c,'rpc',return_value=({},u.now_iso(),False)) as rpc:
            self.c.process({'mode':'reverse','domain':'https://www.snapwidget.com/path','region':'2704','start':'2026-10-01','end':'2026-10-01','pageToken':'next'})
            p=rpc.call_args.args[1]
            self.assertEqual(p['1'],'snapwidget.com');self.assertEqual(p['3']['12']['1'],'snapwidget.com');self.assertNotIn('13',p['3'])
            self.assertEqual(p['3']['4'],1);self.assertEqual(p['3']['14'],[3]);self.assertEqual(p['4'],'next');self.assertEqual(p['3']['7'],20261002)
    def test_reverse_multiple_accounts_and_no_ocr(self):
        data={'1':[{'1':'AR1','2':'CR1','4':1,'14':'snapwidget.com','12':'One','6':{'1':'1700000000'},'7':{'1':'1701000000'}},{'1':'AR2','2':'CR2','4':1,'14':'snapwidget.com','12':'Two'}],'2':'next'}
        with patch.object(self.c,'rpc',return_value=(data,u.now_iso(),False)),patch.object(self.c,'decode_preview',side_effect=AssertionError('No OCR for matched domains')):
            r=self.c.process({'mode':'reverse','domain':'snapwidget.com'})
            self.assertEqual([a['advertiserId'] for a in r['ads']],['AR1','AR2']);self.assertEqual(r['nextPageToken'],'next');self.assertTrue(r['ads'][0]['first'])
            self.assertIn('/advertiser/AR2/',r['ads'][1]['source'])
    def test_reverse_wrong_domain_not_attributed(self):
        data={'1':[{'1':'AR1','2':'CR1','4':1,'14':'other.example'}]}
        with patch.object(self.c,'rpc',return_value=(data,u.now_iso(),False)):
            r=self.c.process({'mode':'reverse','domain':'snapwidget.com'});self.assertIsNone(r['ads'][0]['domain']);self.assertTrue(r['warning'])
    def test_reverse_current_ignores_historical_bounds(self):
        with patch.object(self.c,'rpc',return_value=({},u.now_iso(),False)) as rpc:
            self.c.process({'mode':'reverse-current','domain':'snapwidget.com','start':'2024-01-01','end':'2024-01-01'})
            self.assertEqual(rpc.call_args.args[1]['3']['6'],u.day_number(u.today()))
        with self.assertRaises(u.UltraError):self.c.validate({'mode':'reverse','domain':'invalid'})
    def test_text_only_guard(self):
        data={'1':[{'1':'AR1','2':'CR1','4':2}]}
        with patch.object(self.c,'rpc',return_value=(data,u.now_iso(),False)):
            with self.assertRaises(u.UltraError):self.c.process({'mode':'check','advertiserId':'AR1'})
if __name__=='__main__':unittest.main(verbosity=2)
