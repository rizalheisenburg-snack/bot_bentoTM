"""HTTP server — aiohttp. Melayani API + static webapp."""
from __future__ import annotations
import json
import logging
import pathlib

log = logging.getLogger(__name__)

from aiohttp import web
from telegram.error import Forbidden

from checkout_flow import checkout, verify_init_data
from config import BOT_USERNAME, OWNER_ID
from db import get_conn, get_setting
from geo import ADDRESS_MIN_ORDER, DEFAULT_ADDRESS_MIN_ORDER
from state_machine import (
    change_payment_method,
    force_cancel_order,
    get_active_orders,
    get_order,
    get_user_orders,
    mark_paid,
    transition,
)

WEBAPP_DIR = pathlib.Path(__file__).parent / "webapp"
routes = web.RouteTableDef()


def _json(data, status=200):
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        status=status,
    )


def _auth(request: web.Request) -> dict | None:
    return verify_init_data(request.headers.get("X-Init-Data", ""))


# ── Menu ──────────────────────────────────────────────────────────────────────

@routes.get("/api/menu")
async def api_menu(request):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM menu_items WHERE available=1 ORDER BY category, name"
        ).fetchall()
    by_cat: dict[str, list] = {}
    for r in rows:
        d = dict(r)
        by_cat.setdefault(d["category"], []).append(d)
    return _json({
        "categories": by_cat,
        "open": get_setting("shop_open", "1") == "1",
    })


# ── Minimal Order ─────────────────────────────────────────────────────────────

@routes.get("/api/address-tiers")
async def api_address_tiers(request):
    return _json({"tiers": ADDRESS_MIN_ORDER, "default": DEFAULT_ADDRESS_MIN_ORDER})


# ── Checkout ──────────────────────────────────────────────────────────────────

@routes.post("/api/checkout")
async def api_checkout(request):
    user = _auth(request)
    if not user:
        return _json({"ok": False, "error": "Unauthorized"}, 401)
    if get_setting("shop_open", "1") != "1":
        return _json(
            {"ok": False, "error": "Warung lagi tutup 🌙 Coba lagi pas jam buka ya."},
            400,
        )
    try:
        body = await request.json()
        note = body.get("note", "")
        result = checkout(
            user=user,
            items=body.get("items", []),
            note=note,
            payment_method=body.get("payment_method", "CASH"),
            address=body.get("address", ""),
        )
        # Kirim notif ke owner kalau order masuk
        if result.get("ok"):
            await _notify_owner_new_order(request, result.get("order_id"))
            await broadcast_order_update(result.get("order_id"))
        # Kirim mirror ke pelanggan untuk semua order sukses yang bukan auto-paid
        if result.get("ok") and not result.get("auto_paid"):
            mirror_sent = await _send_order_mirror_to_user(request, result.get("order_id"))
            result["mirror_sent"] = mirror_sent
            if not mirror_sent and BOT_USERNAME:
                result["bot_deeplink"] = f"https://t.me/{BOT_USERNAME}"
        return _json(result, 200 if result["ok"] else 400)
    except Exception as e:
        log.exception("checkout error")
        return _json({"ok": False, "error": f"Server error: {e}"}, 500)


async def _notify_owner_new_order(request: web.Request, order_id: int | None):
    if not order_id:
        return
    bot = request.app["bot"]
    if not bot:
        return
    try:
        from owner_console import _order_keyboard, _order_text
        from state_machine import get_order, set_admin_msg_id
        o = get_order(order_id)
        if not o:
            return
        msg = await bot.send_message(
            chat_id=OWNER_ID,
            text=f"🔔 *Order baru masuk!*\n\n{_order_text(o)}",
            parse_mode="Markdown",
            reply_markup=_order_keyboard(o["id"], o["status"], o["payment_status"]),
        )
        set_admin_msg_id(order_id, msg.message_id)
    except Exception:
        log.exception("gagal kirim notif owner")


async def _send_order_mirror_to_user(request: web.Request, order_id: int | None) -> bool:
    """Return True kalau mirror berhasil terkirim, False kalau gagal (termasuk
    kasus user belum pernah /start bot, di mana Telegram me-reject dengan 403)."""
    if not order_id:
        return False
    bot = request.app["bot"]
    if not bot:
        return False
    try:
        from owner_console import _order_text
        from state_machine import get_order
        from config import ABA_QR_IMAGE_PATH

        o = get_order(order_id)
        if not o:
            return False

        async def _send_photo(path):
            if not path:
                return
            try:
                with open(path, "rb") as f:
                    await bot.send_photo(chat_id=o["user_id"], photo=f)
            except FileNotFoundError:
                log.warning("QR image not found: %s", path)
            except Exception:
                log.exception("gagal kirim foto ke user")

        if o["total"] == 0:
            lines = [f"✅ Order #{o['id']} berhasil. Total 0៛, pesanan Anda telah diterima."]
            await bot.send_message(
                chat_id=o["user_id"],
                text="\n\n".join(lines),
                parse_mode="Markdown",
            )
            return True

        lines = [
            _order_text(o, for_admin=False),
        ]
        proof_needed = []
        if o.get("payment_method") == "ABA":
            proof_needed.append("bukti transfer ABA")
        if proof_needed:
            lines.append(f"📸 Reply pesan ini dengan screenshot {' & '.join(proof_needed)}.")
        text = "\n\n".join(lines)

        await bot.send_message(
            chat_id=o["user_id"],
            text=text,
            parse_mode="Markdown",
        )

        if o.get("payment_method") == "ABA":
            await _send_photo(ABA_QR_IMAGE_PATH)
        return True
    except Forbidden:
        # User belum pernah chat/start bot ini — Telegram menolak sendMessage.
        # Ini kondisi yang diekspektasikan (bukan bug), jadi cukup di-warn.
        log.warning(
            "gagal kirim mirror order #%s: user %s belum pernah start bot",
            order_id, o["user_id"],
        )
        return False
    except Exception:
        log.exception("gagal kirim mirror order ke user")
        return False


# ── Orders ────────────────────────────────────────────────────────────────────

@routes.get("/api/orders")
async def api_orders(request):
    user = _auth(request)
    if not user:
        return _json({"ok": False, "error": "Unauthorized"}, 401)
    return _json({"ok": True, "orders": get_user_orders(user["id"])})


@routes.get("/api/orders/active")
async def api_orders_active(request):
    user = _auth(request)
    if not user or user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    return _json({"ok": True, "orders": get_active_orders()})


@routes.get("/api/orders/{order_id}")
async def api_order_detail(request):
    user = _auth(request)
    if not user:
        return _json({"ok": False, "error": "Unauthorized"}, 401)
    oid = int(request.match_info["order_id"])
    o = get_order(oid)
    if not o:
        return _json({"ok": False, "error": "Tidak ditemukan"}, 404)
    if o["user_id"] != user["id"] and user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    return _json({"ok": True, "order": o})


@routes.post("/api/orders/{order_id}/cancel")
async def api_cancel_order(request):
    user = _auth(request)
    if not user:
        return _json({"ok": False, "error": "Unauthorized"}, 401)
    oid = int(request.match_info["order_id"])
    o = get_order(oid)
    if not o:
        return _json({"ok": False, "error": "Tidak ditemukan"}, 404)
    if o["user_id"] != user["id"] and user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    result = transition(oid, "Dibatalkan", actor="customer")
    if result.get("ok"):
        await broadcast_order_update(oid)
        bot = request.app["bot"]
        if bot:
            try:
                await bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"🚫 Order #{oid} dibatalkan oleh customer.",
                    reply_to_message_id=o.get("admin_msg_id"),
                )
            except Exception:
                log.exception("gagal notif owner soal cancel")
    return _json(result, 200 if result["ok"] else 400)


@routes.post("/api/orders/{order_id}/payment-method")
async def api_change_payment_method(request):
    user = _auth(request)
    if not user:
        return _json({"ok": False, "error": "Unauthorized"}, 401)
    oid = int(request.match_info["order_id"])
    o = get_order(oid)
    if not o:
        return _json({"ok": False, "error": "Tidak ditemukan"}, 404)
    if o["user_id"] != user["id"] and user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    body = await request.json()
    new_method = body.get("payment_method", "")
    result = change_payment_method(oid, new_method)
    if result.get("ok"):
        await _notify_owner_payment_method_change(request, oid, result)
        await broadcast_order_update(oid)
        if new_method == "ABA":
            result["reminder"] = "Jangan lupa upload bukti transfer ABA lewat chat ya 🙏"
    return _json(result, 200 if result["ok"] else 400)


async def _notify_owner_payment_method_change(request: web.Request, order_id: int, result: dict):
    bot = request.app["bot"]
    if not bot:
        return
    try:
        from owner_console import _order_text, _order_keyboard
        o = get_order(order_id)
        if not o:
            return
        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"🔄 Order #{order_id} ganti metode dari {result['old_method']} ke {result['new_method']}.",
            reply_to_message_id=o.get("admin_msg_id"),
        )
        if o.get("admin_msg_id"):
            await bot.edit_message_text(
                chat_id=OWNER_ID,
                message_id=o["admin_msg_id"],
                text=_order_text(o),
                parse_mode="Markdown",
                reply_markup=_order_keyboard(o["id"], o["status"], o["payment_status"]),
            )
    except Exception:
        log.exception("gagal notif ganti metode ke owner")


# ── Realtime (WebSocket kanban) ────────────────────────────────────────────────

_ws_clients: set[web.WebSocketResponse] = set()


def _auth_ws(request: web.Request) -> dict | None:
    """WebSocket handshake browser-native tidak bisa kirim custom header,
    jadi initData dikirim lewat query string, bukan X-Init-Data."""
    return verify_init_data(request.query.get("initData", ""))


@routes.get("/ws/admin")
async def ws_admin(request):
    user = _auth_ws(request)
    if not user or user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)

    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    _ws_clients.add(ws)
    try:
        async for _ in ws:
            pass  # client cuma listen, tidak perlu kirim apa-apa
    finally:
        _ws_clients.discard(ws)
    return ws


async def broadcast_order_update(order_id: int | None):
    if not _ws_clients or not order_id:
        return
    o = get_order(order_id)
    if not o:
        return
    payload = json.dumps({"type": "order_update", "order": o}, ensure_ascii=False)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_str(payload)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


# ── Owner ─────────────────────────────────────────────────────────────────────

@routes.post("/api/owner/orders/{order_id}/status")
async def api_owner_status(request):
    user = _auth(request)
    if not user or user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    oid = int(request.match_info["order_id"])
    body = await request.json()
    result = transition(oid, body.get("status", ""), actor="owner")
    if result.get("ok"):
        await broadcast_order_update(oid)
    return _json(result, 200 if result["ok"] else 400)


@routes.post("/api/owner/orders/{order_id}/force-cancel")
async def api_force_cancel(request):
    user = _auth(request)
    if not user or user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    oid = int(request.match_info["order_id"])
    body = await request.json()
    result = force_cancel_order(oid, body.get("reason", ""))
    if result.get("ok"):
        await _notify_customer_force_cancel(request, oid, result)
        await broadcast_order_update(oid)
    return _json(result, 200 if result["ok"] else 400)


async def _notify_customer_force_cancel(request: web.Request, order_id: int, result: dict):
    bot = request.app["bot"]
    if not bot:
        return
    try:
        from owner_console import cancel_notif_text
        o = get_order(order_id)
        if not o:
            return
        await bot.send_message(
            chat_id=o["user_id"],
            text=cancel_notif_text(order_id, result["reason"]),
            parse_mode="Markdown",
        )
    except Exception:
        log.exception("gagal notif customer soal force-cancel")


@routes.post("/api/owner/orders/{order_id}/pay")
async def api_owner_pay(request):
    user = _auth(request)
    if not user or user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    oid = int(request.match_info["order_id"])
    body = await request.json()
    result = mark_paid(oid, body.get("currency", "RIEL"))
    if result.get("ok"):
        await broadcast_order_update(oid)
    return _json(result, 200 if result["ok"] else 400)


@routes.post("/api/owner/orders/{order_id}/message")
async def api_owner_send_message(request):
    """Kirim pesan ke pelanggan lewat bot — gak pakai deep-link Telegram
    personal karena itu butuh akun admin udah pernah 'kenal' user itu
    (access_hash), yang gak bisa dijamin. Bot selalu bisa kirim ke chat_id
    manapun yang pernah /start, jadi ini satu-satunya jalan yang reliable."""
    user = _auth(request)
    if not user or user["id"] != OWNER_ID:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    oid = int(request.match_info["order_id"])
    o = get_order(oid)
    if not o:
        return _json({"ok": False, "error": "Tidak ditemukan"}, 404)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return _json({"ok": False, "error": "Pesan gak boleh kosong."}, 400)
    bot = request.app["bot"]
    if not bot:
        return _json({"ok": False, "error": "Bot tidak aktif."}, 500)
    try:
        await bot.send_message(
            chat_id=o["user_id"],
            text=f"💬 *Pesan dari Admin:*\n\n{text}",
            parse_mode="Markdown",
        )
        return _json({"ok": True})
    except Forbidden:
        return _json({
            "ok": False,
            "error": "Gagal kirim: pelanggan belum pernah /start bot atau sudah blokir bot.",
        }, 409)
    except Exception:
        log.exception("gagal kirim pesan admin ke customer, order #%s", oid)
        return _json({"ok": False, "error": "Gagal kirim pesan."}, 500)


# ── Kanban admin ─────────────────────────────────────────────────────────────

@routes.get("/admin")
async def admin_page(request):
    return web.FileResponse(WEBAPP_DIR / "admin.html")


# ── Static ────────────────────────────────────────────────────────────────────

@routes.get("/{tail:.*}")
async def static_files(request):
    tail = request.match_info["tail"] or "index.html"
    path = WEBAPP_DIR / tail
    if not path.exists() or not path.is_file():
        path = WEBAPP_DIR / "index.html"
    # JS/CSS/img di-cache 1 jam, HTML tidak (supaya update langsung keliatan)
    is_html = path.suffix == ".html"
    headers = {} if is_html else {"Cache-Control": "public, max-age=3600"}
    return web.FileResponse(path, headers=headers)


def build_app(bot=None) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.add_routes(routes)
    return app
