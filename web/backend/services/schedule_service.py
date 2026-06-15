import os
import sys
import re
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.schedule import Schedule

# Configure module logger
logger = logging.getLogger(__name__)


def _to_local_naive(value):
    """Parse ISO date/time and normalize aware values to naive local time."""
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


class ScheduleService:
    @staticmethod
    def parse_schedule_request(text):
        """Parse schedule request from user text"""
        # Simple pattern matching - can be enhanced
        result = {
            'title': '',
            'description': '',
            'start_time': None,
            'attendees': [],
            'action': 'create'
        }
        
        # Basic parsing logic
        if 'hôm nay' in text.lower() or 'today' in text.lower():
            result['start_time'] = datetime.now()
        elif 'ngày mai' in text.lower() or 'tomorrow' in text.lower():
            result['start_time'] = datetime.now() + timedelta(days=1)
        
        # Extract email addresses (simple pattern)
        emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
        result['attendees'] = emails
        
        return result
    
    @staticmethod
    def create_schedule(title, description, start_time, attendees, end_time=None, location=None, duration_minutes=None, db_path=None):
        """Create new schedule"""
        if not end_time:
            duration = duration_minutes if isinstance(duration_minutes, int) and duration_minutes > 0 else 60
            end_dt = datetime.fromisoformat(start_time) + timedelta(minutes=duration)
            end_time = end_dt.isoformat()
        schedule_id = Schedule.create(
            title,
            description,
            start_time,
            end_time,
            ','.join(attendees),
            email_body='',
            location=location,
            db_path=db_path
        )
        return schedule_id
    
    @staticmethod
    def get_upcoming_schedules(db_path=None):
        """Get upcoming schedules"""
        schedules = Schedule.get_all(db_path=db_path)
        upcoming = []
        now = datetime.now()
        
        for schedule in schedules:
            start_dt = _to_local_naive(schedule.get('start_time'))
            if not start_dt:
                logger.warning("Skipping schedule %s with invalid start_time: %r", schedule.get('id'), schedule.get('start_time'))
                continue
            if start_dt > now:
                upcoming.append((start_dt, schedule))
        
        upcoming.sort(key=lambda item: item[0])
        return [schedule for _, schedule in upcoming[:5]]
