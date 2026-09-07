"""Authenticated SEPay checkout plus public, secret-authenticated IPN."""

import hmac
import html

from flask import Blueprint, Response, current_app, jsonify, request, url_for

from models import sepay_payment
from models import subscription as subscription_model
from models.workspace_sync import WorkspaceSync
from utils.user_context import get_current_user_id


payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


def _error_response(error):
    return jsonify({"success": False, "error": error.code}), error.status


@payments_bp.post("/sepay/checkout")
def create_sepay_checkout():
    user_id = get_current_user_id(request)
    if not user_id or user_id == "default":
        return jsonify({"error": "not_authenticated", "auth_scope": "app"}), 401
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
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
    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlowMate - Chuyển đến SEPay</title></head>
<body><main><h1>Đang chuyển đến cổng thanh toán SEPay…</h1>
<form id="sepay-checkout" method="post" action="{action}">{inputs}
<noscript><button type="submit">Tiếp tục thanh toán</button></noscript></form></main>
<script>document.getElementById('sepay-checkout').submit();</script></body></html>"""
    return Response(page, mimetype="text/html")


@payments_bp.post("/sepay/ipn")
def sepay_ipn():
    expected_secret = current_app.config.get("SEPAY_IPN_SECRET_KEY", "")
    provided_secret = request.headers.get("X-Secret-Key", "")
    if not expected_secret:
        return jsonify({"success": False, "error": "sepay_ipn_not_configured"}), 503
    if not hmac.compare_digest(provided_secret, expected_secret):
        return jsonify({"success": False, "error": "invalid_ipn_secret"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "invalid_ipn_payload"}), 400
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


@payments_bp.get("/sepay/result/<outcome>")
def sepay_result(outcome):
    if outcome not in {"success", "error", "cancel"}:
        return Response("Invalid payment result.", status=404, mimetype="text/plain")
    invoice = str(request.args.get("invoice") or "")[:80]
    payment = sepay_payment.get_payment_status(invoice)
    paid = bool(payment and payment.get("status") == "paid")
    if paid:
        title = "Thanh toán thành công"
        detail = "FlowMate Premium đã được kích hoạt."
    elif outcome == "success":
        title = "Đang xác nhận thanh toán"
        detail = "SEPay đang gửi xác nhận về FlowMate. Vui lòng làm mới trạng thái sau ít phút."
    elif outcome == "cancel":
        title = "Đã hủy thanh toán"
        detail = "Gói Premium chưa được thay đổi."
    else:
        title = "Thanh toán chưa hoàn tất"
        detail = "Bạn có thể quay lại FlowMate và thử lại."
    deep_link = f"flowmateai://payment-result?status={html.escape(outcome)}&invoice={html.escape(invoice)}"
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} - FlowMate</title>
<style>body{{font-family:system-ui;background:#f5f7fb;color:#172033;display:grid;place-items:center;min-height:100vh;margin:0}}main{{background:white;padding:32px;border-radius:20px;box-shadow:0 12px 36px #1720331a;max-width:520px;text-align:center}}a{{display:inline-block;margin:8px;padding:12px 18px;border-radius:10px;background:#2563eb;color:white;text-decoration:none}}a.secondary{{background:#e8eef8;color:#172033}}</style></head>
<body><main><h1>{title}</h1><p>{detail}</p><p>Mã đơn: {html.escape(invoice)}</p>
<a href="{deep_link}">Mở FlowMate Mobile</a><a class="secondary" href="/app?payment={html.escape(outcome)}&invoice={html.escape(invoice)}">Mở FlowMate Web</a>
</main></body></html>"""
    return Response(page, mimetype="text/html")
