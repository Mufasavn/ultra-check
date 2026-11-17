"""Browser-session transport for Google transparency RPCs.

The Ultra Check Bridge extension runs each RPC inside the user's own
adstransparency.google.com tab (same origin, the browser's own cookies and
network stack). This module is the local queue between the Python client and
the Ultra Check page, which relays jobs to the extension.

No CAPTCHA bypass: when Google asks for verification the job fails with
BlockedError and the user completes the check in the tab themselves.
"""
from __future__ import annotations
import secrets,threading,time
from ultra_client import UltraError,BlockedError,CancelledError

METHODS={'SearchService/SearchCreatives','SearchService/SearchSuggestions','LookupService/GetCreativeById'}
MAX_TEXT=8_000_000

class BrowserBridge:
    ONLINE_WINDOW=8
    def __init__(self):
        self.cond=threading.Condition();self.pending=[];self.jobs={}
        self.last_seen=None;self.waiting=0;self.version='';self.last_error=''
    def online(self):
        with self.cond:return self.waiting>0 or (self.last_seen is not None and time.monotonic()-self.last_seen<self.ONLINE_WINDOW)
    def summary(self):
        return {'online':self.online(),'extensionVersion':self.version,'lastError':self.last_error}
    def poll(self,version='',wait=15):
        """Called by the Ultra Check page: wait for the next job (long poll)."""
        with self.cond:
            self.version=str(version or '')[:20];self.waiting+=1
            try:
                end=time.monotonic()+wait
                while not self.pending:
                    left=end-time.monotonic()
                    if left<=0:return None
                    self.cond.wait(left)
                job=self.pending.pop(0)
                return {'id':job['id'],'method':job['method'],'body':job['body']}
            finally:
                self.waiting-=1;self.last_seen=time.monotonic()
    def result(self,job_id,payload):
        with self.cond:
            job=self.jobs.get(job_id)
            if not job or job['done']:return False
            job['result']=payload if isinstance(payload,dict) else {};job['done']=True
            self.cond.notify_all();return True
    def call(self,method,body,cancel,timeout=45):
        """Run one RPC in the browser tab and return the raw response text."""
        if method not in METHODS:raise UltraError('Unsupported source method.')
        job={'id':secrets.token_hex(8),'method':method,'body':body,'done':False,'result':None}
        with self.cond:
            self.jobs[job['id']]=job;self.pending.append(job);self.cond.notify_all()
            end=time.monotonic()+timeout
            try:
                while not job['done']:
                    if cancel.is_set():raise CancelledError('Scan stopped at your request. Downloaded results are retained.')
                    left=end-time.monotonic()
                    if left<=0:
                        self.last_error='timeout'
                        raise UltraError('The Ultra Check Bridge extension did not answer in time. Keep the Ultra Check page open in Chrome and try again.')
                    self.cond.wait(min(left,.25))
            finally:
                self.jobs.pop(job['id'],None)
                if job in self.pending:self.pending.remove(job)
        return self.interpret(job['result'])
    def interpret(self,r):
        try:status=int(r.get('status') or 0)
        except (TypeError,ValueError):status=0
        url=str(r.get('url') or '');text=r.get('text')
        if r.get('blocked') or status in (403,429) or '/sorry/' in url:
            self.last_error='blocked'
            raise BlockedError('Google asks for verification in your Chrome tab. Complete it there yourself, then try again. Ultra Check does not bypass CAPTCHA.')
        if r.get('error') or status==0:
            self.last_error=str(r.get('error') or 'no response')[:200]
            raise UltraError('Chrome could not load Google data: '+self.last_error)
        if status!=200:
            self.last_error='HTTP '+str(status)
            detail=' '.join(str(r.get('detail') or '').split())[:200]
            raise UltraError('Google returned HTTP error '+str(status)+'. This is not an empty result.'+(' Details: '+detail if detail else ''))
        if not isinstance(text,str) or len(text)>MAX_TEXT:raise UltraError('The source response is missing or exceeds the size limit.')
        self.last_error='';return text
