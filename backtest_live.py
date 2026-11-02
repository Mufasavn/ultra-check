import json,sys,time
from pathlib import Path
import ultra_client as u
root=Path(__file__).parent
regions=json.loads((Path('lib/regions.json')).read_text(encoding='utf-8'))
c=u.GoogleClient(root/'test-cache',regions)
def run(label,body):
    print('START',label,flush=True)
    t=time.monotonic();result=c.process(body)
    (root/'test-results').mkdir(exist_ok=True)
    (root/'test-results'/f'{label}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DONE',label,'seconds',round(time.monotonic()-t,1),'ads',len(result.get('ads',[])),'domains',sorted({a['domain'] for a in result.get('ads',[]) if a['domain']}),'missing',sum(a['domain'] is None for a in result.get('ads',[])),'next',bool(result.get('nextPageToken')),'warning',result.get('warning',''),flush=True)
    return result
if __name__=='__main__':
    selected=sys.argv[1:]
    if not selected or 'search' in selected:run('search',{'mode':'discover','text':'Adcore East Limited'})
    base={'advertiserId':'AR15863532213959131137'}
    if not selected or 'all' in selected:run('all',dict(base,mode='check'))
    if 'france' in selected:run('france',dict(base,mode='check',region='2250',start='2026-10-01',end='2026-10-01'))
    if 'vietnam' in selected:run('vietnam',dict(base,mode='check',region='2704',start='2026-10-01',end='2026-10-01'))
    if 'today' in selected:run('today',dict(base,mode='current'))
    if 'old' in selected:run('old',dict(base,mode='check',start='2025-01-01',end='2025-01-01'))
    if 'page2' in selected:
        first=json.loads((root/'test-results/all.json').read_text(encoding='utf-8'))
        run('page2',dict(base,mode='check',pageToken=first['nextPageToken']))
