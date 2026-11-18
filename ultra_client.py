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
FORMATS={'all':None,'text':1,'image':2,'video':3}           # Google Search ad formats; 'all' = no format filter
FORMAT_NAMES={1:'text',2:'image',3:'video'}
FORMAT_LABELS={'all':'all formats','text':'Text','image':'Image','video':'Video'}
SOURCE_FORMATS={'text':'TEXT','image':'IMAGE','video':'VIDEO'}
VERIFY_PAGES=5      # up to 200 ads per advertiser+domain verification call
MAX_VERIFY_PAGES=100  # read at most 4,000 ads of one advertiser+domain list while looking for unmatched ads
PREVIEW_HOSTS={'displayads-formats.googleusercontent.com','tpc.googlesyndication.com'}
VERIFIED_METHODS={'google-verified','google-domain-verified','google-domain-match'}
WEAK_CHECKS=3       # at most this many weak (non-display) candidates verified per ad
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
OCR_URL=re.compile(r'(?<![\w@])(?:https?://)?(?:www\.)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?:/[^\s]*)?')
OCR_LABEL=re.compile(r'^(?:sponsored|ads?|quảng cáo|được tài trợ|tài trợ)(?:\s*[·•:|]\s*|\s+|$)',re.I)
def ocr_domain(lines):
    # Google Search text-ad snapshots put the display URL above the headline:
    #   "Sponsored" / [advertiser name] / "www.example.com/" / headline / description.
    # Only a line that is essentially just a URL counts as the display URL.
    # Do not mine domains from headline or description text or silently repair OCR spellings.
    for line in lines[:4]:
        cleaned=OCR_LABEL.sub('',line.replace(' › ','/').replace(' > ','/').strip(),count=1)
        hits=[(m,d) for m in OCR_URL.finditer(cleaned) for d in [domain(m.group())] if d]
        if not hits:continue
        if len({d for _,d in hits})!=1:return None
        m,d=hits[0]
        rest=cleaned[:m.start()]+cleaned[m.end():]
        if m.start()<=3 and len(re.sub(r'[\W_]','',rest))<=2:return d
    return None

# ---- Domain candidates (verified afterwards by Google's advertiser + domain filter) ----
SECOND_LEVEL={'com','net','org','co','edu','gov','ac','or','ne','go','biz','info','gen','ltd','plc','nom','sch','mil','int','id'}
NOT_TLD={'js','css','png','jpg','jpeg','gif','svg','webp','woff','woff2','ttf','html','htm','json','php','asp','aspx','mp4','txt','xml','map'}
INFRA={'google','gstatic','googleusercontent','googlesyndication','doubleclick','googleapis','googletagmanager','googleadservices',
       'youtube','ytimg','ggpht','gvt1','gvt2','withgoogle','googlevideo','w3','schema','youtu','goo','blogger','android','admob','gmail',
       'ampproject','example','github'}   # boilerplate found in every preview script
HOST_TOKEN=re.compile(r'(?<![\w@.-])(?:https?://)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![\w-])',re.I)
SCRIPT_HEX=re.compile(r'\\x([0-9a-fA-F]{2})');SCRIPT_UNI=re.compile(r'\\u([0-9a-fA-F]{4})')
SCRIPT_STRONG=[re.compile(r"visible_url:\s*'([^']{3,200})'"),                      # video ads
               re.compile(r"destination_url:\s*'([^']{3,400})'"),
               re.compile(r'\[null,null,null,null,null,null,null,"[^"]{0,300}","([^"]{3,200})"'),  # text ads: headline, display URL
               re.compile(r'"([A-Za-z0-9.-]{3,80}\.[A-Za-z]{2,24})","Google"\]'),   # shopping: merchant domain
               re.compile(r'class="ktRTDc[^"]*">([^<]{3,80})<')]
def registrable(host):
    """example.com for www.shop.example.com; example.com.vn keeps three labels. Google's domain filter only matches this form."""
    if not host:return host
    labels=host.split('.')
    if len(labels)<=2:return host
    n=3 if len(labels[-1])==2 and labels[-2] in SECOND_LEVEL else 2
    return '.'.join(labels[-n:])
def site_of(value):
    h=domain(value)
    if not h or h.rsplit('.',1)[-1] in NOT_TLD:return None
    site=registrable(h)
    if site.split('.')[0].isdigit():return None    # OCR of prices such as "990.000đ" -> "990.oood"
    return site
def ranked(values):
    out=[]
    for v in values:
        s=site_of(v) if isinstance(v,str) else None
        if s and s not in out:out.append(s)
    return out
def infra(site):return any(label in INFRA for label in site.split('.')[:-1])
HOST_IN_URL=re.compile(r'(?:https?:)?//(?:www\.)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![\w-])|\bwww\.((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![\w-])',re.I)
def url_tokens(text):
    """Hosts that appear inside URLs only: script code is full of dotted names that are not domains."""
    counts={}
    for m in HOST_IN_URL.finditer(text):
        s=site_of(m.group(1) or m.group(2))
        if s and not infra(s):counts[s]=counts.get(s,0)+1
    return [s for s,_ in sorted(counts.items(),key=lambda x:-x[1])]
def tokens(text):
    counts={}
    for m in HOST_TOKEN.finditer(text):
        s=site_of(m.group(1))
        if s and not infra(s):counts[s]=counts.get(s,0)+1
    return [s for s,_ in sorted(counts.items(),key=lambda x:-x[1])]
def ocr_candidates(lines):
    strong=[ocr_domain(lines)]
    repaired=[re.sub(r'(?<=\w)\s*\.\s+(?=[a-z])','.',l) for l in lines]   # OCR spacing: "info. notion.so"
    strong.append(ocr_domain(repaired))
    return [s for s in strong if s],tokens('\n'.join(repaired))
def script_candidates(body):
    text=SCRIPT_UNI.sub(lambda m:chr(int(m.group(1),16)),SCRIPT_HEX.sub(lambda m:chr(int(m.group(1),16)),body))
    text=html.unescape(text.replace('\\"','"'))
    strong=[m.group(1) for p in SCRIPT_STRONG for m in p.finditer(text)]
    shown=renderer_display_url(body)
    if shown:strong.insert(0,shown)
    return strong,url_tokens(urllib.parse.unquote(text))

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
        self.progress='Ready';self.opener=urllib.request.build_opener(SafeRedirect());self.verified={}
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
        bridge=getattr(self,'bridge',None)
        if body is None and u.hostname in PREVIEW_HOSTS and bridge is not None and bridge.online():
            # Preview files through the user's browser: direct downloads get rate-limited.
            try:
                with self.lock:
                    delay=max(0,0.4-(time.monotonic()-self.last_call))
                    if self.cancel.wait(delay):self.check_cancel()
                    self.last_call=time.monotonic()
                    data=base64.b64decode(bridge.call('FETCH',url,self.cancel,timeout=60))
                if len(data)>max_size:raise UltraError('The source response exceeds the size limit.')
                return data
            except (CancelledError,BlockedError):raise
            except (UltraError,ValueError):pass   # fall back to a direct download
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
        if mode not in ('discover','check','current','details','reverse','reverse-current','resolve'):raise UltraError('Invalid lookup mode.')
        if region and region not in self.regions:raise UltraError('Unsupported country.')
        if mode not in ('discover','reverse','reverse-current') and not re.fullmatch(r'AR\d{1,30}',str(body.get('advertiserId') or '')):raise UltraError('Invalid advertiser ID.')
        if mode in ('reverse','reverse-current') and not domain(body.get('domain')):raise UltraError('Enter a valid domain, such as snapwidget.com.')
        start,end=body.get('start') or '',body.get('end') or ''
        if start or end:
            if not valid_date(start) or not valid_date(end) or start>end or end>today():raise UltraError("Invalid date range or dates later than today in Google's time zone.")
        token=body.get('pageToken') or ''
        if not isinstance(token,str) or len(token)>4000:raise UltraError('Invalid next-page token.')
        if (body.get('format') or 'text') not in FORMATS:raise UltraError('Invalid ad format.')
        return mode,region,start,end,token
    def search_payload(self,advertiser_id,region='',start='',end='',token='',website='',fmt='text'):
        # 6/7 are YYYYMMDD bounds; upper bound is exclusive, as in Google UI.
        # Advertiser and domain filters can be combined: Google then returns only
        # that advertiser's ads matched to that domain (used to verify domains).
        q={'12':{'1':website or '','2':True},'14':[SEARCH_SURFACE]}
        if FORMATS.get(fmt):q['4']=FORMATS[fmt]
        if advertiser_id:q['13']={'1':[advertiser_id]}
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
        cached,_=self.get_cached('preview-v2:'+url.split('&sig=')[0],7*86400)
        if cached is not None:return cached
        value=overlay_display_url(url);method='display-url';evidence=value or ''
        if not domain(value):
            data=self.read_url(url)
            if b'content.js' in url.encode() or url.endswith('.js') or '/search?' in url:
                value=renderer_display_url(data.decode('utf-8',errors='replace'));evidence=value or ''
            else:
                lines=asyncio.run(recognize_image(data));value=ocr_domain(lines);method='ocr';evidence='\n'.join(lines)
        result={'domain':domain(value),'method':method if domain(value) else 'missing','evidence':evidence}
        self.put_cached('preview-v2:'+url.split('&sig=')[0],result);return result
    def preview_candidates(self,url):
        """Every domain an ad preview mentions: strong = shown as the ad's URL, weak = anywhere else."""
        if not url:return {'strong':[],'weak':[],'method':'missing','evidence':''}
        key='cand-v1:'+url.split('&sig=')[0]
        cached,_=self.get_cached(key,7*86400)
        if cached is not None:return cached
        strong=[];weak=[];method='missing';evidence=''
        shown=overlay_display_url(url)
        if domain(shown):strong.append(shown);method='display-url';evidence=shown
        else:
            try:data=self.read_url(url)
            except BlockedError:
                # A preview host refusing a download must not stop the scan: Google's
                # verification of other ads usually covers this one. Not cached.
                return {'strong':[],'weak':[],'method':'preview-unavailable','evidence':''}
            if b'content.js' in url.encode() or url.endswith('.js') or '/search?' in url:
                strong,weak=script_candidates(data.decode('utf-8',errors='replace'));method='preview-data';evidence=strong[0] if strong else ''
            else:
                lines=asyncio.run(recognize_image(data));method='ocr';evidence='\n'.join(lines)
                strong,weak=ocr_candidates(lines)
        result={'strong':ranked(strong),'weak':[d for d in ranked(weak) if d not in ranked(strong)][:12],'method':method,'evidence':evidence[:2000]}
        self.put_cached(key,result);return result
    def verify_domain(self,advertiser_id,site,region,start,end,fmt,fresh=False,ttl=600,resume=None):
        """Ask Google which of this advertiser's ads match `site` (advertiser + domain filters).

        Reads VERIFY_PAGES pages per call; pass the previous result as `resume` to read further.
        """
        key='verify-v2:'+json.dumps([advertiser_id,site,region,start,end,fmt])
        if resume is None and not fresh:
            cached,_=self.get_cached(key,ttl)
            if cached is not None:return cached
        ids=dict(resume['ids']) if resume else {};token=resume.get('token','') if resume else '';pages=resume.get('pages',0) if resume else 0;read=0
        while True:
            data,_,_=self.rpc('SearchService/SearchCreatives',self.search_payload(advertiser_id,region,start,end,token,site,fmt),ttl=ttl,fresh=fresh)
            for a in data.get('1') or []:
                if a.get('1')==advertiser_id and re.fullmatch(r'CR\d+',str(a.get('2',''))):ids[a['2']]=domain(a.get('14')) or site
            token=data.get('2') or '';read+=1
            if not token or read>=VERIFY_PAGES or self.cancel.is_set():break
        result={'site':site,'ids':ids,'complete':not token,'token':token,'pages':pages+read}
        self.put_cached(key,result);return result
    def indexed_domain(self,advertiser_id,cid,filters):
        """Google's matched domain for this ad if any verification so far listed it."""
        site=self.verified.get((advertiser_id,)+tuple(filters),{}).get('index',{}).get(cid)
        return {'domain':site,'method':'google-verified','evidence':'Google lists this ad under '+site} if site else None
    def resolve_domain(self,advertiser_id,cid,url,filters,fresh=False,ttl=600):
        """Domain of one ad, confirmed by Google whenever possible.

        1. An earlier verification already listed this ad -> Google's matched domain.
        2. Otherwise read the preview for candidate domains and verify them with
           Google's advertiser + domain filter. One verification covers every ad
           of that advertiser on that domain, so most ads need no preview at all.
        3. If Google confirms none, keep the domain shown on the ad, marked unverified.
        """
        region,start,end,fmt=filters
        state=self.verified.setdefault((advertiser_id,)+tuple(filters),{'index':{},'checked':{}})
        if cid in state['index']:
            site=state['index'][cid];return {'domain':site,'method':'google-verified','evidence':'Google lists this ad under '+site}
        cand=self.preview_candidates(url)
        weak_checks=0
        for site in cand['strong']+cand['weak']:
            strong=site in cand['strong']
            res=state['checked'].get(site)
            if res is None:
                if not strong and weak_checks>=WEAK_CHECKS:continue
                weak_checks+=0 if strong else 1
                res=self.verify_domain(advertiser_id,site,region,start,end,fmt,fresh,ttl);state['checked'][site]=res
                for other,matched in res['ids'].items():state['index'].setdefault(other,matched)
            if cid in res['ids']:
                matched=res['ids'][cid];return {'domain':matched,'method':'google-verified','evidence':'Google lists this ad under '+matched}
            if strong and res['ids'] and not res['complete']:
                # Google confirms the advertiser runs ads for this domain; the list was too long to page through.
                return {'domain':site,'method':'google-domain-verified','evidence':'Shown on the ad; Google confirms this advertiser advertises '+site}
        # Large advertisers: keep reading this advertiser's verified domain lists (bounded) until the ad appears.
        for site in sorted(state['checked'],key=lambda s:-len(state['checked'][s]['ids'])):
            res=state['checked'][site]
            while res['ids'] and not res['complete'] and res.get('pages',0)<MAX_VERIFY_PAGES and not self.cancel.is_set():
                self.progress=f'Matching ads to {site} · page {res.get("pages",0)+1}'
                res=self.verify_domain(advertiser_id,site,region,start,end,fmt,fresh,ttl,resume=res);state['checked'][site]=res
                for other,matched in res['ids'].items():state['index'].setdefault(other,matched)
                if cid in res['ids']:
                    matched=res['ids'][cid];return {'domain':matched,'method':'google-verified','evidence':'Google lists this ad under '+matched}
        shown='ocr' if cand['method']=='ocr' else 'display-url'
        # A shown domain is refuted when Google's complete list for it does not include this ad.
        usable=[s for s in cand['strong'] if not (s in state['checked'] and state['checked'][s]['complete'] and cid not in state['checked'][s]['ids'])]
        if usable:return {'domain':usable[0],'method':shown,'evidence':cand['evidence']}
        inferred=self.advertiser_domain(state)
        if inferred:return inferred
        if cand['strong']:return {'domain':cand['strong'][0],'method':shown,'evidence':cand['evidence']}
        return {'domain':None,'method':'missing','evidence':cand['evidence']}
    @staticmethod
    def advertiser_domain(state):
        """For ads whose preview shows no domain (app installs, product videos, shopping images):
        the advertiser's only Google-verified domain, when that list is too long to check ad by ad.
        Labelled as inferred; a complete list that lacks the ad is never used."""
        sites=[s for s,r in state['checked'].items() if r['ids']]
        if len(sites)==1 and not state['checked'][sites[0]]['complete']:
            return {'domain':sites[0],'method':'advertiser-domain','evidence':"The advertiser's only domain verified by Google; this ad shows no domain of its own"}
        return None
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
        if mode=='resolve':
            # After a whole advertiser scan: ads still without a Google-verified domain may be
            # covered by verifications made on later pages. Lookup only; no new requests.
            ids=body.get('ids')
            if not isinstance(ids,list) or len(ids)>400:raise UltraError('Invalid ad list.')
            filters=(region,start,end,body.get('format') or 'text');out=[]
            inferred=self.advertiser_domain(self.verified.get((body['advertiserId'],)+filters,{'checked':{}}))
            for cid in ids:
                if isinstance(cid,str) and re.fullmatch(r'CR\d{1,30}',cid):
                    found=self.indexed_domain(body['advertiserId'],cid,filters) or inferred
                    if found:out.append({'id':cid,**found})
            return {'updates':out,'checkedAt':now_iso(),'today':today()}
        reverse=mode in ('reverse','reverse-current');website=registrable(domain(body.get('domain'))) if reverse else ''
        fmt=body.get('format') or 'text';code=FORMATS[fmt];label=FORMAT_LABELS[fmt]
        if mode in ('current','reverse-current'):start=end=today()
        ttl=90 if mode in ('current','reverse-current') else 600
        data,checked,cached=self.rpc('SearchService/SearchCreatives',self.search_payload(body.get('advertiserId',''),region,start,end,token,website,fmt),ttl=ttl,fresh=fresh)
        if data and not isinstance(data.get('1'),list):
            # A legitimate empty response is {} or has explicit count 0.
            if data.get('3') not in (0,'0'):raise UltraError("Google's list response structure has changed.")
        entries=data.get('1',[]);ads=[];warnings=[]
        for i,a in enumerate(entries):
            self.progress=f'Reading ad {i+1}/{len(entries)} · Google Search · {label}'
            if self.cancel.is_set():warnings.append('Stopped; this page is incomplete.');break
            if not re.fullmatch(r'AR\d+',str(a.get('1',''))) or (not reverse and a.get('1')!=body['advertiserId']) or (code and a.get('4')!=code):raise UltraError('The source returned records outside the advertiser or format filters. Stopped to avoid mixing data.')
            url=self.preview(a.get('3',{}));cid=a.get('2','')
            if not re.fullmatch(r'CR\d+',cid):raise UltraError('Invalid creative ID returned by the source.')
            try:
                if reverse:
                    matched=domain(a.get('14'))
                    if not matched or not (matched==website or matched.endswith('.'+website) or website.endswith('.'+matched)):raise UltraError('Google returned a different or missing matched domain. Verify the source.')
                    extracted={'domain':matched,'method':'google-domain-match','evidence':'Domain matched directly by Google: '+str(a['14'])}
                else:extracted=self.resolve_domain(a['1'],cid,url,(region,start,end,fmt),fresh,ttl)
            except BlockedError:raise
            except CancelledError:warnings.append('Stopped; this page is incomplete.');break
            except (UltraError,ImportError,OSError,ValueError,RuntimeError) as e:
                extracted={'domain':None,'method':'missing','evidence':''};warnings.append(str(e))
            kind=FORMAT_NAMES.get(a.get('4'),'other');params={'region':self.iso.get(region,region) or 'anywhere','platform':'SEARCH'}
            if kind in SOURCE_FORMATS:params['format']=SOURCE_FORMATS[kind]
            source=GOOGLE+'/advertiser/'+a['1']+'/creative/'+cid+'?'+urllib.parse.urlencode(params)
            ads.append({'id':cid,'advertiserId':a['1'],'advertiser':a.get('12',a['1']),'domain':extracted['domain'],'method':extracted['method'],'evidence':extracted['evidence'],'preview':url,'first':stamp(a.get('6')),'last':stamp(a.get('7')),'format':kind,'source':source})
        if not reverse:
            # Second pass: a later ad on this page may have verified a domain that covers an earlier one.
            for ad in ads:
                if ad['method'] not in VERIFIED_METHODS:
                    found=self.indexed_domain(ad['advertiserId'],ad['id'],(region,start,end,fmt))
                    if not found and not ad['domain']:found=self.advertiser_domain(self.verified.get((ad['advertiserId'],region,start,end,fmt),{'checked':{}}))
                    if found:ad.update(found)
        return {'ads':ads,'candidates':[],'nextPageToken':token if self.cancel.is_set() else data.get('2'),'checkedAt':checked,'today':today(),'cached':cached,'warning':' '.join(dict.fromkeys(warnings))[:1500],'totalResults':data.get('3'),'lowerBound':data.get('4'),'upperBound':data.get('5'),'filters':{'platform':'SEARCH','format':SOURCE_FORMATS.get(FORMAT_NAMES.get(code),'ALL'),'region':region,'start':start,'end':end}}
