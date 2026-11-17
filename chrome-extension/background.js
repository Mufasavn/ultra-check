// Ultra Check Bridge: runs public Google Ads Transparency RPCs inside the user's
// own adstransparency.google.com tab, so they use the browser's normal session.
// It never solves or bypasses verification: when Google asks for it, the tab is
// brought to the front for the user and the request is reported as blocked.
const GOOGLE = "https://adstransparency.google.com";
const METHODS = new Set(["SearchService/SearchCreatives", "SearchService/SearchSuggestions", "LookupService/GetCreativeById"]);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "RPC") return;
  let from;
  try { from = new URL(sender.url || ""); } catch { from = null; }
  if (!from || from.protocol !== "http:" || from.hostname !== "127.0.0.1") { sendResponse({ status: 0, error: "Sender not allowed." }); return; }
  if (!METHODS.has(message.method) || typeof message.body !== "string" || message.body.length > 20000) { sendResponse({ status: 0, error: "Request not allowed." }); return; }
  run(message.method, message.body).then(sendResponse, error => sendResponse({ status: 0, error: String(error && error.message || error) }));
  return true;
});

async function run(method, body) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const tab = await googleTab(attempt > 0);
    if (tab.blocked) return { status: 429, blocked: true };
    try {
      const [frame] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: "MAIN", func: pageRpc, args: [method, body] });
      const result = frame && frame.result || { status: 0, error: "No result from the Google tab." };
      if (result.blocked || result.status === 429 || result.status === 403) await focus(tab.id);
      return result;
    } catch (error) {
      if (attempt) return { status: 0, error: String(error && error.message || error) };
    }
  }
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
    const response = await fetch("/anji/_/rpc/" + method + "?authuser=0", {
      method: "POST", credentials: withSession ? "include" : "omit", redirect: "manual", headers, body
    });
    if (response.type === "opaqueredirect") return { status: 429, blocked: true };
    const text = await response.text();
    if (text.length > 8000000) return { status: 0, error: "Response too large." };
    if (response.status !== 200) return { status: response.status, url: response.url, detail: text.slice(0, 300) };
    return { status: 200, url: response.url, text };
  }
  try {
    const first = await send(true);
    if (first.status !== 400 && first.status !== 401) return first;
    const anonymous = await send(false);
    if (anonymous.status === 200 || anonymous.blocked) return { ...anonymous, transport: "anonymous" };
    return { ...first, anonymousStatus: anonymous.status };
  } catch (error) {
    return { status: 0, error: String(error && error.message || error) };
  }
}

async function googleTab(forceNew) {
  if (!forceNew) {
    const tabs = await chrome.tabs.query({ url: GOOGLE + "/*" });
    const ready = tabs.find(t => !t.discarded && t.status === "complete");
    if (ready) return { id: ready.id };
    const loading = tabs.find(t => !t.discarded);
    if (loading) return settle(loading.id);
  }
  const created = await chrome.tabs.create({ url: GOOGLE + "/?region=anywhere", active: false });
  return settle(created.id);
}

// Wait for the tab to finish loading; if it left adstransparency.google.com
// (verification page), show it to the user instead of continuing.
async function settle(tabId) {
  for (let i = 0; i < 60; i++) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") {
      if ((tab.url || "").startsWith(GOOGLE + "/")) return { id: tabId };
      await focus(tabId);
      return { id: tabId, blocked: true };
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error("The Google tab did not finish loading.");
}

async function focus(tabId) {
  try {
    const tab = await chrome.tabs.update(tabId, { active: true });
    if (tab && tab.windowId !== undefined) await chrome.windows.update(tab.windowId, { focused: true });
  } catch { /* tab closed */ }
}
