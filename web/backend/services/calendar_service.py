import os
import sys
import logging
import pickle
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from config import Config

# Configure module logger
logger = logging.getLogger(__name__)

CALENDAR_TIMEZONE = 'Asia/Ho_Chi_Minh'
_LOCAL_TZ = datetime.now().astimezone().tzinfo

class CalendarService:
    """Service for Google Calendar API operations"""
    
    def __init__(self, token_file=None):
        self.service = None
        self.token_file = token_file or Config.GMAIL_TOKEN_FILE
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar API using stored credentials."""
        try:
            creds = None
            
            # Load token if exists
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    creds = pickle.load(token)
            
            # If no valid credentials, return False
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    logger.warning(f"No valid credentials found in {self.token_file}")
                    return False
            
            self.service = build('calendar', 'v3', credentials=creds)
            logger.info("Google Calendar service initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Calendar authentication error: {str(e)}")
            return False
    
    def get_events(self, max_results=10, time_min=None, time_max=None):
        """Get upcoming calendar events"""
        try:
            if not self.service:
                logger.warning("Calendar service not initialized")
                return []
            
            # Default to next 7 days if not specified
            if not time_min:
                time_min = datetime.utcnow().isoformat() + 'Z'
            if not time_max:
                time_max = (datetime.utcnow() + timedelta(days=7)).isoformat() + 'Z'
            
            logger.info(f"Fetching calendar events: max_results={max_results}, from {time_min} to {time_max}")
            
            results = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = results.get('items', [])
            logger.info(f"Found {len(events)} calendar events")
            
            # Format events
            formatted_events = []
            for event in events:
                formatted_events.append({
                    'id': event.get('id'),
                    'title': event.get('summary', 'Untitled'),
                    'description': event.get('description', ''),
                    'start': event.get('start', {}).get('dateTime', event.get('start', {}).get('date', '')),
                    'end': event.get('end', {}).get('dateTime', event.get('end', {}).get('date', '')),
                    'attendees': [a.get('email') for a in event.get('attendees', [])],
                    'location': event.get('location', ''),
                    'status': event.get('status', 'confirmed')
                })
            
            return formatted_events
        except Exception as e:
            logger.error(f"Error getting calendar events: {str(e)}")
            return []
    
    def create_event(self, title, description='', start_time=None, end_time=None, attendees=None, location=''):
        """Create a new calendar event"""
        try:
            if not self.service:
                logger.warning("Calendar service not initialized")
                return None
            
            # Parse time strings
            if isinstance(start_time, str):
                # Try to parse ISO format
                try:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                except:
                    # Fallback: assume string is a datetime
                    start_dt = datetime.fromisoformat(start_time)
            else:
                start_dt = start_time or datetime.utcnow()
            
            if isinstance(end_time, str):
                try:
                    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                except:
                    end_dt = datetime.fromisoformat(end_time)
            else:
                end_dt = end_time or (start_dt + timedelta(hours=1))
            
            # Normalize to local timezone to avoid date/time shifting on Calendar.
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=_LOCAL_TZ)
            else:
                start_dt = start_dt.astimezone(_LOCAL_TZ)

            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=_LOCAL_TZ)
            else:
                end_dt = end_dt.astimezone(_LOCAL_TZ)

            # Build event
            event = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start_dt.isoformat(),
                },
                'end': {
                    'dateTime': end_dt.isoformat(),
                },
            }

            if CALENDAR_TIMEZONE:
                event['start']['timeZone'] = CALENDAR_TIMEZONE
                event['end']['timeZone'] = CALENDAR_TIMEZONE
            
            if location:
                event['location'] = location
            
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            logger.info(f"Creating calendar event: {title}")
            created_event = self.service.events().insert(
                calendarId='primary',
                body=event,
                sendNotifications=True
            ).execute()
            
            logger.info(f"Event created with ID: {created_event.get('id')}")
            return created_event.get('id')
        except Exception as e:
            logger.error(f"Error creating calendar event: {str(e)}")
            return None
    
    def update_event(self, event_id, title=None, description=None, start_time=None, end_time=None, attendees=None):
        """Update an existing calendar event"""
        try:
            if not self.service:
                logger.warning("Calendar service not initialized")
                return False
            
            # Get the event first
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            # Update fields
            if title:
                event['summary'] = title
            if description:
                event['description'] = description
            if start_time:
                if isinstance(start_time, str):
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                else:
                    start_dt = start_time
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=_LOCAL_TZ)
                else:
                    start_dt = start_dt.astimezone(_LOCAL_TZ)
                event['start'] = {
                    'dateTime': start_dt.isoformat(),
                }
                if CALENDAR_TIMEZONE:
                    event['start']['timeZone'] = CALENDAR_TIMEZONE
            if end_time:
                if isinstance(end_time, str):
                    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                else:
                    end_dt = end_time
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=_LOCAL_TZ)
                else:
                    end_dt = end_dt.astimezone(_LOCAL_TZ)
                event['end'] = {
                    'dateTime': end_dt.isoformat(),
                }
                if CALENDAR_TIMEZONE:
                    event['end']['timeZone'] = CALENDAR_TIMEZONE
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            logger.info(f"Updating calendar event: {event_id}")
            self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendNotifications=True
            ).execute()
            
            logger.info(f"Event {event_id} updated successfully")
            return True
        except Exception as e:
            logger.error(f"Error updating calendar event: {str(e)}")
            return False
    
    def delete_event(self, event_id):
        """Delete a calendar event"""
        try:
            if not self.service:
                logger.warning("Calendar service not initialized")
                return False
            
            logger.info(f"Deleting calendar event: {event_id}")
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id,
                sendNotifications=True
            ).execute()
            
            logger.info(f"Event {event_id} deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Error deleting calendar event: {str(e)}")
            return False
