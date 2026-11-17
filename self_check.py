import asyncio,json,os,urllib.request,urllib.error
from ultra_client import recognize_image,ocr_domain
def run(server,token,assets):
    """Packaged self-test. Needs a fresh --data-dir (no password set yet).
    Live Google lookups run only when ULTRA_LIVE_TEST=1."""
    url=f'http://127.0.0.1:{server.server_port}';jar={'cookie':''}
    def request(path,body=None,auth=True,origin=None,session=True):
        headers={'Cookie':jar['cookie']} if session and jar['cookie'] else {}
        if body is not None:headers.update({'Content-Type':'application/json','X-Ultra-Token':token if auth else 'invalid','Origin':origin or url})
        req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=60) as r:
                set_cookie=r.headers.get('Set-Cookie')
                if set_cookie:jar['last_set_cookie']=set_cookie;jar['cookie']=set_cookie.split(';')[0]
                return r.status,r.read().decode('utf-8')
        except urllib.error.HTTPError as e:return e.code,e.read().decode('utf-8')
    checks=[]
    status,content=request('/');assert status==200 and 'Ultra Check Windows' in content;checks.append('HTML/assets served')
    # ---- login gate ----
    status,content=request('/api/auth/status');st=json.loads(content)
    assert status==200 and not st['authenticated'],st
    assert not st['configured'],'Self-test needs a fresh --data-dir without a password'
    assert request('/api/search')[0]==401;assert request('/api/saved')[0]==401;assert request('/api/apify-keys')[0]==401
    assert request('/api/search',{'mode':'discover','text':'test'})[0]==401;assert request('/api/shutdown',{})[0]==401;assert request('/api/proxy',{'enabled':False})[0]==401
    checks.append('All data and actions blocked before login (GET and POST)')
    assert request('/api/auth/setup',{'password':'12345'})[0]==400;checks.append('Short password rejected')
    assert request('/api/auth/setup',{'password':'selftest-pass-1'},auth=False)[0]==403;checks.append('Login endpoints still require the page token')
    status,_=request('/api/auth/setup',{'password':'selftest-pass-1'});assert status==200 and 'HttpOnly' in jar['last_set_cookie'] and 'SameSite=Strict' in jar['last_set_cookie'],jar
    checks.append('First-run password created; HttpOnly session cookie set')
    assert request('/api/auth/setup',{'password':'other-pass-2'})[0]==400;checks.append('Existing password cannot be overwritten by setup')
    status,content=request('/api/search');assert status==200 and json.loads(content)['configured'];checks.append('Data available after login')
    assert request('/api/search',{'mode':'discover','text':'x'},session=False)[0]==401;checks.append('Requests without the session cookie still blocked')
    assert request('/api/auth/logout',{})[0]==200;assert request('/api/search')[0]==401;checks.append('Lock (logout) ends the session')
    assert request('/api/auth/login',{'password':'wrong-pass'})[0]==400;checks.append('Wrong password rejected')
    assert request('/api/auth/login',{'password':'selftest-pass-1'})[0]==200 and request('/api/search')[0]==200;checks.append('Correct password logs in')
    old=jar['cookie'];assert request('/api/auth/change',{'oldPassword':'selftest-pass-1','newPassword':'selftest-pass-2'})[0]==200
    assert request('/api/search')[0]==200;jar['cookie'],keep=old,jar['cookie'];assert request('/api/search')[0]==401;jar['cookie']=keep
    checks.append('Password change issues a new session and ends old ones')
    # ---- original 2.9 checks (now behind login) ----
    assert request('/api/search',{'mode':'discover','text':'test'},auth=False)[0]==403;checks.append('Invalid token rejected')
    assert request('/api/search',{'mode':'discover','text':'test'},origin='https://other.example')[0]==403;checks.append('Cross-origin rejected')
    assert request('/../../ultra_client.py')[0]==404;checks.append('Source paths not served')
    assert request('/api/search',{'mode':'check','advertiserId':'AR123','region':'invalid'})[0]==400;checks.append('Invalid region rejected')
    assert request('/api/search',{'mode':'check','advertiserId':'AR123','start':'2026-10-02','end':'2026-10-01'})[0]==400;checks.append('Invalid date range rejected')
    assert request('/api/search',{'mode':'reverse','domain':'invalid'})[0]==400;checks.append('Invalid domain rejected')
    lines=asyncio.run(recognize_image((assets/'selftest.png').read_bytes()))
    assert ocr_domain(lines)=='ads-gorilla.com';checks.append('Packaged Windows OCR correctly reads known Google text-ad image')
    data=reverse=None
    if os.getenv('ULTRA_LIVE_TEST')=='1':
        status,content=request('/api/search',{'mode':'check','advertiserId':'AR15863532213959131137','region':'2704','start':'2026-10-01','end':'2026-10-01'})
        data=json.loads(content)
        assert status==200 and len(data['ads'])==1 and data['ads'][0]['domain']=='snapwidget.com',(status,data)
        checks.append('LIVE lookup Vietnam 2026-10-01: snapwidget.com')
        status,content=request('/api/search',{'mode':'reverse','domain':'snapwidget.com','region':'2704','start':'2026-10-01','end':'2026-10-01'})
        reverse=json.loads(content)
        assert status==200 and len(reverse['ads'])==1 and reverse['ads'][0]['advertiserId']=='AR15863532213959131137',reverse
        checks.append('LIVE reverse lookup snapwidget.com -> Adcore')
    assert request('/api/shutdown',{})[0]==200;checks.append('Clean shutdown (logged in)')
    return {'passed':True,'checks':checks,'sample':data,'reverse':reverse}
