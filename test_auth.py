import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app_auth as a
class AuthTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.path=Path(self.dir.name)/'auth.json'
        self.patch=patch.object(a,'ITERATIONS',1000);self.patch.start()   # fast hashing in tests
        self.auth=a.PasswordAuth(self.path)
    def tearDown(self):self.patch.stop();self.dir.cleanup()
    def test_setup_then_login(self):
        self.assertFalse(self.auth.configured())
        sid=self.auth.setup('secret123');self.assertTrue(self.auth.valid(sid));self.assertTrue(self.auth.configured())
        with self.assertRaises(a.AuthError):self.auth.setup('another123')          # cannot overwrite
        self.assertTrue(self.auth.valid(self.auth.login('secret123')))
    def test_password_not_stored_in_plain_text(self):
        self.auth.setup('secret123');raw=self.path.read_text(encoding='utf-8')
        self.assertNotIn('secret123',raw);rec=json.loads(raw);self.assertEqual(rec['algorithm'],'pbkdf2_sha256');self.assertTrue(rec['salt'] and rec['hash'])
    def test_new_start_requires_login_again(self):
        sid=self.auth.setup('secret123')
        fresh=a.PasswordAuth(self.path)                                            # simulates reopening the app
        self.assertFalse(fresh.valid(sid));self.assertTrue(fresh.configured());self.assertTrue(fresh.valid(fresh.login('secret123')))
    def test_short_password_rejected(self):
        with self.assertRaises(a.AuthError):self.auth.setup('12345')
        self.assertFalse(self.auth.configured())
    def test_wrong_password_and_throttle(self):
        self.auth.setup('secret123')
        for _ in range(a.FREE_ATTEMPTS-1):
            with self.assertRaises(a.AuthError) as cm:self.auth.login('wrong')
            self.assertEqual(cm.exception.retry_after,0)
        with self.assertRaises(a.AuthError) as cm:self.auth.login('wrong')
        self.assertEqual(cm.exception.retry_after,a.BASE_DELAY)
        with self.assertRaises(a.AuthError) as cm:self.auth.login('secret123')          # even the right password waits
        self.assertGreater(cm.exception.retry_after,0)
        self.auth.wait_until=0
        with self.assertRaises(a.AuthError) as cm:self.auth.login('wrong')
        self.assertEqual(cm.exception.retry_after,a.BASE_DELAY*2)                     # doubles
        self.auth.wait_until=0;self.assertTrue(self.auth.valid(self.auth.login('secret123')));self.assertEqual(self.auth.failures,0)
    def test_logout(self):
        sid=self.auth.setup('secret123');self.auth.logout(sid);self.assertFalse(self.auth.valid(sid))
    def test_change_password_invalidates_other_sessions(self):
        sid=self.auth.setup('secret123');other=self.auth.login('secret123')
        with self.assertRaises(a.AuthError):self.auth.change(sid,'wrong','newpass456')
        new=self.auth.change(sid,'secret123','newpass456')
        self.assertTrue(self.auth.valid(new));self.assertFalse(self.auth.valid(sid));self.assertFalse(self.auth.valid(other))
        with self.assertRaises(a.AuthError):self.auth.login('secret123')
        self.assertTrue(self.auth.valid(self.auth.login('newpass456')))
    def test_change_requires_session(self):
        self.auth.setup('secret123')
        with self.assertRaises(a.AuthError):self.auth.change('not-a-session','secret123','newpass456')
    def test_invalid_inputs(self):
        self.auth.setup('secret123')
        for bad in (None,123,'',['secret123'],'x'*1000):
            with self.assertRaises(a.AuthError):self.auth.login(bad)
        self.assertFalse(self.auth.valid(''));self.assertFalse(self.auth.valid(None))
    def test_damaged_file_reports_clearly(self):
        self.path.write_text('{broken',encoding='utf-8')
        with self.assertRaises(a.AuthError) as cm:self.auth.configured()
        self.assertIn('auth.json',str(cm.exception))
if __name__=='__main__':unittest.main(verbosity=2)
