// Runs in the page's own context on adstransparency.google.com, before the site's
// scripts. It only remembers the request token the site itself attaches to its
// own requests, so Ultra Check's lookups carry the same token. Nothing is sent
// anywhere by this file.
(() => {
  if (window.__ultraCheckXsrfHook) return;
  Object.defineProperty(window, "__ultraCheckXsrfHook", { value: true });
  let token = "";
  Object.defineProperty(window, "__ultraCheckXsrf", { get: () => token });
  const NAME = "x-framework-xsrf-token";
  function note(name, value) {
    if (String(name || "").toLowerCase() === NAME && typeof value === "string" && value && value.length < 500) token = value;
  }
  function noteAll(headers) {
    try {
      if (!headers) return;
      if (headers instanceof Headers) { note(NAME, headers.get(NAME)); return; }
      const pairs = Array.isArray(headers) ? headers : Object.entries(headers);
      for (const [name, value] of pairs) note(name, value);
    } catch { /* ignore unusual header shapes */ }
  }
  const setHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    note(name, value);
    return setHeader.apply(this, arguments);
  };
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    if (input && typeof input === "object" && input.headers) noteAll(input.headers);
    if (init && init.headers) noteAll(init.headers);
    return originalFetch.apply(this, arguments);
  };
})();
