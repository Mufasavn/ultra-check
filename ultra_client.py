"""Ultra Check Windows: direct, anonymous Google transparency data.

Protocol field numbers verified against Google's main.dart.js, release
acx-tfaar-tfaa-report-ui-frontend_auto_20261005-0645_RC000.
No account cookies, proxies, paid APIs or advertiser-site requests.
"""
from __future__ import annotations
import asyncio,base64,datetime as dt,gzip,hashlib,html,io,json,re,sqlite3,threading,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PT=ZoneInfo('America/Los_Angeles')
GOOGLE='https://adstransparency.google.com'
SEARCH_SURFACE=3
TEXT_FORMAT=1
PAGE_SIZE=40
HOSTS={'adstransparency.google.com','displayads-formats.googleusercontent.com','tpc.googlesyndication.com','ads-rendering-prod.corp.google.com'}
class UltraError(Exception): pass
class BlockedError(UltraError): pass
class CancelledError(UltraError): pass
def now_iso(): return dt.datetime.now(dt.timezone.utc).isoformat()
def today(): return dt.datetime.now(PT).date().isoformat()
def valid_date(s):
    try: return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',s or '')) and dt.date.fromisoformat(s).isoformat()==s
    except (ValueError,TypeError): return False
def day_number(s,plus=0): return int((dt.date.fromisoformat(s)+dt.timedelta(days=plus)).strftime('%Y%m%d'))
def stamp(value):
    try: return dt.datetime.fromtimestamp(int(value['1']),dt.timezone.utc).isoformat()
    except (TypeError,KeyError,ValueError,OverflowError,OSError): return None
def domain(value):
    if not isinstance(value,str) or not value.strip() or re.search(r'\s',value.strip()): return None
    try:
        u=urllib.parse.urlsplit(value if re.match(r'https?://',value,re.I) else 'https://'+value)
        h=(u.hostname or '').lower().removeprefix('www.').rstrip('.')
        if u.scheme not in ('http','https') or u.username or u.password or '.' not in h: return None
        h=h.encode('idna').decode('ascii')
        if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',h): return None
        return h
    except (ValueError,UnicodeError): return None
def proto_fields(data):
    def varint(pos):
        result=shift=0
        while pos<len(data) and shift<70:
            b=data[pos];pos+=1;result|=(b&127)<<shift
            if not b&128:return result,pos
            shift+=7
        raise ValueError('Invalid protobuf')
    pos=0
    while pos<len(data):
        key,pos=varint(pos);field,wire=key>>3,key&7
        if wire==0:value,pos=varint(pos)
        elif wire==2:
            size,pos=varint(pos)
            if size>len(data)-pos:raise ValueError('Invalid length')
            value=data[pos:pos+size];pos+=size
        elif wire in (1,5):size=8 if wire==1 else 4;value=data[pos:pos+size];pos+=size
        else:raise ValueError('Unknown wire type')
        yield field,wire,value
def overlay_display_url(url):
    try:
        v=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('overlay',[''])[0].lstrip('=')
        if not v or len(v)>200000:return None
        packed=base64.urlsafe_b64decode(v+'='*(-len(v)%4))
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as f:raw=f.read(1_000_001)
        if len(raw)>1_000_000:return None
        for field,wire,value in proto_fields(raw):
            if field!=9 or wire!=2:continue
            name='';text=''
            for n,w,x in proto_fields(value):
                if w!=2:continue
                if n==1:name=x.decode('utf-8')
                if n==2:
                    for ln,lw,lv in proto_fields(x):
                        if ln==1 and lw==2:text=lv.decode('utf-8');break
            if name=='visurl':return text
    except (ValueError,UnicodeError,OSError,EOFError):pass
    return None
def renderer_display_url(body):
    # Parse only the named, rendered display-URL field; never arbitrary JS URLs.
    text=re.sub(r'\\x([0-9a-fA-F]{2})',lambda m:chr(int(m.group(1),16)),body)
    text=text.replace('\\"','"')
    m=re.search(r'data-p="%\.@\.\[1,\[&quot;.*?&quot;,&quot;.*?&quot;,&quot;(.*?)&quot;',text,re.S)
    if m:return html.unescape(m.group(1))
    return None
def ocr_domain(lines):
    # Google Search text-ad snapshots put the display URL at the top.
    # Do not mine domains from description text or silently repair OCR spellings.
    found=[]
    for line in lines[:2]:
        cleaned=line.replace(' › ','/').replace(' > ','/')
        for m in re.finditer(r'(?<![\w@])(?:https?://)?(?:www\.)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?:/[^\s]*)?',cleaned):
            if m.start()>25:continue
            d=domain(m.group())
            if d and d not in found:found.append(d)
    return found[0] if len(found)==1 else None

async def recognize_image(data):
    import winrt.windows.foundation
    import winrt.windows.foundation.collections
    import winrt.windows.globalization
    from winrt.windows.storage.streams import InMemoryRandomAccessStream,DataWriter
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    engine=OcrEngine.try_create_from_user_profile_languages()
    if engine is None:raise UltraError('Windows OCR language is unavailable. Image-based domains remain blank; open the source ad to verify them.')
    stream=InMemoryRandomAccessStream();writer=DataWriter(stream.get_output_stream_at(0));bitmap=None
    try:
        writer.write_bytes(data);await writer.store_async();await writer.flush_async();stream.seek(0)
        decoder=await BitmapDecoder.create_async(stream);bitmap=await decoder.get_software_bitmap_async()
        if bitmap.pixel_width>4096 or bitmap.pixel_height>4096:raise UltraError('The image exceeds the OCR size limit.')
        result=await engine.recognize_async(bitmap)
        return [line.text for line in result.lines]
    finally:
        if bitmap:bitmap.close()
        writer.detach_stream();writer.close();stream.close()

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlsplit(newurl)
        if u.scheme!='https' or u.hostname not in HOSTS or '/sorry/' in u.path:raise BlockedError('Google access is restricted. Stop and try again later; do not change IPs or bypass CAPTCHA.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class GoogleClient:
    def __init__(self,cache_dir:Path,regions:dict):
        self.cache_dir=Path(cache_dir);self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.regions=regions;self.lock=threading.RLock();self.cancel=threading.Event();self.last_call=0
        iso_path=Path(__file__).parent/'assets'/'region-iso.json'
        self.iso=json.loads(iso_path.read_text(encoding='utf-8')) if iso_path.exists() else {}
        self.progress='Ready';self.opener=urllib.request.build_opener(SafeRedirect())
        self.db=sqlite3.connect(self.cache_dir/'cache.sqlite',check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, at REAL NOT NULL, data TEXT NOT NULL)');self.db.commit()
    def get_cached(self,key,ttl):
        with self.lock:r=self.db.execute('SELECT at,data FROM cache WHERE key=?',(key,)).fetchone()
        return (json.loads(r[1]),r[0]) if r and time.time()-r[0]<ttl else (None,None)
    def put_cached(self,key,value):
        with self.lock:self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',(key,time.time(),json.dumps(value,ensure_ascii=False)));self.db.commit()
    def check_cancel(self):
        if self.cancel.is_set():raise CancelledError('Scan stopped at your request. Downloaded results are retained.')
    def read_url(self,url,body=None,max_size=8_000_000):
        self.check_cancel();u=urllib.parse.urlsplit(url)
        if u.scheme!='https' or u.hostname not in HOSTS:raise UltraError('Unsupported source URL.')
        with self.lock:
            delay=max(0,1.25-(time.monotonic()-self.last_call))
            if self.cancel.wait(delay):self.check_cancel()
            self.last_call=time.monotonic()
            req=urllib.request.Request(url,data=body,headers={'User-Agent':'Mozilla/5.0','Referer':GOOGLE+'/',**({'Content-Type':'application/x-www-form-urlencoded'} if body is not None else {})})
            try:
                with self.opener.open(req,timeout=30) as res:
                    data=res.read(max_size+1)
                    if len(data)>max_size:raise UltraError('The source response exceeds the size limit.')
                    return data
            except urllib.error.HTTPError as e:
                if e.code in (403,429):raise BlockedError('Google access is restricted (HTTP '+str(e.code)+'). Stop scanning and try again later.') from e
                raise UltraError('Google returned HTTP error '+str(e.code)+'. This is not an empty result.') from e
            except urllib.error.URLError as e:raise UltraError('Could not connect to Google. Check your Internet connection and try again.') from e
    def browser_rpc(self,bridge,method,form):
        # Same pacing as direct requests; the call runs in the user's own Chrome tab.
        self.check_cancel()
        with self.lock:
            delay=max(0,1.25-(time.monotonic()-self.last_call))
            if self.cancel.wait(delay):self.check_cancel()
            self.last_call=time.monotonic()
            return bridge.call(method,form,self.cancel)
    def rpc(self,method,payload,ttl=300,fresh=False):
        cachekey='rpc:'+method+':'+json.dumps(payload,sort_keys=True)
        data,at=self.get_cached(cachekey,ttl)
        if data is not None and not fresh:return data,dt.datetime.fromtimestamp(at,dt.timezone.utc).isoformat(),True
        form=urllib.parse.urlencode({'f.req':json.dumps(payload)})
        bridge=getattr(self,'bridge',None)
        if bridge is not None and bridge.online():raw=self.browser_rpc(bridge,method,form)
        else:raw=self.read_url(GOOGLE+'/anji/_/rpc/'+method,form.encode()).decode('utf-8')
        if 'captcha' in raw.lower() or '/sorry/' in raw[:1000]:raise BlockedError('Google requires verification. Ultra Check has stopped; CAPTCHA is not bypassed.')
        try:data=json.loads(raw.removeprefix(")]}'\n"))
        except ValueError as e:raise UltraError('Google returned invalid data. This does not mean there are no ads.') from e
        if not isinstance(data,dict) or 'error' in data:raise UltraError("Google's response structure has changed or the source returned an error.")
        self.put_cached(cachekey,data);return data,now_iso(),False
    def validate(self,body):
        mode=body.get('mode');region=str(body.get('region') or '')
        if mode not in ('discover','check','current','details','reverse','reverse-current'):raise UltraError('Invalid lookup mode.')
        if region and region not in self.regions:raise UltraError('Unsupported country.')
        if mode not in ('discover','reverse','reverse-current') and not re.fullmatch(r'AR\d{1,30}',str(body.get('advertiserId') or '')):raise UltraError('Invalid advertiser ID.')
        if mode in ('reverse','reverse-current') and not domain(body.get('domain')):raise UltraError('Enter a valid domain, such as snapwidget.com.')
        start,end=body.get('start') or '',body.get('end') or ''
        if start or end:
            if not valid_date(start) or not valid_date(end) or start>end or end>today():raise UltraError("Invalid date range or dates later than today in Google's time zone.")
        token=body.get('pageToken') or ''
        if not isinstance(token,str) or len(token)>4000:raise UltraError('Invalid next-page token.')
        return mode,region,start,end,token
    def search_payload(self,advertiser_id,region='',start='',end='',token='',website=''):
        # 6/7 are YYYYMMDD bounds; upper bound is exclusive, as in Google UI.
        q={'4':TEXT_FORMAT,'12':{'1':'','2':True},'13':{'1':[advertiser_id]},'14':[SEARCH_SURFACE]}
        if website:
            q.pop('13');q['12']={'1':website,'2':True}
        if region:q['8']=[int(region)]
        if start:q['6']=day_number(start);q['7']=day_number(end,1)
        p={'2':PAGE_SIZE,'3':q,'7':{'1':1,'2':0,'3':int(region or 0)}}
        if website:p['1']=website
        if token:p['4']=token
        return p
    def preview(self,variation):
        if not isinstance(variation,dict):return ''
        for key in ('1','2'):
            value=variation.get(key,{}).get('4') if isinstance(variation.get(key),dict) else None
            if isinstance(value,str):return value
        raw=variation.get('3',{}).get('2','') if isinstance(variation.get('3'),dict) else ''
        if isinstance(raw,str):
            m=re.search(r'src=["\']([^"\']+)',raw)
            if m:return html.unescape(m.group(1))
        return ''
    def decode_preview(self,url):
        if not url:return {'domain':None,'method':'missing','evidence':''}
        cached,_=self.get_cached('preview:'+url.split('&sig=')[0],7*86400)
        if cached is not None:return cached
        value=overlay_display_url(url);method='display-url';evidence=value or ''
        if not domain(value):
            data=self.read_url(url)
            if b'content.js' in url.encode() or url.endswith('.js') or '/search?' in url:
                value=renderer_display_url(data.decode('utf-8',errors='replace'));evidence=value or ''
            else:
                lines=asyncio.run(recognize_image(data));value=ocr_domain(lines);method='ocr';evidence='\n'.join(lines)
        result={'domain':domain(value),'method':method if domain(value) else 'missing','evidence':evidence}
        self.put_cached('preview:'+url.split('&sig=')[0],result);return result
    def process(self,body):
        mode,region,start,end,token=self.validate(body)
        fresh=bool(body.get('fresh'))
        if mode=='discover':
            text=str(body.get('text') or '').strip()
            if not text or len(text)>200:raise UltraError('Enter an advertiser name, up to 200 characters.')
            if re.fullmatch(r'AR\d+',text):return {'candidates':[{'id':text,'name':text,'country':''}],'nextPageToken':None,'today':today(),'checkedAt':now_iso()}
            data,checked,cached=self.rpc('SearchService/SearchSuggestions',{'1':text,'2':30,'3':10},ttl=3600,fresh=fresh)
            if data and not isinstance(data.get('1'),list):raise UltraError("Google's advertiser suggestion structure has changed.")
            candidates=[]
            for item in data.get('1',[]):
                x=item.get('1',{})
                if re.fullmatch(r'AR\d+',str(x.get('2',''))):candidates.append({'id':x['2'],'name':x.get('1',x['2']),'country':x.get('3','')})
            return {'candidates':candidates,'nextPageToken':None,'today':today(),'checkedAt':checked,'cached':cached}
        if mode=='details':
            cid=str(body.get('creativeId') or '')
            if not re.fullmatch(r'CR\d{1,30}',cid):raise UltraError('Invalid creative ID.')
            data,checked,cached=self.rpc('LookupService/GetCreativeById',{'1':body['advertiserId'],'2':cid,'5':{'1':1,'2':0,'3':int(region or 0)}},ttl=3600,fresh=fresh)
            details=data.get('1',{})
            if not isinstance(details,dict):raise UltraError('Google returned no ad details.')
            results=[self.decode_preview(self.preview(v)) for v in details.get('5',[])]
            return {'domains':sorted({r['domain'] for r in results if r['domain']}),'evidence':results,'checkedAt':checked,'cached':cached}
        reverse=mode in ('reverse','reverse-current');website=domain(body.get('domain')) if reverse else ''
        if mode in ('current','reverse-current'):start=end=today()
        data,checked,cached=self.rpc('SearchService/SearchCreatives',self.search_payload(body.get('advertiserId',''),region,start,end,token,website),ttl=90 if mode in ('current','reverse-current') else 600,fresh=fresh)
        if data and not isinstance(data.get('1'),list):
            # A legitimate empty response is {} or has explicit count 0.
            if data.get('3') not in (0,'0'):raise UltraError("Google's list response structure has changed.")
        entries=data.get('1',[]);ads=[];warnings=[]
        for i,a in enumerate(entries):
            self.progress=f'Reading ad {i+1}/{len(entries)} · Google Search / Text'
            if self.cancel.is_set():warnings.append('Stopped; this page is incomplete.');break
            if not re.fullmatch(r'AR\d+',str(a.get('1',''))) or (not reverse and a.get('1')!=body['advertiserId']) or a.get('4')!=TEXT_FORMAT:raise UltraError('The source returned records outside the advertiser or format filters. Stopped to avoid mixing data.')
            url=self.preview(a.get('3',{}));cid=a.get('2','')
            if not re.fullmatch(r'CR\d+',cid):raise UltraError('Invalid creative ID returned by the source.')
            try:
                if reverse:
                    matched=domain(a.get('14'))
                    if matched!=website:raise UltraError('Google returned a different or missing matched domain. Verify the source.')
                    extracted={'domain':matched,'method':'google-domain-match','evidence':'Domain matched directly by Google: '+str(a['14'])}
                else:extracted=self.decode_preview(url)
            except BlockedError:raise
            except (UltraError,ImportError,OSError,ValueError,RuntimeError) as e:
                extracted={'domain':None,'method':'missing','evidence':''};warnings.append(str(e))
            source=GOOGLE+'/advertiser/'+a['1']+'/creative/'+cid+'?'+urllib.parse.urlencode({'region':self.iso.get(region,region) or 'anywhere','platform':'SEARCH','format':'TEXT'})
            ads.append({'id':cid,'advertiserId':a['1'],'advertiser':a.get('12',a['1']),'domain':extracted['domain'],'method':extracted['method'],'evidence':extracted['evidence'],'preview':url,'first':stamp(a.get('6')),'last':stamp(a.get('7')),'format':'text','source':source})
        return {'ads':ads,'candidates':[],'nextPageToken':token if self.cancel.is_set() else data.get('2'),'checkedAt':checked,'today':today(),'cached':cached,'warning':' '.join(dict.fromkeys(warnings))[:1500],'totalResults':data.get('3'),'lowerBound':data.get('4'),'upperBound':data.get('5'),'filters':{'platform':'SEARCH','format':'TEXT','region':region,'start':start,'end':end}}
