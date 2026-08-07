/* ── Telegram WebApp init ─────────────────────────────────────── */
const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();
tg?.setHeaderColor?.("#14161D");
tg?.setBackgroundColor?.("#14161D");

const INIT_DATA = tg?.initData || "";

/* ── State ────────────────────────────────────────────────────── */
const cart = {};       // { item_id: { item, qty, note } }
let menu = {};         // { category: [item, ...] }
let addressTiers = { tiers: {}, default: 0 };  // minimal order per alamat, dari /api/address-tiers
let minOrder = 0;      // ambang minimal order (riel) buat alamat yang lagi dipilih

/* ── Helpers ──────────────────────────────────────────────────── */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", "X-Init-Data": INIT_DATA },
    ...opts,
  });
  return res.json();
}

const riel = n => `${Number(n).toLocaleString("km-KH")}៛`;
const escapeAttr = s => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");

function show(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.getElementById(id).classList.add("active");
}

/* ── Menu screen ──────────────────────────────────────────────── */
let searchQuery = "";

function categorySlug(name) {
  return name
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9\-]/g, "");
}

// Warna tint solid per kategori, deterministik dari nama (biar konsisten tiap render).
function categoryColor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 42%, 24%)`;
}

const usd = n => `≈ $${(n / 4000).toFixed(2)}`;

function menuCardHtml(item) {
  const qty = cart[item.id]?.qty || 0;
  const emoji = item.emoji || "🍽️";
  const visual = item.image_url
    ? `<img src="${item.image_url}" alt="${item.name}" loading="lazy"
           onload="this.nextElementSibling.style.display='none'"
           onerror="this.style.display='none'" />
       <div class="menu-visual-fallback">${emoji}</div>`
    : emoji;
  return `
    <div class="menu-card">
      <div class="menu-visual">${visual}</div>
      <div class="menu-info">
        <div class="menu-cat">${item.category || ""}</div>
        <div class="menu-name">${item.name}</div>
        ${item.description ? `<div class="menu-desc">${item.description}</div>` : ""}
      </div>
      <div class="menu-foot">
        <div class="menu-price">${riel(item.price)}<small>${usd(item.price)}</small></div>
        <div class="qty-control ${qty ? "" : "empty"}" id="ctrl-${item.id}">
          <button class="qty-btn minus" data-id="${item.id}">−</button>
          <span class="qty-num" id="qty-${item.id}">${qty}</span>
          <button class="qty-btn plus" data-id="${item.id}">+</button>
        </div>
      </div>
    </div>`;
}

// Search box + tab kategori dibangun sekali aja (menu gak berubah tiap render),
// biar input search nggak kehilangan fokus tiap kali user ngetik satu huruf.
function renderControls() {
  const tabs = document.getElementById("category-tabs");
  if (document.getElementById("menu-search")) return;

  const catTabsHtml = Object.keys(menu).map((cat, i) =>
    `<button class="cat-tab ${i === 0 ? "active" : ""}" data-cat="${cat}">${cat}</button>`
  ).join("");

  tabs.innerHTML = `
    <div class="menu-controls">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input id="menu-search" class="menu-search" type="search" placeholder="Cari menu..." value="${searchQuery}" autocomplete="off" />
      </div>
    </div>
    <div class="cat-tabs-row" id="cat-tabs-row">${catTabsHtml}</div>
  `;

  document.getElementById("menu-search").addEventListener("input", e => {
    searchQuery = e.target.value;
    renderList();
  });

  document.getElementById("cat-tabs-row").addEventListener("click", e => {
    const tab = e.target.closest(".cat-tab");
    if (!tab) return;
    if (searchQuery) {
      searchQuery = "";
      document.getElementById("menu-search").value = "";
      renderList();
    }
    scrollToCategory(tab.dataset.cat);
  });

  document.getElementById("menu-list").addEventListener("scroll", updateActiveTabFromScroll, { passive: true });
}

function scrollToCategory(cat) {
  document.getElementById(`section-${categorySlug(cat)}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Scroll-spy manual: highlight tab kategori sesuai section yang lagi keliatan di atas.
function updateActiveTabFromScroll() {
  if (searchQuery.trim()) return;
  const list = document.getElementById("menu-list");
  const sections = list.querySelectorAll(".menu-section");
  let current = sections[0];
  for (const sec of sections) {
    if (sec.offsetTop - list.scrollTop <= 80) current = sec;
  }
  if (!current) return;
  const cat = current.dataset.cat;
  document.querySelectorAll(".cat-tab").forEach(t => t.classList.toggle("active", t.dataset.cat === cat));
}

function renderList() {
  const list = document.getElementById("menu-list");
  const q = searchQuery.trim().toLowerCase();

  if (q) {
    const results = Object.values(menu).flat().filter(item =>
      item.name.toLowerCase().includes(q)
    );
    list.innerHTML = results.length
      ? `<div class="section-grid">${results.map(menuCardHtml).join("")}</div>`
      : `<p class='empty-hint'>Tidak ada hasil untuk "${searchQuery}"</p>`;
    return;
  }

  list.innerHTML = Object.keys(menu).map(cat => `
    <div class="menu-section" id="section-${categorySlug(cat)}" data-cat="${cat}">
      <h3 class="section-title">${cat}</h3>
      <div class="section-grid">
        ${menu[cat].map(menuCardHtml).join("")}
      </div>
    </div>`
  ).join("");
}

function renderMenu() {
  const tabs = document.getElementById("category-tabs");
  const list = document.getElementById("menu-list");
  if (!Object.keys(menu).length) {
    tabs.innerHTML = "";
    list.innerHTML = "<p class='empty-hint'>Menu kosong</p>";
    return;
  }
  renderControls();
  renderList();
}

const menuList = document.getElementById("menu-list");

menuList.addEventListener("click", e => {
  const plus = e.target.closest(".qty-btn.plus");
  const minus = e.target.closest(".qty-btn.minus");
  if (!plus && !minus) return;
  const id = parseInt((plus || minus).dataset.id);
  const item = Object.values(menu).flat().find(i => i.id === id);
  if (!item) return;
  if (plus) {
    cart[id] = cart[id] || { item, qty: 0 };
    cart[id].qty++;
  } else {
    if (!cart[id]?.qty) return;
    cart[id].qty--;
    if (cart[id].qty === 0) delete cart[id];
  }
  document.getElementById(`qty-${id}`).textContent = cart[id]?.qty || 0;
  document.getElementById(`ctrl-${id}`)?.classList.toggle("empty", !cart[id]?.qty);
  updateCartFab();
});

function cartSubtotal() {
  return Object.values(cart).reduce((s, { item, qty }) => s + item.price * qty, 0);
}

function updateCartFab() {
  const fab = document.getElementById("btn-cart");
  const count = Object.values(cart).reduce((s, v) => s + v.qty, 0);
  if (!count) { fab.classList.add("hidden"); return; }
  fab.classList.remove("hidden");
  document.getElementById("cart-count").textContent = count;
  document.getElementById("cart-total-fab").textContent = riel(cartSubtotal());
}

/* ── Cart screen ──────────────────────────────────────────────── */
document.getElementById("cart-items").addEventListener("click", e => {
  const plus = e.target.closest(".qty-btn.plus");
  const minus = e.target.closest(".qty-btn.minus");
  if (!plus && !minus) return;
  const id = parseInt((plus || minus).dataset.id);
  if (plus) { cart[id].qty++; }
  else {
    cart[id].qty--;
    if (cart[id].qty === 0) delete cart[id];
  }
  renderCart();
  updateCartFab();
});

document.getElementById("cart-items").addEventListener("input", e => {
  const input = e.target.closest(".cart-item-note-input");
  if (!input) return;
  const id = parseInt(input.dataset.id);
  if (!cart[id]) return;
  cart[id].note = input.value;
});

function renderCart() {
  const container = document.getElementById("cart-items");
  const entries = Object.values(cart);

  if (!entries.length) {
    container.innerHTML = `<div class="empty-cart">🛒 Keranjang kosong</div>`;
  } else {
    container.innerHTML = entries.map(({ item, qty, note }) => `
      <div class="cart-item">
        <div class="cart-item-row">
          <span class="cart-emoji">${item.emoji || "☕"}</span>
          <div class="cart-item-info">
            <div class="cart-item-name">${item.name}</div>
            <div class="cart-item-price">${riel(item.price)} × ${qty} = <strong>${riel(item.price * qty)}</strong></div>
          </div>
          <div class="qty-control">
            <button class="qty-btn minus" data-id="${item.id}">−</button>
            <span class="qty-num">${qty}</span>
            <button class="qty-btn plus" data-id="${item.id}">+</button>
          </div>
        </div>
        <input type="text" class="cart-item-note-input" data-id="${item.id}"
               placeholder="+ catatan untuk item ini (opsional)"
               value="${escapeAttr(note || "")}" maxlength="200" />
      </div>`).join("");
  }

  updatePriceSummary();
  const empty = !entries.length;
  const belowMin = minOrder > 0 && cartSubtotal() < minOrder;
  document.getElementById("btn-pay-cash").disabled = empty || belowMin;
  document.getElementById("btn-pay-aba").disabled = empty || belowMin;
}

function updatePriceSummary() {
  const sub = cartSubtotal();
  document.getElementById("sum-total").textContent = riel(sub);
  const belowMin = minOrder > 0 && sub < minOrder && sub > 0;
  const warning = document.getElementById("min-order-warning");
  warning.classList.toggle("hidden", !belowMin);
  if (belowMin) {
    warning.textContent = `⚠️ Minimal order ${riel(minOrder)} untuk lokasimu — kurang ${riel(minOrder - sub)} lagi.`;
  }
  document.getElementById("btn-pay-cash").classList.remove("hidden");
  document.getElementById("btn-pay-aba").classList.remove("hidden");
}

/* ── Address picker ───────────────────────────────────────────── */
let selectedAddr = "KD";

function _updateAddrBtn(label) {
  document.getElementById("btn-addr-pick").textContent = label + " ▾";
}

function _updateMinOrder() {
  minOrder = addressTiers.tiers[selectedAddr] ?? addressTiers.default;
  updatePriceSummary();
}

function _closePicker() {
  document.getElementById("addr-picker").classList.add("hidden");
}

document.getElementById("btn-addr-pick").addEventListener("click", () => {
  document.getElementById("addr-picker").classList.toggle("hidden");
});

document.querySelectorAll(".addr-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".addr-chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    selectedAddr = chip.dataset.addr;
    document.getElementById("addr-custom").value = "";
    _updateAddrBtn(selectedAddr);
    _updateMinOrder();
    _closePicker();
  });
});

document.getElementById("addr-custom").addEventListener("input", e => {
  if (e.target.value.trim()) {
    document.querySelectorAll(".addr-chip").forEach(c => c.classList.remove("active"));
    selectedAddr = e.target.value.trim();
    _updateAddrBtn(selectedAddr);
  } else {
    const first = document.querySelector(".addr-chip");
    first.classList.add("active");
    selectedAddr = first.dataset.addr;
    _updateAddrBtn(selectedAddr);
  }
  _updateMinOrder();
});

/* ── Checkout ─────────────────────────────────────────────────── */
async function doCheckout(payMethod, onSuccess = showSuccess) {
  const items = Object.values(cart).map(({ item, qty, note }) => ({
    item_id: item.id, qty, note: (note || "").trim(),
  }));
  const noteBase = document.getElementById("note-input").value.trim();
  const addr = document.getElementById("addr-custom").value.trim() || selectedAddr;
  const noteWithAddr = `[${addr}] ${noteBase}`.trim();
  const note = payMethod === "ABA" ? `[Transfer ABA] ${noteWithAddr}` : noteWithAddr;

  const result = await api("/api/checkout", {
    method: "POST",
    body: JSON.stringify({ items, note, payment_method: payMethod, address: addr }),
  });

  if (result.ok) {
    clearCart();
    if (result.unavailable_items?.length) {
      const names = result.unavailable_items.map(i => i.item_name || `#${i.item_id}`).join(", ");
      tg?.showAlert?.(`Item berikut habis dan tidak dimasukkan ke order: ${names}`);
    }
    if (result.mirror_sent === false) {
      const msg = result.bot_deeplink
        ? "Order kamu tetap berhasil ✅, tapi kami tidak bisa mengirim detail order ke chat kamu. Silakan buka chat bot ini dulu dan tekan Start, lalu order kamu akan otomatis dikirim ke chat berikutnya."
        : "Order kamu tetap berhasil ✅, tapi kami tidak bisa mengirim detail order ke chat kamu. Silakan buka chat bot ini dan tekan Start.";
      tg?.showAlert?.(msg);
      if (result.bot_deeplink) {
        tg?.openTelegramLink?.(result.bot_deeplink);
      }
    }
    onSuccess(result);
  } else {
    tg?.showAlert?.(result.error || "Checkout gagal, coba lagi.");
  }
}

document.getElementById("btn-pay-cash").addEventListener("click", async () => {
  const btn = document.getElementById("btn-pay-cash");
  btn.disabled = true; btn.textContent = "Memproses...";
  await doCheckout("CASH");
  btn.disabled = false; btn.textContent = "💵 Cash";
});

document.getElementById("btn-pay-aba").addEventListener("click", async () => {
  const btn = document.getElementById("btn-pay-aba");
  btn.disabled = true; btn.textContent = "Memproses...";
  stopPolling();
  await doCheckout("ABA", showSuccess);
  btn.disabled = false; btn.textContent = "🏦 ABA";
});

function clearCart() {
  Object.keys(cart).forEach(k => delete cart[k]);
  document.getElementById("note-input").value = "";
  document.getElementById("addr-custom").value = "";
  const firstChip = document.querySelector(".addr-chip");
  if (firstChip) {
    document.querySelectorAll(".addr-chip").forEach(c => c.classList.remove("active"));
    firstChip.classList.add("active");
    selectedAddr = firstChip.dataset.addr;
    _updateAddrBtn(selectedAddr);
    _updateMinOrder();
    _closePicker();
  }
  updateCartFab();
}

/* ── Success screen ───────────────────────────────────────────── */
function showSuccess(result) {
  document.getElementById("success-order-id").textContent = "#" + result.order_id;
  document.getElementById("success-total").textContent = result.total > 0 ? riel(result.total) : "GRATIS 🎉";
  show("screen-success");
  tg?.HapticFeedback?.notificationOccurred("success");
}

/* ── Orders list ──────────────────────────────────────────────── */
function _ordersHtml(orders) {
  return orders.map(o => {
    const payBadge = o.payment_status === "PAID"
      ? `<span class="pay-badge paid">Lunas</span>`
      : `<span class="pay-badge unpaid">Belum Bayar</span>`;
    return `
      <div class="order-card" data-id="${o.id}">
        <div class="order-card-header">
          <span class="order-id">Order #${o.id}</span>
          <span class="order-status-badge ${o.status.toLowerCase()}">${o.status_label}</span>
        </div>
        <div class="order-card-meta">${o.created_at} ${payBadge}</div>
        <div class="order-card-total">${riel(o.total)}</div>
      </div>`;
  }).join("");
}

async function loadOrders() {
  const container = document.getElementById("orders-list");
  // Spinner hanya kalau container masih kosong (first load)
  if (!container.innerHTML.trim())
    container.innerHTML = `<div class="empty-orders"><div class="spinner" style="margin:0 auto"></div></div>`;

  const result = await api("/api/orders");
  if (!result.ok || !result.orders?.length) {
    container.innerHTML = `<div class="empty-orders">📋 Belum ada pesanan</div>`;
    return;
  }
  container.innerHTML = _ordersHtml(result.orders);
}

// Listener click cukup sekali, pakai event delegation
document.getElementById("orders-list").addEventListener("click", e => {
  const card = e.target.closest(".order-card");
  if (card) loadOrderDetail(parseInt(card.dataset.id));
});

let _currentDetailOrderId = null;

async function loadOrderDetail(id) {
  _currentDetailOrderId = id;
  document.getElementById("detail-title").textContent = "Order #" + id;
  document.getElementById("order-detail-body").innerHTML = "";
  show("screen-order-detail");
  startPolling(() => _fetchOrderDetail(id));
}

async function _fetchOrderDetail(id) {
  const body = document.getElementById("order-detail-body");
  if (!body.innerHTML.trim())
    body.innerHTML = `<div style="text-align:center;padding:32px"><div class="spinner" style="margin:0 auto"></div></div>`;

  const result = await api(`/api/orders/${id}`);
  if (!result.ok) { body.innerHTML = `<p style="padding:20px;color:var(--red)">Gagal memuat</p>`; return; }
  const o = result.order;

  const itemsHtml = o.items.map(i => `
    <div class="detail-item-block">
      <div class="detail-item-row">
        <span>${i.item_name} × ${i.qty}</span>
        <span>${riel(i.unit_price * i.qty)}</span>
      </div>
      ${i.item_note ? `<div class="detail-item-note">📝 ${i.item_note}</div>` : ""}
    </div>`
  ).join("");

  const payHtml = o.payment_status === "PAID"
    ? `<div class="detail-row green"><span>Pembayaran</span><span>Lunas (${o.paid_currency || ""})</span></div>`
    : `<div class="detail-row" style="color:var(--red)"><span>Pembayaran</span><span>Belum Bayar</span></div>`;

  const cancelHtml = o.status === "Diterima"
    ? `<button id="btn-cancel-order" class="btn-cancel">🚫 Batalkan Order</button>
       <p class="cancel-hint">Bisa dibatalkan selama belum dikonfirmasi warung</p>`
    : "";

  const changeMethodHtml = o.payment_status === "UNPAID"
    ? `<button id="btn-change-method" class="btn-change-method">🔄 Ganti Metode Bayar (${o.payment_method || "CASH"})</button>`
    : "";

  body.innerHTML = `
    <div class="detail-status-big">${o.status_label}</div>
    <div class="detail-items">
      <strong class="section-label">ITEM</strong>
      ${itemsHtml}
    </div>
    <div class="detail-summary">
      <div class="detail-row detail-total"><span>Total</span><span>${riel(o.total)}</span></div>
      ${payHtml}
      ${o.note ? `<div class="detail-note">📝 ${o.note}</div>` : ""}
    </div>
    ${changeMethodHtml}
    ${cancelHtml}`;

  document.getElementById("btn-cancel-order")?.addEventListener("click", () => {
    const doCancel = async () => {
      const r = await api(`/api/orders/${id}/cancel`, { method: "POST" });
      if (r.ok) {
        tg?.HapticFeedback?.notificationOccurred("warning");
        _fetchOrderDetail(id);
      } else {
        tg?.showAlert?.(r.error || "Gagal membatalkan order.");
      }
    };
    if (tg?.showConfirm) {
      tg.showConfirm("Yakin mau batalkan order ini?", ok => { if (ok) doCancel(); });
    } else if (window.confirm("Yakin mau batalkan order ini?")) {
      doCancel();
    }
  });

  document.getElementById("btn-change-method")?.addEventListener("click", () => {
    const target = o.payment_method === "ABA" ? "CASH" : "ABA";
    const label = target === "ABA" ? "🏦 ABA" : "💵 Cash";
    const doChange = async () => {
      const r = await api(`/api/orders/${id}/payment-method`, {
        method: "POST",
        body: JSON.stringify({ payment_method: target }),
      });
      if (r.ok) {
        tg?.HapticFeedback?.notificationOccurred("success");
        if (r.reminder) tg?.showAlert?.(r.reminder);
        _fetchOrderDetail(id);
      } else {
        tg?.showAlert?.(r.error || "Gagal ganti metode bayar.");
      }
    };
    if (tg?.showConfirm) {
      tg.showConfirm(`Ganti metode bayar ke ${label}?`, ok => { if (ok) doChange(); });
    } else if (window.confirm(`Ganti metode bayar ke ${label}?`)) {
      doChange();
    }
  });
}

/* ── Polling ──────────────────────────────────────────────────── */
let _pollTimer = null;

function startPolling(fn, ms = 3000) {
  stopPolling();
  fn(); // langsung fetch sekali
  _pollTimer = setInterval(fn, ms);
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

/* ── Navigation ───────────────────────────────────────────────── */
document.getElementById("btn-cart").addEventListener("click", () => {
  stopPolling();
  renderCart();
  show("screen-cart");
});

document.getElementById("btn-orders-icon").addEventListener("click", () => {
  document.getElementById("orders-list").innerHTML = "";
  show("screen-orders");
  startPolling(loadOrders);
});

document.getElementById("btn-back-menu").addEventListener("click", () => {
  stopPolling();
  show("screen-menu");
});
document.getElementById("btn-see-orders").addEventListener("click", () => {
  document.getElementById("orders-list").innerHTML = "";
  show("screen-orders");
  startPolling(loadOrders);
});

document.querySelectorAll(".back-btn[data-target]").forEach(btn => {
  btn.addEventListener("click", () => {
    stopPolling();
    if (btn.dataset.target === "screen-orders") {
      document.getElementById("orders-list").innerHTML = "";
      show("screen-orders");
      startPolling(loadOrders);
    } else if (btn.dataset.target === "screen-cart") {
      renderCart();
      show("screen-cart");
    } else if (btn.dataset.target === "screen-order-detail" && _currentDetailOrderId != null) {
      show("screen-order-detail");
      startPolling(() => _fetchOrderDetail(_currentDetailOrderId));
    } else {
      show(btn.dataset.target);
    }
  });
});

/* ── Boot ─────────────────────────────────────────────────────── */
(async () => {
  show("loading");
  try {
    const [menuData, tiersData] = await Promise.all([api("/api/menu"), api("/api/address-tiers")]);
    menu = menuData.categories || {};
    addressTiers = { tiers: tiersData.tiers || {}, default: tiersData.default || 0 };
    _updateMinOrder();
    document.getElementById("closed-banner")?.classList.toggle("hidden", menuData.open !== false);
    show("screen-menu");
    renderMenu();
  } catch {
    document.querySelector(".loading-text").textContent = "Gagal memuat menu";
    document.querySelector(".spinner").style.display = "none";
  }
})();
