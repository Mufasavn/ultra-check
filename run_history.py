"""Persistent local Apify run index; only allowlisted public run metadata."""
import json,re
from ultra_client import now_iso

class RunHistory:
    def __init__(self,google):
        self.google=google
        with google.lock:
            google.db.execute('CREATE TABLE IF NOT EXISTS apify_history (id TEXT PRIMARY KEY, created TEXT NOT NULL, data TEXT NOT NULL)');google.db.commit()
            old=google.db.execute("SELECT data FROM cache WHERE key LIKE 'apify-run:%'").fetchall()
        for raw, in old:
            try:
                cached=json.loads(raw);self.record({'id':cached['runId'],'status':'CACHED_PARTIAL' if cached.get('incomplete') else 'CACHED','startedAt':cached.get('checkedAt'),'usageTotalUsd':cached.get('costUsd')},cached.get('input',{}),cached)
            except (ValueError,KeyError,TypeError):continue
    def record(self,run,inputs,result=None):
        rid=run.get('id','')
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9]{1,40}',rid):return
        kind='overview' if inputs.get('overviewOnly') else inputs.get('mode','ads')
        query={'region':next((code for code,iso in self.google.iso.items() if iso.upper()==str(inputs.get('region','')).upper()),''),'start':inputs.get('dateFrom') or '','end':inputs.get('dateTo') or ''}
        domains=inputs.get('domains') or [];ids=inputs.get('advertiserIds') or [];names=inputs.get('advertiserNames') or []
        if len(domains)==1:query.update(mode='reverse',domain=domains[0])
        elif len(ids)==1:query.update(mode='check',advertiserId=ids[0])
        title=', '.join(str(v) for v in domains or ids or names)[:500] or 'Apify run'
        with self.google.lock:
            old=self.google.db.execute('SELECT created,data FROM apify_history WHERE id=?',(rid,)).fetchone()
            previous=json.loads(old[1]) if old else {}
            # Startup cache migration must never overwrite a more recent state.
            if old and run.get('status') in ('CACHED','CACHED_PARTIAL'):return
            created=old[0] if old else run.get('startedAt') or now_iso()
            row={'id':rid,'createdAt':created,'updatedAt':now_iso(),'title':title,'kind':kind,'status':run.get('status') or previous.get('status','UNKNOWN'),'query':query,'importable':kind=='ads' and 'mode' in query and inputs.get('format')=='TEXT' and inputs.get('platform')=='SEARCH','url':'https://console.apify.com/actors/runs/'+rid,'costUsd':run.get('usageTotalUsd',previous.get('costUsd'))}
            if result is not None:row.update(ads=len(result.get('rows',[])),incomplete=bool(result.get('incomplete')))
            else:
                for key in ('ads','incomplete'):
                    if key in previous:row[key]=previous[key]
            self.google.db.execute('INSERT OR REPLACE INTO apify_history VALUES (?,?,?)',(rid,created,json.dumps(row,ensure_ascii=False)));self.google.db.commit()
    def list(self):
        with self.google.lock:rows=self.google.db.execute('SELECT data FROM apify_history ORDER BY created DESC,id DESC').fetchall()
        return {'runs':[json.loads(row[0]) for row in rows]}
