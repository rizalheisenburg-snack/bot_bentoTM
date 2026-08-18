/* ── Telegram WebApp init ─────────────────────────────────────── */
/* tg, INIT_DATA, api(), riel(), escapeHtml() ada di common.js (di-load sebelum file ini) */
tg?.expand();

/* ── State ────────────────────────────────────────────────────── */
const STATUSES = ["Diterima", "Diproses", "Siap", "Selesai", "Dibatalkan"];
const NEXT_STATUS = { Diterima: "Diproses", Diproses: "Siap", Siap: "Selesai" };
const NEXT_LABEL = { Diproses: "👨‍🍳 Mulai Masak", Siap: "🎉 Tandai Siap", Selesai: "✅ Tandai Selesai" };
const CANCEL_REASONS = ["Stok habis", "Request customer", "Kesalahan input", "Lainnya"];
const STALE_MS = 15 * 60 * 1000;

let orders = {};          // { order_id: order }
let currentDetailId = null;

const TERMINAL_STATUSES = new Set(["Selesai", "Dibatalkan"]);

function modifierText(item) {
  if (!item.modifiers_json) return "";
  try {
    return JSON.parse(item.modifiers_json).map(m => m.option_name).join(", ");
  } catch {
    return "";
  }
}

function itemSummary(items) {
  return (items || [])
    .map(i => {
      const mods = modifierText(i);
      return `${escapeHtml(i.item_name)} × ${i.qty} — ${riel(i.unit_price * i.qty)}`
        + (mods ? `<br><small>· ${escapeHtml(mods)}</small>` : "");
    })
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

function cardHtml(o) {
  const mins = minutesSince(o.status_changed_at);
  const stale = !TERMINAL_STATUSES.has(o.status) && mins > 15;
  const payChip = o.payment_status === "PAID"
    ? `<span class="pay-chip paid">Lunas</span>`
    : `<span class="pay-chip unpaid">Belum Bayar</span>`;
  const badge = expressBadgeInfo(o);
  const expressChip = badge ? `<span class="express-chip ${badge.cls}">${badge.text}</span>` : "";
  const name = escapeHtml(o.full_name || o.username || o.user_id);
  // Kirim lewat bot (chat_id = o.user_id), bukan deep-link Telegram personal —
  // deep-link butuh akun admin udah "kenal" user itu (gak bisa dijamin),
  // sedangkan bot selalu bisa kirim ke siapa pun yang pernah /start.
  const chatBtn = `<button class="icon-btn-sm btn-chat" data-id="${o.id}" title="Chat pelanggan">💬</button>`;
  return `
    <div class="card ${stale ? "stale" : ""}" data-id="${o.id}">
      <div class="card-top">
        <span class="card-name">#${o.id} ${name}</span>
        ${chatBtn}
        ${payChip}
        ${expressChip}
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
    const id = parseInt(chatBtn.dataset.id);
    openDetail(id);
    renderChatCompose(orders[id]);
    return;
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
    ${modifierText(i) ? `<div class="detail-item-note">🧩 ${escapeHtml(modifierText(i))}</div>` : ""}
    ${i.item_note ? `<div class="detail-item-note">📝 ${escapeHtml(i.item_note)}</div>` : ""}
  `).join("");

  const payHtml = o.payment_status === "PAID"
    ? `<div class="detail-row green"><span>Pembayaran</span><span>Lunas (${o.paid_currency || ""})</span></div>`
    : `<div class="detail-row red"><span>Pembayaran</span><span>Belum Bayar</span></div>`;

  const methodLabel = o.payment_method === "ABA" ? "🏦 ABA" : "💵 CASH";
  const reasonHtml = o.status === "Dibatalkan" && o.cancel_reason
    ? `<div class="detail-row"><span>Alasan Cancel</span><span>${escapeHtml(o.cancel_reason)}</span></div>` : "";

  const expressBadge = expressBadgeInfo(o);
  const deliveryHtml = o.delivery_type === "express"
    ? `<div class="detail-row"><span>Kurir</span><span>${expressBadge.text}</span></div>
       ${(o.customer_lat != null && o.customer_lng != null)
          ? `<div class="detail-row"><span>Lokasi</span><a class="maps-link" href="https://maps.google.com/?q=${o.customer_lat},${o.customer_lng}" target="_blank" rel="noopener">📍 Buka Google Maps</a></div>`
          : `<div class="detail-row"><span>Lokasi</span><span class="hint">⏳ Belum dikirim</span></div>`}`
    : "";

  const nextStatus = NEXT_STATUS[o.status];
  const actionButtons = [];
  actionButtons.push(`<button class="btn-action secondary" id="btn-chat-open">💬 Chat Pelanggan</button>`);
  if (nextStatus) {
    actionButtons.push(`<button class="btn-action" id="btn-next-status">${NEXT_LABEL[nextStatus]}</button>`);
  }
  if (o.payment_status === "UNPAID" && o.status !== "Dibatalkan") {
    actionButtons.push(`<button class="btn-action secondary" id="btn-mark-paid">💵 Tandai Lunas</button>`);
  }
  if (o.status !== "Dibatalkan") {
    actionButtons.push(`<button class="btn-action danger" id="btn-force-cancel">🚫 Force Cancel</button>`);
  }
  // Fallback admin: dipakai kalau customer minta edit lewat chat manual.
  // Sama seperti tombol di app customer, ini cuma shortcut UI — backend tetap
  // final-check status/payment_status ulang saat Simpan (order_edit.edit_order).
  if (o.editable) {
    actionButtons.push(`<button class="btn-action secondary" id="btn-edit-order">✏️ Edit Order</button>`);
  }

  document.getElementById("detail-body").innerHTML = `
    <div class="detail-row"><span>Customer</span><span>${escapeHtml(o.full_name || o.username || o.user_id)}</span></div>
    ${o.address ? `<div class="detail-row"><span>Alamat</span><span>${escapeHtml(o.address)}</span></div>` : ""}
    <div class="detail-row"><span>Metode Bayar</span><span>${methodLabel}</span></div>
    ${payHtml}
    ${reasonHtml}
    ${deliveryHtml}
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
  document.getElementById("btn-chat-open")?.addEventListener("click", () => renderChatCompose(o));
  document.getElementById("btn-edit-order")?.addEventListener("click", () => renderEditOrder(o));
}

function renderChatCompose(o) {
  const name = escapeHtml(o.full_name || o.username || o.user_id);
  document.getElementById("detail-body").innerHTML = `
    <div class="detail-note">Kirim pesan ke ${name} lewat bot:</div>
    <textarea id="chat-text" class="chat-textarea" rows="4" placeholder="Tulis pesan..."></textarea>
    <div class="action-row">
      <button class="btn-action" id="btn-chat-send">📨 Kirim</button>
      <button class="btn-action secondary" id="btn-chat-back">« Batal</button>
    </div>
  `;
  document.getElementById("chat-text").focus();
  document.getElementById("btn-chat-send").addEventListener("click", async () => {
    const text = document.getElementById("chat-text").value.trim();
    if (!text) return;
    const r = await api(`/api/owner/orders/${o.id}/message`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    if (r.ok) {
      tg?.HapticFeedback?.notificationOccurred("success");
      closeDetail();
    } else {
      tg?.showAlert?.(r.error || "Gagal kirim pesan.");
    }
  });
  document.getElementById("btn-chat-back").addEventListener("click", renderDetail);
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

/* ── Edit Order (fallback admin) ─────────────────────────────────
   Dipakai kalau customer minta edit lewat chat manual. Beda dari app
   customer: TIDAK ada picker modifier di sini (biar gak perlu bangun ulang
   UI browsing-menu di kanban) — item BARU yang ditambah admin harus item
   plain (tanpa varian). Item lama yang punya varian dibawa sebagai
   "carry-over" (cuma qty yang bisa diubah), sama seperti di app customer,
   karena group_id/option_id aslinya memang tidak disimpan lagi setelah
   checkout (lihat komentar di order_edit.py). */
let menuFlat = null;   // [{id, name, price, category, available, has_modifiers}], fetch sekali
let editCart = {};     // { key: {name, unitPrice, qty, carryOverId?, itemId?, modifiersLabel?} }

async function _ensureMenuLoaded() {
  if (menuFlat) return menuFlat;
  const result = await api("/api/menu");
  menuFlat = Object.values(result.categories || {}).flat();
  return menuFlat;
}

function _editCartFromOrder(o) {
  const map = {};
  (o.items || []).forEach(i => {
    if (i.modifiers_json) {
      let label = "";
      try {
        label = JSON.parse(i.modifiers_json).map(m => m.option_name).join(", ");
      } catch { /* biarkan kosong kalau JSON gak valid */ }
      map[`oi:${i.id}`] = { name: i.item_name, unitPrice: i.unit_price, qty: i.qty, carryOverId: i.id, modifiersLabel: label };
    } else {
      map[`item:${i.item_id}`] = { name: i.item_name, unitPrice: i.unit_price, qty: i.qty, itemId: i.item_id };
    }
  });
  return map;
}

function _editCartTotal() {
  return Object.values(editCart).reduce((s, e) => s + e.unitPrice * e.qty, 0);
}

function _editRowHtml(key, e) {
  const lockedHint = e.carryOverId
    ? `<div class="detail-item-note">🧩 ${escapeHtml(e.modifiersLabel || "")} — varian terkunci, cuma qty yang bisa diubah</div>`
    : "";
  return `
    <div class="edit-item-row" data-key="${key}">
      <div class="edit-item-info">
        <div>${escapeHtml(e.name)}</div>
        ${lockedHint}
        <div class="detail-item-note">${riel(e.unitPrice)} × ${e.qty} = ${riel(e.unitPrice * e.qty)}</div>
      </div>
      <div class="qty-control">
        <button class="qty-btn minus" data-key="${key}">−</button>
        <span class="qty-num">${e.qty}</span>
        <button class="qty-btn plus" data-key="${key}">+</button>
      </div>
    </div>`;
}

async function renderEditOrder(o) {
  await _ensureMenuLoaded();
  editCart = _editCartFromOrder(o);
  _renderEditOrderBody(o);
}

function _renderEditOrderBody(o) {
  const entries = Object.entries(editCart);
  const rows = entries.length
    ? entries.map(([k, e]) => _editRowHtml(k, e)).join("")
    : `<div class="column-empty">Order kosong — tambah item dulu di bawah</div>`;

  const addOptions = (menuFlat || [])
    .filter(m => m.available && !m.has_modifiers)
    .map(m => `<option value="${m.id}">${escapeHtml(m.name)} — ${riel(m.price)}</option>`)
    .join("");

  document.getElementById("detail-body").innerHTML = `
    <div class="detail-note">Edit Order #${o.id} — tambah/kurangi/hapus item. Perubahan otomatis renotif kanban & cetak ulang struk.</div>
    <div class="edit-items-list">${rows}</div>
    <div class="edit-add-row">
      <select id="edit-add-select">
        <option value="">+ Tambah item...</option>
        ${addOptions}
      </select>
      <button class="btn-action secondary" id="btn-edit-add">Tambah</button>
    </div>
    <div class="detail-row detail-total"><span>Total</span><span>${riel(_editCartTotal())}</span></div>
    <div class="action-row">
      <button class="btn-action" id="btn-edit-save">💾 Simpan Perubahan</button>
      <button class="btn-action secondary" id="btn-edit-back">« Batal</button>
    </div>
    <div class="detail-note">ℹ️ Item ber-varian (🧩) cuma bisa diubah jumlahnya di sini. Buat ganti varian atau nambah item baru yang punya pilihan varian, arahkan customer edit sendiri lewat app.</div>
  `;

  document.querySelectorAll("#detail-body .edit-item-row .qty-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.key;
      if (btn.classList.contains("plus")) {
        editCart[key].qty++;
      } else {
        editCart[key].qty--;
        if (editCart[key].qty <= 0) delete editCart[key];
      }
      _renderEditOrderBody(o);
    });
  });

  document.getElementById("btn-edit-add").addEventListener("click", () => {
    const select = document.getElementById("edit-add-select");
    const itemId = parseInt(select.value);
    if (!itemId) return;
    const m = (menuFlat || []).find(x => x.id === itemId);
    if (!m) return;
    const key = `item:${itemId}`;
    if (editCart[key]) editCart[key].qty++;
    else editCart[key] = { name: m.name, unitPrice: m.price, qty: 1, itemId };
    _renderEditOrderBody(o);
  });

  document.getElementById("btn-edit-save").addEventListener("click", async () => {
    const btn = document.getElementById("btn-edit-save");
    btn.disabled = true;
    btn.textContent = "Menyimpan...";
    const items = Object.values(editCart).map(e =>
      e.carryOverId ? { order_item_id: e.carryOverId, qty: e.qty } : { item_id: e.itemId, qty: e.qty }
    );
    const r = await api(`/api/orders/${o.id}/edit`, {
      method: "POST",
      body: JSON.stringify({ items }),
    });
    if (r.ok) {
      tg?.HapticFeedback?.notificationOccurred("success");
      closeDetail();
    } else {
      tg?.showAlert?.(r.error || "Gagal menyimpan perubahan.");
      btn.disabled = false;
      btn.textContent = "💾 Simpan Perubahan";
    }
  });

  document.getElementById("btn-edit-back")?.addEventListener("click", renderDetail);
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
