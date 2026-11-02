import unittest,tempfile,json,threading
from pathlib import Path
from saved_store import SavedStore
class SavedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'saved.json';self.store=SavedStore(self.path)
 def tearDown(self):self.tmp.cleanup()
 def test_persistence_duplicates_removal(self):
  self.store.update({'kind':'advertisers','value':' Adcore East Limited '})
  self.store.update({'kind':'advertisers','value':'adcore east limited'})
  self.assertEqual(SavedStore(self.path).read()['advertisers'],['Adcore East Limited'])
  self.store.update({'kind':'advertisers','value':'ADCORE EAST LIMITED','remove':True})
  self.assertEqual(self.store.read()['advertisers'],[])
 def test_domain_normalization(self):
  self.store.update({'kind':'domains','value':'https://www.Example.com/path'})
  self.assertEqual(self.store.read()['domains'],['example.com'])
 def test_bad_input(self):
  for body in [{'kind':'bad','value':'x'},{'kind':'domains','value':'bad'},{'kind':'advertisers','value':'x\ny'},{'kind':'advertisers','value':''}]:
   with self.assertRaises(ValueError):self.store.update(body)
 def test_corrupt_preserved(self):
  self.path.write_text('broken')
  with self.assertRaises(ValueError):self.store.update({'kind':'advertisers','value':'x'})
  self.assertEqual(self.path.read_text(),'broken')
 def test_concurrent_updates(self):
  threads=[threading.Thread(target=self.store.update,args=({'kind':'advertisers','value':str(i)},)) for i in range(20)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(len(self.store.read()['advertisers']),20)
if __name__=='__main__':unittest.main()
