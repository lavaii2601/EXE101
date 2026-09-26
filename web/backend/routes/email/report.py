"""Daily digest report: summarize every email received on a given date.

Split out of the former monolithic routes/email.py -- see
routes/email/__init__.py for the package-level overview.
"""
import logging

from flask import jsonify, request, session, url_for

from models.history import History
from utils.user_context import get_current_user_id, get_user_db_path

from routes.email.shared import email_bp, ai_service
from routes.email.oauth import _load_gmail_service

# Configure module logger
logger = logging.getLogger(__name__)


@email_bp.route('/summarize-by-date', methods=['POST'])
def summarize_emails_by_date():
    """Summarize emails received on a specific date and return tabular report with caching."""
    user_id = get_current_user_id(request, session=session)
    db_path = get_user_db_path(user_id)
    service = _load_gmail_service(user_id)
    if not service:
        return jsonify({'error': 'not_authenticated', 'auth_url': url_for('email.gmail_auth', _external=True)}), 401

    data = request.get_json() or {}
    date_str = (data.get('date') or '').strip()
    max_results = int(data.get('max_results', 20))

    if not date_str:
        return jsonify({'error': 'Missing date. Expected format dd/mm/yyyy'}), 400

    try:
        emails = service.get_emails_by_date(date_str, max_results=max_results)
        if not emails:
            return jsonify({
                'success': True,
                'date': date_str,
                'total_emails': 0,
                'rows': []
            })

        # Try to read cached report first
        cache_key = f"email_report:v2:{user_id}::{date_str}"
        rows = None
        try:
            from models.cache import Cache
            cached = Cache.get(cache_key, db_path=db_path)
            if cached:
                logger.info(f"Using cached summary for {date_str}")
                rows = cached
        except Exception as e:
            logger.debug(f"Cache read error: {e}")

        # Generate summary if not cached
        if not rows:
            rows = ai_service.summarize_email_report(emails, report_date=date_str, user_id=user_id)
            # Cache the results for future use (24 hour TTL)
            try:
                from models.cache import Cache
                Cache.set(cache_key, rows, db_path=db_path, ttl=86400)
                logger.info(f"Cached summary for {date_str}")
            except Exception as e:
                logger.debug(f"Cache write error: {e}")

        report_details = []
        for index, row in enumerate(rows, start=1):
            detail = [
                f"{index}. {row.get('subject') or '(Không có tiêu đề)'}",
                f"Người gửi: {row.get('sender') or 'Không xác định'}",
                f"Tóm tắt: {row.get('summary') or 'Không có tóm tắt'}",
            ]
            if row.get('is_meeting'):
                detail.append(
                    f"Gợi ý lịch: {row.get('meeting_note') or row.get('schedule_title') or 'Có nội dung liên quan đến lịch hẹn'}"
                )
            report_details.append("\n".join(detail))

        History.create(
            f"Báo cáo tóm tắt email theo ngày {date_str}",
            f"Tổng {len(rows)} email đã được tóm tắt\n\n" + "\n\n".join(report_details),
            action_type='email_daily_summary',
            db_path=db_path
        )

        return jsonify({
            'success': True,
            'date': date_str,
            'total_emails': len(emails),
            'rows': rows
        })
    except Exception as e:
        logger.exception("Failed to summarize emails for date %s", date_str)
        return jsonify({'error': str(e)}), 500
