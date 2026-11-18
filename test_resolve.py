"""Google-verified domain resolution (advertiser + domain filter) and ad-format selection."""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import ultra_client as u

def ad(cid, fmt=1, adv='AR1', **extra):
    return {'1': adv, '2': cid, '3': {'3': {'2': '<img src="https://tpc.googlesyndication.com/archive/simgad/' + cid[2:] + '">'}}, '4': fmt, '12': 'Adv', **extra}

class Resolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.c = u.GoogleClient(Path(self.tmp.name), {'2704': 'Vietnam'})
        self.calls = []
    def tearDown(self): self.c.db.close(); self.tmp.cleanup()
    def google(self, listing, verified):
        """listing: the advertiser's ads; verified: {site: [cids]} as Google's advertiser+domain filter returns them."""
        def rpc(method, payload, ttl=300, fresh=False):
            self.calls.append(payload)
            site = payload['3']['12']['1']
            if not site: return {'1': listing}, u.now_iso(), False
            return {'1': [{'1': 'AR1', '2': c, '4': 1, '14': site} for c in verified.get(site, [])]}, u.now_iso(), False
        return patch.object(self.c, 'rpc', side_effect=rpc)
    def cands(self, table):
        return patch.object(self.c, 'preview_candidates', side_effect=lambda url: table.get(url.rsplit('/', 1)[-1], {'strong': [], 'weak': [], 'method': 'ocr', 'evidence': ''}))

    def test_one_verification_covers_other_ads_without_reading_them(self):
        listing = [ad('CR1'), ad('CR2'), ad('CR3')]
        with self.google(listing, {'shop.com': ['CR1', 'CR2', 'CR3']}), self.cands({'1': {'strong': ['shop.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}) as cand:
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual([a['domain'] for a in r['ads']], ['shop.com'] * 3)
        self.assertEqual({a['method'] for a in r['ads']}, {'google-verified'})
        self.assertEqual(cand.call_count, 1)                     # only the first ad's preview was read
    def test_second_pass_fixes_earlier_ad_without_candidates(self):
        listing = [ad('CR1'), ad('CR2')]
        with self.google(listing, {'shop.com': ['CR1', 'CR2']}), self.cands({'2': {'strong': ['shop.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual([(a['domain'], a['method']) for a in r['ads']], [('shop.com', 'google-verified')] * 2)
    def test_display_url_not_confirmed_keeps_google_match(self):
        # Ad shows other.com but Google lists it under real.com (found among weak candidates).
        listing = [ad('CR1')]
        with self.google(listing, {'real.com': ['CR1']}), self.cands({'1': {'strong': ['other.com'], 'weak': ['real.com'], 'method': 'preview-data', 'evidence': ''}}):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual((r['ads'][0]['domain'], r['ads'][0]['method']), ('real.com', 'google-verified'))
    def test_unverified_display_domain_is_labelled(self):
        with self.google([ad('CR1')], {}), self.cands({'1': {'strong': ['shown.com'], 'weak': [], 'method': 'ocr', 'evidence': 'x'}}):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual((r['ads'][0]['domain'], r['ads'][0]['method']), ('shown.com', 'ocr'))
    def test_long_domain_list_confirms_advertiser_level(self):
        def rpc(method, payload, ttl=300, fresh=False):
            if not payload['3']['12']['1']: return {'1': [ad('CR9')]}, u.now_iso(), False
            return {'1': [{'1': 'AR1', '2': 'CR%d' % (100 + len(self.calls)), '4': 1, '14': 'big.com'}], '2': 'more'}, u.now_iso(), False
        with patch.object(self.c, 'rpc', side_effect=lambda *a, **k: (self.calls.append(1), rpc(*a, **k))[1]), self.cands({'9': {'strong': ['big.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual((r['ads'][0]['domain'], r['ads'][0]['method']), ('big.com', 'google-domain-verified'))
        self.assertLessEqual(len(self.calls), 1 + u.VERIFY_PAGES)
    def test_weak_candidates_are_capped(self):
        weak = ['w%d.com' % i for i in range(10)]
        with self.google([ad('CR1')], {}), self.cands({'1': {'strong': [], 'weak': weak, 'method': 'preview-data', 'evidence': ''}}):
            self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual(len([p for p in self.calls if p['3']['12']['1']]), u.WEAK_CHECKS)
    def test_verification_uses_advertiser_and_domain_filters(self):
        with self.google([ad('CR1', 2)], {'shop.com': ['CR1']}), self.cands({'1': {'strong': ['shop.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}):
            self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'image', 'region': '2704'})
        p = [p for p in self.calls if p['3']['12']['1']][0]
        self.assertEqual(p['3']['13'], {'1': ['AR1']}); self.assertEqual(p['1'], 'shop.com'); self.assertEqual(p['3']['4'], 2); self.assertEqual(p['3']['8'], [2704])
    def test_resolve_mode_uses_earlier_verifications_only(self):
        with self.google([ad('CR1')], {'shop.com': ['CR1', 'CR7']}), self.cands({'1': {'strong': ['shop.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}):
            self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
            n = len(self.calls)
            r = self.c.process({'mode': 'resolve', 'advertiserId': 'AR1', 'format': 'all', 'ids': ['CR7', 'CR8', 'bad']})
        self.assertEqual([(x['id'], x['domain']) for x in r['updates']], [('CR7', 'shop.com')]); self.assertEqual(len(self.calls), n)
    def big_list(self, site):
        """Google keeps returning pages for `site` (a very large advertiser) without these ads."""
        def rpc(method, payload, ttl=300, fresh=False):
            self.calls.append(payload); s = payload['3']['12']['1']
            if not s: return {'1': [ad('CR1'), ad('CR2'), ad('CR3')]}, u.now_iso(), False
            if s == site: return {'1': [{'1': 'AR1', '2': 'CR9%d' % len(self.calls), '4': 1, '14': site}], '2': 'more'}, u.now_iso(), False
            return {'1': []}, u.now_iso(), False
        return patch.object(self.c, 'rpc', side_effect=rpc)
    def test_ad_without_domain_gets_advertisers_only_domain(self):
        # CR1 shows big.com (confirmed advertiser-level); CR2 is an app-install ad with no domain.
        with self.big_list('big.com'), patch.object(u, 'MAX_VERIFY_PAGES', 10), self.cands({'1': {'strong': ['big.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        got = {a['id']: (a['domain'], a['method']) for a in r['ads']}
        self.assertEqual(got['CR1'], ('big.com', 'google-domain-verified'))
        self.assertEqual(got['CR2'], ('big.com', 'advertiser-domain')); self.assertEqual(got['CR3'], ('big.com', 'advertiser-domain'))
    def test_no_inference_when_advertiser_has_several_domains(self):
        def rpc(method, payload, ttl=300, fresh=False):
            s = payload['3']['12']['1']
            if not s: return {'1': [ad('CR1'), ad('CR2'), ad('CR3')]}, u.now_iso(), False
            return {'1': [{'1': 'AR1', '2': 'CR9' + s[0], '4': 1, '14': s}], '2': 'more'}, u.now_iso(), False
        table = {'1': {'strong': ['a.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}, '2': {'strong': ['b.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}
        with patch.object(self.c, 'rpc', side_effect=rpc), patch.object(u, 'MAX_VERIFY_PAGES', 6), self.cands(table):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertIsNone([a for a in r['ads'] if a['id'] == 'CR3'][0]['domain'])
    def test_no_inference_from_a_complete_list(self):
        # The advertiser's only domain list is complete and lacks CR2: CR2 is not that domain.
        with self.google([ad('CR1'), ad('CR2')], {'shop.com': ['CR1']}), self.cands({'1': {'strong': ['shop.com'], 'weak': [], 'method': 'ocr', 'evidence': ''}}):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertIsNone(r['ads'][1]['domain'])
    def test_refuted_display_domain_replaced_by_advertiser_domain(self):
        # A product video shows apple.com; Google's complete apple.com list for this advertiser is empty.
        def rpc(method, payload, ttl=300, fresh=False):
            s = payload['3']['12']['1']
            if not s: return {'1': [ad('CR1'), ad('CR2', 3)]}, u.now_iso(), False
            if s == 'shop.vn': return {'1': [{'1': 'AR1', '2': 'CR1', '4': 1, '14': 'shop.vn'}], '2': 'more'}, u.now_iso(), False
            return {'1': []}, u.now_iso(), False
        table = {'1': {'strong': ['shop.vn'], 'weak': [], 'method': 'ocr', 'evidence': ''}, '2': {'strong': ['apple.com'], 'weak': [], 'method': 'preview-data', 'evidence': ''}}
        with patch.object(self.c, 'rpc', side_effect=rpc), patch.object(u, 'MAX_VERIFY_PAGES', 6), self.cands(table):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual((r['ads'][1]['domain'], r['ads'][1]['method']), ('shop.vn', 'advertiser-domain'))
    def test_price_text_is_not_a_domain(self):
        self.assertIsNone(u.site_of('990.oood')); self.assertEqual(u.site_of('www.990shop.vn'), '990shop.vn')
    def test_blocked_preview_does_not_stop_scan(self):
        with self.google([ad('CR1'), ad('CR2')], {}), patch.object(self.c, 'read_url', side_effect=u.BlockedError('limited')), patch.object(self.c, 'get_cached', return_value=(None, None)):
            r = self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'all'})
        self.assertEqual(len(r['ads']), 2); self.assertIsNone(r['ads'][0]['domain'])

class Formats(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(); self.c = u.GoogleClient(Path(self.tmp.name), {})
    def tearDown(self): self.c.db.close(); self.tmp.cleanup()
    def test_payload_per_format(self):
        self.assertNotIn('4', self.c.search_payload('AR1', fmt='all')['3'])
        for fmt, code in (('text', 1), ('image', 2), ('video', 3)): self.assertEqual(self.c.search_payload('AR1', fmt=fmt)['3']['4'], code)
    def test_invalid_format_rejected(self):
        with self.assertRaises(u.UltraError): self.c.validate({'mode': 'check', 'advertiserId': 'AR1', 'format': 'gif'})
    def test_all_formats_reverse_lists_each_format(self):
        data = {'1': [ad('CR1', 1, '14x', **{'14': 'tiki.vn'}) | {'1': 'AR1'}, ad('CR2', 2, **{'14': 'tiki.vn'}), ad('CR3', 3, **{'14': 'shop.tiki.vn'})]}
        with patch.object(self.c, 'rpc', return_value=(data, u.now_iso(), False)) as rpc:
            r = self.c.process({'mode': 'reverse', 'domain': 'https://www.tiki.vn/', 'format': 'all'})
        self.assertEqual([a['format'] for a in r['ads']], ['text', 'image', 'video'])
        self.assertEqual([a['domain'] for a in r['ads']], ['tiki.vn', 'tiki.vn', 'shop.tiki.vn'])
        self.assertNotIn('4', rpc.call_args.args[1]['3']); self.assertIn('format=IMAGE', r['ads'][1]['source'])
    def test_single_format_guard(self):
        with patch.object(self.c, 'rpc', return_value=({'1': [ad('CR1', 3)]}, u.now_iso(), False)):
            with self.assertRaises(u.UltraError): self.c.process({'mode': 'check', 'advertiserId': 'AR1', 'format': 'image'})
    def test_subdomain_query_uses_registrable_domain(self):
        with patch.object(self.c, 'rpc', return_value=({}, u.now_iso(), False)) as rpc:
            self.c.process({'mode': 'reverse', 'domain': 'shop.tiki.vn', 'format': 'all'})
        self.assertEqual(rpc.call_args.args[1]['1'], 'tiki.vn')

class Candidates(unittest.TestCase):
    def test_script_fields(self):
        video = "x({visible_url: \\x27genspark.ai\\x27,destination_url: \\x27https://www.genspark.ai/?a\\x3d1\\x27})"
        self.assertEqual(u.ranked(u.script_candidates(video)[0]), ['genspark.ai'])
        shopping = '<div>["https://encrypted-tbn0.gstatic.com/x","Bảng tuần hoàn","tiki.vn","Google"]</div>'
        self.assertEqual(u.ranked(u.script_candidates(shopping)[0]), ['tiki.vn'])
        text = '[null,null,null,null,null,null,null,"AI 作曲 | Genspark","www.genspark.ai/ナレーション/ai","desc"]'
        self.assertEqual(u.ranked(u.script_candidates(text)[0]), ['genspark.ai'])
    def test_script_weak_only_real_urls(self):
        weak = u.script_candidates('a.length;this.width;"https://cdn.ampproject.org/v0.js";"https://www.brand.com/x"')[1]
        self.assertEqual(weak, ['brand.com'])
    def test_registrable(self):
        self.assertEqual(u.registrable('www.shop.tiki.vn'), 'tiki.vn'); self.assertEqual(u.registrable('a.example.co.uk'), 'example.co.uk')
        self.assertEqual(u.registrable('fptshop.com.vn'), 'fptshop.com.vn'); self.assertIsNone(u.site_of('style.css'))
    def test_ocr_spacing_repair(self):
        self.assertEqual(u.ranked(u.ocr_candidates(['info. notion.so/', 'Notion'])[0]), ['notion.so'])

if __name__ == '__main__': unittest.main()
