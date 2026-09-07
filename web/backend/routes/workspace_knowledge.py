"""Business Knowledge API: workspace-curated policy/template/FAQ docs.

Phase 5 ("Advanced workspace and AI") of WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md,
section 8.7. Mirrors routes/work_hub.py's shape exactly (WorkspaceError-style
exceptions mapped to stable HTTP status codes, strict tenant resolution via
workspace_model.resolve_context, membership/role checks resolved once per
request) -- this is the same kind of business-data route, not Bob, so a
stale/invalid X-Workspace-Id header fails loudly rather than silently
falling back to the caller's personal workspace.

Auto/web/mentor-learned personal knowledge (services/chat_agents/common.py,
freeform_agent.py) never flows through here -- Bob does not decide on its
own that a personal fact belongs to the company (Phase 4's confirm-before-
sharing principle). Only an explicit owner/admin write via this API creates
a workspace-scoped knowledge_documents row.
"""

from flask import Blueprint, jsonify, request, session

from models import workspace as workspace_model
from models import workspace_subscription
from routes.knowledge import knowledge_service
from utils.security import header_workspace_id
from utils.user_context import get_current_user_id

workspace_knowledge_bp = Blueprint('workspace_knowledge', __name__, url_prefix='/api/workspace-knowledge')

_ERROR_STATUS = {
    'membership_required': 403,
    'insufficient_role': 403,
    'workspace_not_found': 404,
    'workspace_read_only': 403,
    'knowledge_not_found': 404,
    'knowledge_title_required': 400,
    'knowledge_content_required': 400,
}

_MANAGE_ROLES = ('owner', 'admin')


def _error_response(exc):
    status = _ERROR_STATUS.get(exc.code, 400)
    body = {'error': exc.code}
    body.update(exc.extra)
    return jsonify(body), status


def _resolve():
    """Auth + strict tenant resolution shared by every handler below.

    Returns (user_id, workspace, membership). Raises WorkspaceError, which
    callers must catch and pass to _error_response.
    """
    user_id = get_current_user_id(request, session=session)
    workspace, membership = workspace_model.resolve_context(user_id, header_workspace_id())
    if membership is None or membership.get('status') != 'active':
        raise workspace_model.WorkspaceError('membership_required')
    return user_id, workspace, membership


def _require_manage_role(membership):
    if membership.get('role') not in _MANAGE_ROLES:
        raise workspace_model.WorkspaceError('insufficient_role')


@workspace_knowledge_bp.route('', methods=['GET'])
def list_documents():
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    documents = knowledge_service.list_for_workspace(workspace['id'])
    return jsonify({'success': True, 'documents': documents, 'count': len(documents)})


@workspace_knowledge_bp.route('', methods=['POST'])
def create_document():
    try:
        user_id, workspace, membership = _resolve()
        _require_manage_role(membership)
        workspace_subscription.assert_writable(workspace)
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError) as exc:
        return _error_response(exc)

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    tags = (data.get('tags') or '').strip()
    if not title:
        return _error_response(workspace_model.WorkspaceError('knowledge_title_required'))
    if not content:
        return _error_response(workspace_model.WorkspaceError('knowledge_content_required'))

    document = knowledge_service.add_document(
        title, content, tags=tags, source='manual',
        workspace_id=workspace['id'], created_by_user_id=user_id,
    )
    return jsonify({'success': True, 'document': document}), 201


@workspace_knowledge_bp.route('/<int:doc_id>', methods=['PATCH'])
def update_document(doc_id):
    try:
        user_id, workspace, membership = _resolve()
        _require_manage_role(membership)
        workspace_subscription.assert_writable(workspace)
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError) as exc:
        return _error_response(exc)

    existing = knowledge_service.get_workspace_document(workspace['id'], doc_id)
    if existing is None:
        return _error_response(workspace_model.WorkspaceError('knowledge_not_found'))

    data = request.get_json(silent=True) or {}
    title = data.get('title')
    content = data.get('content')
    tags = data.get('tags')
    if title is not None and not title.strip():
        return _error_response(workspace_model.WorkspaceError('knowledge_title_required'))
    if content is not None and not content.strip():
        return _error_response(workspace_model.WorkspaceError('knowledge_content_required'))

    document = knowledge_service.update_document(
        doc_id,
        title=title.strip() if title is not None else None,
        content=content.strip() if content is not None else None,
        tags=tags.strip() if tags is not None else None,
    )
    return jsonify({'success': True, 'document': document})


@workspace_knowledge_bp.route('/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    try:
        user_id, workspace, membership = _resolve()
        _require_manage_role(membership)
        workspace_subscription.assert_writable(workspace)
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError) as exc:
        return _error_response(exc)

    existing = knowledge_service.get_workspace_document(workspace['id'], doc_id)
    if existing is None:
        return _error_response(workspace_model.WorkspaceError('knowledge_not_found'))

    knowledge_service.delete_document(doc_id)
    return jsonify({'success': True})
