"""The browser loads the extension from a fixed folder: the app must keep it, not recreate it."""
import json, os, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
import ultra_server as s

class ExtensionInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.src = root / 'bundle' / 'chrome-extension'; self.src.mkdir(parents=True)
        (self.src / 'manifest.json').write_text('{"version": "1.0.0"}'); (self.src / 'background.js').write_text('// v1')
        self.data = root / 'data'
    def tearDown(self): self.tmp.cleanup()
    def install(self):
        with patch.object(s, 'ROOT', self.src.parent): return Path(s.install_extension(self.data))

    def test_fixed_folder_with_note(self):
        dst = self.install()
        self.assertEqual(dst, self.data / 'chrome-extension')
        self.assertEqual((dst / 'background.js').read_text(), '// v1')
        self.assertIn('do not delete', (dst / 'READ-ME-DO-NOT-DELETE.txt').read_text())
    def test_unchanged_files_are_not_rewritten(self):
        dst = self.install(); old = time.time() - 3600
        os.utime(dst / 'background.js', (old, old))
        self.install()
        self.assertAlmostEqual((dst / 'background.js').stat().st_mtime, old, delta=1)
    def test_update_changes_files_in_place(self):
        dst = self.install(); marker = dst / 'browser-state.tmp'; marker.write_text('kept')
        (self.src / 'background.js').write_text('// v2')
        self.assertEqual(self.install(), dst)
        self.assertEqual((dst / 'background.js').read_text(), '// v2')
        self.assertTrue(marker.exists())                  # the folder itself is never recreated
    def test_real_manifest_has_fixed_id_key(self):
        manifest = json.loads((Path(__file__).parent / 'chrome-extension' / 'manifest.json').read_text(encoding='utf-8'))
        self.assertTrue(manifest.get('key', '').startswith('MIIB'))

if __name__ == '__main__': unittest.main()
