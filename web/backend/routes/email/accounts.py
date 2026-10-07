"""Linked Google accounts: list, switch, and unlink multiple Gmail/Calendar
accounts under one FlowMate user. See utils/user_context.py's
list_google_accounts/activate_google_account/delete_google_credentials for
the credential-layer mechanics (the "active slot" design) -- these routes
are a thin HTTP wrapper around that, plus mirroring the active account onto
users.gmail_* so every existing single-account-shaped reader (admin
dashboard, /api/user/gmail-info, chat agents, overview service) keeps
working unmodified.

Split out of routes/email/oauth.py -- see routes/email/__init__.py for the
package-level overview.
"""
import logging

from flask import jsonify, request, session

from models.cache import Cache
from models.user import User
from utils.user_context import (
    CredentialStoreError,
    activate_google_account,
    delete_google_credentials,
    get_current_user_id,
    get_user_db_path,
    list_google_accounts,
)

from routes.email.shared import email_bp, _clear_email_list_cache

logger = logging.getLogger(__name__)


def _mirror_active_account_onto_user(user_id, account):
    User.update(
        user_id,
        gmail_email=account.get('account_email') or '',
        gmail_name=account.get('account_name') or '',
        gmail_picture=account.get('account_picture') or '',
        gmail_connected=1,
    )


def _bust_mailbox_caches(user_id):
    # Gmail message ids are per-mailbox and could coincidentally collide
    # across two different linked mailboxes -- bust every cache for this
    # user (not just the email-list cache) so nothing from the
    # previously-active account's inbox lingers after a switch/unlink.
    db_path = get_user_db_path(user_id)
    _clear_email_list_cache(user_id)
    Cache.clear_pattern(f"{user_id}:*", db_path=db_path)


@email_bp.route('/accounts', methods=['GET'])
def list_linked_accounts():
    user_id = get_current_user_id(request, session=session)
    accounts = list_google_accounts(user_id)
    return jsonify({'success': True, 'accounts': accounts})


@email_bp.route('/accounts/activate', methods=['POST'])
def activate_linked_account():
    user_id = get_current_user_id(request, session=session)
    data = request.get_json(silent=True) or {}
    account_email = str(data.get('account_email') or '').strip().lower()
    if not account_email:
        return jsonify({'success': False, 'error': 'account_email_required'}), 400

    try:
        activate_google_account(user_id, account_email)
    except CredentialStoreError as exc:
        return jsonify({'success': False, 'error': 'account_not_found', 'message': str(exc)}), 404

    accounts = list_google_accounts(user_id)
    active = next((a for a in accounts if a.get('account_email') == account_email), None)
    if active:
        _mirror_active_account_onto_user(user_id, active)
    _bust_mailbox_caches(user_id)

    return jsonify({'success': True, 'accounts': accounts})


@email_bp.route('/accounts/<account_email>', methods=['DELETE'])
def unlink_account(account_email):
    user_id = get_current_user_id(request, session=session)
    account_email = str(account_email or '').strip().lower()
    if not account_email:
        return jsonify({'success': False, 'error': 'account_email_required'}), 400

    try:
        delete_google_credentials(user_id, account_email=account_email)
    except CredentialStoreError as exc:
        return jsonify({'success': False, 'error': 'unlink_failed', 'message': str(exc)}), 500

    accounts = list_google_accounts(user_id)
    active = next((a for a in accounts if a.get('is_active')), None)
    if active:
        _mirror_active_account_onto_user(user_id, active)
    else:
        # No linked account left -- matches the existing single-account
        # "disconnect Gmail" semantics for users.gmail_connected.
        User.update(user_id, gmail_connected=0)
    _bust_mailbox_caches(user_id)

    return jsonify({'success': True, 'accounts': accounts})
