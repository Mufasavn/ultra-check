
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, Check, ChevronDown, Download, Globe2, KeyRound, Layers, LoaderCircle, Search, ShieldCheck, SlidersHorizontal, X, Zap } from "lucide-react";
import regions from "./assets/regions.json";
import { csvCell, groupDomains, today } from "./ultra-core.mjs";

type Ad = { platform?: string; method?: string; evidence?: string; preview?: string; id: string; advertiserId: string; advertiser: string; domain: string | null; first: string | null; last: string | null; format: string; source: string };
type Candidate = { id: string; name: string };
type Query = { region: string; start: string; end: string };
type SearchQuery = Query & { domain?: string };
type Discovery = { text: string; candidates: Candidate[]; next: string | null; error?: string };
type Scan = { incomplete?:boolean; id: string; name: string; next: string | null; error?: string };
type Current = { incomplete?:boolean; date: string; domains: string[]; next: string | null; checkedAt: string };
type Group = { domain: string; advertiser: string; advertiserId: string; first: string | null; last: string | null; ads: Ad[] };
type ApiData = { configured?: boolean; error?: string; today: string; candidates: Candidate[]; ads: Ad[]; nextPageToken: string | null; checkedAt: string; domains: string[]; warning?: string; cached?: boolean; incomplete?:boolean; halt?:boolean; coverageLimited?:boolean; costUsd?:number; runId?:string; sourceIncomplete?:boolean; keyUsage?:any };
const labels: Record<string, string> = { "2704": "Vietnam", "2840": "United States", "2764": "Thailand", "2702": "Singapore", "2826": "United Kingdom", "2250": "France", "2276": "Germany", "2392": "Japan", "2410": "South Korea", "2036": "Australia", "2124": "Canada", "2356": "India", "2360": "Indonesia", "2458": "Malaysia", "2608": "Philippines", "2156": "China" };
function dateText(s: string | null, bing=false) { return s ? new Intl.DateTimeFormat("en-US", { timeZone: bing?"UTC":"America/Los_Angeles", day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(s)) : "Unknown"; }
function displayDay(s: string) { return s ? s.split("-").reverse().join("/") : ""; }
function mergeAds(a: Ad[], b: Ad[]) { return [...new Map([...a, ...b].map(x => [x.advertiserId + ":" + x.id + ":" + x.domain, x])).values()]; }
function Pagination({page, count, onChange}: {page:number; count:number; onChange:(n:number)=>void}) {
  if (!count) return null;
  const pages = Math.max(1, Math.ceil(count / 10));
  const numbers = Array.from({length:pages},(_,i)=>i+1).filter(n=>n===1||n===pages||Math.abs(n-page)<=2);
  return <nav className="pagination" aria-label="Results pagination"><span>{(page-1)*10+1}–{Math.min(page*10,count)} / {count}  results · 10 per page</span><button className="outline" disabled={page===1} onClick={()=>onChange(page-1)}>Previous</button>{numbers.map((n,i)=><span key={n}>{i>0&&n>numbers[i-1]+1&&<span>…</span>}<button className={n===page?"primary":"outline"} aria-current={n===page?"page":undefined} onClick={()=>onChange(n)}>Page {n}</button></span>)}<button className="outline" disabled={page===pages} onClick={()=>onChange(page+1)}>Next</button></nav>;
}

function UsageRing({info}:{info:any}) {
  const slot=info?.slots?.find((s:any)=>s.active);
  const value=typeof slot?.usedPercent==="number"?Math.max(0,Math.min(100,slot.usedPercent)):null;
  return <span className="usage-ring" role="img" aria-label={value==null?"No usage data for the active API key":`API ${slot.slot}: used ${value.toFixed(1)}%`} title={value==null?"No usage data for the active API key":`API ${slot.slot} · used ${value.toFixed(1)}%${slot.stale?" · saved usage snapshot":""}`}><svg viewBox="0 0 44 44" aria-hidden="true"><circle className="ring-track" cx="22" cy="22" r="19"/><circle className="ring-value" cx="22" cy="22" r="19" pathLength="100" strokeDasharray={`${value??0} 100`}/><text x="22" y="25">{value==null?"—":value.toFixed(1)+"%"}</text></svg></span>;
}

function proxySize(bytes:number=0) { return bytes>=1e9 ? (bytes/1e9).toFixed(2)+" GB" : (bytes/1e6).toFixed(2)+" MB"; }
function ProxyRing({info,large=false}:{info:any;large?:boolean}) {
  const value=info?.usedPercent??0;const parts=proxySize(info?.usedBytes).split(" ");
  return <span className={large?"usage-ring proxy-ring":"usage-ring proxy-ring-small"} role="img" aria-label={`Estimated proxy data used ${proxySize(info?.usedBytes)}`}><svg viewBox="0 0 44 44" aria-hidden="true"><circle className="ring-track" cx="22" cy="22" r="19"/><circle className="ring-value" cx="22" cy="22" r="19" pathLength="100" strokeDasharray={`${value} 100`}/><text x="22" y="21">{parts[0]}</text><text className="proxy-unit" x="22" y="28">{parts[1]}</text></svg></span>;
}

export default function UltraCheck() {
  const [platform,setPlatform]=useState("google");
  const isBing=platform==="bing";
  const [bingInfo,setBingInfo]=useState<any>(null);
  useEffect(()=>{fetch("/api/bing").then(r=>r.json()).then(setBingInfo).catch(()=>{});},[]);
  function changePlatform(value:string){
    setPlatform(value);setRegion("");setRange("all");setStart("");setEnd("");setAds([]);setQuery(null);setDiscoveries([]);setSelected([]);setScans([]);setCurrent({});setReverseToday(null);setReverseNext(null);setReverseIncomplete(false);setMessage("");setLastRun(null);setStatusFilter("all");setDomainFilter("");setCheckedAt("");setExpanded("");
    setServerToday(value==="bing"?new Date().toISOString().slice(0,10):today());
  }
  const countryName=(id:string)=>isBing?bingInfo?.countries?.[id]||id:labels[id]||(regions as Record<string,string>)[id];
  const [saved, setSaved] = useState<{advertisers:string[];domains:string[]}>({advertisers:[],domains:[]});
  const [dataDirectory,setDataDirectory]=useState("");
  const [savedReady, setSavedReady] = useState(false); const [saving,setSaving] = useState(false);
  const [importRunId,setImportRunId]=useState("");
  const [runHistory,setRunHistory]=useState<any[]>([]);const [runPage,setRunPage]=useState(1);const [runError,setRunError]=useState("");
  async function loadRunHistory(){try{const r=await fetch("/api/apify-runs");if(!r.ok)throw Error("Could not read Apify run history.");setRunHistory((await r.json()).runs||[]);setRunError("");}catch(e){setRunError((e as Error).message);}}
  useEffect(()=>{loadRunHistory();const timer=setInterval(loadRunHistory,5000);return()=>clearInterval(timer);},[]);
  async function copyRun(id:string){try{await navigator.clipboard.writeText(id);setMessage("Copied run ID "+id);}catch{setImportRunId(id);setMessage("The run ID has been filled in. Select it to copy manually.");}}

  const [keyInfo,setKeyInfo] = useState<any>(null);
  const [keyDrafts,setKeyDrafts] = useState<string[]>(Array(10).fill(""));
  const [clearKeys,setClearKeys] = useState<boolean[]>(Array(10).fill(false));
  const [keysBusy,setKeysBusy] = useState(false);const [keysError,setKeysError] = useState("");
  async function loadKeys() {
    try{const r=await fetch("/api/apify-keys");if(!r.ok)throw Error("Could not read the key vault.");setKeyInfo(await r.json());}catch(e){setKeysError((e as Error).message);}
  }
  useEffect(()=>{loadKeys();},[]);
  useEffect(()=>{const timer=setInterval(()=>{loadKeys();},5000);return()=>clearInterval(timer);},[]);
  async function manageKeys(action:string) {
    setKeysBusy(true);setKeysError("");
    try {
      const r=await fetch("/api/apify-keys",{method:"POST",headers:{"Content-Type":"application/json","X-Ultra-Token":(window as any).ULTRA_TOKEN},body:JSON.stringify({action,enabled:true,slots:keyDrafts.map((key,i)=>({key,clear:clearKeys[i]}))})});
      const d=await r.json();if(!r.ok)throw Error(d.error||"Could not update API settings.");setKeyInfo(d);setKeyDrafts(Array(10).fill(""));setClearKeys(Array(10).fill(false));if(action==="save"){setProvider(d.enabled?"apify":"direct");loadProxy();}
      if(action==="save"){setAds([]);setQuery(null);setDiscoveries([]);setSelected([]);setScans([]);setCurrent({});setReverseToday(null);setLastRun(null);}
    }catch(e){setKeysError((e as Error).message);}finally{setKeysBusy(false);}
  }
  const [proxyInfo,setProxyInfo]=useState<any>(null);
  const [proxyDraft,setProxyDraft]=useState({host:"thehub.proxy-cheap.com",port:8080,username:"",password:"",totalGb:5,baselineMb:0});
  const [proxyBusy,setProxyBusy]=useState(false);const [proxyError,setProxyError]=useState("");const [proxyNotice,setProxyNotice]=useState("");
  async function loadProxy(initialize=false) {
    try{const r=await fetch("/api/proxy");if(!r.ok)throw Error("Could not read proxy settings.");const d=await r.json();setProxyInfo(d);if(initialize)setProxyDraft({host:d.host,port:d.port,username:d.username,password:"",totalGb:d.totalGb,baselineMb:d.baselineMb});}catch(e){setProxyError((e as Error).message);}
  }
  useEffect(()=>{loadProxy(true);const timer=setInterval(()=>loadProxy(),5000);return()=>clearInterval(timer);},[]);
  async function saveProxy(enabled:boolean,reset=false) {
    setProxyBusy(true);setProxyError("");setProxyNotice("");
    try {
      const r=await fetch("/api/proxy",{method:"POST",headers:{"Content-Type":"application/json","X-Ultra-Token":(window as any).ULTRA_TOKEN},body:JSON.stringify({...proxyDraft,enabled,action:reset?"reset":"save"})});
      const d=await r.json();if(!r.ok)throw Error(d.error||"Could not save proxy settings.");setProxyInfo(d.proxy);if(!reset)setProxyDraft(prev=>({...prev,password:""}));
      if(d.provider!==provider)await configureProvider(d.provider);else setProvider(d.provider);
      setProxyNotice(reset?"Baseline updated and local meter restarted.":"Encrypted settings saved on this computer.");loadKeys();
    }catch(e){setProxyError((e as Error).message);}finally{setProxyBusy(false);}
  }
  const collectAll = true;
  const [provider,setProvider] = useState("direct");
  const [maxAds,setMaxAds] = useState(40); const [maxCharge,setMaxCharge] = useState(0.10);
  const [lastRun,setLastRun] = useState<{id:string;cost:number;cached:boolean}|null>(null);
  const [connecting,setConnecting] = useState(false);const [providerError,setProviderError] = useState("");
  useEffect(()=>{fetch("/api/provider").then(r=>r.json()).then(d=>{setProvider(d.provider);setMaxAds(d.maxAds);setMaxCharge(d.maxChargeUsd);}).catch(()=>{});},[]);
  async function configureProvider(name:string) {
    setConnecting(true);setProviderError("");
    try {
      const r=await fetch("/api/provider",{method:"POST",headers:{"Content-Type":"application/json","X-Ultra-Token":(window as any).ULTRA_TOKEN},body:JSON.stringify({provider:name,key:keyDraft,maxAds,maxChargeUsd:maxCharge})});
      const d=await r.json();if(!r.ok)throw Error(d.error||"Could not change the data source.");
      setProvider(d.provider);setKeyDraft("");loadKeys();setModal(false);setQuery(null);setAds([]);setScans([]);setCurrent({});setReverseToday(null);setReverseNext(null);setReverseIncomplete(false);setDiscoveries([]);setSelected([]);setLastRun(null);setMessage("");
    }catch(e){setProviderError((e as Error).message);}finally{setConnecting(false);}
  }
  const [view,setView] = useState("search");
  useEffect(()=>{fetch("/api/saved").then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{setSaved(d);setSavedReady(true);}).catch(()=>setMessage("Could not read saved lists. Check your Windows application data folder."));},[]);
  async function saveEntry(kind:"advertisers"|"domains", value:string, remove=false) {
    if(!savedReady || saving)return; setSaving(true);
    try { const r=await fetch("/api/saved",{method:"POST",headers:{"Content-Type":"application/json","X-Ultra-Token":(window as any).ULTRA_TOKEN},body:JSON.stringify({kind,value,remove})}); const d=await r.json();if(!r.ok)throw Error(d.error);setSaved(d); }
    catch(e){setMessage((e as Error).message||"Could not save the list.");}finally{setSaving(false);}
  }
  const [lookup, setLookup] = useState("advertiser"); const [website, setWebsite] = useState("");
  const [resultPage, setResultPage] = useState(1); const [reverseNext, setReverseNext] = useState<string|null>(null);
  const [reverseIncomplete, setReverseIncomplete] = useState(false);
  const [reverseToday, setReverseToday] = useState<{date:string; ids:string[]; next:string|null}|null>(null);
  const stopRequested = useRef(false);
  const [names, setNames] = useState("Adcore East Limited");
  const [region, setRegion] = useState("");
  const [range, setRange] = useState("all");
  const [start, setStart] = useState(""); const [end, setEnd] = useState("");
  const [serverToday, setServerToday] = useState("");
  const [configured, setConfigured] = useState(true); const [key, setKey] = useState(""); const [keyDraft, setKeyDraft] = useState("");
  const [modal, setModal] = useState(false); const [guide, setGuide] = useState(false);
  const [fresh, setFresh] = useState(false); const [closed, setClosed] = useState(false); const [busy, setBusy] = useState(""); const [message, setMessage] = useState("");
  const [discoveries, setDiscoveries] = useState<Discovery[]>([]); const [selected, setSelected] = useState<string[]>([]);
  const [discoveryRegion, setDiscoveryRegion] = useState("");
  const [query, setQuery] = useState<SearchQuery | null>(null); const [ads, setAds] = useState<Ad[]>([]); const [scans, setScans] = useState<Scan[]>([]);
  const [current, setCurrent] = useState<Record<string, Current>>({}); const [checkedAt, setCheckedAt] = useState("");
  const [domainFilter, setDomainFilter] = useState(""); const [statusFilter, setStatusFilter] = useState("all");
  const [expanded, setExpanded] = useState(""); const resultsRef = useRef<HTMLElement>(null);
  const options = useMemo(() => Object.entries(isBing?bingInfo?.countries||{}:regions).map(([id, name]) => ({ id, name: isBing?String(name):labels[id] || String(name) })).sort((a,b) => a.name.localeCompare(b.name, "en")), [isBing,bingInfo]);
  const candidates = useMemo(() => [...new Map(discoveries.flatMap(d => d.candidates).map(c => [c.id, c])).values()], [discoveries]);
  const groups: Group[] = useMemo(() => groupDomains(ads), [ads]);
  const getStatus = (g: Group) => {
    if(isBing)return g.last?.slice(0,10)===serverToday?"today":"unknown";
    if(query?.domain) {
      if(!reverseToday || reverseToday.date!==serverToday) return "unknown";
      return reverseToday.ids.includes(g.advertiserId)?"today":reverseToday.next?"unknown":"history";
    }
    const c = current[g.advertiserId];
    if (!c || c.date !== serverToday) return "unknown";
    return c.domains.includes(g.domain) ? "today" : c.next||c.incomplete ? "unknown" : "history";
  };
  const visible = groups.filter(g => (g.domain + " " + g.advertiser).toLowerCase().includes(domainFilter.toLowerCase()) && (statusFilter === "all" || getStatus(g) === statusFilter));
  const pageCount = Math.max(1,Math.ceil(visible.length/10)); const page = Math.min(resultPage,pageCount);
  const pageRows = visible.slice((page-1)*10,page*10);
  useEffect(()=>setResultPage(1),[domainFilter,statusFilter,query]);
  const partialResults=isBing&&!!query||reverseIncomplete||scans.some(s=>!!s.next||!!s.error||!!s.incomplete);
  const missing = ads.filter(a => !a.domain);
  const ready = true;
  useEffect(() => {
    setServerToday(today());
    fetch("/api/search").then(r => r.json() as Promise<ApiData>).then(d => { if ((d as any).dataDirectory)setDataDirectory((d as any).dataDirectory); if (d.today) setServerToday(d.today); setConfigured(Boolean(d.configured)); if (d.error) setMessage(d.error); }).catch(() => setMessage("Could not check the local server. You can still open the connection guide."));

  }, []);
  useEffect(()=>{const clock=setInterval(()=>setServerToday(isBing?new Date().toISOString().slice(0,10):today()),60000);return()=>clearInterval(clock);},[isBing]);
  useEffect(() => {
    if (!busy) return;
    const poll = setInterval(() => fetch("/api/progress").then(r=>r.json()).then((p:any)=> {if(p.busy) setBusy(p.progress);}).catch(()=>{}),1000);
    return () => clearInterval(poll);
  }, [Boolean(busy)]);
  useEffect(() => {
    if (!modal) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setModal(false); };
    document.addEventListener("keydown", handler);
    
    return () => document.removeEventListener("keydown", handler);
  }, [modal]);
  async function request(body: Record<string, unknown>) {
    const r = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json", "X-Ultra-Token": (window as any).ULTRA_TOKEN }, body: JSON.stringify({ ...body, fresh, collectAll, platform }) });
    let d: ApiData;
    try { d = await r.json() as ApiData; } catch { throw Error("The server returned no results. Please try again."); }
    if (!r.ok) throw Error(d.error || "Search failed.");
    if (d.keyUsage) setKeyInfo(d.keyUsage);
    if ((d as any).proxyUsage) setProxyInfo((d as any).proxyUsage);
    if (d.today) setServerToday(d.today);
    if (d.runId) setLastRun({id:d.runId,cost:d.costUsd||0,cached:!!d.cached});
    if (d.warning) setMessage(d.warning);
    return d;
  }
  function requireKey() { return true; }
  async function discover() {
    const list = [...new Set(names.split(/[\n;,]+/).map(s => s.trim()).filter(Boolean))];
    if (!list.length || list.length > 10) { setMessage("Enter 1 to 10 advertiser names, one per line."); return; }
    if (!requireKey()) return;
    setMessage(""); setDiscoveries([]); setSelected([]); setDiscoveryRegion(region);
    const found: Discovery[] = [];
    try {
      for (let i = 0; i < list.length; i++) {
        setBusy(`Find profiles ${i+1}/${list.length}…`);
        try {
          if (!isBing && /^AR\d+$/.test(list[i])) { found.push({ text: list[i], candidates: [{ id: list[i], name: list[i] }], next: null }); }
          else { const d = await request({ mode: "discover", text: list[i], region }); found.push({ text: list[i], candidates: d.candidates, next: d.nextPageToken }); }
        } catch (e) { found.push({ text: list[i], candidates: [], next: null, error: (e as Error).message }); }
        setDiscoveries([...found]);
      }
    } finally { setBusy(""); }
  }
  async function moreCandidates(entry: Discovery) {
    if (!requireKey()) return; setBusy("Loading more profiles…"); setMessage("");
    try { const d = await request({ mode: "discover", text: entry.text, region: discoveryRegion, pageToken: entry.next }); setDiscoveries(prev => prev.map(x => x.text === entry.text ? { ...x, candidates: [...new Map([...x.candidates,...d.candidates].map(c => [c.id,c])).values()] as Candidate[], next: d.nextPageToken, error: undefined } : x)); }
    catch(e) { setMessage((e as Error).message); } finally { setBusy(""); }
  }
  async function scan() {
    if (!selected.length || selected.length > 10) { setMessage("Select between 1 and 10 advertiser profiles."); return; }
    if (!requireKey()) return;
    const q = { region, start: range === "all" ? "" : start, end: range === "all" ? "" : end };
    if (range !== "all" && (!start || !end || start > end || end > serverToday)) { setMessage("Select valid dates. The end date cannot be later than today in the selected source time zone."); return; }
    setQuery(q); setAds([]); setScans([]); setCurrent({}); setReverseToday(null); setReverseNext(null); setReverseIncomplete(false); setMessage(""); setExpanded("");
    stopRequested.current=false;
    const loaded: Ad[] = []; const info: Scan[] = [];
    try {
      for (let i=0; i<selected.length && !stopRequested.current; i++) {
        const id=selected[i],name=candidates.find(c=>c.id===id)?.name||id;
        const item:Scan={id,name,next:null,incomplete:false};info.push(item);
        let token:string|null=null;const seen=new Set<string>();
        try {
          do {
            setBusy(`Reading profile ${i+1}/${selected.length} · ${loaded.length} ads downloaded…`);
            const d=await request({mode:"check",advertiserId:id,...q,pageToken:token});
            loaded.push(...d.ads);item.next=d.nextPageToken;item.incomplete=isBing?!!d.incomplete:!!item.incomplete||!!d.incomplete;
            setAds(mergeAds([],loaded));setScans(info.map(x=>({...x})));setCheckedAt(d.checkedAt);
            token=d.nextPageToken;
            if(token&&seen.has(token))throw Error("The source repeated a page. Results are incomplete.");
            if(token)seen.add(token);
            if(isBing||d.halt)break;
          }while(token&&!stopRequested.current);
        }catch(e){item.error=(e as Error).message;}
        setScans(info.map(x=>({...x})));
      }
      setTimeout(()=>resultsRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),100);
    }finally{setBusy("");}
  }
  async function more(scanInfo:Scan) {
    if(!requireKey())return;stopRequested.current=false;setBusy("Loading remaining pages…");setMessage("");
    let token=scanInfo.next;const seen=new Set<string>();let incomplete=!!scanInfo.incomplete;
    try {
      do {
        const d=await request({mode:"check",advertiserId:scanInfo.id,...query,pageToken:token});
        setAds(prev=>mergeAds(prev,d.ads));incomplete=isBing?!!d.incomplete:incomplete||!!d.incomplete;
        setScans(prev=>prev.map(s=>s.id===scanInfo.id?{...s,next:d.nextPageToken,incomplete,error:undefined}:s));setCheckedAt(d.checkedAt);token=d.nextPageToken;
        if(token&&seen.has(token))throw Error("The source repeated a page. Results are incomplete.");
        if(token)seen.add(token);
        if(isBing||d.halt)break;
      }while(token&&!stopRequested.current);
    }catch(e){setMessage((e as Error).message);}finally{setBusy("");}
  }

  async function reverseScan(resume = false) {
    const q:SearchQuery = resume && query?.domain ? query : {region,start:range==="all"?"":start,end:range==="all"?"":end,domain:website.trim()};
    if(!q.domain){setMessage("Enter a domain to find advertisers.");return;}
    if(!resume && range!=="all" && (!start||!end||start>end||end>serverToday)){setMessage("Select a valid date range in the selected source time zone.");return;}
    stopRequested.current=false; setMessage(""); setBusy("Finding advertisers for this domain…");
    setReverseIncomplete(true);
    if(!resume){setQuery(q);setAds([]);setScans([]);setCurrent({});setReverseToday(null);setReverseNext(null);setExpanded("");}
    let token = resume ? reverseNext : null; const seen = new Set<string>();let sourceIncomplete=false;
    try {
      do {
        const d=await request({mode:"reverse",...q,pageToken:token});
        setAds(prev=>mergeAds(prev,d.ads));setCheckedAt(d.checkedAt);setReverseNext(d.nextPageToken);
        token=d.nextPageToken;
        sourceIncomplete=sourceIncomplete||!!d.incomplete;
        if(!token)setReverseIncomplete(sourceIncomplete);
        if(stopRequested.current)break;
        if(token&&seen.has(token))throw Error("The source repeated a page. Results are incomplete.");
        if(token)seen.add(token);
        if(isBing||d.halt)break;
      } while(token);
      if(!isBing&&!stopRequested.current)await reverseCheckToday(q);
    } catch(e){setMessage((e as Error).message);} finally{setBusy("");}
  }
  async function reverseCheckToday(q:SearchQuery = query!) {
    if(!q?.domain)return;
    stopRequested.current=false;setBusy("Checking advertisers observed today…");
    let token:string|null=null; const ids=new Set<string>();const seen=new Set<string>();let incomplete=false;
    try {
      do {
        const d=await request({mode:"reverse-current",domain:q.domain,region:q.region,pageToken:token});
        d.ads.forEach(a=>ids.add(a.advertiserId));
        if(!q.start||q.end>=d.today)setAds(prev=>mergeAds(prev,d.ads));
        incomplete=incomplete||!!d.incomplete||!!d.warning;
        setReverseToday({date:d.today,ids:[...ids],next:d.nextPageToken||(incomplete||stopRequested.current?"incomplete":null)});setCheckedAt(d.checkedAt);token=d.nextPageToken;
        if(stopRequested.current)break;
        if(token&&seen.has(token))throw Error("The source repeated a page for today.");
        if(token)seen.add(token);
      }while(token);
    }finally{setBusy("");}
  }
  async function checkToday(id?: string, pageToken?: string | null) {
    if(isBing)return;
    if(query?.domain){try{await reverseCheckToday();}catch(e){setMessage((e as Error).message);}return;}
    if (!query || !requireKey()) return; setMessage("");
    stopRequested.current=false;
    const targets=id?scans.filter(s=>s.id===id):scans.filter(s=>!s.error);
    try {
      for(let i=0;i<targets.length&&!stopRequested.current;i++) {
        const target=targets[i];let token=pageToken||null;const seen=new Set<string>();
        const domains=new Set<string>(pageToken&&current[target.id]?.date===serverToday?current[target.id].domains:[]);let incomplete=false;
        try {
          do {
            setBusy(`Check today ${i+1}/${targets.length}…`);
            const d=await request({mode:"current",advertiserId:target.id,region:query.region,pageToken:token});
            d.ads.forEach(a=>{if(a.domain)domains.add(a.domain);});
            if(!query.start||query.end>=d.today)setAds(prev=>mergeAds(prev,d.ads));
            incomplete=incomplete||!!d.incomplete||!!d.warning;
            setCurrent(prev=>({...prev,[target.id]:{date:d.today,domains:[...domains],next:d.nextPageToken,incomplete,checkedAt:d.checkedAt}}));setCheckedAt(d.checkedAt);token=d.nextPageToken;
            if(token&&seen.has(token))throw Error("The source repeated a page for today. Results are incomplete.");
            if(token)seen.add(token);
            if(isBing||d.halt)break;
          }while(token&&!stopRequested.current);
        }catch(e){setCurrent(prev=>({...prev,[target.id]:{date:serverToday,domains:[...domains],next:token,incomplete:true,checkedAt:prev[target.id]?.checkedAt||""}}));setMessage(`${target.name}: ${(e as Error).message}`);}
      }
    }finally{setBusy("");}
  }

  async function enrich(ad: Ad) {
    if (!requireKey()) return; setBusy("Reading domains from ad details…"); setMessage("");
    try { const d = await request({ mode: "details", advertiserId: ad.advertiserId, creativeId: ad.id, region: query?.region || "" });
      if (!d.domains.length) { setMessage("The ad details do not expose a domain. Open the original ad to verify it."); return; }
      setAds(prev => mergeAds(prev.filter(a => !(a.id === ad.id && a.advertiserId === ad.advertiserId && !a.domain)), d.domains.map((domain: string) => ({ ...ad, domain }))));
    } catch(e) { setMessage((e as Error).message); } finally { setBusy(""); }
  }
  async function importExistingRun(item?:any) {
    if(isBing){setMessage("Switch to Google before importing an Apify run.");return;}
    const id=(item?.id||importRunId).trim();const importLookup=item?.query?.domain?"domain":item?"advertiser":lookup;if(!/^[A-Za-z0-9]{10,30}$/.test(id)){setMessage("Paste an Apify run ID, not a website URL. The ID is at the end of the run link.");return;}
    const q:SearchQuery=item?.query?{region:item.query.region,start:item.query.start,end:item.query.end,...(item.query.domain?{domain:item.query.domain}:{})}:{region,start:range==="all"?"":start,end:range==="all"?"":end,...(importLookup==="domain"?{domain:website.trim()}: {})};
    const advertiserId=item?.query?.advertiserId||(selected.length===1?selected[0]:/^AR\d+$/.test(names.trim())?names.trim():"");
    if(importLookup!=="domain"&&!advertiserId){setMessage("Select one advertiser profile or enter its AR ID before importing a run.");return;}
    const body={mode:importLookup==="domain"?"reverse":"check",...q,...(advertiserId?{advertiserId}:{}),collectAll};
    if(item){setImportRunId(id);setLookup(importLookup);setRegion(q.region);setStart(q.start);setEnd(q.end);setRange(q.start?"custom":"all");if(q.domain)setWebsite(q.domain);if(advertiserId){setNames(advertiserId);setSelected([]);}}
    stopRequested.current=false;setBusy("Reading an existing Apify run; no new scan…");setMessage("");
    try {
      const response=await fetch("/api/apify-import",{method:"POST",headers:{"Content-Type":"application/json","X-Ultra-Token":(window as any).ULTRA_TOKEN},body:JSON.stringify({...body,runId:id})});
      const first=await response.json();if(!response.ok)throw Error(first.error||"Could not import the existing run.");
      setQuery(q);setAds([]);setScans([]);setCurrent({});setReverseToday(null);setReverseNext(null);setExpanded("");
      const loaded:Ad[]=[];let d:ApiData=first;let incomplete=false;const seen=new Set<string>();
      while(true) {
        loaded.push(...d.ads);incomplete=incomplete||!!d.incomplete;
        setAds(mergeAds([],loaded));setCheckedAt(d.checkedAt);if(d.keyUsage)setKeyInfo(d.keyUsage);
        if(d.runId)setLastRun({id:d.runId,cost:d.costUsd||0,cached:true});
        if(importLookup==="domain"){setReverseNext(d.nextPageToken);setReverseIncomplete(incomplete||!!d.nextPageToken);}
        else setScans([{id:advertiserId,name:d.ads[0]?.advertiser||advertiserId,next:d.nextPageToken,incomplete}]);
        if(!d.nextPageToken||stopRequested.current)break;
        if(seen.has(d.nextPageToken))throw Error("The imported page was repeated.");seen.add(d.nextPageToken);
        d=await request({...body,pageToken:d.nextPageToken});
      }
      setMessage(incomplete?"The existing run was imported, but source data remains incomplete.":`Used ${loaded.length} ads from an existing Apify run. No new scan was created; today's status has not been checked.`);
    }catch(e){setMessage((e as Error).message);}finally{setBusy("");}
  }
  function quick(value: string) {
    setRange(value);
    if (value === "all") return;
    const t = serverToday || today(); const d = new Date(t + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() - (value === "today" ? 0 : 29));
    setStart(d.toISOString().slice(0, 10)); setEnd(t);
  }
  function exportSavedCsv(){
    const rows=[["Type","Name or domain"],...saved.advertisers.map(value=>["Advertiser",value]),...saved.domains.map(value=>["Domain",value])];
    const blob=new Blob(["\uFEFF"+rows.map(row=>row.map(csvCell).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="Ultra-Check-saved.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function exportCsv() {
    const rows = [["Platform", "Domain", "Advertiser", "Advertiser ID", "Status", "First observed (source)", "Last observed (source)", "Ads downloaded", "Country filter", "Date filter from", "Date filter to", "Checked at", "Source", "Scope", "Domain extraction method", "Needs verification"]];
    for (const g of visible) rows.push([isBing?"Microsoft Bing":"Google",g.domain,g.advertiser,g.advertiserId,getStatus(g) === "today" ? "Observed today" : getStatus(g) === "unknown" ? "Not checked today" : "Previously observed; not observed today",g.first || "",g.last || "",String(g.ads.length),query?.region ? countryName(query.region) : isBing?"All EU/EEA countries":"All countries",query?.start || "All time",query?.end || "All time",checkedAt,g.ads[0].source,(isBing||reverseIncomplete || scans.some(s=>s.next||s.error||s.incomplete)) ? (isBing?"Bing text candidates; EU/EEA; placement unverified; not an exhaustive domain index":"Incomplete results") : "Ads returned by the source; some domains may be missing",g.ads.map(a=>a.method || "Unknown").filter((v,i,a)=>a.indexOf(v)===i).join("; "),"Yes; final destination after redirects is unverified"]);
    const blob = new Blob(["\uFEFF" + rows.map(r => r.map(csvCell).join(",")).join("\r\n")], { type:"text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href=url; a.download="Ultra-Check-domains.csv"; a.click(); setTimeout(()=> URL.revokeObjectURL(url),1000);
  }
  const scanRegion = query?.region ? countryName(query.region) : isBing?"All EU/EEA countries":"All countries";
  async function control(action: string) { if(action==="stop")stopRequested.current=true; await fetch("/api/"+action,{method:"POST",headers:{"Content-Type":"application/json","X-Ultra-Token":(window as any).ULTRA_TOKEN},body:"{}"}); if(action==="stop")stopRequested.current=true; if(action==="shutdown")setClosed(true); }
  if(closed) return <main><h1>Ultra Check has closed.</h1><p>You can close this tab. Open Ultra-Check.exe to use the application again.</p></main>;
  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Ultra Check home"><span className="brand-icon"><Zap size={23} fill="currentColor" /></span><span>Ultra Check<small>AD INTELLIGENCE</small></span></a>
      <div className="side-label">WORKSPACE</div>
      <button className={view==="search"?"nav-item active":"nav-item"} onClick={()=>setView("search")}><Search size={18}/>Domain lookup{view==="search"&&<span className="nav-dot"/>}</button>
      <button className={view==="saved"?"nav-item active":"nav-item"} onClick={()=>setView("saved")}><Layers size={18}/>Saved lists{view==="saved"&&<span className="nav-dot"/>}</button>
      <button aria-label="Apify API" className={view==="apify"?"nav-item api-nav active":"nav-item api-nav"} onClick={()=>{setView("apify");loadKeys();}}><KeyRound size={18}/><span>Apify API</span><UsageRing info={keyInfo}/></button>
      <button aria-label="Proxy-Cheap" className={view==="proxy"?"nav-item api-nav active":"nav-item api-nav"} onClick={()=>{setView("proxy");loadProxy();}}><Globe2 size={18}/><span>Proxy-Cheap</span><ProxyRing info={proxyInfo}/></button>
      <button className="nav-item" disabled={!!busy} onClick={()=>setModal(true)}><KeyRound size={18}/>Data source</button>
      <button className="nav-item" onClick={()=>{setView("search");setGuide(!guide);}}><ShieldCheck size={18}/>User guide</button>
      <div className="side-bottom"><span className="avatar">UC</span><div>Windows · local application<small>Ultra Check · v2.10</small></div></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div><span className="breadcrumb">Windows</span><span className="slash">/</span><strong>{view==="saved"?"Saved lists":view==="apify"?"Apify API":view==="proxy"?"Proxy-Cheap":"Domain explorer"}</strong></div><button className={ready ? "connection ready" : "connection"} disabled={!!busy} onClick={()=>setModal(true)}><span className="dot"/>{isBing?"Bing · public API":provider==="apify"?"Apify · Google Ads":provider==="proxy"?"Google · Proxy-Cheap":"Direct Google · no paid API"}<ChevronDown size={14}/></button></header>
      <main>
        <div hidden={view!=="search"}>
        <section className="intro"><div className="eyebrow"><span/>  {isBing?"BING · TEXT CANDIDATES":"GOOGLE SEARCH · TEXT"}</div><div className="intro-title"><div><h1>Discover ad domains</h1><p>{isBing?"Explore Bing Ad Library by advertiser or domain · EU/EEA coverage.":"Find Google Search text ads by advertiser or domain."}</p></div><span className="edition">ULTRA / 01</span></div></section>

        <div className="platform-choice panel"><label htmlFor="platform">Advertising platform</label><select id="platform" value={platform} disabled={!!busy} onChange={e=>changePlatform(e.target.value)}><option value="google">Google · Search / Text</option><option value="bing">Microsoft Bing · Text candidates</option></select></div>
        {isBing&&<section className="coverage bing-scope"><strong>Microsoft Ad Library · public API · no Apify charges</strong><p>{bingInfo?.scope||"EU/EEA impressions only. Search/Text placement cannot be verified from the public API. Dates are UTC and may lag 1–3 days."}</p><p>{lookup==="domain"?bingInfo?.domainScope:"Search by legal advertiser name or numeric Microsoft advertiser ID, then select a profile."}</p><p>One source page per click, with cached results and a 5-second minimum request interval. Use Load more to continue. No automatic proxy or paid fallback.</p></section>}
        {guide && !isBing && <section className="guide panel"><h2>How to use Ultra Check</h2><ol><li>Open Ultra-Check.exe. Direct Google access requires no API key.</li><li>Enter advertiser names, one per line. Match the name and AR ID before selecting a profile.</li><li>Select a country and date range, then click Find domains.</li><li>Click Check today to mark domains observed in today's ads.</li></ol><p>Up to 40 ads are loaded per source page. More pages are loaded automatically. Heavy use may trigger Google's limits; the application stops on restrictions. A missing green dot does not mean an ad has stopped. Google's platform filter excludes ads displayed before September 4, 2023.</p></section>}
        <section className="search-panel panel" id="search"><div className="panel-heading"><span className="section-icon"><SlidersHorizontal size={18}/></span><h2>Search settings</h2><span className="step-label">STEP 01</span></div>
          <div className="lookup-tabs"><button className={lookup==="advertiser"?"primary":"outline"} disabled={!!busy} onClick={()=>setLookup("advertiser")}>Advertiser → Domain</button><button className={lookup==="domain"?"primary":"outline"} disabled={!!busy} onClick={()=>setLookup("domain")}>Domain → Advertiser</button></div><div className="search-grid"><div className="names-field">{lookup==="domain" ? <><label htmlFor="website">Domain to search</label><input id="website" className="website-input" value={website} onChange={e=>setWebsite(e.target.value)} placeholder="Example: snapwidget.com" disabled={!!busy}/><p className="field-help">{isBing?"Find content-search candidates whose destination or displayed host matches this domain.":"Find advertisers whose Google ads point to this domain. Choose All time to include historical records."}</p></> : <><label htmlFor="names">Advertiser <span>Up to 10 names</span></label><textarea id="names" value={names} onChange={e=>setNames(e.target.value)} placeholder={"Enter advertiser names…\nOne per line"} disabled={!!busy} rows={4}/><p className="field-help">{isBing?"You can enter a numeric Microsoft advertiser ID for an exact profile lookup.":"You can enter an AR advertiser ID for an exact match."}</p></>}</div><div className="filters-field"><label htmlFor="region">Advertising market</label><div className="select-wrap"><Globe2 size={17}/><select id="region" value={region} onChange={e=>setRegion(e.target.value)} disabled={!!busy}><option value="">{isBing?"All EU/EEA countries":"All countries"}</option>{options.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</select></div><label className="date-label">Date range</label><div className="date-presets">{[["all","All time"],["today","Today"],["30","30 days"],["custom","Custom"]].map(([v,t])=><button key={v} className={range===v ? "selected" : ""} disabled={!!busy} onClick={()=>quick(v)}>{t}</button>)}</div>{range!=="all" && <div className="date-inputs"><label>From<input aria-label="From" type="date" value={start} max={serverToday} disabled={!!busy} onChange={e=>{setStart(e.target.value);if(range==="today")setEnd(e.target.value);}}/></label><span>→</span><label>To<input aria-label="To" type="date" value={end} min={start} max={serverToday} disabled={!!busy} onChange={e=>setEnd(e.target.value)}/></label></div>}<p className="field-help">{isBing?"Search dates use UTC. Recent impressions may appear after 1–3 days.":"Search dates use Google's time zone: US Pacific."}</p></div></div>
          <div className="search-footer"><label className="cache-choice"><input type="checkbox" checked={fresh} onChange={e=>setFresh(e.target.checked)} disabled={!!busy}/>  Refresh data (skip cache)</label><span><ShieldCheck size={15}/>{isBing?"One source page per click · text candidates":lookup==="domain"?"Loads all source pages · Search / Text only":"Select the correct advertiser profile before looking up domains"}</span><button className="primary" disabled={!!busy} onClick={()=>lookup==="domain"?reverseScan():discover()}>{busy ? <LoaderCircle size={17} className="spin"/> : <Search size={17}/>} {lookup==="domain"?"Find advertisers":"Find advertisers"}</button></div>
        </section>
        {message && <div className="message" role="alert">{message}<button aria-label="Dismiss message" onClick={()=>setMessage("")}><X size={16}/></button></div>}
        {!isBing && provider==="apify" && lastRun && <div className="coverage">{lastRun.cached?"Existing source run · historical reported cost":"Apify · reported cost of the latest run"}: {lastRun.cost.toFixed(5)}  USD (not the session total) {lastRun.cached?"· cached data, no new run created":""} · <a href={"https://console.apify.com/actors/runs/"+lastRun.id} target="_blank" rel="noreferrer">View run</a></div>}
        {!!busy && <div className="progress" role="status"><LoaderCircle size={16} className="spin"/>{busy}<button className="outline" onClick={()=>control("stop")}>Stop scan</button></div>}
        {!isBing&&<details className="panel import-panel run-history" onToggle={e=>{if(e.currentTarget.open)loadRunHistory();}}><summary>Apify run history · {runHistory.length}  saved run IDs</summary><p>Run IDs are saved locally as soon as Apify returns them, even if a run later fails or stops. Import again restores the exact domain/profile, country and dates, and reads only the existing run.</p>{runError&&<p className="error-text">{runError}</p>}{!runHistory.length&&<p>No runs saved yet. Run IDs still in older local caches are recovered automatically.</p>}<div className="history-list">{runHistory.slice((runPage-1)*10,runPage*10).map(item=><article key={item.id}><div><strong>{item.title}</strong><small>{new Date(item.createdAt).toLocaleString("en-US")} · {item.kind==="overview"?"Estimate":item.kind==="advertisers"?"Find profiles":"Ads"} · {item.status}</small><small>{item.query.region?labels[item.query.region]||(regions as Record<string,string>)[item.query.region]:"All countries"} · {item.query.start?displayDay(item.query.start)+" – "+displayDay(item.query.end):"All time"}{item.ads!=null?` · ${item.ads} ads`:""}</small><input aria-label={"Run ID "+item.id} readOnly value={item.id} onFocus={e=>e.target.select()}/></div><div className="history-actions"><button className="outline" onClick={()=>copyRun(item.id)}>Copy ID</button><a href={item.url} target="_blank" rel="noreferrer">View run ↗</a><button className="primary" disabled={!!busy||provider!=="apify"||!item.importable||["READY","RUNNING","ABORTING","TIMING-OUT"].includes(item.status)} onClick={()=>importExistingRun(item)}>Import again</button></div></article>)}</div><Pagination page={runPage} count={runHistory.length} onChange={setRunPage}/>{provider!=="apify"&&<p>Select Apify with an account that can access the run before importing. No new scan is created.</p>}</details>}
        {!isBing&&provider==="apify"&&<details className="panel import-panel"><summary>Use an existing Apify run · no new scan</summary><p>Import a run matching the selected domain/profile, country, dates and Search/Text filters. Only the existing dataset is read; no new Actor is started.</p><div className="lookup-tabs"><input aria-label="Existing Apify run ID" value={importRunId} onChange={e=>setImportRunId(e.target.value)} placeholder="Apify run ID" disabled={!!busy}/><button className="outline" disabled={!!busy} onClick={()=>importExistingRun()}>Import existing run</button></div></details>}
        {lookup==="advertiser" && !!discoveries.length && <section className="panel profiles"><div className="panel-heading"><span className="section-icon"><ShieldCheck size={18}/></span><h2>Select advertiser profiles</h2><span className="step-label">STEP 02</span></div><p className="muted">Similar names may represent different organizations. Check the source profile before selecting.</p>{discoveries.map(d=><div className="discovery" key={d.text}><div className="discovery-title">Results for “{d.text}”</div>{d.error && <p className="error-text">{d.error}</p>}{!d.error && !d.candidates.length && <p className="muted">No advertiser profile was returned. Try its legal name or the platform advertiser ID.</p>}<div className="candidate-grid">{d.candidates.map(c=><div className={selected.includes(c.id)?"candidate chosen":"candidate"} key={c.id}><label><input type="checkbox" disabled={!!busy} checked={selected.includes(c.id)} onChange={e=>setSelected(prev=> e.target.checked ? [...new Set([...prev,c.id])] : prev.filter(id=>id!==c.id))}/><span><strong>{c.name}</strong><small>{c.id}</small></span></label><a aria-label={`Open profile ${c.name}`} href={isBing?`https://adlibrary.ads.microsoft.com/?q=${encodeURIComponent(c.name)}`:`https://adstransparency.google.com/advertiser/${c.id}`} target="_blank" rel="noreferrer"><ArrowUpRight size={17}/></a></div>)}</div>{d.next && <button className="text-button" disabled={!!busy} onClick={()=>moreCandidates(d)}>Load more profiles for this name</button>}</div>)}<div className="profile-footer"><span>{selected.length}  profiles selected · up to 10 profiles per search</span><button className="primary" disabled={!!busy || !selected.length} onClick={scan}><Zap size={17}/>Domain lookup</button></div></section>}
        <section className="results" ref={resultsRef}>
          <div className="results-title"><div><h2>{query?.domain?"Advertisers for "+query.domain:"Recorded domains"} <span className="count">{query ? `${partialResults?"At least ":""}${groups.length}` : "—"}</span></h2><p>{query ? `${scanRegion} · ${query.start ? displayDay(query.start) + " — " + displayDay(query.end) : "All time"}` : "Results will appear here after a search."}</p></div><button className="outline" disabled={!visible.length || !!busy} onClick={exportCsv}><Download size={16}/>Export CSV</button></div>
          {query && <><div className="stats"><div><span>{query?.domain?"ADVERTISERS FOUND":"DOMAINS FOUND"}</span><strong>{partialResults?"≥ ":""}{groups.length.toString().padStart(2,"0")}</strong><small>{partialResults?"Not a total · source is incomplete":"In the downloaded source records"}</small></div><div><span><i className="green-dot"/>  OBSERVED TODAY</span><strong>{(isBing|| (query?.domain?reverseToday:Object.keys(current).length)) ? groups.filter(g=>getStatus(g)==="today").length.toString().padStart(2,"0") : "—"}</strong><small>{isBing?"Source last-observed date · UTC, delayed":"For the selected country"}</small></div><div><span>ADS DOWNLOADED</span><strong>{ads.length.toString().padStart(2,"0")}</strong><small>{missing.length}  ads without a domain</small></div></div><div className="results-controls"><div className="domain-search"><Search size={16}/><input aria-label="Filter domain or advertiser" placeholder="Filter domain or advertiser…" value={domainFilter} onChange={e=>setDomainFilter(e.target.value)}/></div><select aria-label="Filter status" value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="all">All statuses</option><option value="today">Observed today</option><option value="history">Previously observed</option><option value="unknown">Not checked today</option></select><button className="outline" disabled={isBing || !!busy || (!query?.domain && !scans.some(s=>!s.error))} onClick={()=>checkToday()}><span className="green-dot"/>Check today</button></div>{scans.filter(s=>s.error).map(s=><div className="message" key={s.id}>{s.name}: {s.error}<button className="text-button" disabled={!!busy} onClick={scan}>Retry search</button></div>)}{(reverseIncomplete || scans.some(s=>s.next||s.incomplete)) && <div className="coverage">Results are incomplete: a source limit was reached, pages remain, or domains could not be extracted. Downloaded ads are retained.</div>}</>}
          <div className="table-panel panel"><div className="table-scroll"><table><thead><tr><th>DOMAIN / ADVERTISER</th><th>STATUS</th><th>FIRST / LAST OBSERVED</th><th>ADS LOADED</th><th>SOURCE</th></tr></thead><tbody>{pageRows.map(g=><tr key={g.advertiserId+g.domain}><td><button className="domain-name" onClick={()=>setExpanded(expanded===g.advertiserId+g.domain ? "" : g.advertiserId+g.domain)}><span className="domain-symbol"><Globe2 size={17}/></span>{query?.domain?g.advertiser:g.domain}<ChevronDown size={14}/></button><small className="advertiser-name">{query?.domain?g.advertiserId:g.advertiser}</small><div className="row-actions"><button className="text-button" disabled={!savedReady||saving} onClick={()=>saveEntry("advertisers",g.advertiser)}>Save advertiser</button><button className="text-button" disabled={!savedReady||saving} onClick={()=>saveEntry("domains",g.domain)}>Save domain</button></div><small className="evidence-tag">{isBing?"Microsoft URL · text candidate · placement unverified":g.ads.some(a=>a.method==="ocr") ? "Read from image · verify manually" : g.ads.some(a=>a.method==="google-domain-match")?(provider==="apify"?"Domain matched by Apify":"Domain matched directly by Google"):"Ad display URL"}</small>{expanded===g.advertiserId+g.domain && <div className="ad-list">{g.ads.map(a=><a key={a.id} href={a.source} target="_blank" rel="noreferrer">{a.format} · {a.id}<ArrowUpRight size={12}/></a>)}<pre className="evidence-text">{g.ads[0].evidence || "No source text available"}</pre></div>}</td><td><span className={`status ${getStatus(g)}`}><i/>{getStatus(g)==="today" ? "Observed today" : getStatus(g)==="history" ? "Previously observed" : isBing?"Live status unavailable":"Not checked today"}</span></td><td><span className="date-cell">{dateText(g.first,isBing)}</span><small className="last-date">{dateText(g.last,isBing)}</small></td><td><span className="ad-count">{g.ads.length}</span></td><td><a className="source-link" href={g.ads[0].source} target="_blank" rel="noreferrer" aria-label={`View ads for ${g.domain}`}>{isBing?"Bing":"Google"} <ArrowUpRight size={14}/></a></td></tr>)}</tbody></table></div><Pagination page={page} count={visible.length} onChange={n=>{setResultPage(n);setExpanded("");}}/>{!visible.length && <div className="empty-state"><div className="empty-orbit"><Globe2 size={32}/><span className="orbit-dot"/></div><h3>{!query ? "Every domain tells a story." : busy ? "Loading results…" : groups.length ? "No domains match the filters" : "No domains recorded"}</h3><p>{!query ? "Start with an advertiser name to discover\nthe domains shown in its ads." : "The source may return no ads or no domains.\nAn empty result does not prove the advertiser has never advertised."}</p>{!query && <span className="empty-tag"><Layers size={13}/> {isBing?"BING · TEXT CANDIDATES":"GOOGLE SEARCH · TEXT"}</span>}</div>}</div>
          {scans.filter(s=>s.next).map(s=><div className="load-row" key={s.id}><span>More ads are available for: <strong>{s.name}</strong></span><button className="outline" disabled={!!busy} onClick={()=>more(s)}>{isBing?"Load more Bing ads":"Load up to 40 more ads"}</button></div>)}
          {Object.entries(current).filter(([,c])=>c.next).map(([id,c])=><div className="load-row" key={id}><span>Today's check is incomplete: {scans.find(s=>s.id===id)?.name}</span><button className="outline" disabled={!!busy} onClick={()=>checkToday(id,c.next)}>Load more results for today</button></div>)}
          {query?.domain && reverseIncomplete && !reverseNext && !ads.length && <div className="coverage">The first page could not be loaded. <button className="outline" disabled={!!busy} onClick={()=>reverseScan(true)}>Retry connection</button></div>}
          {query?.domain && reverseIncomplete && reverseNext && <div className="coverage">More source pages are available. <button className="outline" disabled={!!busy} onClick={()=>reverseScan(true)}>Continue loading advertisers</button></div>}
          {!!missing.length && <details className="missing panel"><summary>{missing.length}  ads have no public domain</summary><p className="muted">Open individual ad details to find missing domains. This sends additional requests to Google. Domains read from images need verification; displayed domains may differ from final redirect destinations.</p>{missing.map(a=><div className="missing-row" key={a.advertiserId+a.id}><span>{a.advertiser}<small>{a.id}</small></span><a href={a.source} target="_blank" rel="noreferrer">View source <ArrowUpRight size={13}/></a><button className="outline" disabled={!!busy} onClick={()=>enrich(a)}>Read domain</button></div>)}</details>}
          {isBing?<div className="legend"><p>Dates are the first/last eligible Bing impressions reported by Microsoft, in UTC. They may lag 1–3 days and do not confirm live campaign status. Text candidates exclude records with media assets; the public API does not identify Search/Text placement. Domain lookup is not exhaustive. A missing result is not proof that an advertiser never used a domain.</p>{checkedAt&&<small>Oldest fetch in the latest page: {new Date(checkedAt).toLocaleString("en-US")}.</small>}</div>:<div className="legend"><span><i className="green-dot"/>Green dot: the source returned ads for today (US Pacific).</span><p>This does not confirm campaigns are enabled at every moment. Previously observed does not mean stopped. First/last observed dates come from downloaded ads, not campaign start/end dates, and may fall outside the selected range. Results cover Google Search / Text only. Displayed or OCR domains may differ from final redirect destinations. Missing domains are never guessed.</p>{checkedAt && <small>Checked at {new Date(checkedAt).toLocaleString("en-US", { timeZone:"Asia/Bangkok" })}  (UTC+7). Today's check applies only to the date checked.</small>}</div>}
        </section>
        </div>
        <section className="panel saved-panel" id="saved" hidden={view!=="saved"}><h2>Saved lists</h2><p>Saved permanently on this Windows account, across restarts and app updates.</p><button className="outline" disabled={!savedReady||(!saved.advertisers.length&&!saved.domains.length)} onClick={exportSavedCsv}><Download size={16}/>Export saved CSV</button><p className="saved-location">Storage: {dataDirectory||"Windows application data"}</p><div className="saved-columns">{(["advertisers","domains"] as const).map(kind=><div key={kind}><h3>{kind==="advertisers"?"Advertiser":"Domain"}<span className="saved-count">{saved[kind].length}</span></h3><button className="outline" disabled={!savedReady||saving} onClick={()=>saveEntry(kind,kind==="advertisers"?names:website)}>Save {kind==="advertisers"?"current name":"current domain"}</button>{!saved[kind].length&&<p>The list is empty.</p>}<ul>{saved[kind].map(value=><li key={value}><button className="text-button" disabled={!!busy} onClick={()=>{if(kind==="advertisers"){setLookup("advertiser");setNames(value);}else{setLookup("domain");setWebsite(value);}setView("search");window.scrollTo({top:0,behavior:"smooth"});}}>{value}</button><button className="text-button" disabled={saving} aria-label={"Remove "+value} onClick={()=>saveEntry(kind,value,true)}>Remove</button></li>)}</ul></div>)}</div></section>
        <section className="panel api-page" hidden={view!=="apify"}><div className="api-heading"><div><h2>Apify API</h2><p>10 API slots · automatic quota failover · encrypted Windows storage.</p></div><button className="outline" disabled={keysBusy||!!busy} onClick={()=>manageKeys("refresh")}>{keysBusy?"Checking…":"Refresh usage"}</button></div><p className="api-note">Usage = current cycle spending / the account's USD limit. Keys on the same account share one quota. This is not the percentage of prepaid balance.</p>{(keysError||keyInfo?.error)&&<p className="message" role="alert">{keysError||keyInfo?.error}</p>}<div className="api-slots">{Array.from({length:10},(_,i)=>{const info=keyInfo?.slots?.[i];const status:Record<string,string>={empty:"No key saved",ready:"Ready",unknown:"Quota unknown",exhausted:"Quota / balance exhausted",unavailable:"Unavailable",invalid:"Invalid key"};return <article className={info?.active?"api-slot is-active":"api-slot"} key={i}><div className="api-slot-heading"><h3>API {i+1}</h3><span>{info?.active?"Active":status[info?.state||"empty"]}</span></div><label htmlFor={"api-slot-"+i}>API key</label><input id={"api-slot-"+i} type="password" autoComplete="off" placeholder={info?.saved?"Saved "+info.hint+" · leave blank to keep":"apify_api_…"} value={keyDrafts[i]} disabled={keysBusy||!!busy||clearKeys[i]} onChange={e=>setKeyDrafts(prev=>prev.map((v,j)=>j===i?e.target.value:v))}/>{info?.saved&&<label className="api-delete"><input type="checkbox" checked={clearKeys[i]} disabled={keysBusy||!!busy} onChange={e=>setClearKeys(prev=>prev.map((v,j)=>j===i?e.target.checked:v))}/>Remove this key when saving</label>}<div className="api-percent"><span>Used <b>{info?.usedPercent==null?"—":info.usedPercent.toFixed(1)+"%"}</b></span><span>Remaining <b>{info?.remainingPercent==null?"—":info.remainingPercent.toFixed(1)+"%"}</b></span></div><progress max={100} value={info?.usedPercent??undefined} aria-label={"API usage "+(i+1)}/><p>{info?.usedUsd!=null&&info?.limitUsd!=null?`${info.usedUsd.toFixed(4)} / ${info.limitUsd.toFixed(2)} USD`:"No quota data available"}</p>{info?.cycle?.endAt&&<small>Cycle ends: {new Date(info.cycle.endAt).toLocaleDateString("en-US")}</small>}{info?.sharedWith&&<p className="api-shared">Shares account with slot {info.sharedWith}</p>}{info?.stale&&info?.saved&&<small>Saved usage snapshot. Click Refresh to update it.</small>}{info?.message&&<small>{info.message}</small>}</article>;})}</div><div className="api-actions"><button className="primary" disabled={keysBusy||!!busy||!!keyInfo?.error} onClick={()=>manageKeys("save")}>{keysBusy?"Saving…":"Save & use Apify"}</button><span>Blank slots keep their saved keys. Select Remove to delete a key.</span></div><p className="api-note">Keys are encrypted for the current Windows account and restored on launch. Enter them again on another machine or Windows account. Failover happens only before a new run; network errors, CAPTCHA or rate limits never recreate an accepted run.</p></section>
        <section className="panel api-page proxy-page" hidden={view!=="proxy"}>
          <div className="api-heading"><div><h2>Proxy-Cheap <span className="proxy-badge">OPTIONAL</span></h2><p>Google via HTTP proxy · one fixed session per search.</p></div><span className="proxy-state">{provider==="proxy"?"Enabled":"Disabled"}</span></div>
          <div className="proxy-meter"><ProxyRing info={proxyInfo} large/><div><h3>Estimated data usage</h3><strong>{(proxyInfo?.usedPercent??0).toFixed(2)}% used</strong><p>{proxySize(proxyInfo?.usedBytes)} / {proxySize(proxyInfo?.totalBytes??5e9)}  · remaining {proxySize(proxyInfo?.remainingBytes??5e9)}</p><small>Measured by Ultra Check: {proxySize(proxyInfo?.measuredBytes)} · {proxyInfo?.requests??0}  requests</small></div></div>
          <p className="api-note">The estimate adds your starting baseline to data sent and received by Ultra Check. It is not synchronized with Proxy-Cheap billing and does not include all connection overhead. Cached results do not add proxy traffic.</p>
          <div className="proxy-fields">
            <label>Hostname<input id="proxy-host" autoComplete="off" value={proxyDraft.host} disabled={proxyBusy||!!busy} onChange={e=>setProxyDraft({...proxyDraft,host:e.target.value})}/></label>
            <label>HTTP port<input id="proxy-port" type="number" min={1} max={65535} value={proxyDraft.port} disabled={proxyBusy||!!busy} onChange={e=>setProxyDraft({...proxyDraft,port:Number(e.target.value)})}/></label>
            <label>Proxy username<input id="proxy-user" autoComplete="off" value={proxyDraft.username} disabled={proxyBusy||!!busy} onChange={e=>setProxyDraft({...proxyDraft,username:e.target.value})}/></label>
            <label>Base password<input id="proxy-password" type="password" autoComplete="new-password" value={proxyDraft.password} placeholder={proxyInfo?.saved?"Saved · leave blank to keep":"Enter proxy password"} disabled={proxyBusy||!!busy} onChange={e=>setProxyDraft({...proxyDraft,password:e.target.value})}/></label>
            <label>Plan allowance (GB)<input id="proxy-total" type="number" min={0.001} step="any" value={proxyDraft.totalGb} disabled={proxyBusy||!!busy} onChange={e=>setProxyDraft({...proxyDraft,totalGb:Number(e.target.value)})}/></label>
            <label>Proxy-Cheap usage baseline (MB)<input id="proxy-baseline" type="number" min={0} step="any" value={proxyDraft.baselineMb} disabled={proxyBusy||!!busy} onChange={e=>setProxyDraft({...proxyDraft,baselineMb:Number(e.target.value)})}/></label>
          </div>
          <p className="api-note">Enter the base password without a session/TTL suffix. Ultra Check creates a 10-minute sticky session. Use your Proxy-Cheap dashboard's current usage as the baseline. Set new baseline resets the local meter when you synchronize usage or change plans.</p>
          {(proxyError||proxyInfo?.error)&&<p className="message" role="alert">{proxyError||proxyInfo.error}</p>}{proxyNotice&&<p className="proxy-notice" role="status">{proxyNotice}</p>}
          <div className="api-actions"><button className="primary" disabled={proxyBusy||connecting||!!busy||!!proxyInfo?.error} onClick={()=>saveProxy(true)}>{proxyBusy?"Saving…":"Save & use proxy"}</button><button className="outline" disabled={proxyBusy||connecting||!!busy||!!proxyInfo?.error} onClick={()=>saveProxy(provider==="proxy")}>Save settings</button><button className="outline" disabled={proxyBusy||!!busy||!!proxyInfo?.error} onClick={()=>saveProxy(provider==="proxy",true)}>Set new baseline</button>{provider==="proxy"&&<button className="text-button" disabled={proxyBusy||connecting||!!busy} onClick={()=>configureProvider("direct")}>Disable proxy</button>}</div>
          <p className="api-note">Settings are encrypted for your Windows account and restored on launch. The proxy applies only to Ultra Check. Connection errors are retried within limits; downloaded pages are kept. Google restrictions or CAPTCHA stop the session. No automatic paid Apify fallback.</p>
        </section>
        <footer className="footer"><span>ULTRA CHECK <b>© 2026</b> · {isBing?"Microsoft Bing":provider==="apify"?"Apify":provider==="proxy"?"Proxy-Cheap":"Direct Google"}</span><a href={isBing?"https://adlibrary.ads.microsoft.com/":"https://adstransparency.google.com/"} target="_blank" rel="noreferrer">{isBing?"Public Microsoft data":"Public Google data"} <ArrowUpRight size={12}/></a><button className="text-button" onClick={()=>control("shutdown")}>Exit Ultra Check</button></footer>
      </main>
    </div>
    {modal && <div className="modal-backdrop" onClick={()=>setModal(false)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="connect-title" onClick={e=>e.stopPropagation()}><button className="modal-close" aria-label="Close" onClick={()=>setModal(false)}><X size={20}/></button><span className="modal-icon"><Globe2 size={25}/></span><div className="eyebrow">ULTRA CHECK WINDOWS</div><h2 id="connect-title">Data source</h2><p>Bing uses Microsoft’s public API directly, without Apify or Proxy-Cheap. The settings below apply only to Google.</p><p>Google Search / Text filters are fixed. Choose direct Google access, Proxy-Cheap, or Apify.</p><div className="provider-form"><label htmlFor="apify-key">Apify API key</label><input id="apify-key" type="password" autoComplete="off" value={keyDraft} onChange={e=>setKeyDraft(e.target.value)} placeholder="apify_api_…" disabled={connecting}/><p>Keys are encrypted on Windows. Manage all 10 slots and usage in Apify API.</p><div className="provider-limits"><label>USD limit per run<input type="number" min={0.01} max={100} step={0.01} value={maxCharge} onChange={e=>setMaxCharge(Number(e.target.value))}/></label></div><p>Apify charges per run. A domain lookup can include history and a separate check for today; each advertiser may require a separate run. Refreshing data creates new runs. Up to 100,000 ads may be requested, always within your USD limit per run. If the limit is reached, results are marked incomplete.</p>{providerError&&<p role="alert" className="error-text">{providerError}</p>}<div className="lookup-tabs"><button className="primary" disabled={connecting||!!busy} onClick={()=>configureProvider("apify")}>{connecting?"Connecting…":"Connect Apify"}</button><button className="outline" disabled={connecting||!!busy} onClick={()=>configureProvider("direct")}>Use Google directly</button><button className="outline" disabled={connecting||!!busy} onClick={()=>{setModal(false);setView("proxy");loadProxy(true);}}>Configure Proxy-Cheap</button></div><small>Actor: solidfetch/google-ads-transparency-scraper · tested build 0.7.41.</small></div><p>Source: Google Ads Transparency Center. Filters are fixed to Google Search / Text. Direct access needs no API; Apify uses your key and run budget.</p><ol><li>Up to 40 ads are loaded per source page. Use Load more to retrieve additional records.</li><li>Domains come from the ad's displayed URL or image. OCR can be inaccurate; check the source.</li><li>Google may restrict access. The application stops and reports the error instead of treating it as an empty result.</li><li>Data is stored in your Windows account's application data folder. Apify history is cached for 24 hours, today's data for 10 minutes, and images for 7 days. Use Refresh data to update sooner.</li><li>Use Refresh data to update results. The displayed timestamp is the original fetch time, including cached results.</li></ol><p className="secret-note">Closing the browser does not stop the application. Use Exit Ultra Check at the bottom of the page to shut it down.</p><button className="primary" onClick={()=>setModal(false)}>Start searching</button></section></div>}
  </div>;
}

import {createRoot} from "react-dom/client"; createRoot(document.getElementById("root")!).render(<UltraCheck/>);
