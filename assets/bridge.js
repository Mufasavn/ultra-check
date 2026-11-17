// Ultra Check page <-> Ultra Check Bridge extension relay.
// The page long-polls the local server for Google RPC jobs and hands them to the
// extension, which runs them inside the user's own adstransparency.google.com tab.
(() => {
  const token = window.ULTRA_TOKEN;
  const waiters = new Map();
  let seq = 0;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  window.addEventListener("message", e => {
    if (e.source !== window || e.origin !== location.origin) return;
    const m = e.data;
    if (!m || m.source !== "ultra-check-bridge") return;
    const done = waiters.get(m.id);
    if (done) { waiters.delete(m.id); done(m); }
  });
  function ask(message, timeout) {
    return new Promise(resolve => {
      const id = "uc" + (++seq);
      const timer = setTimeout(() => { waiters.delete(id); resolve(null); }, timeout);
      waiters.set(id, m => { clearTimeout(timer); resolve(m); });
      window.postMessage({ ...message, source: "ultra-check-page", id }, location.origin);
    });
  }
  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Ultra-Token": token }, body: JSON.stringify(body) });
    if (!r.ok) throw Error("HTTP " + r.status);
    return r.json();
  }
  async function loop() {
    for (;;) {
      try {
        const pong = await ask({ type: "PING" }, 1500);
        if (!pong) { await sleep(5000); continue; }          // extension not installed in this browser
        const d = await post("/api/bridge/poll", { version: pong.version });
        if (!d.job) continue;
        const answer = await ask({ type: "RPC", method: d.job.method, body: d.job.body }, 40000);
        await post("/api/bridge/result", { id: d.job.id, result: answer ? answer.result : { status: 0, error: "The extension did not answer." } });
      } catch { await sleep(3000); }                          // not logged in yet, or server restarting
    }
  }
  loop();
})();
