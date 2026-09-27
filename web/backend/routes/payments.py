"""Authenticated SEPay checkout plus public, secret-authenticated IPN."""

import hmac
import html

from flask import Blueprint, Response, current_app, jsonify, request, url_for

from models import sepay_payment
from models import subscription as subscription_model
from models.workspace_sync import WorkspaceSync
from utils.user_context import get_current_user_id


payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")

# Shared brand palette/typography for the two SEPay hand-off pages below --
# matches web/frontend/landing.html's :root variables so a user bounced out
# to these pages (a real payment flow, not a dead end worth looking bare)
# still feels like they're inside FlowMate. Kept as a plain string, not part
# of the f-strings below, so its literal `{`/`}` never need doubling.
_SEPAY_PAGE_STYLE = """
:root {
  --primary: #0B5ED7;
  --primary-dark: #0847A6;
  --success: #1E9E6C;
  --warning: #B8860B;
  --text: #173042;
  --text-secondary: #587181;
  --border: #CBE7EC;
  --bg: #F4FAFB;
  --panel: #ffffff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  background: var(--bg);
  font-family: 'Poppins', Arial, Helvetica, sans-serif;
  color: var(--text);
}
main {
  width: min(440px, 100%);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 36px 28px;
  text-align: center;
  box-shadow: 0 14px 40px rgba(22, 78, 99, 0.12);
}
.logo { width: 56px; height: 56px; border-radius: 16px; margin-bottom: 16px; }
h1 { font-size: 19px; margin: 0 0 8px; line-height: 1.4; }
p.detail { color: var(--text-secondary); font-size: 14px; line-height: 1.6; margin: 0 0 20px; }
.summary {
  background: #eff6ff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  text-align: left;
  font-size: 13px;
  margin-bottom: 22px;
}
.summary div { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; }
.summary div + div { border-top: 1px dashed var(--border); }
.summary span:first-child { color: var(--text-secondary); }
.summary span:last-child { font-weight: 600; text-align: right; }
.spinner {
  width: 34px; height: 34px; margin: 4px auto 20px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: sepay-spin 0.85s linear infinite;
}
@keyframes sepay-spin { to { transform: rotate(360deg); } }
.status-icon {
  width: 60px; height: 60px; margin: 0 auto 16px;
  border-radius: 50%;
  display: grid; place-items: center;
}
.status-icon.success { background: #e6f6ee; color: var(--success); }
.status-icon.warning { background: #fdf3dd; color: var(--warning); }
.status-icon.muted { background: #eef2f6; color: var(--text-secondary); }
.actions { display: flex; flex-direction: column; gap: 10px; margin-top: 4px; }
a.btn, button.btn {
  display: block;
  width: 100%;
  padding: 13px;
  border: none;
  border-radius: 12px;
  background: var(--primary);
  color: #fff;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.15s ease;
}
a.btn:hover, button.btn:hover { background: var(--primary-dark); }
a.btn.secondary { background: #eef2f6; color: var(--text); }
a.btn.secondary:hover { background: var(--border); }
.lock {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  font-size: 12px; color: var(--text-secondary); margin-top: 20px;
}
"""


def _error_response(error):
    return jsonify({"success": False, "error": error.code}), error.status


def _format_vnd(amount, currency):
    """"520.000 đ" style formatting, matching web/frontend/js/admin.js's
    money() -- dot thousands separator, đ suffix. Falls back to a plain
    "<amount> <currency>" for anything that isn't a clean VND integer,
    rather than raising on unexpected data mid checkout-redirect."""
    currency = (currency or "VND").upper()
    try:
        value = int(amount)
    except (TypeError, ValueError):
        return f"{amount} {currency}"
    grouped = f"{value:,}".replace(",", ".")
    return f"{grouped} đ" if currency == "VND" else f"{grouped} {currency}"


def _configuration_error():
    environment = str(current_app.config.get("SEPAY_ENV", "sandbox")).lower()
    if environment not in {"sandbox", "production"}:
        return "invalid_sepay_environment"
    expected_url = (
        "https://pay.sepay.vn/v1/checkout/init"
        if environment == "production"
        else "https://pay-sandbox.sepay.vn/v1/checkout/init"
    )
    configured_url = str(current_app.config.get("SEPAY_CHECKOUT_URL", "")).rstrip("/")
    if configured_url != expected_url:
        return "sepay_environment_mismatch"
    required_config = (
        current_app.config.get("SEPAY_MERCHANT_ID"),
        current_app.config.get("SEPAY_SECRET_KEY"),
        current_app.config.get("SEPAY_IPN_SECRET_KEY"),
    )
    return None if all(required_config) else "sepay_not_configured"


@payments_bp.post("/sepay/checkout")
def create_sepay_checkout():
    user_id = get_current_user_id(request)
    if not user_id or user_id == "default":
        return jsonify({"error": "not_authenticated", "auth_scope": "app"}), 401
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    configuration_error = _configuration_error()
    if configuration_error:
        return jsonify({"success": False, "error": configuration_error}), 503
    try:
        state = subscription_model.validate_action(user_id, action)
        if not state["eligible"]:
            error = "premium_already_active" if state["allowed_action"] == "renew" else "no_active_premium"
            return jsonify({
                "success": False,
                "error": error,
                "allowed_action": state["allowed_action"],
                "subscription": state,
            }), 409
        payment = sepay_payment.create_checkout(
            user_id,
            data.get("plan_code"),
            action,
            data.get("payment_method"),
        )
    except ValueError:
        return jsonify({"success": False, "error": "invalid_subscription_action"}), 400
    except sepay_payment.SepayPaymentError as error:
        return _error_response(error)

    checkout_url = url_for(
        "payments.start_sepay_checkout",
        token=payment["checkout_token"],
        _external=True,
    )
    return jsonify({
        "success": True,
        "checkout_url": checkout_url,
        "invoice_number": payment["provider_payment_id"],
        "environment": current_app.config.get("SEPAY_ENV", "sandbox"),
    }), 201


@payments_bp.get("/sepay/start/<token>")
def start_sepay_checkout(token):
    configuration_error = _configuration_error()
    if configuration_error:
        return Response(configuration_error, status=503, mimetype="text/plain")
    payment = sepay_payment.get_checkout_by_token(token)
    if not payment:
        return Response("Checkout not found.", status=404, mimetype="text/plain")
    if payment.get("status") != "pending":
        return Response("Checkout is no longer pending.", status=409, mimetype="text/plain")
    invoice = payment["provider_payment_id"]
    callbacks = {
        outcome: url_for(
            "payments.sepay_result",
            outcome=outcome,
            invoice=invoice,
            _external=True,
        )
        for outcome in ("success", "error", "cancel")
    }
    try:
        fields = sepay_payment.checkout_fields(
            payment,
            current_app.config.get("SEPAY_MERCHANT_ID", ""),
            current_app.config.get("SEPAY_SECRET_KEY", ""),
            callbacks,
        )
    except sepay_payment.SepayPaymentError as error:
        return Response(error.code, status=error.status, mimetype="text/plain")

    inputs = "\n".join(
        f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(str(value), quote=True)}">'
        for key, value in fields.items()
    )
    action = html.escape(current_app.config.get("SEPAY_CHECKOUT_URL", ""), quote=True)
    metadata = payment.get("metadata") or {}
    plan_name = html.escape(str(metadata.get("plan_name") or "FlowMate Premium"))
    amount = html.escape(_format_vnd(payment.get("gross_amount"), payment.get("currency")))
    invoice_display = html.escape(str(invoice))
    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlowMate - Chuyển đến SEPay</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<style>{_SEPAY_PAGE_STYLE}</style></head>
<body>
<main>
<img class="logo" src="/img/logo.png" alt="FlowMate">
<div class="spinner" role="status" aria-label="Đang chuyển hướng"></div>
<h1>Đang chuyển đến cổng thanh toán SEPay…</h1>
<p class="detail">Vui lòng đợi trong giây lát, bạn sẽ được chuyển tới trang thanh toán an toàn của SEPay.</p>
<div class="summary">
<div><span>Gói</span><span>{plan_name}</span></div>
<div><span>Số tiền</span><span>{amount}</span></div>
<div><span>Mã đơn</span><span>{invoice_display}</span></div>
</div>
<form id="sepay-checkout" method="post" action="{action}">{inputs}
<button type="submit" class="btn">Tiếp tục thanh toán</button>
</form>
<div class="lock">🔒 Kết nối bảo mật qua SEPay</div>
</main>
<script>document.getElementById('sepay-checkout').submit();</script>
</body></html>"""
    return Response(page, mimetype="text/html")


def _sepay_ipn_provided_secret(req):
    """SePay's "API Key" webhook auth (its only simple shared-secret option
    -- the other choices are "Khong xac thuc", this, HMAC-SHA256, or OAuth
    2.0) sends `Authorization: Apikey <key>`, not a custom header. Fall back
    to X-Secret-Key for any caller still using that shape."""
    auth_header = (req.headers.get("Authorization") or "").strip()
    scheme, _, value = auth_header.partition(" ")
    if scheme.lower() == "apikey" and value:
        return value.strip()
    return req.headers.get("X-Secret-Key", "")


@payments_bp.post("/sepay/ipn")
def sepay_ipn():
    expected_secret = current_app.config.get("SEPAY_IPN_SECRET_KEY", "")
    provided_secret = _sepay_ipn_provided_secret(request)
    if not expected_secret:
        return jsonify({"success": False, "error": "sepay_ipn_not_configured"}), 503
    if not hmac.compare_digest(provided_secret, expected_secret):
        return jsonify({"success": False, "error": "invalid_ipn_secret"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "invalid_ipn_payload"}), 400
    try:
        timestamp = int(payload.get("timestamp"))
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp <= 0:
        return jsonify({"success": False, "error": "invalid_ipn_timestamp"}), 400
    notification_type = str(payload.get("notification_type") or "").upper()
    try:
        if notification_type == "ORDER_PAID":
            result = sepay_payment.process_order_paid(payload)
            if result.get("user_id") and not result.get("duplicate"):
                WorkspaceSync.bump(result["user_id"], ("profile", "settings", "overview"))
        elif notification_type == "TRANSACTION_VOID":
            result = sepay_payment.process_transaction_void(payload)
        else:
            return jsonify({"success": False, "error": "unsupported_notification_type"}), 400
    except sepay_payment.SepayPaymentError as error:
        return _error_response(error)
    return jsonify({"success": True, "duplicate": bool(result.get("duplicate"))})


@payments_bp.get("/sepay/status/<invoice>")
def sepay_payment_status(invoice):
    user_id = get_current_user_id(request)
    payment = sepay_payment.get_payment_status(invoice, user_id=user_id)
    if not payment:
        return jsonify({"success": False, "error": "payment_not_found"}), 404
    return jsonify({"success": True, "payment": payment})


_SEPAY_RESULT_ICONS = {
    "success": (
        "success",
        '<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" '
        'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
    ),
    "pending": (
        "warning",
        '<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
    ),
    "muted": (
        "muted",
        '<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    ),
}


@payments_bp.get("/sepay/result/<outcome>")
def sepay_result(outcome):
    if outcome not in {"success", "error", "cancel"}:
        return Response("Invalid payment result.", status=404, mimetype="text/plain")
    invoice = str(request.args.get("invoice") or "")[:80]
    payment = sepay_payment.get_payment_status(invoice)
    paid = bool(payment and payment.get("status") == "paid")
    if paid:
        title = "Thanh toán thành công"
        detail = "FlowMate Premium đã được kích hoạt cho tài khoản của bạn."
        icon_key = "success"
    elif outcome == "success":
        title = "Đang xác nhận thanh toán"
        detail = "SEPay đang gửi xác nhận về FlowMate. Vui lòng làm mới trạng thái sau ít phút."
        icon_key = "pending"
    elif outcome == "cancel":
        title = "Đã hủy thanh toán"
        detail = "Gói Premium chưa được thay đổi. Bạn có thể thử lại bất cứ lúc nào."
        icon_key = "muted"
    else:
        title = "Thanh toán chưa hoàn tất"
        detail = "Có sự cố khi xử lý thanh toán. Bạn có thể quay lại FlowMate và thử lại."
        icon_key = "muted"
    icon_class, icon_svg = _SEPAY_RESULT_ICONS[icon_key]
    deep_link = f"flowmateai://payment-result?status={html.escape(outcome)}&invoice={html.escape(invoice)}"
    web_link = f"/app?payment={html.escape(outcome)}&invoice={html.escape(invoice)}"
    invoice_row = (
        f'<div class="summary"><div><span>Mã đơn</span><span>{html.escape(invoice)}</span></div></div>'
        if invoice
        else ""
    )
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} - FlowMate</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<style>{_SEPAY_PAGE_STYLE}</style></head>
<body>
<main>
<img class="logo" src="/img/logo.png" alt="FlowMate">
<div class="status-icon {icon_class}">{icon_svg}</div>
<h1>{title}</h1>
<p class="detail">{detail}</p>
{invoice_row}
<div class="actions">
<a class="btn" href="{deep_link}">Mở FlowMate Mobile</a>
<a class="btn secondary" href="{web_link}">Mở FlowMate Web</a>
</div>
</main>
</body></html>"""
    return Response(page, mimetype="text/html")
