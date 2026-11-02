"""Apify provider for Ultra Check. Credentials are supplied by the Windows encrypted key vault."""
import datetime as dt
import hashlib
import math
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from apify_keys import ApiError
from ultra_client import UltraError, CancelledError, domain, today, now_iso, GOOGLE, PT

ACTOR = 'solidfetch~google-ads-transparency-scraper'
BUILD = '0.7.41'

class BudgetRequired(UltraError):
    def __init__(self, estimate, current, partial=False):
        super().__init__('Run budget confirmation required. No ad scan has started.')
        self.estimate=estimate;self.current=current;self.partial=partial

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise UltraError('Unexpected Apify redirect. Stopped to protect your API key.')

class ApifyClient:
    def __init__(self, google):
        self.google = google
        self.key = ''
        self.keys = None
        self.history = None
        self.max_ads = 40
        self.max_charge = 0.10
        self.opener = urllib.request.build_opener(NoRedirect())

    def api(self, path, body=None):
        if not self.key:
            raise UltraError('Enter your Apify key in Data source.')
        request = urllib.request.Request('https://api.apify.com/v2/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+self.key, 'Content-Type':'application/json'})
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(20_000_001)
                if len(raw)>20_000_000: raise UltraError('The Apify response is too large.')
                result=json.loads(raw)
        except urllib.error.HTTPError as error:
            messages={401:'Invalid or expired Apify key.',403:'This Apify key does not have access.',402:'Insufficient Apify balance or a subscription is required.',429:'Apify rate limit reached. Try again later.'}
            try:
                payload=json.loads(error.read(100000));kind=payload.get('error',{}).get('type','')
                if not isinstance(kind,str) or not re.fullmatch(r'[a-z0-9-]{1,100}',kind):kind=''
            except (ValueError,AttributeError,TypeError):kind=''
            raise ApiError(messages.get(error.code, 'Apify returned HTTP error '+str(error.code)+'. This is not an empty result.'),error.code,kind) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise UltraError('Could not connect to Apify. Check the network before retrying; accepted runs are not recreated automatically to avoid duplicate charges.') from None
        except (ValueError, UnicodeError):
            raise UltraError('Apify returned invalid data.') from None
        return result.get('data',result) if isinstance(result,dict) else result

    def read_log(self, run_id):
        req=urllib.request.Request('https://api.apify.com/v2/actor-runs/'+run_id+'/log',headers={'Authorization':'Bearer '+self.key})
        try:
            with self.opener.open(req,timeout=20) as response:return response.read(2_000_000).decode('utf-8',errors='replace')
        except (urllib.error.URLError,TimeoutError,OSError,UltraError):return ''

    def configure(self, key, max_ads, max_charge):
        if not isinstance(key,str) or not re.fullmatch(r'apify_api_[A-Za-z0-9]{10,150}',key):
            raise UltraError('Invalid Apify key format.')
        if type(max_ads) is not int or not 1<=max_ads<=2000:
            raise UltraError('The sample limit must be between 1 and 2,000.')
        if isinstance(max_charge,bool) or not isinstance(max_charge,(float,int)) or not 0.01<=max_charge<=100:
            raise UltraError('The run budget must be between USD 0.01 and USD 100.')
        previous=self.key
        self.key=key
        try:self.api('users/me')
        except Exception:
            self.key=previous
            raise
        self.max_ads=max_ads; self.max_charge=float(max_charge)

    def context(self, body):
        mode,region,start,end,_=self.google.validate(body)
        if mode in ('current','reverse-current'): start=end=today()
        text=str(body.get('text') or '').strip()
        if mode=='discover' and (not text or len(text)>200):raise UltraError('Enter an advertiser name, up to 200 characters.')
        if region and not self.google.iso.get(region):raise UltraError('No country code is available for Apify. The scope will not be changed to all countries.')
        inputs={'mode':'advertisers' if mode=='discover' else 'ads','region':self.google.iso.get(region,'')}
        if mode=='discover': inputs['advertiserNames']=[text]
        else:
            inputs.update({'format':'TEXT','platform':'SEARCH','maxAds':100000 if body.get('collectAll',True) else self.max_ads,'includeAdText':True,'previewImages':False,'adDetails':False})
            if mode in ('reverse','reverse-current'): inputs['domains']=[domain(body['domain'])]
            else: inputs['advertiserIds']=[body['advertiserId']]
            if start: inputs.update(dateFrom=start,dateTo=end)
        identity=hashlib.sha256(json.dumps({'actor':ACTOR,'build':BUILD,'input':inputs,'cap':self.max_charge},sort_keys=True).encode()).hexdigest()
        return mode,region,start,end,inputs,identity

    def abort(self, run_id):
        try:self.api('actor-runs/'+run_id+'/abort',{})
        except UltraError:pass

    def run(self, inputs):
        self.google.check_cancel()
        self.google.progress='Starting Apify run · maximum '+str(self.max_charge)+' USD'
        # Never automatically retry this POST: each accepted run can be billed.
        start_api=self.keys.start if self.keys else self.api
        timeout=3600 if inputs.get('maxAds',self.max_ads)>2000 else 240
        run=start_api('acts/'+ACTOR+'/runs?'+urllib.parse.urlencode({'build':BUILD,'timeout':timeout,'memory':256,'maxTotalChargeUsd':self.max_charge}),inputs)
        run_id=run.get('id','')
        if not re.fullmatch(r'[A-Za-z0-9]+',run_id):raise UltraError('Apify returned an invalid run ID.')
        if self.history:self.history.record(run,inputs)
        deadline=time.monotonic()+timeout+30
        while run.get('status') in ('READY','RUNNING','TIMING-OUT','ABORTING'):
            if self.google.cancel.wait(2):
                self.abort(run_id);raise CancelledError('Apify cancellation requested. Charges already incurred still apply.')
            if time.monotonic()>deadline:
                self.abort(run_id);raise UltraError('Apify timed out. Check run '+run_id+' before running again.')
            self.google.progress='Apify is processing · run '+run_id
            try:run=self.api('actor-runs/'+run_id)
            except UltraError:
                self.abort(run_id);raise UltraError('Lost connection while waiting for Apify. Check run '+run_id+' before running again; cancellation has not been confirmed.') from None
            if self.history:self.history.record(run,inputs)
        return self.read_run_result(run,inputs)

    def read_run_result(self,run,inputs):
        run_id=run['id']
        if self.history:self.history.record(run,inputs)
        stopped=run.get('status')!='SUCCEEDED'
        dataset=run.get('defaultDatasetId','')
        if not re.fullmatch(r'[A-Za-z0-9]+',dataset):raise UltraError('Apify returned no valid dataset or the run failed. This is not an empty result.')
        rows=[]
        for offset in range(0,100001,1000):
            self.google.check_cancel()
            page=self.api('datasets/'+dataset+'/items?clean=true&limit=1000&offset='+str(offset))
            if not isinstance(page,list):raise UltraError('Invalid Apify dataset.')
            rows.extend(page)
            if len(rows)>100000:raise UltraError('Dataset exceeds 100,000 ads.')
            if len(page)<1000:break
        else:raise UltraError('Dataset exceeds 100,000 rows. Results were not silently truncated.')
        if any(not isinstance(row,dict) or row.get('error') for row in rows):
            raise UltraError('Actor reported invalid data. See run '+run_id+'; this is not an empty result.')
        if stopped and not rows:raise UltraError('Apify run '+run_id+' ended '+str(run.get('status'))+' and returned no ads. This is not proof that no ads exist.')
        # A successful run can still stop at a budget. Check the pinned Actor's
        # source-pagination log rather than treating a short dataset as exhaustive.
        log=self.read_log(run_id) if inputs['mode']=='ads' else ''
        exhausted='no more ads after page' in log.lower()
        message=str(run.get('statusMessage') or '')
        reason=''
        if stopped:reason='actor-stopped'
        elif inputs['mode']=='ads' and len(rows)>=inputs.get('maxAds',self.max_ads):reason='sample-limit'
        elif inputs['mode']=='ads' and any(x in message.lower() for x in ('limit','maximum','charge','cap reached')):reason='cost-limit'
        elif inputs['mode']=='ads' and not exhausted:reason='unverified'
        result={'rows':rows,'runId':run_id,'datasetId':dataset,'costUsd':run.get('usageTotalUsd'),'checkedAt':run.get('finishedAt') or now_iso(),'incomplete':bool(reason),'incompleteReason':reason,'sourceExhausted':exhausted,'input':inputs}
        if self.history:self.history.record(run,inputs,result)
        return result

    def estimate(self, inputs):
        preview={**inputs,'overviewOnly':True,'includeAdText':False,'previewImages':False}
        owner=self.keys.slots[self.keys.active].get('accountId','') if self.keys else ''
        cachekey='apify-estimate:'+hashlib.sha256(json.dumps({'input':preview,'owner':owner},sort_keys=True).encode()).hexdigest()
        cached,_=self.google.get_cached(cachekey,3600)
        if cached is not None:return cached
        data=self.run(preview)
        if len(data['rows'])!=1 or data['rows'][0].get('type')!='overview':raise UltraError('No valid estimate was returned. No ad scan has started.')
        row=data['rows'][0];cost=row.get('estimatedCostUsd')
        cost=float(cost) if isinstance(cost,(int,float)) and not isinstance(cost,bool) and math.isfinite(cost) and cost>=0 else None
        if cost is None and row.get('approximateTotalAds')==0 and row.get('sampleSize')==0:cost=0.0
        result={'approximateAds':row.get('approximateTotalAds'),'estimatedCostUsd':cost,'suggestedBudgetUsd':math.ceil((cost+.01)*100)/100 if cost is not None else None,'previewRunId':data['runId']}
        self.google.put_cached(cachekey,result);return result

    def import_run(self,body,run_id):
        if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9]{10,30}',run_id):raise UltraError('Invalid Apify run ID.')
        mode,region,start,end,wanted,identity=self.context(body)
        if mode not in ('reverse','check'):raise UltraError('Only historical runs for a domain or advertiser ID can be imported.')
        run=self.api('actor-runs/'+run_id)
        if run.get('actId')!='6gAFfuqX4Chhom1FY':raise UltraError('This run does not belong to the tested Google Ads Actor.')
        if run.get('status') not in ('SUCCEEDED','FAILED','ABORTED','TIMED-OUT'):raise UltraError('The Apify run is not finished. Import it after it ends.')
        store=run.get('defaultKeyValueStoreId','')
        if not re.fullmatch(r'[A-Za-z0-9]+',store):raise UltraError('Could not read the Apify run configuration.')
        remote=self.api('key-value-stores/'+store+'/records/INPUT')
        if not isinstance(remote,dict) or remote.get('mode','ads')!='ads' or remote.get('format')!='TEXT' or remote.get('platform')!='SEARCH':raise UltraError('The imported run must use Google Search / Text.')
        for field in ('overviewOnly','onlyNewSinceLastRun','onlyWithProducts','minDaysShown','shownInLastDays'):
            if remote.get(field):raise UltraError('The imported run has additional filters that differ from this query.')
        if not isinstance(remote.get('region',''),str) or remote.get('region','').upper()!=wanted['region'].upper() or (remote.get('dateFrom') or '')!=start or (remote.get('dateTo') or '')!=end:raise UltraError("The imported run's country or dates do not match this query.")
        if any(remote.get(field) for field in ('search','startUrls','advertiserNames','advertiserNamesText','domainsText')):raise UltraError('The imported run mixes query types and cannot be assigned automatically.')
        if mode=='reverse':
            if len(remote.get('domains',[]))!=1 or domain(remote['domains'][0])!=domain(body['domain']) or remote.get('advertiserIds'):raise UltraError("The imported run's domain does not match.")
        else:
            if remote.get('advertiserIds')!=[body['advertiserId']] or remote.get('domains'):raise UltraError("The imported run's advertiser profile does not match.")
        data=self.read_run_result(run,remote)
        for row in data['rows']:
            if row.get('format')!='TEXT' or not re.fullmatch(r'AR\d+',str(row.get('advertiserId',''))) or not re.fullmatch(r'CR\d+',str(row.get('creativeId',''))):raise UltraError('The imported data contains invalid IDs or formats.')
            if mode=='reverse' and domain(row.get('domain'))!=domain(body['domain']):raise UltraError('The imported data contains a different domain.')
            if mode=='check' and row['advertiserId']!=body['advertiserId']:raise UltraError('The imported data contains a different advertiser.')
        data['imported']=True
        self.google.put_cached('apify-run:'+identity,data)
        return self.process({**body,'fresh':False,'pageToken':None,'allowPartial':True})

    def normalize(self, row, body, region):
        aid,cid=row.get('advertiserId'),row.get('creativeId')
        if not re.fullmatch(r'AR\d+',str(aid)) or not re.fullmatch(r'CR\d+',str(cid)) or row.get('format')!='TEXT':
            raise UltraError('The Actor returned IDs or formats outside the filters. Stopped to avoid mixing data.')
        reverse=body['mode'] in ('reverse','reverse-current')
        if not reverse and aid!=body['advertiserId']:raise UltraError('The Actor returned a different advertiser.')
        extracted={'domain':domain(row.get('domain')) or domain(row.get('displayUrl')),'method':'display-url','evidence':row.get('displayUrl') or row.get('domain') or ''}
        if reverse:
            if domain(row.get('domain'))!=domain(body['domain']):raise UltraError('The Actor returned a different domain. Results were not assigned to this advertiser.')
            extracted.update(method='google-domain-match',evidence='Domain matched in Apify data: '+row['domain'])
        if not extracted['domain']:
            preview=row.get('imageUrl') or row.get('previewScriptUrl')
            try:extracted=self.google.decode_preview(preview)
            except (UltraError,ImportError,OSError,ValueError,RuntimeError):extracted={'domain':None,'method':'missing','evidence':''}
        for field in ('firstShown','lastShown'):
            if row.get(field):
                try: dt.datetime.fromisoformat(row[field].replace('Z','+00:00'))
                except (ValueError,TypeError):raise UltraError('The Actor returned an invalid observation date.')
        start,end=body.get('start') or '',body.get('end') or ''
        if body['mode'] in ('current','reverse-current'):start=end=today()
        if start:
            first=dt.datetime.fromisoformat(row['firstShown'].replace('Z','+00:00')).astimezone(PT).date().isoformat() if row.get('firstShown') else None
            last=dt.datetime.fromisoformat(row['lastShown'].replace('Z','+00:00')).astimezone(PT).date().isoformat() if row.get('lastShown') else None
            if (first and first>end) or (last and last<start):raise UltraError('The Actor returned ads outside the selected dates. Stopped to avoid incorrect results.')
        self.google.put_cached('apify-ad:'+aid+':'+cid,row)
        source=GOOGLE+'/advertiser/'+aid+'/creative/'+cid+'?'+urllib.parse.urlencode({'region':self.google.iso.get(region,'anywhere'),'platform':'SEARCH','format':'TEXT'})
        return {'id':cid,'advertiserId':aid,'advertiser':row.get('advertiserName') or aid,'domain':extracted['domain'],'method':extracted['method'],'evidence':extracted['evidence'],'preview':row.get('imageUrl') or '', 'first':row.get('firstShown'),'last':row.get('lastShown'),'format':'text','source':source}

    def process(self, body):
        if body.get('mode')=='details':
            self.google.validate(body)
            aid,cid=body['advertiserId'],str(body.get('creativeId',''))
            if not re.fullmatch(r'CR\d+',cid):raise UltraError('Invalid creative ID.')
            row,_=self.google.get_cached('apify-ad:'+aid+':'+cid,86400)
            if not row:raise UltraError('No ad preview is cached in Apify. Search this advertiser again first.')
            ad=self.normalize(row,{'mode':'check','advertiserId':aid},str(body.get('region') or ''))
            return {'domains':[ad['domain']] if ad['domain'] else [],'checkedAt':now_iso(),'cached':True}
        mode,region,start,end,inputs,identity=self.context(body)
        if mode=='discover' and re.fullmatch(r'AR\d+',inputs['advertiserNames'][0]):
            return {'candidates':[{'id':inputs['advertiserNames'][0],'name':inputs['advertiserNames'][0]}],'ads':[],'nextPageToken':None,'today':today(),'checkedAt':now_iso()}
        token=body.get('pageToken') or '';offset=0
        ttl=600 if mode in ('current','reverse-current') else 86400
        if token:
            match=re.fullmatch(r'ap:([a-f0-9]{64}):(\d{1,5})',token)
            if not match or match[1]!=identity:raise UltraError('This Apify page does not belong to the current query or settings.')
            offset=int(match[2]);data,_=self.google.get_cached('apify-run:'+identity,86400)
            if data is None:raise UltraError('The cached page has expired. Search again.')
            cached=True
        else:
            data,_=self.google.get_cached('apify-run:'+identity,ttl)
            cached=data is not None and not body.get('fresh')
            if not cached:
                data=self.run(inputs);self.google.put_cached('apify-run:'+identity,data)
        warnings=[]
        if data['incomplete']:
            reason=data.get('incompleteReason','')
            if reason=='unverified':warnings.append('All dataset rows were read, but source exhaustion was not confirmed. Results are not marked complete.')
            elif reason=='actor-stopped':warnings.append('The Actor stopped early. Downloaded records are retained; results are incomplete.')
            else:warnings.append('The source reached its sample or cost limit. All available dataset rows are still read, but records beyond the cap were not fetched. Raising the cap and searching again may charge for old ads again.')
        result={'today':today(),'checkedAt':data['checkedAt'],'cached':cached,'provider':'Apify','runId':data['runId'],'costUsd':data['costUsd'],'incomplete':data['incomplete'],'sourceIncomplete':data['incomplete'],'candidates':[],'ads':[],'nextPageToken':None,'domains':[],'filters':{'platform':'SEARCH','format':'TEXT','region':region,'start':start,'end':end}}
        if mode=='discover':
            for row in data['rows']:
                if not re.fullmatch(r'AR\d+',str(row.get('advertiserId',''))):raise UltraError('The Actor returned an invalid advertiser profile.')
                result['candidates'].append({'id':row['advertiserId'],'name':row.get('name') or row['advertiserId'],'country':row.get('country','')})
        else:
            rows=data['rows'];subset=rows[offset:offset+40]
            if offset>len(rows):raise UltraError('The Apify page exceeds the downloaded row count.')
            for i,row in enumerate(subset):
                self.google.check_cancel();self.google.progress='Reading Apify domains '+str(i+1)+'/'+str(len(subset))
                result['ads'].append(self.normalize(row,body,region))
            if offset+40<len(rows):result['nextPageToken']='ap:'+identity+':'+str(offset+40)
            result['domains']=sorted({a['domain'] for a in result['ads'] if a['domain']})
            if any(not a['domain'] for a in result['ads']):
                warnings.append('Some ads are images and their domains could not be extracted. Open the source to verify them.')
                result['incomplete']=True
        result['warning']=' '.join(warnings)
        return result
