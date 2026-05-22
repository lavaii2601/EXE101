import os
import sys
import logging
import pickle
import base64
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from config import Config

# Configure module logger
logger = logging.getLogger(__name__)

class GmailService:
    # require both read and send permissions for our features
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/calendar.events',
        'https://www.googleapis.com/auth/userinfo.profile'
    ]
    
    def __init__(self, token_file=None):
        self.service = None
        self.token_file = token_file or Config.GMAIL_TOKEN_FILE
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API (used only if token file missing).

        For the web‑based OAuth flow our routes create the token; this
        method remains as a fallback during development or testing.
        """
        try:
            creds = None
            
            # Load token if exists
            if os.path.exists(self.token_file):
                with open(self.token_file, 'rb') as token:
                    creds = pickle.load(token)
            
            # If no valid credentials, get new ones
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    # fallback; not normally used in production
                    flow = InstalledAppFlow.from_client_secrets_file(
                        Config.GMAIL_CREDENTIALS_FILE, self.SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(self.token_file, 'wb') as token:
                    pickle.dump(creds, token)
            
            self.service = build('gmail', 'v1', credentials=creds)
            return True
        except Exception as e:
            print(f"Gmail authentication error: {str(e)}")
            return False
    
    def get_emails(self, max_results=10, query='is:unread', include_read=False):
        """Get emails from inbox with lazy body loading"""
        try:
            # If include_read, get all emails in inbox (read + unread)
            if include_read and query == 'is:unread':
                query = 'in:inbox'
            
            logger.info(f"Fetching emails: max_results={max_results}, query={query}")
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            logger.info(f"Found {len(messages)} messages matching query: {query}")
            
            emails = []
            
            # Serial fetch with lazy body loading (skip body for speed)
            for msg in messages:
                email_data = self.get_email_details(msg['id'], lazy=True)
                if email_data:
                    emails.append(email_data)
            
            logger.info(f"Successfully fetched {len(emails)} email details")
            return emails
        except Exception as e:
            logger.error(f"Error getting emails: {str(e)}")
            return []

    def get_emails_by_date(self, date_str, max_results=20):
        """Get emails received on a specific date.

        Accepted formats: dd/mm/yyyy, d/m/yyyy, yyyy-mm-dd, yyyy/mm/dd
        """
        try:
            target_date = self._parse_date(date_str)
            if not target_date:
                raise ValueError("Invalid date format. Use dd/mm/yyyy")

            next_date = target_date + timedelta(days=1)
            after_str = target_date.strftime('%Y/%m/%d')
            before_str = next_date.strftime('%Y/%m/%d')

            query = f"after:{after_str} before:{before_str}"
            return self.get_emails(max_results=max_results, query=query)
        except Exception as e:
            print(f"Error getting emails by date: {str(e)}")
            return []

    @staticmethod
    def _parse_date(date_str):
        if not date_str:
            return None

        date_str = date_str.strip()
        formats = ['%d/%m/%Y', '%Y-%m-%d', '%Y/%m/%d']

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None
    
    def get_email_details(self, message_id, lazy=False):
        """Get email details - lazy=True skips full body for speed"""
        try:
            # Use 'metadata' format for lazy loading (has headers but no body), 'full' for complete body
            format_type = 'metadata' if lazy else 'full'
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format=format_type
            ).execute()
            
            headers = message['payload']['headers']
            
            # Extract header information
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            snippet = message.get('snippet', '')
            
            # Extract body only if not lazy loading
            body = "" if lazy else self._get_email_body(message['payload'])
            
            # Check if email is unread based on labels
            label_ids = message.get('labelIds', [])
            is_unread = 'UNREAD' in label_ids
            
            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body,
                'snippet': snippet,
                'is_unread': is_unread
            }
        except Exception as e:
            print(f"Error getting email details: {str(e)}")
            return None
    
    def _get_email_body(self, payload):
        """Extract email body from payload - handles multipart, HTML, and plain text"""
        try:
            body = ""
            
            # If payload has multiple parts (multipart email)
            if 'parts' in payload:
                # Priority: text/plain > text/html > first available part
                text_plain = None
                text_html = None
                
                for part in payload['parts']:
                    mime_type = part.get('mimeType', '')
                    data = part['body'].get('data', '')
                    
                    if mime_type == 'text/plain' and data:
                        text_plain = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    elif mime_type == 'text/html' and data:
                        text_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    
                    # Handle nested parts (e.g., alternative/related)
                    if 'parts' in part and not body:
                        nested_body = self._get_email_body(part)
                        if nested_body and nested_body != "Could not extract email body":
                            body = nested_body
                
                # Prefer plain text over HTML
                if text_plain:
                    body = text_plain[:5000]  # Limit to first 5000 chars
                elif text_html:
                    body = text_html[:5000]
                elif body:
                    body = body[:5000]
                else:
                    body = ""
            else:
                # Simple payload (not multipart)
                data = payload['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')[:5000]
            
            return body if body else "Email body unavailable"
        except Exception as e:
            print(f"Error extracting email body: {str(e)}")
            return f"Error reading email: {str(e)[:100]}"
    
    def send_email(self, to, subject, body):
        """Send email reply"""
        try:
            message = self._create_message(to, subject, body)
            self.service.users().messages().send(
                userId='me',
                body=message
            ).execute()
            return True
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False
    
    def mark_as_read(self, message_id):
        """Mark an email as read"""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked message {message_id} as read")
            return True
        except Exception as e:
            logger.error(f"Error marking message as read: {str(e)}")
            return False
    
    def mark_as_unread(self, message_id):
        """Mark an email as unread"""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked message {message_id} as unread")
            return True
        except Exception as e:
            logger.error(f"Error marking message as unread: {str(e)}")
            return False
    
    @staticmethod
    def _create_message(to, subject, body):
        """Create message for Gmail API"""
        import base64
        from email.mime.text import MIMEText
        
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {'raw': raw_message}
