"""Password login for Ultra Check.

The password is never stored: only a salted PBKDF2-SHA256 hash in auth.json.
Sessions live in memory, so every new start of the app asks for the password again.
"""
from __future__ import annotations
import base64,hashlib,hmac,json,os,secrets,threading,time
from pathlib import Path

ITERATIONS=600_000
MIN_LENGTH=6
MAX_LENGTH=256
FREE_ATTEMPTS=5          # wrong passwords allowed before waiting
BASE_DELAY=30            # first wait (seconds); doubles each further failure
MAX_DELAY=15*60

class AuthError(Exception):
    def __init__(self,message,retry_after=0):
        super().__init__(message);self.retry_after=int(retry_after)

def _b64(raw):return base64.b64encode(raw).decode('ascii')
def _hash(password,salt,iterations):return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,iterations)

class PasswordAuth:
    def __init__(self,path:Path):
        self.path=Path(path);self.lock=threading.Lock();self.sessions=set()
        self.failures=0;self.wait_until=0.0
    # ---- stored password ----
    def _read(self):
        try:value=json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:return None
        except (OSError,ValueError) as e:raise AuthError('The password file is damaged. Delete auth.json in the data folder to set a new password.') from e
        if not isinstance(value,dict) or value.get('algorithm')!='pbkdf2_sha256' or not all(k in value for k in ('salt','hash','iterations')):
            raise AuthError('The password file is damaged. Delete auth.json in the data folder to set a new password.')
        return value
    def configured(self):return self._read() is not None
    def _write(self,password):
        salt=secrets.token_bytes(16)
        record={'version':1,'algorithm':'pbkdf2_sha256','iterations':ITERATIONS,'salt':_b64(salt),'hash':_b64(_hash(password,salt,ITERATIONS))}
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w',encoding='utf-8') as f:json.dump(record,f);f.flush();os.fsync(f.fileno())
        os.replace(tmp,self.path)
    @staticmethod
    def _validate_new(password):
        if not isinstance(password,str) or len(password)<MIN_LENGTH:raise AuthError(f'Use a password of at least {MIN_LENGTH} characters.')
        if len(password)>MAX_LENGTH:raise AuthError(f'The password can be at most {MAX_LENGTH} characters.')
    def _matches(self,password):
        record=self._read()
        if record is None or not isinstance(password,str) or len(password)>MAX_LENGTH:return False
        try:salt=base64.b64decode(record['salt']);expected=base64.b64decode(record['hash']);iterations=int(record['iterations'])
        except (ValueError,TypeError) as e:raise AuthError('The password file is damaged. Delete auth.json in the data folder to set a new password.') from e
        return hmac.compare_digest(_hash(password,salt,iterations),expected)
    # ---- throttling ----
    def _check_wait(self):
        left=self.wait_until-time.monotonic()
        if left>0:raise AuthError(f'Too many wrong passwords. Try again in {int(left)+1} seconds.',left+1)
    def _failed(self):
        self.failures+=1
        if self.failures>=FREE_ATTEMPTS:
            delay=min(MAX_DELAY,BASE_DELAY*2**(self.failures-FREE_ATTEMPTS))
            self.wait_until=time.monotonic()+delay
            raise AuthError(f'Wrong password. Too many attempts: wait {delay} seconds.',delay)
        raise AuthError(f'Wrong password. {FREE_ATTEMPTS-self.failures} attempt(s) left before a wait.')
    # ---- public actions ----
    def _new_session(self):
        sid=secrets.token_urlsafe(32);self.sessions.add(sid);return sid
    def setup(self,password):
        with self.lock:
            if self.configured():raise AuthError('A password is already set. Log in instead.')
            self._validate_new(password);self._write(password);self.failures=0;return self._new_session()
    def login(self,password):
        with self.lock:
            if not self.configured():raise AuthError('No password is set yet. Create one first.')
            self._check_wait()
            if not self._matches(password):self._failed()
            self.failures=0;self.wait_until=0.0;return self._new_session()
    def change(self,sid,old,new):
        with self.lock:
            if not self.valid(sid):raise AuthError('Log in first.')
            self._check_wait()
            if not self._matches(old):self._failed()
            self._validate_new(new);self._write(new);self.failures=0
            self.sessions.clear();return self._new_session()   # other open tabs must log in again
    def logout(self,sid):
        with self.lock:self.sessions.discard(sid)
    def valid(self,sid):
        return bool(sid) and any(hmac.compare_digest(sid,s) for s in self.sessions)
