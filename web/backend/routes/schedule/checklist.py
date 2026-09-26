"""Overview checklist: per-day cached checklist state (custom items plus
completed-map) backing the Overview page widget, and the two
/api/schedule/checklist routes that read/write it."""
from datetime import datetime

from flask import request, jsonify

from models.cache import Cache
from models.schedule import LOCAL_TZ
from models import entitlements
from utils.user_context import get_current_user_id, get_user_db_path

from .shared import schedule_bp

_CHECKLIST_CACHE_TTL_SECONDS = 365 * 24 * 60 * 60


def _checklist_cache_key(user_id, date_value):
    safe_date = str(date_value or '').strip().replace('%', '').replace(':', '-')
    return f"overview:checklist:{user_id}:{safe_date}"


def _custom_item_sort_key(item):
    completed = bool(item.get('completed'))
    pinned_rank = 0 if item.get('pinned') else 1
    due_value = item.get('due_at') or item.get('due_date') or '9999-12-31'
    priority = -int(item.get('priority_score') or 0)
    created = item.get('created_at') or ''
    return (completed, pinned_rank, due_value, priority, created)


def _sort_custom_items(items):
    return sorted(items or [], key=_custom_item_sort_key)


def _group_custom_items_by_subject(items):
    """Group already-sorted custom checklist items by their `subject` tag
    (Student-mode Premium feature, entitlements.STUDENT_*_LIMITS
    ['checklist_subject_grouping']). Items without a subject land in a
    'Khac' bucket. Sort order within each group is whatever _sort_custom_items
    already produced (soonest due / highest priority first)."""
    groups = {}
    order = []
    for item in items or []:
        subject = item.get('subject') or 'Khac'
        if subject not in groups:
            groups[subject] = []
            order.append(subject)
        groups[subject].append(item)
    return [{'subject': subject, 'items': groups[subject]} for subject in order]


def _normalize_checklist_payload(data):
    data = data or {}
    try:
        revision = max(0, int(data.get('revision') or 0))
    except (TypeError, ValueError):
        revision = 0
    completed = data.get('completed') if isinstance(data.get('completed'), dict) else {}
    custom_items = data.get('custom_items') if isinstance(data.get('custom_items'), list) else []
    normalized_custom = []
    for item in custom_items[:100]:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        item_id = str(item.get('id') or '').strip()
        if not title or not item_id:
            continue
        normalized_custom.append({
            'id': item_id[:120],
            'title': title[:240],
            'completed': bool(item.get('completed')),
            'created_at': str(item.get('created_at') or datetime.utcnow().isoformat())[:40],
            'source': str(item.get('source') or 'manual')[:40],
            'item_type': str(item.get('item_type') or 'task')[:40],
            'due_date': str(item.get('due_date') or '')[:20],
            'due_at': str(item.get('due_at') or '')[:40],
            'ai_reason': str(item.get('ai_reason') or '')[:260],
            'priority_score': int(item.get('priority_score') or 0),
            'pinned': bool(item.get('pinned')),
            # Student-mode-only tag (see routes/overview.py's sibling
            # entitlements.student_context pattern) -- harmless free text
            # for every other mode, just never surfaced as a group there.
            'subject': str(item.get('subject') or '').strip()[:60],
        })
    return {
        'revision': revision,
        'completed': {str(key)[:180]: bool(value) for key, value in completed.items()},
        'custom_items': _sort_custom_items(normalized_custom),
    }


@schedule_bp.route('/checklist', methods=['GET'])
def get_overview_checklist():
    """Return per-day overview checklist state for the current user."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    date_value = (request.args.get('date') or datetime.now(LOCAL_TZ).date().isoformat()).strip()
    cached = Cache.get(_checklist_cache_key(user_id, date_value), db_path=db_path)
    payload = _normalize_checklist_payload(cached)
    response = {
        'success': True,
        'date': date_value,
        **payload,
    }
    if request.args.get('group_by') == 'subject':
        is_student, is_premium = entitlements.student_context(user_id)
        if not is_student:
            return jsonify({'error': 'not_found'}), 404
        if not entitlements.student_limits_for(is_premium)['checklist_subject_grouping']:
            return jsonify({'error': 'premium_required', 'feature': 'checklist_subject_grouping'}), 403
        response['grouped_by_subject'] = _group_custom_items_by_subject(payload['custom_items'])
    return jsonify(response)


@schedule_bp.route('/checklist', methods=['PUT', 'POST'])
def save_overview_checklist():
    """Persist per-day overview checklist state for the current user."""
    user_id = get_current_user_id(request)
    db_path = get_user_db_path(user_id)
    data = request.get_json() or {}
    date_value = (data.get('date') or request.args.get('date') or datetime.now(LOCAL_TZ).date().isoformat()).strip()
    payload = _normalize_checklist_payload(data)
    saved, current = Cache.set_versioned(
        _checklist_cache_key(user_id, date_value),
        payload,
        expected_revision=payload['revision'],
        ttl=_CHECKLIST_CACHE_TTL_SECONDS,
        db_path=db_path,
    )
    if not saved:
        return jsonify({
            'error': 'checklist_conflict',
            'message': 'Checklist changed on another device. Reload and try again.',
            'date': date_value,
            **_normalize_checklist_payload(current),
        }), 409
    return jsonify({
        'success': True,
        'date': date_value,
        **current,
    })
