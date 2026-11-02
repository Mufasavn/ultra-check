"""Optional HTTP proxy transport, encrypted settings, persistent local byte meter.

No provider billing API is used. Meter measures HTTP payloads, not TLS overhead.
"""
import copy, hashlib, json, math, os, re, secrets, socket, threading, time
import urllib.request, urllib.parse, urllib.error
from pathlib import Path
from key_vault import crypt
from ultra_client import GoogleClient, UltraError, BlockedError, SafeRedirect, HOSTS

class ProxySettings:
    def __init__(self, directory):
        self.root=Path(directory);self.path=self.root/'proxy-settings.dat';self.meter_path=self.root/'proxy-usage.json'
        self.lock=threading.RLock();self.error=''
        self.config={'enabled':False,'host':'thehub.proxy-cheap.com','port':8080,'username':'','password':'','totalGb':5.0,'baselineMb':0.0}
        self.meter={'sentBytes':0,'receivedBytes':0,'requests':0,'startedAt':time.time()}
        try:
            if self.path.exists():self.config.update(json.loads(crypt(self.path.read_bytes(),True)))
        except Exception:self.error='Could not open encrypted proxy settings. Keep the existing file and use the same Windows account.'
        try:
            if self.meter_path.exists():
                loaded=json.loads(self.meter_path.read_text(encoding='utf-8'))
                if any(not isinstance(loaded.get(k),int) or loaded[k]<0 for k in ('sentBytes','receivedBytes','requests')):raise ValueError()
                self.meter.update(loaded)
        except (ValueError,OSError,TypeError):self.error='Could not read the proxy meter. Usage was not reset.'
    def summary(self):
        with self.lock:
            c=self.config;m=self.meter;measured=m['sentBytes']+m['receivedBytes'];used=c['baselineMb']*1_000_000+measured;total=c['totalGb']*1_000_000_000
            return {k:c[k] for k in ('enabled','host','port','username','totalGb','baselineMb')} | {'saved':bool(c['password']),'configured':bool(c['username'] and c['password']),'measuredBytes':measured,'usedBytes':used,'remainingBytes':max(0,total-used),'totalBytes':total,'usedPercent':min(100,used/total*100) if total else None,'requests':m['requests'],'error':self.error,'measurement':'local-http-payloads-not-provider-billing'}
    def save(self, body):
        if self.error:raise UltraError(self.error)
        with self.lock:
            c=copy.deepcopy(self.config)
            for k in ('host','username'):
                if k in body:c[k]=str(body[k]).strip()
            if body.get('password'):c['password']=str(body['password'])
            if body.get('clear'):c['password']='';c['username']=''
            try:
                c['port']=int(body.get('port',c['port']));c['totalGb']=float(body.get('totalGb',c['totalGb']));c['baselineMb']=float(body.get('baselineMb',c['baselineMb']))
            except (ValueError,TypeError,OverflowError):raise UltraError('Invalid proxy port or allowance.') from None
            if not re.fullmatch(r'[a-zA-Z0-9.-]{1,253}',c['host']) or not 1<=c['port']<=65535:raise UltraError('Enter a valid proxy hostname and port without http://.')
            if any(not math.isfinite(c[k]) for k in ('totalGb','baselineMb')) or not 0<c['totalGb']<=1_000_000 or not 0<=c['baselineMb']<=c['totalGb']*1000:raise UltraError('Plan allowance must be positive; the baseline cannot exceed it.')
            if any(ch in c['username']+c['password'] for ch in '\r\n\x00') or len(c['username'])>250 or len(c['password'])>500:raise UltraError('Invalid proxy settings.')
            if re.search(r'_session-.+_ttl-\d+$',c['password']):raise UltraError('Enter the base password; Ultra Check adds the sticky-session suffix.')
            c['enabled']=bool(body.get('enabled',c['enabled']))
            if c['enabled'] and not(c['username'] and c['password']):raise UltraError('Enter the proxy username and password before enabling it.')
            raw=crypt(json.dumps(c).encode());tmp=self.path.with_suffix('.tmp');tmp.write_bytes(raw);os.replace(tmp,self.path);self.config=c
            return self.summary()
    def enable(self, enabled):return self.save({'enabled':enabled})
    def add(self, sent=0, received=0, request=False):
        with self.lock:
            if self.error:raise UltraError(self.error)
            self.meter['sentBytes']+=sent;self.meter['receivedBytes']+=received;self.meter['requests']+=int(request)
            tmp=self.meter_path.with_suffix('.tmp');tmp.write_text(json.dumps(self.meter),encoding='utf-8');os.replace(tmp,self.meter_path)
    def reset(self, baseline):
        # Explicit user action starts a new manual meter baseline.
        with self.lock:
            self.save({'baselineMb':baseline})
            self.meter={'sentBytes':0,'receivedBytes':0,'requests':0,'startedAt':time.time()}
            self.add();return self.summary()

class ProxyGoogleClient(GoogleClient):
    def __init__(self, directory, regions, settings, shared):
        super().__init__(directory,regions);self.settings=settings;self.cancel=shared.cancel;self.sessions={};self.session_id='';self.shared=shared;self.blocked=False
    def process(self, body):
        if self.blocked:raise BlockedError("This proxy session encountered Google's limits. Stop and try later; IP addresses are not changed automatically.")
        signature=json.dumps({k:v for k,v in body.items() if k not in ('pageToken','fresh','collectAll')},sort_keys=True)
        key=hashlib.sha256(signature.encode()).hexdigest();old=self.sessions.get(key)
        if old is not None and body.get('pageToken') and time.monotonic()-old[1]>540:raise UltraError('The proxy session is near expiry. Results are retained. Start the search again to use cached pages and open a new session.')
        # New root lookup may start a new session after TTL; a continuation never
        # swaps IP to work around a blocked request.
        if old is None or (not body.get('pageToken') and time.monotonic()-old[1]>540):
            self.sessions[key]=(secrets.token_hex(6),time.monotonic())
        self.session_id=self.sessions[key][0]
        try:return super().process(body)
        except BlockedError:
            self.blocked=True;raise
    def read_url(self,url,body=None,max_size=8_000_000):
        self.check_cancel();u=urllib.parse.urlsplit(url)
        if u.scheme!='https' or u.hostname not in HOSTS:raise UltraError('Unsupported source URL.')
        c=self.settings.config
        if not(c['enabled'] and c['username'] and c['password']):raise UltraError('The proxy is disabled or has no connection details.')
        if self.settings.summary()['remainingBytes']<=0:raise UltraError('The estimated proxy allowance has been reached. Check your plan before continuing.')
        password=c['password']+'_session-'+self.session_id+'_ttl-10'
        address='http://'+urllib.parse.quote(c['username'],safe='')+':'+urllib.parse.quote(password,safe='')+'@'+c['host']+':'+str(c['port'])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':address}),SafeRedirect())
        req=urllib.request.Request(url,data=body,headers={'User-Agent':'Mozilla/5.0','Referer':'https://adstransparency.google.com/','Content-Type':'application/x-www-form-urlencoded'})
        for attempt in range(3):
            self.check_cancel()
            delay=max(0,2-(time.monotonic()-self.last_call))
            if self.cancel.wait(delay):self.check_cancel()
            self.last_call=time.monotonic();self.settings.add(sent=len(body or b''),request=True)
            try:
                with opener.open(req,timeout=30) as response:
                    chunks=[];size=0
                    while True:
                        self.check_cancel();chunk=response.read(min(65536,max_size+1-size))
                        if not chunk:break
                        self.settings.add(received=len(chunk));chunks.append(chunk);size+=len(chunk)
                        if size>max_size:raise UltraError('The source response exceeds the size limit.')
                    return b''.join(chunks)
            except urllib.error.HTTPError as error:
                if error.code in (403,429):raise BlockedError('Google access is restricted. Stopped; no IP changes or CAPTCHA bypass.') from None
                if error.code==407:raise UltraError('Proxy authentication failed (407). Check your username and base password.') from None
                if error.code in (500,502,503,504):
                    if attempt==2:raise UltraError('Source returned HTTP '+str(error.code)+' after 3 attempts in the same session. Click Retry or Continue loading; downloaded results are retained.') from None
                    self.progress='Source is slow · retrying the same page in the same session…'
                    if self.cancel.wait(3):self.check_cancel()
                    continue
                raise UltraError('Source returned HTTP error '+str(error.code)+'. Results are incomplete.') from None
            except (urllib.error.URLError,TimeoutError,OSError) as error:
                cause=getattr(error,'reason',error);reason=str(cause)
                match=re.search(r'Tunnel connection failed:\s*(\d{3})',reason,re.I)
                code=int(match[1]) if match else None
                if code==407:raise UltraError('Proxy authentication failed (407). Check your username and base password.') from None
                if code in (403,429):raise BlockedError('The proxy gateway reported HTTP restriction '+str(code)+'. Stopped; session unchanged.') from None
                if code==400:raise UltraError('The proxy rejected connection parameters (400). Check your username, base password and HTTP proxy type.') from None
                if code==402:raise UltraError('The proxy requires payment (402). Check your Proxy-Cheap plan status and allowance.') from None
                if isinstance(cause,socket.gaierror):raise UltraError('Could not resolve the proxy hostname. Check the hostname and Internet connection.') from None
                if 'certificate verify failed' in reason.lower():raise UltraError('Could not verify the connection certificate. Check Windows date/time or network certificates. TLS verification remains enabled.') from None
                transient=code in (500,502,503,504) or isinstance(cause,(TimeoutError,ConnectionResetError,ConnectionAbortedError)) or getattr(cause,'winerror',None) in (10054,10060,10061) or any(text in reason.lower() for text in ('timed out','timeout'))
                if not transient or attempt==2:
                    detail=('Proxy-Cheap returned HTTP '+str(code)) if code else ('Proxy connection timed out' if transient else 'Could not connect to the proxy')
                    raise UltraError(detail+'. '+('Tried 3 attempts in the same session. ' if attempt==2 else '')+'Click Retry or Continue loading. Downloaded results are retained.') from None
                self.progress='Proxy is slow'+(' (HTTP '+str(code)+')' if code else '')+' · retrying the same page in the same session…'
                if self.cancel.wait(3):self.check_cancel()
