"""Multi-tenant workspace API (Phase 1 foundation).

See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md sections 10-11 for the full
contract. Two blueprints exist because the design doc's own API list splits
invitation accept/decline onto a separate /api/workspace-invitations path
(the invitee doesn't need to already know/be a member of the workspace_id
to act on their own invitation, so it isn't nested under /api/workspaces/<id>).
"""

from flask import Blueprint, jsonify, request, session

from models import workspace as workspace_model
from models.user import User
from utils.user_context import get_current_user_id

workspace_bp = Blueprint('workspace', __name__, url_prefix='/api/workspaces')
workspace_invitations_bp = Blueprint(
    'workspace_invitations', __name__, url_prefix='/api/workspace-invitations'
)

# Stable reason codes from design doc section 10.4, so web/mobile clients can
# branch on `error` without parsing message text.
_ERROR_STATUS = {
    'membership_required': 403,
    'insufficient_role': 403,
    'workspace_not_found': 404,
    'workspace_name_required': 400,
    'invalid_role': 400,
    'invalid_email': 400,
    'cannot_disable_owner': 400,
    'cannot_change_owner_role': 400,
    'membership_not_found': 404,
    'invitation_not_found': 404,
    'invitation_not_pending': 409,
    'invitation_expired': 410,
    'invitation_email_mismatch': 403,
}


def _error_response(exc):
    status = _ERROR_STATUS.get(exc.code, 400)
    body = {'error': exc.code}
    body.update(exc.extra)
    return jsonify(body), status


def _current_user_emails(user_id):
    """The two email addresses that count as this user's verified login email."""
    user = User.get(user_id) or {}
    return [e for e in (user.get('email'), user.get('gmail_email')) if e]


def _email_matches_any(candidate, emails):
    normalized = workspace_model.normalize_email(candidate)
    return any(normalized == workspace_model.normalize_email(e) for e in emails)


def _require_role(membership, allowed_roles):
    if not membership or membership.get('status') != 'active':
        raise workspace_model.WorkspaceError('membership_required')
    if membership.get('role') not in allowed_roles:
        raise workspace_model.WorkspaceError('insufficient_role')


@workspace_bp.route('', methods=['GET'])
def list_workspaces():
    user_id = get_current_user_id(request, session=session)
    workspace_model.ensure_personal_workspace(user_id)
    return jsonify({'success': True, 'workspaces': workspace_model.list_workspaces_for_user(user_id)})


@workspace_bp.route('', methods=['POST'])
def create_workspace():
    user_id = get_current_user_id(request, session=session)
    data = request.get_json(silent=True) or {}
    try:
        workspace = workspace_model.create_business_workspace(user_id, data.get('name', ''))
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'workspace': workspace}), 201


@workspace_bp.route('/<workspace_id>', methods=['GET'])
def get_workspace(workspace_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    try:
        _require_role(membership, workspace_model.ROLES)
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    workspace = workspace_model.get_workspace(workspace_id)
    if workspace is None:
        return _error_response(workspace_model.WorkspaceError('workspace_not_found'))
    return jsonify({'success': True, 'workspace': workspace, 'membership': membership})


@workspace_bp.route('/<workspace_id>', methods=['PATCH'])
def patch_workspace(workspace_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    try:
        _require_role(membership, ('owner', 'admin'))
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    data = request.get_json(silent=True) or {}
    workspace = workspace_model.update_workspace(
        workspace_id, user_id, name=data.get('name'), settings=data.get('settings'),
    )
    if workspace is None:
        return _error_response(workspace_model.WorkspaceError('workspace_not_found'))
    return jsonify({'success': True, 'workspace': workspace})


@workspace_bp.route('/<workspace_id>/members', methods=['GET'])
def list_members(workspace_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    try:
        _require_role(membership, workspace_model.ROLES)
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'members': workspace_model.list_members(workspace_id)})


@workspace_bp.route('/<workspace_id>/members/<target_user_id>/disable', methods=['POST'])
def disable_member(workspace_id, target_user_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    try:
        _require_role(membership, ('owner', 'admin'))
        result = workspace_model.disable_member(workspace_id, target_user_id, user_id)
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'membership': result})


@workspace_bp.route('/<workspace_id>/members/<target_user_id>/role', methods=['PATCH'])
def change_member_role(workspace_id, target_user_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    data = request.get_json(silent=True) or {}
    try:
        _require_role(membership, ('owner', 'admin'))
        result = workspace_model.update_member_role(
            workspace_id, target_user_id, data.get('role', ''), user_id,
        )
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'membership': result})


@workspace_bp.route('/<workspace_id>/invitations', methods=['GET'])
def list_invitations(workspace_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    try:
        _require_role(membership, ('owner', 'admin'))
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'invitations': workspace_model.list_invitations(workspace_id)})


@workspace_bp.route('/<workspace_id>/invitations', methods=['POST'])
def create_invitation(workspace_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    data = request.get_json(silent=True) or {}
    try:
        _require_role(membership, ('owner', 'admin'))
        invitation = workspace_model.create_invitation(
            workspace_id, data.get('email', ''), data.get('role', 'worker'), user_id,
        )
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    # The raw token only ever appears in this one response. In Phase 1 there
    # is no email delivery yet (see design doc section 1.1), so the
    # owner/admin is expected to relay the invite link out-of-band.
    return jsonify({'success': True, 'invitation': invitation}), 201


@workspace_bp.route('/<workspace_id>/invitations/<invitation_id>', methods=['DELETE'])
def revoke_invitation(workspace_id, invitation_id):
    user_id = get_current_user_id(request, session=session)
    membership = workspace_model.get_membership(workspace_id, user_id)
    try:
        _require_role(membership, ('owner', 'admin'))
        result = workspace_model.revoke_invitation(invitation_id, user_id)
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'invitation': result})


@workspace_invitations_bp.route('/<token>/accept', methods=['POST'])
def accept_invitation(token):
    user_id = get_current_user_id(request, session=session)
    emails = _current_user_emails(user_id)
    if not emails:
        return _error_response(workspace_model.WorkspaceError('invitation_email_mismatch'))
    try:
        invitation = workspace_model.find_invitation_by_token(token)
        if invitation is None:
            raise workspace_model.WorkspaceError('invitation_not_found')
        matched_email = next((e for e in emails if _email_matches_any(e, [invitation['email_normalized']])), None)
        if matched_email is None:
            raise workspace_model.WorkspaceError('invitation_email_mismatch')
        result = workspace_model.accept_invitation(token, user_id, matched_email)
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'invitation': result})


@workspace_invitations_bp.route('/<invitation_id>/decline', methods=['POST'])
def decline_invitation(invitation_id):
    user_id = get_current_user_id(request, session=session)
    emails = _current_user_emails(user_id)
    try:
        invitation = workspace_model.get_invitation(invitation_id)
        if invitation is None:
            raise workspace_model.WorkspaceError('invitation_not_found')
        matched_email = next(
            (e for e in emails if _email_matches_any(e, [invitation['email_normalized']])), None
        )
        if matched_email is None:
            raise workspace_model.WorkspaceError('invitation_email_mismatch')
        result = workspace_model.decline_invitation(invitation_id, user_id, matched_email)
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'invitation': result})
