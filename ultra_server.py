from __future__ import annotations
import argparse,hashlib,json,os,secrets,socket,sys,threading,time,traceback,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from saved_store import SavedStore
from run_history import RunHistory
from data_store import data_directory
from bing_client import BingClient
from apify_client import ApifyClient,BudgetRequired
from apify_keys import ApifyKeys
from proxy_client import ProxySettings,ProxyGoogleClient
from ultra_client import GoogleClient,UltraError,BlockedError,CancelledError,today,now_iso

VERSION='2.10.0-windows-google-bing'
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
ASSETS=ROOT/'assets'
def main():
    p=argparse.ArgumentParser();p.add_argument('--no-browser',action='store_true');p.add_argument('--port',type=int,default=0);p.add_argument('--data-dir');p.add_argument('--self-test-report');args=p.parse_args()
    executable=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
    data=data_directory(executable,args.data_dir)
    regions=json.loads((ASSETS/'regions.json').read_text(encoding='utf-8'))
    saved=SavedStore(data/"saved.json")
    client=GoogleClient(data,regions);apify=ApifyClient(client);keys=ApifyKeys(apify,data/'apify-keys.dat');apify.keys=keys;provider={'name':'apify' if keys.enabled else 'direct'};token=secrets.token_urlsafe(32);operation=threading.Lock()
    history=RunHistory(client);apify.history=history
    bing=BingClient(client);active_platform={'name':'google'}
    proxy_settings=ProxySettings(data);proxy_client=ProxyGoogleClient(data/'proxy-cache',regions,proxy_settings,client)
    if proxy_settings.config['enabled'] and not proxy_settings.error:provider['name']='proxy'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def same_host(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def send_json(self,value,status=200):
            raw=json.dumps(value,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            if not self.same_host():return self.send_json({'error':'Invalid Host header.'},403)
            path=urlsplit(self.path).path
            if path=='/api/search':return self.send_json({'configured':True,'today':today(),'version':VERSION,'provider':provider['name'],'dataDirectory':str(data),'filters':{'platform':'SEARCH','format':'TEXT'}})
            if path=='/api/apify-runs':return self.send_json(history.list())
            if path=='/api/bing':return self.send_json(bing.metadata())
            if path=='/api/apify-keys':return self.send_json(keys.summary())
            if path=='/api/proxy':return self.send_json(proxy_settings.summary())
            if path=='/api/provider':return self.send_json({'provider':provider['name'],'apifyConfigured':bool(apify.key),'maxAds':apify.max_ads,'maxChargeUsd':apify.max_charge})
            if path=='/api/saved':
                try:return self.send_json(saved.read())
                except (OSError,ValueError):return self.send_json({'error':'Could not read saved lists.'},500)
            if path=='/api/progress':return self.send_json({'busy':operation.locked(),'progress':bing.progress if active_platform['name']=='bing' else proxy_client.progress if provider['name']=='proxy' else client.progress})
            if path in ('/','/index.html'):
                raw=(ASSETS/'index.html').read_text(encoding='utf-8').replace('__ULTRA_TOKEN__',token).encode('utf-8');kind='text/html; charset=utf-8'
            elif path in ('/app.js','/styles.css','/favicon.svg'):
                raw=(ASSETS/path[1:]).read_bytes();kind={'/app.js':'text/javascript; charset=utf-8','/styles.css':'text/css; charset=utf-8','/favicon.svg':'image/svg+xml'}[path]
            else:return self.send_json({'error':'Not found.'},404)
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'nonce-"+token+"'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            origin=self.headers.get('Origin');expected=f'http://127.0.0.1:{self.server.server_port}'
            if not self.same_host() or (origin and origin!=expected) or not secrets.compare_digest(self.headers.get('X-Ultra-Token',''),token):return self.send_json({'error':'Request not allowed.'},403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send_json({'error':'Invalid request format.'},415)
            path=urlsplit(self.path).path
            if path=='/api/stop':client.cancel.set();return self.send_json({'stopped':True})
            if path=='/api/shutdown':
                client.cancel.set();self.send_json({'shutdown':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            if path not in ('/api/search','/api/saved','/api/provider','/api/apify-keys','/api/apify-import','/api/proxy'):return self.send_json({'error':'Not found.'},404)
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:return self.send_json({'error':'Invalid request.'},400)
            if length<1 or length>12000:return self.send_json({'error':'The request is too large or empty.'},413)
            try:body=json.loads(self.rfile.read(length))
            except (ValueError,UnicodeError):return self.send_json({'error':'Invalid request.'},400)
            if not isinstance(body,dict):return self.send_json({'error':'Invalid request.'},400)
            if path=='/api/saved':
                try:return self.send_json(saved.update(body))
                except ValueError as e:return self.send_json({'error':str(e)},400)
                except OSError:return self.send_json({'error':'Could not save the list. Check data-folder permissions.'},500)
            if not operation.acquire(blocking=False):return self.send_json({'error':'Another scan is in progress. Wait for it to finish.'},409)
            client.cancel.clear()
            try:
                platform=body.get('platform','google')
                if platform not in ('google','bing'):raise UltraError('Invalid advertising platform.')
                active_platform['name']=platform
                if path=='/api/search' and platform=='bing':return self.send_json(bing.process(body))
                if path=='/api/proxy':
                    if body.get('action')=='reset':result=proxy_settings.reset(body.get('baselineMb',0))
                    else:result=proxy_settings.save(body)
                    if result['enabled']:
                        keys.enable(False);provider['name']='proxy'
                    elif provider['name']=='proxy':provider['name']='direct'
                    return self.send_json({'provider':provider['name'],'proxy':result})
                if path=='/api/apify-keys':
                    if body.get('action')=='refresh':result=keys.refresh()
                    elif body.get('action')=='save':result=keys.save(body.get('slots'),body.get('enabled',True))
                    else:raise UltraError('Invalid Apify API action.')
                    if keys.enabled:proxy_settings.enable(False)
                    provider['name']='apify' if keys.enabled else ('proxy' if proxy_settings.config['enabled'] else 'direct')
                    return self.send_json(result)
                if path=='/api/provider':
                    if body.get('provider')=='direct':keys.enable(False);proxy_settings.enable(False);provider['name']='direct'
                    elif body.get('provider')=='proxy':
                        proxy_settings.enable(True);keys.enable(False);provider['name']='proxy'
                    elif body.get('provider')=='apify':
                        candidate=body.get('key') or apify.key
                        old_config=(apify.key,apify.max_ads,apify.max_charge)
                        try:
                            apify.configure(candidate,body.get('maxAds',40),body.get('maxChargeUsd',0.10))
                            if body.get('key'):
                                edits=[{} for _ in range(10)];edits[keys.active]={'key':body['key']};keys.save(edits,True)
                            else:keys.enable(True)
                        except Exception:
                            apify.key,apify.max_ads,apify.max_charge=old_config
                            raise
                        proxy_settings.enable(False);provider['name']='apify'
                    else:raise UltraError('Invalid data source.')
                    return self.send_json({'provider':provider['name'],'apifyConfigured':bool(apify.key),'maxAds':apify.max_ads,'maxChargeUsd':apify.max_charge})
                if path=='/api/apify-import':
                    if provider['name']!='apify':raise UltraError('Connect Apify before importing an existing run.')
                    result=apify.import_run(body,body.get('runId'))
                else:result=apify.process(body) if provider['name']=='apify' else proxy_client.process(body) if provider['name']=='proxy' else client.process(body)
                if provider['name']=='apify':
                    if result.get('runId') and not result.get('cached'):
                        try:keys.refresh()
                        except (UltraError,OSError):pass
                    result['keyUsage']=keys.summary()
                if provider['name']=='proxy':result['proxyUsage']=proxy_settings.summary()
                self.send_json(result)
            except BudgetRequired as e:self.send_json({'error':str(e),'code':'BUDGET_REQUIRED','estimate':e.estimate,'currentBudgetUsd':e.current,'cachedPartial':e.partial,'keyUsage':keys.summary()},409)
            except BlockedError as e:self.send_json({'error':str(e),'code':'GOOGLE_BLOCKED'},429)
            except CancelledError as e:self.send_json({'error':str(e),'code':'CANCELLED'},409)
            except UltraError as e:self.send_json({'error':str(e)},400)
            except Exception:
                with (data/'errors.log').open('a',encoding='utf-8') as log:log.write(now_iso()+'\n'+traceback.format_exc()+'\n')
                self.send_json({'error':"Data processing error. Details were saved in the local data folder's errors.log."},500)
            finally:client.progress='Ready';proxy_client.progress='Ready';bing.progress='Ready';operation.release()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.daemon_threads=True
    url=f'http://127.0.0.1:{server.server_port}'
    (data/'session.json').write_text(json.dumps({'url':url,'version':VERSION,'pid':os.getpid()}),encoding='utf-8')
    if args.self_test_report:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            import self_check
            result=self_check.run(server,token,ASSETS)
        except Exception:result={'passed':False,'error':traceback.format_exc()}
        finally:server.shutdown();thread.join(3);server.server_close();client.db.close();proxy_client.db.close()
        Path(args.self_test_report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if not result['passed']:sys.exit(1)
        return
    if sys.stdout:print('Ultra Check '+url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever(poll_interval=.3)
    finally:server.server_close();client.db.close();proxy_client.db.close()
if __name__=='__main__':
    try:main()
    except Exception:
        message=traceback.format_exc()
        if sys.stderr:sys.stderr.write(message)
        if getattr(sys,'frozen',False):
            import ctypes;ctypes.windll.user32.MessageBoxW(0,'Could not start Ultra Check.\n\n'+message[-1500:],'Ultra Check',16)
        raise
