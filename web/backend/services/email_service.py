import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email, reset_url):
    """Sends the password-reset link via Resend.

    Logs and returns on failure instead of raising -- forgot_password()
    must still return its generic success response either way, so a
    transient provider error never leaks account existence through a
    different response shape.
    """
    if not Config.RESEND_API_KEY:
        logger.warning('RESEND_API_KEY not configured; skipping password reset email to %s', to_email)
        return
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {Config.RESEND_API_KEY}'},
            json={
                'from': Config.RESEND_FROM_EMAIL,
                'to': [to_email],
                'subject': 'Đặt lại mật khẩu FlowMate',
                'html': (
                    '<p>Nhấn vào link sau để đặt lại mật khẩu FlowMate (hết hạn sau 30 phút):</p>'
                    f'<p><a href="{reset_url}">{reset_url}</a></p>'
                    '<p>Nếu bạn không yêu cầu điều này, hãy bỏ qua email này.</p>'
                ),
            },
            timeout=10,
        )
        if response.status_code >= 300:
            logger.error('Resend API error %s sending reset email: %s', response.status_code, response.text[:500])
    except requests.RequestException:
        logger.exception('Failed to send password reset email to %s', to_email)
