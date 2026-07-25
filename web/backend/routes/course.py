import os
import sys

from flask import Blueprint, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import entitlements
from models.course import Course, calculate_gpa
from utils.user_context import get_current_user_id, get_user_db_path

course_bp = Blueprint('course', __name__, url_prefix='/api/courses')

# Student-mode-only (GPA calculator). Every route here 404s for any other
# user_mode; is_premium then decides free (compute-only) vs premium
# (persisted) depth, mirroring the pattern in routes/overview.py and
# routes/schedule.py's checklist subject grouping -- see
# entitlements.student_context / student_limits_for.

_MAX_ROWS = 60


def _parse_course_rows(raw_rows):
    """Validate/coerce a client-supplied course list for calculation. Skips
    (rather than rejects the whole request on) any row missing a usable
    name/credits/grade, since a partially-filled draft row is normal while
    a student is still typing."""
    rows = []
    for item in (raw_rows or [])[:_MAX_ROWS]:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()[:120]
        try:
            credits = float(item.get('credits'))
            grade = float(item.get('grade'))
        except (TypeError, ValueError):
            continue
        if not name or credits <= 0:
            continue
        rows.append({'name': name, 'credits': credits, 'grade': grade})
    return rows


@course_bp.route('/calculate', methods=['POST'])
def calculate():
    """Free tier: compute a GPA from courses sent in the request body.
    Nothing is persisted -- the student re-enters their list each time."""
    user_id = get_current_user_id(request)
    is_student, _ = entitlements.student_context(user_id)
    if not is_student:
        return jsonify({'error': 'not_found'}), 404

    data = request.get_json(silent=True) or {}
    rows = _parse_course_rows(data.get('courses'))
    gpa = calculate_gpa(rows)
    return jsonify({'success': True, 'gpa': gpa, 'courses': rows})


@course_bp.route('', methods=['GET'])
def list_courses():
    """Premium tier: saved course list (entitlements.STUDENT_*_LIMITS['gpa_persist'])."""
    user_id = get_current_user_id(request)
    is_student, is_premium = entitlements.student_context(user_id)
    if not is_student:
        return jsonify({'error': 'not_found'}), 404
    if not entitlements.student_limits_for(is_premium)['gpa_persist']:
        return jsonify({'error': 'premium_required', 'feature': 'gpa_persist'}), 403

    term = (request.args.get('term') or '').strip() or None
    db_path = get_user_db_path(user_id)
    courses = Course.get_all(user_id, term=term, db_path=db_path)
    gpa = calculate_gpa(courses)
    return jsonify({'success': True, 'courses': courses, 'gpa': gpa})


@course_bp.route('', methods=['POST'])
def add_course():
    """Premium tier: save one course row."""
    user_id = get_current_user_id(request)
    is_student, is_premium = entitlements.student_context(user_id)
    if not is_student:
        return jsonify({'error': 'not_found'}), 404
    if not entitlements.student_limits_for(is_premium)['gpa_persist']:
        return jsonify({'error': 'premium_required', 'feature': 'gpa_persist'}), 403

    data = request.get_json(silent=True) or {}
    rows = _parse_course_rows([data])
    if not rows:
        return jsonify({'error': 'invalid_course', 'message': 'name/credits/grade required'}), 400
    row = rows[0]
    term = (data.get('term') or '').strip()[:40] or None
    db_path = get_user_db_path(user_id)
    course = Course.create(user_id, row['name'], row['credits'], row['grade'], term=term, db_path=db_path)
    return jsonify({'success': True, 'course': course}), 201


@course_bp.route('/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    """Premium tier: delete one saved course row (scoped to the caller)."""
    user_id = get_current_user_id(request)
    is_student, is_premium = entitlements.student_context(user_id)
    if not is_student:
        return jsonify({'error': 'not_found'}), 404
    if not entitlements.student_limits_for(is_premium)['gpa_persist']:
        return jsonify({'error': 'premium_required', 'feature': 'gpa_persist'}), 403

    db_path = get_user_db_path(user_id)
    deleted = Course.delete(course_id, user_id, db_path=db_path)
    if not deleted:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    return jsonify({'success': True})
