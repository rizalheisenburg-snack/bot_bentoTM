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
