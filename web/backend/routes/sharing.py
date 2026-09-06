"""Privacy-first sharing API: confirm-before-sharing personal data into a
Business workspace, plus the cross-workspace "Sharing Center" view.

Phase 4 of WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md. Mirrors routes/work_hub.py's
shape, kept in its own file/blueprint rather than folded into work_hub_bp --
shared_artifacts is a distinctly higher-stakes privacy surface (someone's
personal data, not workspace-authored business content) than projects/tasks.
"""

from flask import Blueprint, jsonify, request, session

from models import shared_artifact as artifact_model
from models import workspace as workspace_model
from models import workspace_subscription
from utils.security import header_workspace_id
from utils.user_context import get_current_user_id

sharing_bp = Blueprint('sharing', __name__, url_prefix='/api')

_ERROR_STATUS = {
    'membership_required': 403,
    'insufficient_role': 403,
    'workspace_not_found': 404,
    'workspace_read_only': 403,
    'artifact_not_found': 404,
    'invalid_source_type': 400,
    'invalid_visibility': 400,
    'artifact_title_required': 400,
}


def _error_response(exc):
    status = _ERROR_STATUS.get(exc.code, 400)
    body = {'error': exc.code}
    body.update(exc.extra)
    return jsonify(body), status


def _resolve():
    """Auth + strict tenant resolution shared by every workspace-scoped
    handler below. Returns (user_id, workspace, membership). Raises
    WorkspaceError, which callers must catch and pass to _error_response."""
    user_id = get_current_user_id(request, session=session)
    workspace, membership = workspace_model.resolve_context(user_id, header_workspace_id())
    if membership is None or membership.get('status') != 'active':
        raise workspace_model.WorkspaceError('membership_required')
    return user_id, workspace, membership


@sharing_bp.route('/workspaces/<workspace_id>/shared-artifacts', methods=['GET'])
def list_shared_artifacts(workspace_id):
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    artifacts = artifact_model.list_artifacts(
        workspace['id'], user_id, membership['role'],
        source_type=request.args.get('source_type'),
    )
    return jsonify({'success': True, 'artifacts': artifacts})


@sharing_bp.route('/workspaces/<workspace_id>/shared-artifacts', methods=['POST'])
def create_shared_artifact(workspace_id):
    try:
        user_id, workspace, membership = _resolve()
        workspace_subscription.assert_writable(workspace)
        data = request.get_json(silent=True) or {}
        artifact = artifact_model.create_artifact(
            workspace['id'], user_id,
            source_type=data.get('source_type', ''),
            title=data.get('title', ''),
            content=data.get('content') or {},
            visibility=data.get('visibility', 'workspace'),
        )
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            artifact_model.ArtifactError) as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'artifact': artifact}), 201


@sharing_bp.route('/workspaces/<workspace_id>/shared-artifacts/<artifact_id>', methods=['DELETE'])
def revoke_shared_artifact(workspace_id, artifact_id):
    try:
        user_id, workspace, membership = _resolve()
        workspace_subscription.assert_writable(workspace)
        revoked = artifact_model.revoke_artifact(workspace['id'], artifact_id, user_id)
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            artifact_model.ArtifactError) as exc:
        return _error_response(exc)
    if not revoked:
        return _error_response(artifact_model.ArtifactError('artifact_not_found'))
    return jsonify({'success': True})


@sharing_bp.route('/user/sharing', methods=['GET'])
def list_my_sharing():
    """The caller's own cross-workspace "Trung tam chia se" (Sharing
    Center) -- everything they personally have shared, wherever they
    shared it. No workspace resolution needed: this is scoped to the
    caller's own user_id, not a specific workspace."""
    user_id = get_current_user_id(request, session=session)
    artifacts = artifact_model.list_my_shares(user_id)
    return jsonify({'success': True, 'artifacts': artifacts})
