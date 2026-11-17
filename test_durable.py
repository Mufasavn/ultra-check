import tempfile,unittest,os,json
from pathlib import Path
from unittest.mock import patch
from data_store import data_directory
from saved_store import SavedStore
class DurableTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_fixed_path_survives_different_exe_folders(self):
  old=self.root/'old';old.mkdir();source=old/'UltraCheck-data';source.mkdir();SavedStore(source/'saved.json').update({'kind':'advertisers','value':'Adcore East Limited'});SavedStore(source/'saved.json').update({'kind':'domains','value':'getdex.com'})
  with patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'profile')}):
   first=data_directory(old);store=SavedStore(first/'saved.json');store.update({'kind':'domains','value':'example.com'})
   second=data_directory(self.root/'new-version');self.assertEqual(first,second);self.assertEqual(SavedStore(second/'saved.json').read()['domains'],['getdex.com','example.com']);self.assertEqual(SavedStore(second/'saved.json').read()['advertisers'],['Adcore East Limited'])
 def test_backup_and_deleted_items_not_reimported(self):
  old=self.root/'old';old.mkdir();source=old/'UltraCheck-data';source.mkdir();SavedStore(source/'saved.json').update({'kind':'domains','value':'getdex.com'})
  with patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'profile')}):
   data=data_directory(old);store=SavedStore(data/'saved.json');store.update({'kind':'domains','value':'getdex.com','remove':True});data_directory(old);self.assertEqual(store.read()['domains'],[])
   store.update({'kind':'domains','value':'example.com'});store.update({'kind':'domains','value':'second.com'});store.path.write_text('corrupt');self.assertEqual(store.read()['domains'],['example.com'])
 def test_explicit_data_dir_is_respected(self):self.assertEqual(data_directory(self.root,self.root/'test-data'),self.root/'test-data')
if __name__=='__main__':unittest.main()
