import asyncio,json,re,threading,urllib.request,urllib.error
from pathlib import Path
from ultra_client import recognize_image,ocr_domain
def run(server,token,assets):
    url=f'http://127.0.0.1:{server.server_port}'
    def request(path,body=None,auth=True,origin=None):
        headers={}
        if body is not None:headers={'Content-Type':'application/json','X-Ultra-Token':token if auth else 'invalid','Origin':origin or url}
        req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=45) as r:return r.status,r.read().decode('utf-8')
        except urllib.error.HTTPError as e:return e.code,e.read().decode('utf-8')
    checks=[]
    status,content=request('/');assert status==200 and 'Ultra Check Windows' in content;checks.append('HTML/assets served')
    status,content=request('/api/search');assert status==200 and json.loads(content)['configured'];checks.append('No API key required')
    assert request('/api/search',{'mode':'discover','text':'test'},auth=False)[0]==403;checks.append('Invalid token rejected')
    assert request('/api/search',{'mode':'discover','text':'test'},origin='https://other.example')[0]==403;checks.append('Cross-origin rejected')
    assert request('/../../ultra_client.py')[0]==404;checks.append('Source paths not served')
    assert request('/api/search',{'mode':'check','advertiserId':'AR123','region':'invalid'})[0]==400;checks.append('Invalid region rejected')
    assert request('/api/search',{'mode':'check','advertiserId':'AR123','start':'2026-10-02','end':'2026-10-01'})[0]==400;checks.append('Invalid date range rejected')
    lines=asyncio.run(recognize_image((assets/'selftest.png').read_bytes()))
    assert ocr_domain(lines)=='ads-gorilla.com';checks.append('Packaged Windows OCR correctly reads known Google text-ad image')
    status,content=request('/api/search',{'mode':'check','advertiserId':'AR15863532213959131137','region':'2704','start':'2026-10-01','end':'2026-10-01'})
    data=json.loads(content)
    assert status==200,(status,data)
    assert len(data['ads'])==1 and data['ads'][0]['domain']=='snapwidget.com',data
    assert data['filters']['platform']=='SEARCH' and data['filters']['format']=='TEXT'
    checks.append('Packaged live lookup Vietnam 2026-10-01: one creative, snapwidget.com, Search/Text')
    assert request('/api/search',{'mode':'reverse','domain':'invalid'})[0]==400;checks.append('Invalid domain rejected')
    status,content=request('/api/search',{'mode':'reverse','domain':'snapwidget.com','region':'2704','start':'2026-10-01','end':'2026-10-01'})
    reverse=json.loads(content)
    assert status==200 and len(reverse['ads'])==1 and reverse['ads'][0]['advertiserId']=='AR15863532213959131137',reverse
    assert reverse['ads'][0]['method']=='google-domain-match' and reverse['ads'][0]['first'] and reverse['ads'][0]['last']
    checks.append('Packaged reverse lookup: snapwidget.com / Vietnam 2026-10-01 matches Adcore with dates')
    assert request('/api/shutdown',{})[0]==200;checks.append('Clean shutdown')
    return {'passed':True,'checks':checks,'sample':data,'reverse':reverse}
