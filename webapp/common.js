/* ── Shared antara index.html (app.js) dan admin.html (admin.js) ─────── */
const tg = window.Telegram?.WebApp;
tg?.ready();

const INIT_DATA = tg?.initData || "";

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", "X-Init-Data": INIT_DATA },
    ...opts,
  });
  return res.json();
}

const riel = n => `${Number(n).toLocaleString("km-KH")}៛`;
const escapeHtml = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/* Badge Express diturunkan dari delivery_type + timestamp, BUKAN kolom status baru
   (kitchen state machine di server tidak disentuh). Dipakai app.js (customer) & admin.js (kanban). */
function expressBadgeInfo(o) {
  if (o.delivery_type !== "express") return null;
  return o.location_received_at
    ? { cls: "waiting-courier",  text: "🚀 Express · Menunggu Booking Kurir" }
    : { cls: "waiting-location", text: "🚀 Express · Menunggu Lokasi" };
}
