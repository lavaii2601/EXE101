"""Reply/forward compose/send.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import logging

from flask import jsonify, request, session, url_for

from models.history import History
from services.email_html_sanitizer import sanitize_email_html
from services.gmail_service import GmailService
from utils.user_context import get_current_user_id, get_user_db_path

from routes.email.shared import email_bp
from routes.email.oauth import _load_gmail_service

# Configure module logger
logger = logging.getLogger(__name__)

# Gmail itself caps a full outgoing message (headers + body + attachments,
# after base64 encoding) at 25MB. Base64 inflates raw bytes by ~4/3, so cap
# the raw attachment bytes well under that so the encoded message still has
# headroom for the body/headers.
MAX_ATTACHMENT_BYTES_TOTAL = 18 * 1024 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 10


def _collect_uploaded_attachments():
    """Read attachment files from a multipart/form-data request (field name
    'attachments', possibly repeated). Returns (attachments, error_response).
    error_response is a (dict, status) tuple on validation failure, else None."""
    files = request.files.getlist('attachments')
    if not files:
        return [], None
    if len(files) > MAX_ATTACHMENTS_PER_MESSAGE:
        return None, ({'error': f'Tối đa {MAX_ATTACHMENTS_PER_MESSAGE} tệp đính kèm mỗi email'}, 400)

    attachments = []
    total_bytes = 0
    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        data = file_storage.read()
        total_bytes += len(data)
        if total_bytes > MAX_ATTACHMENT_BYTES_TOTAL:
            return None, ({
                'error': f'Tổng dung lượng đính kèm vượt quá {MAX_ATTACHMENT_BYTES_TOTAL // (1024 * 1024)}MB'
            }, 400)
        attachments.append({
            'filename': file_storage.filename,
            'mime_type': file_storage.mimetype or 'application/octet-stream',
            'data': data,
        })
    return attachments, None


def _collect_inline_images():
    """Read inline-image files from a multipart/form-data request (field
    name 'inline_images'), paired in upload order with repeated
    'inline_image_ids' text fields -- the content_id the composer already
    embedded as src="cid:<id>" in body_html before upload. Returns
    (inline_images, error_response); error_response is a (dict, status)
    tuple on validation failure, else None."""
    files = request.files.getlist('inline_images')
    if not files:
        return [], None
    content_ids = request.form.getlist('inline_image_ids')
    if len(content_ids) != len(files):
        return None, ({'error': 'Mismatched inline image count'}, 400)
    if len(files) > MAX_ATTACHMENTS_PER_MESSAGE:
        return None, ({'error': f'Tối đa {MAX_ATTACHMENTS_PER_MESSAGE} ảnh chèn trực tiếp mỗi email'}, 400)

    inline_images = []
    for file_storage, content_id in zip(files, content_ids):
        if not file_storage or not file_storage.filename or not content_id:
            continue
        inline_images.append({
            'filename': file_storage.filename,
            'mime_type': file_storage.mimetype or 'application/octet-stream',
            'data': file_storage.read(),
            'content_id': content_id,
        })
    return inline_images, None


def _check_combined_attachment_budget(attachments, inline_images):
    """attachments and inline_images are collected (and budget-checked)
    separately, but both count against the same outgoing-message size
    Gmail itself enforces -- reject here if the combined total is over,
    even when each individually passed its own check."""
    total_bytes = (
        sum(len(a.get('data') or b'') for a in attachments)
        + sum(len(i.get('data') or b'') for i in inline_images)
    )
    if total_bytes > MAX_ATTACHMENT_BYTES_TOTAL:
        return {'error': f'Tổng dung lượng đính kèm vượt quá {MAX_ATTACHMENT_BYTES_TOTAL // (1024 * 1024)}MB'}, 400
    return None


def _request_field(name, default=''):
    """Read one field from either a JSON body or multipart/form-data, so
    callers without attachments can keep sending plain JSON unchanged."""
    if request.content_type and 'multipart/form-data' in request.content_type:
        return (request.form.get(name) or default).strip()
    data = request.get_json(silent=True) or {}
    return str(data.get(name) or default).strip()


@email_bp.route('/send-reply', methods=['POST'])
def send_email_reply():
    """Send a new email or a reply; requires authentication. Accepts either
    application/json (no attachments) or multipart/form-data (optional
    'attachments' files)."""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    db_path = get_user_db_path(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated', 'auth_url': url_for('email.gmail_auth', _external=True)}), 401

    to_email = _request_field('to')
    cc = _request_field('cc')
    bcc = _request_field('bcc')
    subject = _request_field('subject')
    body = _request_field('body')
    body_html = _request_field('body_html')
    in_reply_to_id = _request_field('in_reply_to_id')

    if not to_email or not subject or not (body or body_html):
        return jsonify({'error': 'Missing email details'}), 400

    attachments, error_response = _collect_uploaded_attachments()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    inline_images, error_response = _collect_inline_images()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    error_response = _check_combined_attachment_budget(attachments, inline_images)
    if error_response:
        return jsonify(error_response[0]), error_response[1]

    # Allow-list sanitized before it ever leaves FlowMate as a real email --
    # the composer only ever produces safe formatting tags, but this is the
    # one place that content actually reaches someone else's inbox.
    sanitized_body_html = sanitize_email_html(body_html) if body_html else None
    # An image-only message (no typed text) still needs a non-empty plain-
    # text alternative for clients that don't render HTML -- derive one
    # from the HTML itself rather than sending an empty text/plain part.
    if not body and sanitized_body_html:
        body = GmailService._html_to_text(sanitized_body_html).strip() or 'Xem nội dung HTML đính kèm.'

    thread_id = None
    rfc_in_reply_to = None
    rfc_references = None
    if in_reply_to_id:
        original = service.get_email_details(in_reply_to_id, lazy=True)
        if original:
            thread_id = original.get('thread_id') or None
            rfc_in_reply_to = original.get('rfc_message_id') or None
            if rfc_in_reply_to:
                existing_references = original.get('references') or ''
                rfc_references = f"{existing_references} {rfc_in_reply_to}".strip()

    try:
        success = service.send_email(
            to_email, subject, body,
            cc=cc or None, bcc=bcc or None,
            attachments=attachments,
            thread_id=thread_id,
            in_reply_to=rfc_in_reply_to,
            references=rfc_references,
            body_html=sanitized_body_html,
            inline_images=inline_images,
        )
        if success:
            History.create(f"Gửi email tới {to_email}", body, action_type='email_sent', db_path=db_path)
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to send email'}), 500
    except Exception as e:
        logger.exception("Failed to send email to %s", to_email)
        return jsonify({'error': str(e)}), 500


@email_bp.route('/forward', methods=['POST'])
def forward_email():
    """Forward an existing email (with its original attachments re-attached)
    to new recipients, optionally with extra new attachments and a note."""
    user_id = get_current_user_id(request, session=session)
    service = _load_gmail_service(user_id)
    db_path = get_user_db_path(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated', 'auth_url': url_for('email.gmail_auth', _external=True)}), 401

    message_id = _request_field('message_id')
    to_email = _request_field('to')
    cc = _request_field('cc')
    bcc = _request_field('bcc')
    note = _request_field('body')

    if not message_id or not to_email:
        return jsonify({'error': 'Missing forward details'}), 400

    original = service.get_email_details(message_id, lazy=False)
    if not original:
        return jsonify({'error': 'Original email not found'}), 404

    subject = original.get('subject') or ''
    if not subject.lower().startswith('fwd:'):
        subject = f"Fwd: {subject}"

    quoted = (
        f"\n\n---------- Forwarded message ---------\n"
        f"From: {original.get('sender', '')}\n"
        f"Date: {original.get('date', '')}\n"
        f"Subject: {original.get('subject', '')}\n"
        f"To: {original.get('to', '')}\n\n"
        f"{original.get('body', '')}"
    )
    body = f"{note}{quoted}" if note else quoted.lstrip('\n')

    new_attachments, error_response = _collect_uploaded_attachments()
    if error_response:
        return jsonify(error_response[0]), error_response[1]

    original_attachments = []
    total_bytes = sum(len(a.get('data') or b'') for a in new_attachments)
    for meta in original.get('attachments') or []:
        if len(new_attachments) + len(original_attachments) >= MAX_ATTACHMENTS_PER_MESSAGE:
            break
        fetched = service.get_attachment(message_id, meta.get('id'))
        if not fetched:
            continue
        total_bytes += len(fetched.get('data') or b'')
        if total_bytes > MAX_ATTACHMENT_BYTES_TOTAL:
            break
        original_attachments.append({
            'filename': fetched.get('filename'),
            'mime_type': fetched.get('mime_type'),
            'data': fetched.get('data'),
        })

    try:
        success = service.send_email(
            to_email, subject, body,
            cc=cc or None, bcc=bcc or None,
            attachments=new_attachments + original_attachments,
        )
        if success:
            History.create(f"Chuyển tiếp email tới {to_email}", body, action_type='email_sent', db_path=db_path)
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to forward email'}), 500
    except Exception as e:
        logger.exception("Failed to forward email %s to %s", message_id, to_email)
        return jsonify({'error': str(e)}), 500
