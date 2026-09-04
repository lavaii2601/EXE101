"""Work Hub API: shared projects, tasks, and manual Status Reports.

Phase 3 ("Bob Core va Status Report") of WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md,
sections 8.4-8.5. Mirrors routes/workspace.py's shape (WorkspaceError-style
exceptions mapped to stable HTTP status codes, membership/role checks
resolved once per request).

Workspace resolution here is the strict `workspace_model.resolve_context`
(raises on an invalid/foreign workspace id), not the soft
`utils.user_context.get_current_workspace_id` that chat routes use --
these are business-data routes like routes/workspace.py's own, not Bob,
so a stale/invalid X-Workspace-Id header should fail loudly rather than
silently falling back to the caller's personal workspace.
"""

from flask import Blueprint, jsonify, request, session

from models import project as project_model
from models import status_report as status_report_model
from models import task as task_model
from models import workspace as workspace_model
from models import workspace_subscription
from utils.security import header_workspace_id
from utils.user_context import get_current_user_id

work_hub_bp = Blueprint('work_hub', __name__, url_prefix='/api')

_ERROR_STATUS = {
    'membership_required': 403,
    'insufficient_role': 403,
    'workspace_not_found': 404,
    'workspace_read_only': 403,
    'project_not_found': 404,
    'project_name_required': 400,
    'invalid_project_status': 400,
    'invalid_visibility': 400,
    'task_not_found': 404,
    'task_title_required': 400,
    'invalid_task_status': 400,
    'invalid_task_priority': 400,
    'report_not_found': 404,
    'report_not_editable': 409,
    'report_not_author': 403,
    'report_empty': 400,
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


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@work_hub_bp.route('/projects', methods=['GET'])
def list_projects():
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    status = request.args.get('status')
    projects = project_model.list_projects(workspace['id'], user_id, membership['role'], status=status)
    return jsonify({'success': True, 'projects': projects})


@work_hub_bp.route('/projects', methods=['POST'])
def create_project():
    try:
        user_id, workspace, membership = _resolve()
        _require_manage_role(membership)
        workspace_subscription.assert_writable(workspace)
        data = request.get_json(silent=True) or {}
        project = project_model.create_project(
            workspace['id'], user_id,
            name=data.get('name', ''),
            description=data.get('description'),
            status=data.get('status', 'planning'),
            visibility=data.get('visibility', 'workspace'),
            owner_user_id=data.get('owner_user_id'),
            start_date=data.get('start_date'),
            due_date=data.get('due_date'),
        )
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            project_model.ProjectError) as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'project': project}), 201


@work_hub_bp.route('/projects/<project_id>', methods=['GET'])
def get_project(project_id):
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    project = project_model.get_project(workspace['id'], project_id)
    if project is None or not project_model.is_project_visible(project, user_id, membership['role']):
        return _error_response(project_model.ProjectError('project_not_found'))
    project['can_manage'] = project_model.can_manage_project(project, user_id, membership['role'])
    return jsonify({'success': True, 'project': project})


@work_hub_bp.route('/projects/<project_id>', methods=['PATCH'])
def patch_project(project_id):
    try:
        user_id, workspace, membership = _resolve()
        existing = project_model.get_project(workspace['id'], project_id)
        if existing is None:
            raise project_model.ProjectError('project_not_found')
        if not project_model.can_manage_project(existing, user_id, membership['role']):
            raise workspace_model.WorkspaceError('insufficient_role')
        workspace_subscription.assert_writable(workspace)
        data = request.get_json(silent=True) or {}
        project = project_model.update_project(
            workspace['id'], project_id, user_id,
            name=data.get('name'), description=data.get('description'),
            status=data.get('status'), visibility=data.get('visibility'),
            owner_user_id=data.get('owner_user_id'),
            start_date=data.get('start_date'), due_date=data.get('due_date'),
        )
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            project_model.ProjectError) as exc:
        return _error_response(exc)
    if project is None:
        return _error_response(project_model.ProjectError('project_not_found'))
    return jsonify({'success': True, 'project': project})


@work_hub_bp.route('/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    try:
        user_id, workspace, membership = _resolve()
        _require_manage_role(membership)
        workspace_subscription.assert_writable(workspace)
        deleted = project_model.delete_project(workspace['id'], project_id, user_id)
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError) as exc:
        return _error_response(exc)
    if not deleted:
        return _error_response(project_model.ProjectError('project_not_found'))
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@work_hub_bp.route('/tasks', methods=['GET'])
def list_tasks():
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    tasks = task_model.list_tasks(
        workspace['id'], user_id, membership['role'],
        project_id=request.args.get('project_id'),
        status=request.args.get('status'),
        assignee_user_id=request.args.get('assignee_user_id'),
    )
    return jsonify({'success': True, 'tasks': tasks})


@work_hub_bp.route('/tasks', methods=['POST'])
def create_task():
    try:
        user_id, workspace, membership = _resolve()
        workspace_subscription.assert_writable(workspace)
        data = request.get_json(silent=True) or {}
        project_id = data.get('project_id')
        project = project_model.get_project(workspace['id'], project_id) if project_id else None
        if project is None or not project_model.is_project_visible(project, user_id, membership['role']):
            raise task_model.TaskError('project_not_found')
        task = task_model.create_task(
            workspace['id'], project_id, user_id,
            title=data.get('title', ''),
            description=data.get('description'),
            status=data.get('status', 'todo'),
            priority=data.get('priority', 'medium'),
            visibility=data.get('visibility', 'workspace'),
            assignee_user_id=data.get('assignee_user_id'),
            due_date=data.get('due_date'),
            blocker=data.get('blocker'),
        )
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            task_model.TaskError) as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'task': task}), 201


@work_hub_bp.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    task = task_model.get_task(workspace['id'], task_id)
    if task is None:
        return _error_response(task_model.TaskError('task_not_found'))
    project = project_model.get_project(workspace['id'], task['project_id'])
    if project is None or not task_model.is_task_visible(task, project, user_id, membership['role']):
        return _error_response(task_model.TaskError('task_not_found'))
    task['can_manage'] = task_model.can_manage_task(task, project, user_id, membership['role'])
    return jsonify({'success': True, 'task': task})


@work_hub_bp.route('/tasks/<task_id>', methods=['PATCH'])
def patch_task(task_id):
    try:
        user_id, workspace, membership = _resolve()
        existing = task_model.get_task(workspace['id'], task_id)
        if existing is None:
            raise task_model.TaskError('task_not_found')
        project = project_model.get_project(workspace['id'], existing['project_id'])
        if project is None or not task_model.can_manage_task(existing, project, user_id, membership['role']):
            raise workspace_model.WorkspaceError('insufficient_role')
        workspace_subscription.assert_writable(workspace)
        data = request.get_json(silent=True) or {}
        task = task_model.update_task(
            workspace['id'], task_id, user_id,
            title=data.get('title'), description=data.get('description'),
            status=data.get('status'), priority=data.get('priority'),
            visibility=data.get('visibility'), assignee_user_id=data.get('assignee_user_id'),
            due_date=data.get('due_date'), blocker=data.get('blocker'),
        )
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            task_model.TaskError) as exc:
        return _error_response(exc)
    if task is None:
        return _error_response(task_model.TaskError('task_not_found'))
    return jsonify({'success': True, 'task': task})


@work_hub_bp.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    try:
        user_id, workspace, membership = _resolve()
        existing = task_model.get_task(workspace['id'], task_id)
        if existing is None:
            raise task_model.TaskError('task_not_found')
        project = project_model.get_project(workspace['id'], existing['project_id'])
        if project is None or not task_model.can_manage_task(existing, project, user_id, membership['role']):
            raise workspace_model.WorkspaceError('insufficient_role')
        workspace_subscription.assert_writable(workspace)
        deleted = task_model.delete_task(workspace['id'], task_id, user_id)
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            task_model.TaskError) as exc:
        return _error_response(exc)
    if not deleted:
        return _error_response(task_model.TaskError('task_not_found'))
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Status reports
# ---------------------------------------------------------------------------

@work_hub_bp.route('/status-reports', methods=['GET'])
def list_status_reports():
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    reports = status_report_model.list_reports(
        workspace['id'], user_id, membership['role'],
        project_id=request.args.get('project_id'),
        author_user_id=request.args.get('author_user_id'),
        status=request.args.get('status'),
    )
    return jsonify({'success': True, 'reports': reports})


@work_hub_bp.route('/status-reports', methods=['POST'])
def create_status_report():
    try:
        user_id, workspace, membership = _resolve()
        workspace_subscription.assert_writable(workspace)
        data = request.get_json(silent=True) or {}
        report = status_report_model.create_draft(
            workspace['id'], user_id,
            project_id=data.get('project_id'),
            report_date=data.get('report_date'),
            visibility=data.get('visibility', 'workspace'),
            done_text=data.get('done_text', ''),
            doing_text=data.get('doing_text', ''),
            blocked_text=data.get('blocked_text', ''),
            next_text=data.get('next_text', ''),
            risks_text=data.get('risks_text', ''),
        )
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            status_report_model.StatusReportError) as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'report': report}), 201


@work_hub_bp.route('/status-reports/<report_id>', methods=['GET'])
def get_status_report(report_id):
    try:
        user_id, workspace, membership = _resolve()
    except workspace_model.WorkspaceError as exc:
        return _error_response(exc)
    report = status_report_model.get_report(workspace['id'], report_id)
    if report is None or not status_report_model.is_report_visible(report, user_id, membership['role']):
        return _error_response(status_report_model.StatusReportError('report_not_found'))
    return jsonify({'success': True, 'report': report})


@work_hub_bp.route('/status-reports/<report_id>', methods=['PATCH'])
def patch_status_report(report_id):
    try:
        user_id, workspace, membership = _resolve()
        workspace_subscription.assert_writable(workspace)
        data = request.get_json(silent=True) or {}
        report = status_report_model.update_draft(
            workspace['id'], report_id, user_id,
            project_id=data.get('project_id'), report_date=data.get('report_date'),
            visibility=data.get('visibility'),
            done_text=data.get('done_text'), doing_text=data.get('doing_text'),
            blocked_text=data.get('blocked_text'), next_text=data.get('next_text'),
            risks_text=data.get('risks_text'),
        )
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            status_report_model.StatusReportError) as exc:
        return _error_response(exc)
    if report is None:
        return _error_response(status_report_model.StatusReportError('report_not_found'))
    return jsonify({'success': True, 'report': report})


@work_hub_bp.route('/status-reports/<report_id>/publish', methods=['POST'])
def publish_status_report(report_id):
    try:
        user_id, workspace, membership = _resolve()
        workspace_subscription.assert_writable(workspace)
        report = status_report_model.publish_report(workspace['id'], report_id, user_id)
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            status_report_model.StatusReportError) as exc:
        return _error_response(exc)
    return jsonify({'success': True, 'report': report})


@work_hub_bp.route('/status-reports/<report_id>', methods=['DELETE'])
def delete_status_report(report_id):
    try:
        user_id, workspace, membership = _resolve()
        workspace_subscription.assert_writable(workspace)
        deleted = status_report_model.delete_report(workspace['id'], report_id, user_id, membership['role'])
    except (workspace_model.WorkspaceError, workspace_subscription.WorkspaceSubscriptionError,
            status_report_model.StatusReportError) as exc:
        return _error_response(exc)
    if not deleted:
        return _error_response(status_report_model.StatusReportError('report_not_found'))
    return jsonify({'success': True})
