// Ultra Check Bridge: runs public Google Ads Transparency RPCs inside the user's
// own adstransparency.google.com tab, so they use the browser's normal session.
// It never solves or bypasses verification: when Google asks for it, the tab is
// brought to the front for the user and the request is reported as blocked.
const GOOGLE = "https://adstransparency.google.com";
const METHODS = new Set(["SearchService/SearchCreatives", "SearchService/SearchSuggestions", "LookupService/GetCreativeById", "FETCH"]);
// Ad preview files (images and preview scripts) shown by the Transparency Center.
const PREVIEW_HOSTS = new Set(["displayads-formats.googleusercontent.com", "tpc.googlesyndication.com"]);
const STEP_TIMEOUT = 20000;   // one request inside the Google tab
const LOAD_TIMEOUT = 20000;   // the Google tab loading or reloading
const POLL = 400;
let currentTabId = null;      // the tab used last; lost if the worker restarts, which is fine

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "RPC") return;
  let from;
  try { from = new URL(sender.url || ""); } catch { from = null; }
  if (!from || from.protocol !== "http:" || from.hostname !== "127.0.0.1") { sendResponse({ status: 0, error: "Sender not allowed." }); return; }
  if (!METHODS.has(message.method) || typeof message.body !== "string" || message.body.length > 20000) { sendResponse({ status: 0, error: "Request not allowed." }); return; }
  const job = message.method === "FETCH" ? fetchPreview(message.body) : run(message.method, message.body);
  job.then(sendResponse, error => sendResponse({ status: 0, error: text(error) }));
  return true;
});

// Download one ad preview through the browser (base64), for reading the ad's domain.
async function fetchPreview(address) {
  let url;
  try { url = new URL(address); } catch { return { status: 0, error: "Invalid preview URL." }; }
  if (url.protocol !== "https:" || !PREVIEW_HOSTS.has(url.hostname)) return { status: 0, error: "Preview host not allowed." };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(url.href, { credentials: "omit", signal: controller.signal });
    if (response.status !== 200) return { status: response.status, url: response.url };
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length > 8000000) return { status: 0, error: "Preview too large." };
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return { status: 200, url: response.url, text: btoa(binary), encoding: "base64" };
  } catch (error) {
    return { status: 0, error: error && error.name === "AbortError" ? "Preview download timed out." : text(error) };
  } finally {
    clearTimeout(timer);
  }
}

const text = error => String(error && error.message || error);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function limit(promise, ms, what) {
  let timer;
  const expired = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(what + " did not respond within " + Math.round(ms / 1000) + " s")), ms); });
  return Promise.race([promise, expired]).finally(() => clearTimeout(timer));
}

// Browsers put background tabs to sleep (Edge sleeping tabs, Chrome Memory Saver).
// A sleeping tab never runs the request, so each attempt escalates:
// 0 = reuse the tab, 1 = reload it, 2 = open a fresh tab.
async function run(method, body) {
  let lastError = "";
  for (let attempt = 0; attempt < 3; attempt++) {
    let tab;
    try { tab = await googleTab(attempt); }
    catch (error) { lastError = text(error); continue; }
    if (tab.blocked) return { status: 429, blocked: true };
    try {
      const frames = await limit(
        chrome.scripting.executeScript({ target: { tabId: tab.id }, world: "MAIN", func: pageRpc, args: [method, body] }),
        STEP_TIMEOUT, "The Google tab");
      const result = frames && frames[0] && frames[0].result;
      if (!result) { lastError = "No result from the Google tab."; continue; }
      if (result.blocked || result.status === 429 || result.status === 403) { await focus(tab.id); return result; }
      if (result.status === 0 && attempt < 2) { lastError = result.error || "Network error in the Google tab."; continue; }
      return attempt ? { ...result, recovered: attempt } : result;
    } catch (error) {
      lastError = text(error);
    }
  }
  return { status: 0, error: lastError + " (also after reloading the Google tab and opening a new one)" };
}

// In-page function: same-origin request from the Google tab itself.
// A signed-in Google session requires the page's own request token (captured by
// xsrf-hook.js). If the signed-in request is still rejected, the same request is
// sent once without cookies, which Google accepts like a signed-out visitor.
async function pageRpc(method, body) {
  async function send(withSession) {
    const headers = { "content-type": "application/x-www-form-urlencoded;charset=UTF-8", "x-same-domain": "1" };
    const token = withSession && window.__ultraCheckXsrf;
    if (token) headers["x-framework-xsrf-token"] = token;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 9000);
    try {
      const response = await fetch("/anji/_/rpc/" + method + "?authuser=0", {
        method: "POST", credentials: withSession ? "include" : "omit", redirect: "manual", headers, body, signal: controller.signal
      });
      if (response.type === "opaqueredirect") return { status: 429, blocked: true };
      const text = await response.text();
      if (text.length > 8000000) return { status: 0, error: "Response too large." };
      if (response.status !== 200) return { status: response.status, url: response.url, detail: text.slice(0, 300) };
      return { status: 200, url: response.url, text };
    } finally {
      clearTimeout(timer);
    }
  }
  try {
    const first = await send(true);
    if (first.status !== 400 && first.status !== 401) return first;
    const anonymous = await send(false);
    if (anonymous.status === 200 || anonymous.blocked) return { ...anonymous, transport: "anonymous" };
    return { ...first, anonymousStatus: anonymous.status };
  } catch (error) {
    const timedOut = error && error.name === "AbortError";
    return { status: 0, error: timedOut ? "Google did not answer within 9 s." : String(error && error.message || error) };
  }
}

async function googleTab(attempt) {
  if (attempt >= 2) return openTab();
  const tabs = await chrome.tabs.query({ url: GOOGLE + "/*" });
  const awake = t => !t.discarded && !t.frozen;
  const tab = tabs.find(t => t.id === currentTabId && awake(t))
    || tabs.find(t => awake(t) && t.status === "complete")
    || tabs.find(t => t.id === currentTabId)
    || tabs[0];
  if (!tab) return openTab();
  if (attempt === 1 || !awake(tab)) {
    await chrome.tabs.reload(tab.id);
    await sleep(800);           // let the reload start before waiting for "complete"
  }
  return prepare(tab.id);
}

async function openTab() {
  const created = await chrome.tabs.create({ url: GOOGLE + "/?region=anywhere", active: false });
  await sleep(300);
  return prepare(created.id);
}

async function prepare(tabId) {
  currentTabId = tabId;
  try { await chrome.tabs.update(tabId, { autoDiscardable: false }); } catch { /* older browsers */ }
  return settle(tabId);
}

// Wait for the tab to finish loading; if it left adstransparency.google.com
// (verification page), show it to the user instead of continuing.
async function settle(tabId) {
  for (let waited = 0; waited < LOAD_TIMEOUT; waited += POLL) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") {
      if ((tab.url || "").startsWith(GOOGLE + "/")) return { id: tabId };
      await focus(tabId);
      return { id: tabId, blocked: true };
    }
    await sleep(POLL);
  }
  throw new Error("The Google tab did not finish loading within " + Math.round(LOAD_TIMEOUT / 1000) + " s");
}

async function focus(tabId) {
  try {
    const tab = await chrome.tabs.update(tabId, { active: true });
    if (tab && tab.windowId !== undefined) await chrome.windows.update(tab.windowId, { focused: true });
  } catch { /* tab closed */ }
}
