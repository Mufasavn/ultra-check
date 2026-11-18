"""Display-URL extraction from Windows OCR lines of Google Search text-ad images.

Line lists below are the real OCR output of ads from advertiser
AR10717808501658222593 (Nov 2026). The newer layout adds an advertiser-name
line, which pushes the display URL to the third line.
"""
import unittest
import ultra_client as u

class OcrLayout(unittest.TestCase):
    def test_new_layout_with_advertiser_name_line(self):
        self.assertEqual(u.ocr_domain(['Sponsored','Host Havoc','www.hosthavoc.com/','HostHavoc Game Hosting','Host Havoc - Game Server and Infrastructure Hosting','Provider']),'hosthavoc.com')
        self.assertEqual(u.ocr_domain(['Sponsored','eXtremeRate','www.extremerate.com/','ExtremeRate Controller Mods - Shop','ExtremeRate Accessories']),'extremerate.com')
    def test_layout_without_advertiser_name_line(self):
        self.assertEqual(u.ocr_domain(['Sponsored','www.pond5.com/','Pond5 Offical Site','Power your creative team with unlimited access to stock']),'pond5.com')
    def test_label_and_breadcrumbs_on_one_line(self):
        self.assertEqual(u.ocr_domain(['Ad · www.example.com › shop › deals','Headline']),'example.com')
        self.assertEqual(u.ocr_domain(['Quảng cáo','Brand','https://shop.example.vn › sale','Tiêu đề']),'shop.example.vn')
    def test_brand_named_ads_is_not_stripped(self):
        self.assertEqual(u.ocr_domain(['ads-gorilla.com/','Headline']),'ads-gorilla.com')
        self.assertEqual(u.ocr_domain(['Sponsored','Ads Gorilla','ads-gorilla.com/','Headline']),'ads-gorilla.com')
    def test_ocr_noise_before_url(self):
        self.assertEqual(u.ocr_domain(['Sponsored','@ www.pond5.com/','Headline']),'pond5.com')
    def test_no_domain_from_headline_or_description(self):
        self.assertIsNone(u.ocr_domain(['Sponsored','Brand','Visit example.com for deals today','Description']))
        self.assertIsNone(u.ocr_domain(['Sponsored','Brand','Headline','Example.com Official Site']))
        self.assertIsNone(u.ocr_domain(['Sponsored','Brand','Headline','Description','www.late.com/']))
    def test_ambiguous_line_is_rejected(self):
        self.assertIsNone(u.ocr_domain(['Sponsored','www.one.com/ www.two.com/','Headline']))
    def test_empty_input(self):
        self.assertIsNone(u.ocr_domain([]))
        self.assertIsNone(u.ocr_domain(['Sponsored']))

if __name__=='__main__':unittest.main()
