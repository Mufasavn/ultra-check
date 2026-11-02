"""Ten Apify credentials with account-level usage and conservative failover."""
import copy,datetime as dt,math,re,time
from key_vault import KeyVault
from ultra_client import UltraError,now_iso

class QuotaError(UltraError):pass
class ApiError(UltraError):
    def __init__(self,message,status=0,kind=''):super().__init__(message);self.status=status;self.kind=kind

class ApifyKeys:
    def __init__(self,client,path):
        self.client=client;self.vault=KeyVault(path);self.slots=[{} for _ in range(10)];self.active=0;self.enabled=False;self.error='';self.updated=0
        try:
            saved=self.vault.load()
            if saved:
                self.slots=saved['slots']+[{} for _ in range(10-len(saved['slots']))];self.active=saved.get('active',0);self.enabled=bool(saved.get('enabled'));client.max_ads=saved.get('maxAds',40);client.max_charge=saved.get('maxChargeUsd',.10)
                if type(self.active) is not int or not 0<=self.active<10:raise ValueError()
                for slot in self.slots:
                    if not isinstance(slot,dict):raise ValueError()
                    # Usage is a saved snapshot, never treated as fresh after restart.
                    slot['fresh']=False
                client.key=self.slots[self.active].get('key','')
        except (UltraError,ValueError,TypeError):self.error='Could not open the key vault. Keep apify-keys.dat and use the same Windows account.';self.enabled=False
    def persist(self):
        self.vault.save({'version':1,'slots':self.slots,'active':self.active,'enabled':self.enabled,'maxAds':self.client.max_ads,'maxChargeUsd':self.client.max_charge})
    def call_with(self,key,path):
        old=self.client.key;self.client.key=key
        try:return self.client.api(path)
        finally:self.client.key=old
    def inspect(self,key):
        me=self.call_with(key,'users/me');uid=me.get('id')
        if not isinstance(uid,str) or not uid:raise UltraError('Apify returned an invalid account ID.')
        result={'key':key,'accountId':uid,'state':'ready','checkedAt':now_iso(),'fresh':True}
        try:
            data=self.call_with(key,'users/me/limits');limit=data.get('limits',{}).get('maxMonthlyUsageUsd');used=data.get('current',{}).get('monthlyUsageUsd')
            if isinstance(limit,bool) or isinstance(used,bool) or not isinstance(limit,(int,float)) or not isinstance(used,(int,float)) or not math.isfinite(limit) or not math.isfinite(used) or used<0 or limit<0:raise ValueError()
            result.update(limitUsd=limit,usedUsd=used,cycle=data.get('monthlyUsageCycle'),quotaKnown=True)
            result['state']='exhausted' if used>=limit else 'ready'
        except (UltraError,ValueError):
            result.update(quotaKnown=False,state='unknown',message='Could not read the account limit. Usage percentage is unverified.')
        return result
    def save(self,edits,enabled=True):
        if self.error:raise UltraError(self.error)
        if not isinstance(edits,list) or len(edits)!=10:raise UltraError('Exactly 10 API slots are required.')
        slots=copy.deepcopy(self.slots)
        for i,edit in enumerate(edits):
            if not isinstance(edit,dict):raise UltraError('Invalid API slot.')
            if edit.get('clear') is True:slots[i]={};continue
            key=edit.get('key','')
            if not isinstance(key,str):raise UltraError('Invalid key.')
            key=key.strip()
            if not key:continue
            if not re.fullmatch(r'apify_api_[A-Za-z0-9]{10,150}',key):raise UltraError('Slot '+str(i+1)+': invalid key format.')
            try:slots[i]=self.inspect(key)
            except UltraError:raise UltraError('Slot '+str(i+1)+': authentication failed. Check the key and connection. Changes were not saved.') from None
        if enabled and not any(s.get('key') for s in slots):
            if any(e.get('clear') is True for e in edits):enabled=False
            else:raise UltraError('Enter at least one key to use Apify.')
        old=(self.slots,self.enabled,self.active)
        self.slots=slots;self.enabled=bool(enabled)
        if not slots[self.active].get('key'):self.active=next((i for i,s in enumerate(slots) if s.get('key')),0)
        try:self.persist()
        except Exception:self.slots,self.enabled,self.active=old;raise
        self.client.key=self.slots[self.active].get('key','');self.updated=time.monotonic()
        return self.summary()
    def refresh(self):
        if self.error:raise UltraError(self.error)
        seen={}
        for i,slot in enumerate(self.slots):
            if not slot.get('key'):continue
            uid=slot.get('accountId')
            try:
                if uid and uid in seen:self.slots[i]={**seen[uid],'key':slot['key']}
                else:
                    self.slots[i]=self.inspect(slot['key']);seen[self.slots[i]['accountId']]=self.slots[i]
            except UltraError:
                self.slots[i]={**slot,'fresh':False,'state':'unavailable','message':'Could not verify the key or connection.'}
        self.updated=time.monotonic();self.persist();return self.summary()
    def summary(self):
        items=[];accounts={}
        for i,s in enumerate(self.slots):
            uid=s.get('accountId');shared=accounts.get(uid) if uid else None
            if uid and uid not in accounts:accounts[uid]=i+1
            used,limit=s.get('usedUsd'),s.get('limitUsd');known=s.get('quotaKnown') and isinstance(limit,(int,float)) and limit>0
            percent=min(100,max(0,used/limit*100)) if known else None
            items.append({'slot':i+1,'saved':bool(s.get('key')),'hint':('••••'+s['key'][-4:]) if s.get('key') else '', 'state':s.get('state','empty'),'active':i==self.active and self.enabled,'sharedWith':shared,'usedPercent':percent,'remainingPercent':100-percent if percent is not None else None,'usedUsd':used,'limitUsd':limit,'remainingUsd':max(0,limit-used) if isinstance(limit,(int,float)) and isinstance(used,(int,float)) else None,'cycle':s.get('cycle'),'checkedAt':s.get('checkedAt'),'stale':not s.get('fresh',False),'message':s.get('message','')})
        return {'slots':items,'activeSlot':self.active+1,'enabled':self.enabled,'error':self.error,'maxAds':self.client.max_ads,'maxChargeUsd':self.client.max_charge}
    def enable(self,enabled):
        if self.error:raise UltraError(self.error)
        if enabled and not any(s.get('key') for s in self.slots):raise UltraError('Save at least one key in Apify API.')
        old=self.enabled;self.enabled=bool(enabled)
        try:self.persist()
        except Exception:self.enabled=old;raise
        self.client.key=self.slots[self.active].get('key','')
    def select(self,excluded=None):
        excluded=excluded or set()
        if not any(s.get('key') for s in self.slots):raise UltraError('No API key saved. Add a key in Apify API.')
        # Only refresh at a new paid-run boundary, never during an existing run.
        if time.monotonic()-self.updated>60:self.refresh()
        for i in list(range(self.active,10))+list(range(0,self.active)):
            s=self.slots[i]
            if not s.get('key') or s.get('accountId') in excluded or s.get('state') in ('exhausted','invalid','unavailable'):continue
            old=self.active;self.active=i
            try:self.persist()
            except Exception:self.active=old;raise
            self.client.key=s['key'];return i
        raise UltraError('All API slots are exhausted or unavailable. Refresh their status in Apify API.')
    def start(self,path,body):
        excluded=set()
        for _ in range(10):
            i=self.select(excluded);slot=self.slots[i]
            try:return self.client.api(path,body)
            except ApiError as e:
                # These errors conclusively reject the start before a run exists.
                quota=e.kind in ('monthly-usage-limit-exceeded','not-enough-usage-to-run-paid-actor','insufficient-usage-credits','insufficient-funds')
                if e.status==401:
                    self.slots[i].update(state='invalid',message="Apify rejected the key's authentication.",checkedAt=now_iso());self.persist();continue
                if not quota:raise
                uid=slot.get('accountId');excluded.add(uid)
                for s in self.slots:
                    if uid and s.get('accountId')==uid:s.update(state='exhausted',message='Apify rejected the new run because the quota or balance is exhausted.',checkedAt=now_iso())
                self.persist()
        raise UltraError('No Apify account has enough quota to start a new run.')
