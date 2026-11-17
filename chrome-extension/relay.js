// Runs on the local Ultra Check page (http://127.0.0.1:<port>) and relays
// requests from the page to the extension's background worker.
(() => {
  function reply(message) { window.postMessage({ ...message, source: "ultra-check-bridge" }, location.origin); }
  window.addEventListener("message", event => {
    if (event.source !== window || event.origin !== location.origin) return;
    const m = event.data;
    if (!m || m.source !== "ultra-check-page" || typeof m.id !== "string") return;
    try {
      if (m.type === "PING") { reply({ type: "PONG", id: m.id, version: chrome.runtime.getManifest().version }); return; }
      if (m.type !== "RPC") return;
      chrome.runtime.sendMessage({ type: "RPC", method: m.method, body: m.body }).then(
        result => reply({ type: "RPC_RESULT", id: m.id, result: result || { status: 0, error: "Empty answer from the extension." } }),
        error => reply({ type: "RPC_RESULT", id: m.id, result: { status: 0, error: String(error && error.message || error) } })
      );
    } catch (error) {
      // Extension was reloaded or removed: this page needs a refresh to reconnect.
      if (m.type === "RPC") reply({ type: "RPC_RESULT", id: m.id, result: { status: 0, error: "Extension reloaded. Refresh the Ultra Check page." } });
    }
  });
})();
