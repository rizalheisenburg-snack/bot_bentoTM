"""Owner bot — python-telegram-bot. Manage order, stok, omzet, push kartu."""
from __future__ import annotations
import logging
import re
from datetime import datetime

log = logging.getLogger(__name__)

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, CAFE_LAT, CAFE_LON, OWNER_ID, WEBAPP_URL
from db import get_conn, get_setting, set_setting, set_user_min_order
from geo import get_min_order, haversine
from state_machine import (
    CANCEL_REASONS,
    STATUS_LABEL,
    TRANSITIONS,
    add_payment_proof,
    force_cancel_order,
    get_cancel_warning,
    get_latest_unpaid_order,
    get_omzet,
    get_order,
    get_pending_orders,
    mark_paid,
    transition,
)

_LOCATION_KEYWORD_RE = re.compile(r"(antar|delivery|bisa\s*ke|sampe\s*mana)", re.IGNORECASE)

def _location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Cek Lokasi Saya", request_location=True)]],
        resize_keyboard=True,
    )

USD_RATE = 4_000  # 1 USD = 4000 riel, statis

PAYMENT_METHOD_LABEL: dict[str, str] = {
    "CASH": "💵 CASH",
    "ABA": "🏦 ABA",
}

# Pesan notif ke customer per status (dipakai pas owner pencet tombol)
CUSTOMER_STATUS_MSG: dict[str, str] = {
    "Diproses":   "👨‍🍳 *Order #{id} diterima & mulai dimasak!*\nEstimasi ±10-25 menit tergantung antrian dapur ya 🙏",
    "Siap":       "🎉 *Order #{id} selesai!*\nPesananmu siap / lagi diantar ke tujuan.",
    "Dibatalkan": "🚫 *Order #{id} dibatalkan.*",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def riel(n: int) -> str:
    return f"{n:,}៛"


def _order_text(o: dict, *, for_admin: bool = True) -> str:
    def _item_line(i: dict) -> str:
        line = f"  • {i['item_name']} x{i['qty']}  {riel(i['unit_price'] * i['qty'])}"
        note = (i.get("item_note") or "").strip()
        if note:
            line += f"\n     📝 {note}"
        return line

    items_text = "\n".join(_item_line(i) for i in o.get("items", []))
    pay_status = "✅ LUNAS" if o["payment_status"] == "PAID" else "❌ BELUM BAYAR"
    paid_info = f" ({o['paid_currency']})" if o.get("paid_currency") else ""
    note_line = f"📝 Note    : {o.get('note') or '-'}\n\n"
    payment_method_line = ""
    if for_admin:
        method = o.get("payment_method") or "CASH"
        payment_method_line = f"💳 Metode  : {PAYMENT_METHOD_LABEL.get(method, method)}\n"
    cancel_reason_line = ""
    if o["status"] == "Dibatalkan" and o.get("cancel_reason"):
        cancel_reason_line = f"🚫 Alasan  : {o['cancel_reason']}\n"
    return (
        f"🧾 *Order #{o['id']}*\n"
        f"👤 {o.get('full_name') or o.get('username') or o['user_id']}\n"
        f"📋 Status  : {STATUS_LABEL.get(o['status'], o['status'])}\n"
        f"💳 Bayar   : {pay_status}{paid_info}\n"
        f"{payment_method_line}"
        f"{cancel_reason_line}"
        f"{note_line}"
        f"{items_text}\n\n"
        f"  *Total   : {riel(o['total'])}*"
    )


def _order_keyboard(order_id: int, status: str, payment_status: str) -> InlineKeyboardMarkup:
    rows = []

    # Tombol transisi status (Dibatalkan dikeluarkan dari sini — semua cancel
    # admin wajib lewat alur Force Cancel supaya alasan selalu ke-capture)
    next_states = [s for s in TRANSITIONS.get(status, []) if s != "Dibatalkan"]
    state_btns = [
        InlineKeyboardButton(STATUS_LABEL[s], callback_data=f"status:{order_id}:{s}")
        for s in next_states
    ]
    if state_btns:
        rows.append(state_btns)

    # Tombol lunas (kalau belum bayar dan order masih aktif)
    if payment_status == "UNPAID" and status != "Dibatalkan":
        rows.append([
            InlineKeyboardButton("💵 Lunas",  callback_data=f"paid:{order_id}:RIEL"),

        ])

    # Tombol force-cancel: selalu tampil dari kolom manapun (kecuali sudah Dibatalkan)
    if status != "Dibatalkan":
        rows.append([
            InlineKeyboardButton("🚫 Force Cancel", callback_data=f"forcecancel:{order_id}")
        ])

    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh:{order_id}")])
    return InlineKeyboardMarkup(rows)


def cancel_notif_text(order_id: int, reason: str) -> str:
    return f"🚫 *Order #{order_id} dibatalkan.*\nAlasan: {reason}"


def _cancel_reason_keyboard(order_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(reason, callback_data=f"cancelreason:{order_id}:{i}")]
        for i, reason in enumerate(CANCEL_REASONS)
    ]
    rows.append([InlineKeyboardButton("« Batal", callback_data=f"refresh:{order_id}")])
    return InlineKeyboardMarkup(rows)


async def _is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        await update.message.reply_text(
            "👋 Halo! Buat cek minimal order ke lokasi kamu, share lokasi dulu ya lewat tombol di bawah.",
            reply_markup=_location_keyboard(),
        )
        return
    shop_status = "🔓 BUKA" if get_setting("shop_open", "1") == "1" else "🔒 TUTUP"
    await update.message.reply_text(
        "☕ *Jakarta Cafe — Owner Panel*\n\n"
        f"Status warung: *{shop_status}*\n\n"
        "/pending — order masuk\n"
        "/order \\<id\\> — detail 1 order\n"
        "/omzet — rekap bulan ini\n"
        "/omzet 6 2026 — rekap bulan tertentu\n"
        "/stok — lihat & toggle stok menu\n"
        "/menu — daftar harga menu\n"
        "/buka — buka warung \\(terima order\\)\n"
        "/tutup — tutup warung \\(blok checkout\\)\n"
        "/push \\<user\\_id\\> \\[pesan\\] — kirim promo ke user\n"
        "/admin — buka Kanban order",
        parse_mode="MarkdownV2",
    )


async def cmd_buka(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    set_setting("shop_open", "1")
    await update.message.reply_text("🔓 Warung DIBUKA — order bisa masuk lagi.")


async def cmd_tutup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    set_setting("shop_open", "0")
    await update.message.reply_text(
        "🔒 Warung DITUTUP — checkout diblok.\n"
        "Order yang udah masuk tetap bisa diproses. /buka untuk buka lagi."
    )


async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    orders = get_pending_orders()
    if not orders:
        await update.message.reply_text("Tidak ada order pending saat ini.")
        return
    for o in orders:
        full = get_order(o["id"])
        await update.message.reply_text(
            _order_text(full),
            parse_mode="Markdown",
            reply_markup=_order_keyboard(full["id"], full["status"], full["payment_status"]),
        )


async def cmd_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    args = ctx.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Cara pakai: /order <id>")
        return
    o = get_order(int(args[0]))
    if not o:
        await update.message.reply_text("Order tidak ditemukan.")
        return
    await update.message.reply_text(
        _order_text(o),
        parse_mode="Markdown",
        reply_markup=_order_keyboard(o["id"], o["status"], o["payment_status"]),
    )


async def cmd_omzet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    now = datetime.utcnow()
    args = ctx.args
    try:
        bulan = int(args[0]) if args else now.month
        tahun = int(args[1]) if len(args or []) > 1 else now.year
    except ValueError:
        await update.message.reply_text("Cara Pakai: /omzet [bulan] [tahun]\nContoh: /omzet 6 2026")
        return

    d = get_omzet(bulan, tahun)
    nama_bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                  "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

    usd_equiv = d["omzet_riel"] // USD_RATE
    top = "\n".join(
        f"  {i+1}. {r['item_name']} x{r['total_qty']}"
        for i, r in enumerate(d["top_items"])
    ) or "  (belum ada data)"

    await update.message.reply_text(
        f"📊 *Omzet {nama_bulan[bulan]} {tahun}*\n\n"
        f"Total Order  : {d['total_order']}\n"
        f"Lunas        : {d['lunas']}\n"
        f"Dibatalkan   : {d['batal']}\n"
        f"Bayar USD    : {d['bayar_usd']} transaksi\n\n"
        f"💰 *Omzet    : {riel(d['omzet_riel'])}*\n"
        f"   ≈ ${usd_equiv:,} (rate {USD_RATE:,})\n\n"
        f"*Top Item:*\n{top}",
        parse_mode="Markdown",
    )


async def cmd_stok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, price, category, available FROM menu_items ORDER BY category, name"
        ).fetchall()

    if not rows:
        await update.message.reply_text("Menu kosong.")
        return

    buttons = []
    for r in rows:
        status_icon = "✅" if r["available"] else "❌"
        buttons.append([InlineKeyboardButton(
            f"{status_icon} {r['name']} — {riel(r['price'])}",
            callback_data=f"toggle:{r['id']}"
        )])

    await update.message.reply_text(
        "📦 *Stok Menu* — tap untuk toggle ada/habis:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM menu_items ORDER BY category, name"
        ).fetchall()

    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    lines = []
    for cat, items in by_cat.items():
        lines.append(f"\n*{cat}*")
        for item in items:
            stok = "" if item["available"] else " _(habis)_"
            lines.append(f"  {item['emoji']} {item['name']} — {riel(item['price'])}{stok}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_push(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    args = ctx.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Cara Pakai: /push <user_id> [pesan opsional]")
        return
    target_uid = int(args[0])
    msg = " ".join(args[1:]) if len(args) > 1 else "Ada promo spesial buat kamu hari ini!"
    try:
        await ctx.bot.send_message(
            chat_id=target_uid,
            text=f"*Dari Jakarta Cafe*\n\n{msg}\n\nOrder sekarang:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Buka Menu", url=WEBAPP_URL)
            ]]),
        )
        await update.message.reply_text(f"Kartu terkirim ke user {target_uid}")
    except Exception as e:
        await update.message.reply_text(f"Gagal kirim: {e}")


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _is_owner(update):
        return
    admin_url = WEBAPP_URL.rstrip("/") + "/admin"
    await update.message.reply_text(
        "📋 Kanban order — tap tombol di bawah buat buka.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Buka Kanban", web_app=WebAppInfo(url=admin_url))
        ]]),
    )


# ── Bukti transfer ────────────────────────────────────────────────────────────

async def handle_payment_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == OWNER_ID:
        return

    order = get_latest_unpaid_order(user.id)
    if not order:
        await update.message.reply_text("Tidak ada order aktif.")
        return

    photo_file_id = update.message.photo[-1].file_id
    add_payment_proof(order["id"], photo_file_id)

    try:
        await ctx.bot.send_photo(
            chat_id=OWNER_ID,
            photo=photo_file_id,
            caption=f"📸 Bukti transfer — Order #{order['id']}",
            reply_to_message_id=order.get("admin_msg_id"),
        )
    except Exception:
        log.exception(f"gagal forward bukti transfer order #{order['id']}")

    await update.message.reply_text(
        "Bukti transfer diterima, terima kasih! Ditunggu konfirmasi dari admin ya 🙏"
    )


# ── Radius & minimal order ──────────────────────────────────────────────────────

async def handle_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == OWNER_ID:
        return
    loc = update.message.location
    distance_km = haversine(loc.latitude, loc.longitude, CAFE_LAT, CAFE_LON)
    min_order = get_min_order(loc.latitude, loc.longitude, CAFE_LAT, CAFE_LON)
    set_user_min_order(update.effective_user.id, min_order, distance_km)
    await update.message.reply_text(
        f"📍 Lokasi diterima! Jarak kamu ~{distance_km:.1f} km dari cafe.\n\n"
        f"Minimal order ditentuin dari alamat yang kamu pilih di keranjang ya 🛒",
        reply_markup=ReplyKeyboardRemove(),
    )


async def handle_text_fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == OWNER_ID:
        return
    if not _LOCATION_KEYWORD_RE.search(update.message.text or ""):
        return
    await update.message.reply_text(
        "Buat cek ongkir/minimal order ke lokasi kamu, share lokasi dulu ya lewat tombol ini 👇",
        reply_markup=_location_keyboard(),
    )


# ── Callback handler ──────────────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from server import broadcast_order_update  # lazy import, hindari circular import

    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return

    data = query.data

    if data.startswith("status:"):
        _, oid, new_status = data.split(":")
        result = transition(int(oid), new_status, actor="owner")
        if result["ok"]:
            await broadcast_order_update(int(oid))
            o = get_order(int(oid))
            await query.edit_message_text(
                _order_text(o),
                parse_mode="Markdown",
                reply_markup=_order_keyboard(o["id"], o["status"], o["payment_status"]),
            )
            try:
                msg = CUSTOMER_STATUS_MSG.get(
                    o["status"],
                    f"*Order #{o['id']}* diperbarui\nStatus: {result['label']}",
                ).format(id=o["id"])
                await ctx.bot.send_message(
                    chat_id=o["user_id"],
                    text=msg,
                    parse_mode="Markdown",
                )
            except Exception as e:
                log.warning(f"Gagal kirim notif customer {o['user_id']}: {e}")
        else:
            await query.answer(result["error"], show_alert=True)

    elif data.startswith("paid:"):
        _, oid, currency = data.split(":")
        result = mark_paid(int(oid), currency)
        if result["ok"]:
            await broadcast_order_update(int(oid))
            o = get_order(int(oid))
            await query.edit_message_text(
                _order_text(o),
                parse_mode="Markdown",
                reply_markup=_order_keyboard(o["id"], o["status"], o["payment_status"]),
            )
            try:
                await ctx.bot.send_message(
                    chat_id=o["user_id"],
                    text=f"💵 *Pembayaran Order #{o['id']} diterima.*\nTerima kasih! 🙏",
                    parse_mode="Markdown",
                )
            except Exception as e:
                log.warning(f"Gagal kirim notif lunas ke {o['user_id']}: {e}")
        else:
            await query.answer(result["error"], show_alert=True)

    elif data.startswith("forcecancel:"):
        oid = int(data.split(":")[1])
        o = get_order(oid)
        if not o:
            await query.answer("Order tidak ditemukan", show_alert=True)
            return
        warning = get_cancel_warning(o["payment_status"])
        if warning:
            await query.answer(warning, show_alert=True)
        await query.edit_message_text(
            _order_text(o) + "\n\n*Pilih alasan cancel:*",
            parse_mode="Markdown",
            reply_markup=_cancel_reason_keyboard(oid),
        )

    elif data.startswith("cancelreason:"):
        _, oid, reason_idx = data.split(":")
        oid = int(oid)
        reason_idx = int(reason_idx)
        if reason_idx < 0 or reason_idx >= len(CANCEL_REASONS):
            await query.answer("Alasan tidak valid", show_alert=True)
            return
        reason = CANCEL_REASONS[reason_idx]
        result = force_cancel_order(oid, reason)
        if result["ok"]:
            await broadcast_order_update(oid)
            o = get_order(oid)
            await query.edit_message_text(
                _order_text(o),
                parse_mode="Markdown",
                reply_markup=_order_keyboard(o["id"], o["status"], o["payment_status"]),
            )
            try:
                await ctx.bot.send_message(
                    chat_id=o["user_id"],
                    text=cancel_notif_text(oid, reason),
                    parse_mode="Markdown",
                )
            except Exception as e:
                log.warning(f"Gagal kirim notif cancel ke {o['user_id']}: {e}")
        else:
            await query.answer(result["error"], show_alert=True)

    elif data.startswith("toggle:"):
        item_id = int(data.split(":")[1])
        with get_conn() as conn:
            conn.execute(
                "UPDATE menu_items SET available = 1 - available WHERE id=?", (item_id,)
            )
            conn.commit()
            rows = conn.execute(
                "SELECT id, name, price, available FROM menu_items ORDER BY category, name"
            ).fetchall()

        buttons = []
        for r in rows:
            icon = "✅" if r["available"] else "❌"
            buttons.append([InlineKeyboardButton(
                f"{icon} {r['name']} — {riel(r['price'])}",
                callback_data=f"toggle:{r['id']}"
            )])
        await query.edit_message_reply_markup(InlineKeyboardMarkup(buttons))

    elif data.startswith("refresh:"):
        oid = int(data.split(":")[1])
        o = get_order(oid)
        if o:
            await query.edit_message_text(
                _order_text(o),
                parse_mode="Markdown",
                reply_markup=_order_keyboard(o["id"], o["status"], o["payment_status"]),
            )


# ── Build ─────────────────────────────────────────────────────────────────────

def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("order",   cmd_order))
    app.add_handler(CommandHandler("omzet",   cmd_omzet))
    app.add_handler(CommandHandler("stok",    cmd_stok))
    app.add_handler(CommandHandler("menu",    cmd_menu))
    app.add_handler(CommandHandler("buka",    cmd_buka))
    app.add_handler(CommandHandler("tutup",   cmd_tutup))
    app.add_handler(CommandHandler("push",    cmd_push))
    app.add_handler(CommandHandler("admin",   cmd_admin))
    app.add_handler(MessageHandler(filters.PHOTO, handle_payment_proof))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_fallback))
    app.add_handler(CallbackQueryHandler(callback_handler))
    return app
