/* ── Telegram WebApp init ─────────────────────────────────────── */
const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const INIT_DATA = tg?.initData || "";

/* ── State ────────────────────────────────────────────────────── */
const STATUSES = ["Diterima", "Diproses", "Siap", "Selesai", "Dibatalkan"];
const NEXT_STATUS = { Diterima: "Diproses", Diproses: "Siap", Siap: "Selesai" };
const NEXT_LABEL = { Diproses: "👨‍🍳 Mulai Masak", Siap: "🎉 Tandai Siap", Selesai: "✅ Tandai Selesai" };
const CANCEL_REASONS = ["Stok habis", "Request customer", "Kesalahan input", "Lainnya"];
const STALE_MS = 15 * 60 * 1000;

let orders = {};          // { order_id: order }
let currentDetailId = null;

/* ── Helpers ──────────────────────────────────────────────────── */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", "X-Init-Data": INIT_DATA },
    ...opts,
  });
  return res.json();
}

const riel = n => `${Number(n).toLocaleString("km-KH")}៛`;
const escapeHtml = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const TERMINAL_STATUSES = new Set(["Selesai", "Dibatalkan"]);

function itemSummary(items) {
  return (items || [])
    .map(i => `${escapeHtml(i.item_name)} × ${i.qty} — ${riel(i.unit_price * i.qty)}`)
    .join("<br>");
}

function minutesSince(isoLikeUtc) {
  // Kolom TEXT SQLite datetime('now') formatnya "YYYY-MM-DD HH:MM:SS", UTC
  const ts = Date.parse(isoLikeUtc.replace(" ", "T") + "Z");
  if (Number.isNaN(ts)) return 0;
  return Math.floor((Date.now() - ts) / 60000);
}

/* ── Bootstrap ────────────────────────────────────────────────── */
async function boot() {
  const result = await api("/api/orders/active");
  if (!result.ok) {
    document.getElementById("forbidden").classList.remove("hidden");
    return;
  }
  document.getElementById("board-wrap").classList.remove("hidden");
  for (const o of result.orders) orders[o.id] = o;
  renderBoard();
  connectWS();
  setInterval(renderBoard, 30000); // refresh badge timer tiap 30 detik
}

/* ── Render board ─────────────────────────────────────────────── */
function renderBoard() {
  const byStatus = { Diterima: [], Diproses: [], Siap: [], Selesai: [], Dibatalkan: [] };
  for (const o of Object.values(orders)) {
    if (byStatus[o.status]) byStatus[o.status].push(o);
  }

  for (const status of STATUSES) {
    const list = byStatus[status].sort((a, b) => a.created_at.localeCompare(b.created_at));
    document.getElementById(`count-${status}`).textContent = list.length;
    document.getElementById(`tab-count-${status}`).textContent = list.length;
    document.getElementById(`col-${status}`).innerHTML = list.length
      ? list.map(cardHtml).join("")
      : `<div class="column-empty">Belum ada order</div>`;
  }

  // Klik di-handle via event delegation (#board), lihat listener di bawah —
  // ga perlu attach per-card/per-tombol di sini lagi.
}

function chatLinkFor(o) {
  if (o.user_id) return `tg://user?id=${o.user_id}`;
  if (o.username) return `https://t.me/${o.username}`;
  return null;
}

function cardHtml(o) {
  const mins = minutesSince(o.status_changed_at);
  const stale = !TERMINAL_STATUSES.has(o.status) && mins > 15;
  const payChip = o.payment_status === "PAID"
    ? `<span class="pay-chip paid">Lunas</span>`
    : `<span class="pay-chip unpaid">Belum Bayar</span>`;
  const name = escapeHtml(o.full_name || o.username || o.user_id);
  const chatLink = chatLinkFor(o);
  const chatBtn = chatLink
    ? `<button class="icon-btn-sm btn-chat" data-link="${escapeHtml(chatLink)}" title="Chat pelanggan">💬</button>`
    : `<button class="icon-btn-sm btn-chat" disabled title="Chat tidak tersedia">💬</button>`;
  return `
    <div class="card ${stale ? "stale" : ""}" data-id="${o.id}">
      <div class="card-top">
        <span class="card-name">#${o.id} ${name}</span>
        ${chatBtn}
        ${payChip}
      </div>
      <div class="card-summary">${itemSummary(o.items)}</div>
      ${stale ? `<span class="card-timer">⏱ ${mins} menit</span>` : ""}
    </div>`;
}

/* ── Klik kanban: event delegation (1 listener permanen, board tidak
   pernah di-replace innerHTML-nya — cuma isi kolom di dalamnya) ─────── */
document.getElementById("board").addEventListener("click", e => {
  const chatBtn = e.target.closest(".btn-chat");
  if (chatBtn) {
    if (!chatBtn.disabled && chatBtn.dataset.link) {
      window.open(chatBtn.dataset.link, "_blank");
    }
    return; // baik enabled maupun disabled, jangan lanjut ke openDetail
  }
  const card = e.target.closest(".card");
  if (card) openDetail(parseInt(card.dataset.id));
});

/* ── Tab status: quick-jump + scroll-spy ───────────────────────── */
document.getElementById("status-tabs").addEventListener("click", e => {
  const tab = e.target.closest(".status-tab");
  if (!tab) return;
  document.querySelector(`.column[data-status="${tab.dataset.status}"]`)
    ?.scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
});

document.getElementById("board").addEventListener("scroll", () => {
  const board = document.getElementById("board");
  const cols = board.querySelectorAll(".column");
  let current = cols[0];
  for (const col of cols) {
    if (col.offsetLeft - board.scrollLeft <= 40) current = col;
  }
  if (!current) return;
  document.querySelectorAll(".status-tab").forEach(t =>
    t.classList.toggle("active", t.dataset.status === current.dataset.status));
}, { passive: true });

/* ── Detail panel ─────────────────────────────────────────────── */
function openDetail(id) {
  currentDetailId = id;
  renderDetail();
  document.getElementById("detail-overlay").classList.remove("hidden");
}

function closeDetail() {
  currentDetailId = null;
  document.getElementById("detail-overlay").classList.add("hidden");
}

function renderDetail() {
  const o = orders[currentDetailId];
  if (!o) { closeDetail(); return; }

  document.getElementById("detail-title").textContent = `Order #${o.id}`;

  const itemsHtml = (o.items || []).map(i => `
    <div class="detail-item-row">
      <span>${escapeHtml(i.item_name)} × ${i.qty}</span>
      <span>${riel(i.unit_price * i.qty)}</span>
    </div>
    ${i.item_note ? `<div class="detail-item-note">📝 ${escapeHtml(i.item_note)}</div>` : ""}
  `).join("");

  const payHtml = o.payment_status === "PAID"
    ? `<div class="detail-row green"><span>Pembayaran</span><span>Lunas (${o.paid_currency || ""})</span></div>`
    : `<div class="detail-row red"><span>Pembayaran</span><span>Belum Bayar</span></div>`;

  const methodLabel = o.payment_method === "ABA" ? "🏦 ABA" : "💵 CASH";
  const reasonHtml = o.status === "Dibatalkan" && o.cancel_reason
    ? `<div class="detail-row"><span>Alasan Cancel</span><span>${escapeHtml(o.cancel_reason)}</span></div>` : "";

  const nextStatus = NEXT_STATUS[o.status];
  const actionButtons = [];
  if (nextStatus) {
    actionButtons.push(`<button class="btn-action" id="btn-next-status">${NEXT_LABEL[nextStatus]}</button>`);
  }
  if (o.payment_status === "UNPAID" && o.status !== "Dibatalkan") {
    actionButtons.push(`<button class="btn-action secondary" id="btn-mark-paid">💵 Tandai Lunas</button>`);
  }
  if (o.status !== "Dibatalkan") {
    actionButtons.push(`<button class="btn-action danger" id="btn-force-cancel">🚫 Force Cancel</button>`);
  }

  document.getElementById("detail-body").innerHTML = `
    <div class="detail-row"><span>Customer</span><span>${escapeHtml(o.full_name || o.username || o.user_id)}</span></div>
    <div class="detail-row"><span>Metode Bayar</span><span>${methodLabel}</span></div>
    ${payHtml}
    ${reasonHtml}
    ${o.note ? `<div class="detail-note">📝 ${escapeHtml(o.note)}</div>` : ""}
    <div class="detail-items">${itemsHtml}</div>
    <div class="detail-row detail-total"><span>Total</span><span>${riel(o.total)}</span></div>
    <div class="action-row">${actionButtons.join("")}</div>
  `;

  document.getElementById("btn-next-status")?.addEventListener("click", async () => {
    const r = await api(`/api/owner/orders/${o.id}/status`, {
      method: "POST",
      body: JSON.stringify({ status: nextStatus }),
    });
    if (!r.ok) tg?.showAlert?.(r.error || "Gagal update status.");
  });

  document.getElementById("btn-mark-paid")?.addEventListener("click", async () => {
    const r = await api(`/api/owner/orders/${o.id}/pay`, {
      method: "POST",
      body: JSON.stringify({ currency: "RIEL" }),
    });
    if (!r.ok) tg?.showAlert?.(r.error || "Gagal tandai lunas.");
  });

  document.getElementById("btn-force-cancel")?.addEventListener("click", () => renderCancelReasons(o));
}

function renderCancelReasons(o) {
  const warning = o.payment_status === "PAID"
    ? `<div class="detail-warning">⚠️ Order ini sudah dibayar (uang masuk). Kalau tetap dibatalkan, perlu refund manual ke customer.</div>`
    : "";
  document.getElementById("detail-body").innerHTML = `
    <div class="detail-note">Pilih alasan cancel Order #${o.id}:</div>
    ${warning}
    <div class="reason-list">
      ${CANCEL_REASONS.map(r => `<button class="btn-reason" data-reason="${r}">${r}</button>`).join("")}
      <button class="btn-action secondary" id="btn-cancel-back">« Batal</button>
    </div>
  `;
  document.querySelectorAll(".btn-reason").forEach(btn => {
    btn.addEventListener("click", async () => {
      const r = await api(`/api/owner/orders/${o.id}/force-cancel`, {
        method: "POST",
        body: JSON.stringify({ reason: btn.dataset.reason }),
      });
      if (r.ok) closeDetail();
      else tg?.showAlert?.(r.error || "Gagal force-cancel.");
    });
  });
  document.getElementById("btn-cancel-back")?.addEventListener("click", renderDetail);
}

document.getElementById("btn-detail-close").addEventListener("click", closeDetail);
document.getElementById("detail-overlay").addEventListener("click", e => {
  if (e.target.id === "detail-overlay") closeDetail();
});

/* ── WebSocket realtime ───────────────────────────────────────── */
let ws = null;

function connectWS() {
  const proto = location.protocol === "https:" ? "wss://" : "ws://";
  const url = `${proto}${location.host}/ws/admin?initData=${encodeURIComponent(INIT_DATA)}`;
  ws = new WebSocket(url);

  ws.onopen = () => setWsStatus(true);
  ws.onclose = () => { setWsStatus(false); setTimeout(connectWS, 3000); };
  ws.onerror = () => ws.close();

  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "order_update" && msg.order) {
      const isNew = !orders[msg.order.id];
      orders[msg.order.id] = msg.order;
      renderBoard();
      if (currentDetailId === msg.order.id) renderDetail();
      if (isNew) {
        tg?.HapticFeedback?.notificationOccurred("success");
        flashNewCard(msg.order.id);
      }
    }
  };
}

function flashNewCard(id) {
  const el = document.querySelector(`.card[data-id="${id}"]`);
  if (!el) return;
  el.classList.add("card-new");
  setTimeout(() => el.classList.remove("card-new"), 2000);
}

function setWsStatus(online) {
  const el = document.getElementById("ws-status");
  el.textContent = online ? "● online" : "● offline";
  el.className = `ws-status ${online ? "online" : "offline"}`;
}

boot();
