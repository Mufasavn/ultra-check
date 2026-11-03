"""Microsoft's documented public Ad Library API. No Apify or proxy fallback.

The API searches ad content, not a complete destination-domain index. It also
does not expose placement/ad type. Text-shaped records are candidates only.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from ultra_client import UltraError, CancelledError, domain, valid_date, now_iso

BASE = 'https://adlibrary.api.bingads.microsoft.com/api/v1/'
LIBRARY = 'https://adlibrary.ads.microsoft.com/'
COUNTRIES = dict(zip(
    ['10','14','26','49','207','51','53','61','65','66','72','76','88','92','93','104','108','109','115','129','151','152','226','165','167','170','175','89','107','139'],
    ['Austria','Belgium','Bulgaria','Croatia','Cyprus','Czechia','Denmark','Estonia','Finland','France','Germany','Greece','Hungary','Ireland','Italy','Latvia','Lithuania','Luxembourg','Malta','Netherlands','Poland','Portugal','Romania','Slovakia','Slovenia','Spain','Sweden','Iceland','Liechtenstein','Norway']))
SCOPE = ('Bing Ad Library covers EU/EEA impressions only. Microsoft does not expose '
         'a placement/ad-type field here: text-shaped records are candidates, not '
         'verified Search/Text placements. Dates are UTC and may lag 1–3 days.')
DOMAIN_SCOPE = ('Domain lookup searches ad content, then verifies destination/display '
                'hosts. Microsoft does not document an exhaustive destination-domain '
                'search; this is a candidate list, not all advertisers for a domain.')

def today_utc():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()

def id_text(value):
    text = str(value or '')
    return text if re.fullmatch(r'[1-9][0-9]{0,19}', text) else None

def date_value(value):
    if isinstance(value,str) and valid_date(value[:10]):
        return value[:10]+'T00:00:00+00:00'
    return None

def text_candidate(item):
    # Deliberately conservative; no media/OCR extraction for the Bing adapter.
    return (not item.get('AssetJson') and bool(str(item.get('Title') or '').strip())
            and bool(str(item.get('Description') or '').strip())
            and bool(domain(item.get('DestinationUrl')) or domain(item.get('DisplayUrl'))))

class BingClient:
    page_size = 10
    interval = 5.0

    def __init__(self, cache):
        self.cache = cache
        self.last_call = 0.0
        self.progress = 'Ready'
        # Never follow source redirects to a login, CAPTCHA or an arbitrary host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def metadata(self):
        return {'countries':COUNTRIES,'today':today_utc(),'scope':SCOPE,
                'domainScope':DOMAIN_SCOPE,'pageSize':self.page_size,'paid':False}

    def _request(self, path, params=None, fresh=False, ttl=3600):
        url = BASE+path+('?' + urllib.parse.urlencode(params) if params else '')
        key = 'bing:v1:'+url
        value, at = self.cache.get_cached(key,ttl)
        if value is not None and not fresh:
            return value,dt.datetime.fromtimestamp(at,dt.timezone.utc).isoformat(),True
        self.cache.check_cancel()
        cooldown,_ = self.cache.get_cached('bing:cooldown',86400)
        if cooldown and cooldown['until']>time.time():
            raise UltraError('Microsoft rate limit: wait '+str(int(cooldown['until']-time.time())+1)+' seconds before loading more. Downloaded results are retained.')
        delay = max(0,self.interval-(time.monotonic()-self.last_call))
        self.progress = 'Bing · waiting between public API requests…'
        if self.cache.cancel.wait(delay): self.cache.check_cancel()
        self.last_call = time.monotonic()
        request = urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'UltraCheck/2.10 (Microsoft public Ad Library client)'})
        try:
            with self.opener.open(request,timeout=35) as response:
                raw = response.read(4_000_001)
                if len(raw)>4_000_000: raise UltraError('Microsoft response exceeded the size limit.')
        except urllib.error.HTTPError as e:
            if e.code in (403,429):
                wait = 60
                retry = e.headers.get('Retry-After','')
                try: wait = max(60,int(retry))
                except ValueError:
                    try: wait = max(60,int(parsedate_to_datetime(retry).timestamp()-time.time()))
                    except (ValueError,TypeError,OverflowError): pass
                self.cache.put_cached('bing:cooldown',{'until':time.time()+wait})
                raise UltraError('Microsoft public API access is limited (HTTP '+str(e.code)+'). Wait at least '+str(wait)+' seconds, then use Load more. No proxy switching or paid fallback was used.') from e
            raise UltraError('Microsoft returned HTTP '+str(e.code)+'. This is not an empty result.') from e
        except (urllib.error.URLError,TimeoutError,OSError) as e:
            raise UltraError('Could not connect to Microsoft Ad Library or the request timed out. Downloaded results are retained; try Load more later.') from e
        try: value = json.loads(raw)
        except (ValueError,UnicodeError) as e: raise UltraError('Microsoft returned invalid JSON; no empty-result assumption was made.') from e
        if not isinstance(value,dict) or 'error' in value:
            raise UltraError('Microsoft returned an API error or an unsupported response structure.')
        self.cache.put_cached(key,value)
        return value,now_iso(),False

    def _token(self, fingerprint, offset):
        token='bing:'+secrets.token_urlsafe(18)
        self.cache.put_cached(token,{'query':fingerprint,'skip':offset})
        return token

    def _offset(self, token, fingerprint):
        if not token: return 0
        if not isinstance(token,str) or not re.fullmatch(r'bing:[A-Za-z0-9_-]{24}',token):
            raise UltraError('Invalid Bing continuation token.')
        value,_=self.cache.get_cached(token,7*86400)
        if not value or value.get('query')!=fingerprint:
            raise UltraError('Bing continuation expired or belongs to different filters. Start the search again.')
        return value['skip']

    def process(self, body):
        mode=body.get('mode');region=str(body.get('region') or '')
        if mode not in ('discover','check','reverse','details'):
            raise UltraError('Bing does not offer a reliable live/today status. Use the reported first/last dates instead.')
        if region and region not in COUNTRIES: raise UltraError('Choose an EU/EEA country for Bing.')
        start,end=body.get('start') or '',body.get('end') or ''
        if (start or end) and (not valid_date(start) or not valid_date(end) or start>end or end>today_utc()):
            raise UltraError('Choose valid Bing dates, no later than today in UTC.')
        fresh=bool(body.get('fresh'))
        text=str(body.get('text') or '').strip()
        advertiser=id_text(body.get('advertiserId'))
        website=domain(body.get('domain'))
        if mode=='discover' and (not text or len(text)>200):raise UltraError('Enter an advertiser name, up to 200 characters.')
        if mode in ('check','details') and not advertiser:raise UltraError('Enter a numeric Microsoft advertiser ID.')
        if mode=='reverse' and not website:raise UltraError('Enter a valid domain.')
        fingerprint=hashlib.sha256(json.dumps([mode,region,start,end,text,advertiser,website],sort_keys=True).encode()).hexdigest()
        skip=self._offset(body.get('pageToken'),fingerprint)
        result={'platform':'bing','today':today_utc(),'checkedAt':now_iso(),'ads':[],
                'candidates':[],'domains':[],'nextPageToken':None,'incomplete':False,
                'warning':SCOPE+(' '+DOMAIN_SCOPE if mode=='reverse' else ''),
                'filters':{'platform':'BING','format':'TEXT_CANDIDATE','placementVerified':False},
                'coverageLimited':True,'cached':True}
        if mode=='discover':
            if id_text(text):
                data,at,cached=self._request('Advertisers/'+text,fresh=fresh)
                items=[data];has_more=False
            else:
                data,at,cached=self._request('Advertisers',{'top':self.page_size,'skip':skip,'searchText':text},fresh=fresh)
                items=data.get('value');has_more=self._has_more(data,items,skip)
            if not isinstance(items,list):raise UltraError('Microsoft advertiser response structure changed.')
            for item in items:
                if not isinstance(item,dict) or not id_text(item.get('AdvertiserId')):raise UltraError('Microsoft returned an invalid advertiser record.')
                result['candidates'].append({'id':str(item['AdvertiserId']),'name':str(item.get('AdvertiserName') or item['AdvertiserId']),'country':str(item.get('AdvertiserCountry') or '')})
            result.update(checkedAt=at,cached=cached,nextPageToken=self._token(fingerprint,skip+len(items)) if has_more else None)
            return result
        if mode=='details':
            creative=id_text(body.get('creativeId'))
            if not creative:raise UltraError('Invalid Microsoft ad ID.')
            item,at,cached=self._request('Ads/'+creative,{'expand':'AdDetails'},fresh=fresh,ttl=86400)
            if str(item.get('AdvertiserId'))!=advertiser:raise UltraError('Microsoft ad belongs to a different advertiser.')
            ad=self._normalize(item)
            result.update(ads=[ad] if ad else [],domains=[ad['domain']] if ad and ad['domain'] else [],checkedAt=at,cached=cached)
            return result
        params={'top':self.page_size,'skip':skip}
        if mode=='reverse':params['searchText']=website
        else:params['advertiserId']=advertiser
        if region:params['countryCodes']=region
        if start:params.update(startDate=start,endDate=end)
        try:
            data,at,cached=self._request('Ads',params,fresh=fresh)
            result.update(checkedAt=at,cached=cached)
            items=data.get('value')
            if not isinstance(items,list):raise UltraError('Microsoft ad-list response structure changed.')
        except CancelledError: raise
        except UltraError as e:
            result.update(nextPageToken=self._token(fingerprint,skip),incomplete=True,warning=str(e)+' '+result['warning'],halt=True)
            return result
        processed=0
        for item in items:
            try:
                self.cache.check_cancel()
                if not isinstance(item,dict) or not id_text(item.get('AdId')) or not id_text(item.get('AdvertiserId')):
                    raise UltraError('Microsoft returned an invalid ad record.')
                if not text_candidate(item):processed+=1;continue
                self.progress='Bing · reading ad dates '+str(processed+1)+'/'+str(len(items))+'…'
                detail,at,cached=self._request('Ads/'+str(item['AdId']),{'expand':'AdDetails'},fresh=fresh,ttl=86400)
                result['cached']=result['cached'] and cached
                # Keep the oldest original fetch time when any record is cached.
                result['checkedAt']=min(result['checkedAt'],at)
                if str(detail.get('AdId'))!=str(item['AdId']) or str(detail.get('AdvertiserId'))!=str(item['AdvertiserId']):
                    raise UltraError('Microsoft ad details did not match the requested record.')
                ad=self._normalize(detail,website if mode=='reverse' else None)
                if ad:result['ads'].append(ad)
                processed+=1
            except (UltraError,CancelledError) as e:
                result.update(incomplete=True,warning=str(e)+' '+result['warning'],halt=True)
                break
        more=processed<len(items) or self._has_more(data,items,skip)
        if more:result['nextPageToken']=self._token(fingerprint,skip+processed)
        result['incomplete']=result['incomplete'] or more
        return result

    def _has_more(self,data,items,skip):
        if not isinstance(items,list):return False
        if not items:return False
        count=data.get('@odata.count')
        return bool(data.get('@odata.nextLink')) or len(items)>=self.page_size or (isinstance(count,int) and count>skip+len(items))

    def _normalize(self,item,website=None):
        if not text_candidate(item):return None
        target=domain(item.get('DestinationUrl'));display=domain(item.get('DisplayUrl'))
        host=target or display
        if website:
            # Never infer a match from title/description substrings or lookalike hosts.
            matches=[h for h in (target,display) if h and (h==website or h.endswith('.'+website))]
            if not matches:return None
            host=website
        details=item.get('AdDetails') or {}
        if not isinstance(details,dict):raise UltraError('Microsoft ad-date response structure changed.')
        advertiser=str(item['AdvertiserId']);creative=str(item['AdId'])
        destination_match=bool(target and (not website or target==website or target.endswith('.'+website)))
        return {'platform':'bing','id':creative,'advertiserId':advertiser,
                'advertiser':str(item.get('AdvertiserName') or advertiser),'domain':host,
                'first':date_value(details.get('StartDate')),'last':date_value(details.get('EndDate')),
                'format':'text candidate','method':'bing-destination-url' if destination_match else 'bing-display-url',
                'evidence':'\n'.join(str(item.get(k) or '') for k in ('Title','Description','DisplayUrl','DestinationUrl')),
                'source':BASE+'Ads/'+creative+'?expand=AdDetails',
                'placementVerified':False}
