export const TIME_ZONE = "America/Los_Angeles";
export function today(now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
export function validDate(s) {
  return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().slice(0, 10) === s;
}
export function nextDate(s) {
  if (!validDate(s)) throw new Error("Ngày không hợp lệ.");
  const d = new Date(s + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}
export function normalizeDomain(input) {
  if (typeof input !== "string" || !input.trim()) return null;
  try {
    const u = new URL(/^https?:\/\//i.test(input.trim()) ? input.trim() : "https://" + input.trim());
    const host = u.hostname.toLowerCase().replace(/^www\./, "").replace(/\.$/, "");
    if (!["https:", "http:"].includes(u.protocol) || u.username || u.password || !host.includes(".") || /\s/.test(host)) return null;
    return host;
  } catch { return null; }
}
export function safeSource(input, advertiserId, creativeId) {
  try { const u = new URL(input); if (u.protocol === "https:" && u.hostname === "adstransparency.google.com") return u.href; } catch {}
  return `https://adstransparency.google.com/advertiser/${encodeURIComponent(advertiserId)}${creativeId ? "/creative/" + encodeURIComponent(creativeId) : ""}`;
}
export function timestamp(value) {
  if (typeof value === "number" && Number.isFinite(value) && value > 0 && value < 253402300800) return new Date(value * 1000).toISOString();
  return null;
}
export function normalizeAds(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.filter(a => /^AR\d+$/.test(a?.advertiser_id || "") && /^CR\d+$/.test(a?.ad_creative_id || "")).map(a => ({
    id: a.ad_creative_id, advertiserId: a.advertiser_id, advertiser: String(a.advertiser || a.advertiser_id).slice(0, 300),
    domain: normalizeDomain(a.target_domain), first: timestamp(a.first_shown), last: timestamp(a.last_shown),
    format: ["text", "image", "video"].includes(a.format) ? a.format : "unknown",
    source: safeSource(a.details_link, a.advertiser_id, a.ad_creative_id),
  }));
}
export function groupDomains(ads) {
  const map = new Map();
  for (const ad of ads) {
    if (!ad.domain) continue;
    const k = ad.advertiserId + ":" + ad.domain;
    if (!map.has(k)) map.set(k, { domain: ad.domain, advertiser: ad.advertiser, advertiserId: ad.advertiserId, ads: [], first: null, last: null });
    const g = map.get(k);
    if (g.ads.some(a => a.id === ad.id)) continue;
    g.ads.push(ad);
    if (ad.first && (!g.first || ad.first < g.first)) g.first = ad.first;
    if (ad.last && (!g.last || ad.last > g.last)) g.last = ad.last;
  }
  return [...map.values()].sort((a,b) => (b.last || "").localeCompare(a.last || "") || a.domain.localeCompare(b.domain));
}
export function csvCell(value) {
  const s = String(value ?? "");
  return '"' + (/^[=+@\-\t\r\n]/.test(s) ? "'" : "") + s.replaceAll('"', '""') + '"';
}
export function buildParams(input, regions) {
  const mode = input.mode;
  if (!["discover", "check", "current", "details"].includes(mode)) throw new Error("Loại tra cứu không hợp lệ.");
  const region = String(input.region || "");
  if (region && !Object.hasOwn(regions, region)) throw new Error("Quốc gia không được hỗ trợ.");
  const params = new URLSearchParams({ engine: mode === "details" ? "google_ads_transparency_center_ad_details" : "google_ads_transparency_center", no_cache: "true" });
  if (mode !== "details") params.set("num", "100");
  if (region) params.set("region", region);
  if (mode === "discover") {
    const text = String(input.text || "").trim();
    if (!text || text.length > 200) throw new Error("Nhập tên nhà quảng cáo (tối đa 200 ký tự).");
    params.set("text", text);
  } else {
    if (!/^AR\d{1,30}$/.test(input.advertiserId || "")) throw new Error("Mã nhà quảng cáo không hợp lệ.");
    params.set("advertiser_id", input.advertiserId);
  }
  if (mode === "details") {
    if (!/^CR\d{1,30}$/.test(input.creativeId || "")) throw new Error("Mã quảng cáo không hợp lệ.");
    params.set("creative_id", input.creativeId);
  } else if (mode === "current") {
    const date = today(); params.set("start_date", date.replaceAll("-", "")); params.set("end_date", nextDate(date).replaceAll("-", ""));
  } else if (mode === "check") {
    const { start, end } = input;
    if (start || end) {
      if (!validDate(start) || !validDate(end) || start > end || end > today()) throw new Error("Chọn khoảng ngày hợp lệ, không vượt quá hôm nay theo giờ Google.");
      params.set("start_date", start.replaceAll("-", "")); params.set("end_date", nextDate(end).replaceAll("-", ""));
    }
  }
  if (input.pageToken) {
    if (typeof input.pageToken !== "string" || input.pageToken.length > 3000) throw new Error("Trang tiếp theo không hợp lệ.");
    params.set("next_page_token", input.pageToken);
  }
  return params;
}
