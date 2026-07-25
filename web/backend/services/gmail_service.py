import os
import sys
import logging
import pickle
import base64
import html
import re
import socket
import ssl
import random
import time
import httplib2
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from config import Config
from utils.google_service_cache import get_cached_service
from utils.user_context import persist_google_credentials, user_id_from_token_file

# Retried automatically by googleapiclient's execute(num_retries=...) on
# transient network/SSL/5xx errors (see GMAIL_EXECUTE_RETRIES below). A
# connect/read timeout is also required -- without one, a stalled connection
# can hang indefinitely and later surface as a raw SSL record-layer error
# instead of a clean, retryable timeout.
GMAIL_HTTP_TIMEOUT_SECONDS = 20
GMAIL_EXECUTE_RETRIES = 2

# Configure module logger
logger = logging.getLogger(__name__)


def _is_transient_batch_error(exc):
    """Whether exc is the kind of transient error googleapiclient's own
    num_retries would normally retry (5xx, SSL, timeout, connection drop)."""
    if isinstance(exc, HttpError):
        return exc.resp is not None and exc.resp.status >= 500
    return isinstance(exc, (ssl.SSLError, socket.timeout, ConnectionError, TimeoutError, httplib2.HttpLib2Error))


def _execute_batch_with_retries(batch, num_retries):
    """BatchHttpRequest.execute() has no num_retries parameter (unlike
    HttpRequest.execute()), so retry transient errors on the /batch call
    itself here. Per-item errors inside the batch are reported via each
    request's callback, not raised here, so they are unaffected."""
    for retry_num in range(num_retries + 1):
        try:
            return batch.execute()
        except Exception as exc:
            if retry_num == num_retries or not _is_transient_batch_error(exc):
                raise
            sleep_time = random.random() * 2 ** retry_num
            logger.warning(
                f"Batch execute failed (attempt {retry_num + 1}/{num_retries + 1}), "
                f"retrying in {sleep_time:.2f}s: {exc}"
            )
            time.sleep(sleep_time)


def get_cached_gmail_service(token_file):
    """Return a cached GmailService instance for this token file instead of
    re-authenticating on every call. Shared by every caller that already has
    a validated token_file path (services/chat_agents.py, services/overview_service.py)."""
    return get_cached_service(
        token_file,
        lambda: GmailService(token_file=token_file),
        service_kind='gmail',
    )


class GmailService:
    # Keep this in sync with MainActivity's GoogleSignInOptions. Google adds
    # the OpenID identity scopes to Android server auth codes.
    SCOPES = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/calendar.events',
    ]
    
    def __init__(self, token_file=None):
        self.service = None
        self.token_file = token_file or Config.GMAIL_TOKEN_FILE
        self.last_error = None
        self.last_error_status = None
        self.last_error_reason = None
        self._authenticate()

    def _remember_error(self, error):
        self.last_error = str(error)
        self.last_error_status = getattr(getattr(error, 'resp', None), 'status', None)
        self.last_error_reason = None
        if isinstance(error, HttpError):
            try:
                import json
                payload = json.loads(error.content.decode('utf-8'))
                details = payload.get('error') or {}
                errors = details.get('errors') or []
                if errors:
                    self.last_error_reason = errors[0].get('reason')
                self.last_error = details.get('message') or self.last_error
            except Exception:
                pass
    
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
            
            # OAuth is completed by routes/email.py. Never start an
            # interactive local-server flow from a production API request:
            # that would hang the request and eventually look like an empty
            # inbox to the mobile client.
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    logger.warning("Stored Gmail credentials are missing or cannot be refreshed")
                    return False
                
                # Save the credentials for the next run
                with open(self.token_file, 'wb') as token:
                    pickle.dump(creds, token)
                self._persist_refreshed_credentials(creds)
            
            authorized_http = AuthorizedHttp(creds, http=httplib2.Http(timeout=GMAIL_HTTP_TIMEOUT_SECONDS))
            self.service = build('gmail', 'v1', http=authorized_http)
            return True
        except Exception as e:
            self._remember_error(e)
            logger.warning("Gmail authentication error: %s", e)
            return False

    def _persist_refreshed_credentials(self, creds):
        try:
            user_id = user_id_from_token_file(self.token_file)
            if user_id and user_id != 'default':
                persist_google_credentials(user_id, creds)
        except Exception:
            logger.debug("Could not persist refreshed Gmail credentials", exc_info=True)
    
    def get_emails(
        self,
        max_results=10,
        query='is:unread',
        include_read=False,
        lazy=True,
        raise_errors=False,
    ):
        """Get emails from inbox. lazy=True skips body for speed; pass lazy=False when
        callers need the full body (e.g. meeting-suggestion detection)."""
        try:
            try:
                max_results = max(1, min(int(max_results), 150))
            except Exception:
                max_results = 10

            # If include_read, get all emails in inbox (read + unread)
            if include_read and query == 'is:unread':
                query = 'in:inbox'

            logger.info(f"Fetching emails: max_results={max_results}, query={query}")
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)

            messages = results.get('messages', [])
            logger.info(f"Found {len(messages)} messages matching query: {query}")

            message_ids = [msg.get('id') for msg in messages if msg.get('id')]
            emails = self._get_email_details_batch(
                message_ids,
                lazy=lazy,
                raise_errors=raise_errors,
            )
            
            logger.info(f"Successfully fetched {len(emails)} email details")
            return emails
        except Exception as e:
            self._remember_error(e)
            logger.error(f"Error getting emails ({type(e).__name__}): {e}", exc_info=True)
            if raise_errors:
                raise
            return []

    def _get_email_details_batch(
        self,
        message_ids,
        lazy=True,
        batch_size=25,
        raise_errors=False,
    ):
        """Fetch many email metadata records with Gmail batch requests."""
        if not message_ids:
            return []

        collected = {}
        batch_errors = []
        format_type = 'metadata' if lazy else 'full'

        try:
            for start in range(0, len(message_ids), batch_size):
                chunk = message_ids[start:start + batch_size]
                batch = self.service.new_batch_http_request()

                def _callback(request_id, response, exception):
                    if exception:
                        batch_errors.append(exception)
                        logger.warning(f"Batch email fetch failed for {request_id}: {exception}")
                        return
                    parsed = self._parse_message(response, request_id, lazy=lazy)
                    if parsed:
                        collected[request_id] = parsed

                for message_id in chunk:
                    request_kwargs = {
                        'userId': 'me',
                        'id': message_id,
                        'format': format_type
                    }
                    if lazy:
                        request_kwargs['metadataHeaders'] = ['Subject', 'From', 'Date']
                    batch.add(
                        self.service.users().messages().get(**request_kwargs),
                        request_id=message_id,
                        callback=_callback
                    )

                _execute_batch_with_retries(batch, GMAIL_EXECUTE_RETRIES)

            if raise_errors and batch_errors and not collected:
                raise batch_errors[0]
            return [collected[mid] for mid in message_ids if mid in collected]
        except Exception as e:
            if raise_errors:
                raise
            logger.warning(f"Batch email fetch failed, falling back to serial fetch: {e}")
            emails = []
            for message_id in message_ids:
                email_data = self.get_email_details(message_id, lazy=lazy)
                if email_data:
                    emails.append(email_data)
            return emails

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

    def list_message_ids_by_date(self, date_str, max_results=50):
        """Return just the message IDs received on a date, no detail fetch.

        Used to cheaply detect whether new mail arrived for a day without
        paying for the batch metadata fetch that get_emails_by_date does.
        """
        try:
            target_date = self._parse_date(date_str)
            if not target_date:
                return []

            next_date = target_date + timedelta(days=1)
            query = (
                f"after:{target_date.strftime('%Y/%m/%d')} "
                f"before:{next_date.strftime('%Y/%m/%d')}"
            )
            try:
                max_results = max(1, min(int(max_results), 150))
            except Exception:
                max_results = 50

            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=max_results
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            return [msg.get('id') for msg in results.get('messages', []) if msg.get('id')]
        except Exception as e:
            logger.warning(f"Error listing message ids by date: {e}")
            return []

    def list_unread_ids(self, max_results=5):
        """Cheaply list unread message ids plus a total count estimate.

        No metadata/body fetch -- used by the new-mail poller, which runs
        every ~90s and only needs to know whether the newest unread id
        changed, not the full inbox.
        """
        try:
            max_results = max(1, min(int(max_results), 25))
        except Exception:
            max_results = 5
        try:
            results = self.service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=max_results,
                fields='messages(id),resultSizeEstimate'
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            message_ids = [msg.get('id') for msg in results.get('messages', []) if msg.get('id')]
            return {
                'ids': message_ids,
                'unread_count': int(results.get('resultSizeEstimate') or len(message_ids)),
            }
        except Exception as e:
            logger.warning(f"Error listing unread ids: {e}")
            return {'ids': [], 'unread_count': 0}

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
    
    def get_email_details_batch(self, message_ids):
        """Fetch full details (body + attachments) for several messages in one batch call."""
        return self._get_email_details_batch(list(message_ids or []), lazy=False)

    def get_email_details(self, message_id, lazy=False):
        """Get email details - lazy=True skips full body for speed"""
        try:
            # Use 'metadata' format for lazy loading (has headers but no body), 'full' for complete body
            format_type = 'metadata' if lazy else 'full'
            request_kwargs = {
                'userId': 'me',
                'id': message_id,
                'format': format_type
            }
            if lazy:
                request_kwargs['metadataHeaders'] = ['Subject', 'From', 'Date']
            message = self.service.users().messages().get(**request_kwargs).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            return self._parse_message(message, message_id, lazy=lazy)
        except Exception as e:
            print(f"Error getting email details: {str(e)}")
            return None

    def _parse_message(self, message, message_id, lazy=False):
        try:
            payload = message.get('payload', {}) or {}
            headers = payload.get('headers', []) or []

            def header_value(name, default=''):
                name_lower = name.lower()
                return next(
                    (h.get('value', default) for h in headers if h.get('name', '').lower() == name_lower),
                    default
                )

            subject = header_value('Subject', 'No Subject')
            sender = header_value('From', 'Unknown')
            date = header_value('Date', '')
            # To/Cc matter for summarization: whether the user is the sole/
            # primary recipient versus one of several To/Cc'd people changes
            # who an action item actually belongs to.
            to = header_value('To', '')
            cc = header_value('Cc', '')
            snippet = message.get('snippet', '') or ''
            body = "" if lazy else self._get_email_body(payload)
            attachments = [] if lazy else self._get_attachments(payload)
            label_ids = message.get('labelIds', []) or []

            return {
                'id': message_id,
                'thread_id': message.get('threadId', ''),
                'subject': subject,
                'sender': sender,
                'date': date,
                'to': to,
                'cc': cc,
                'body': body,
                'attachments': attachments,
                'snippet': snippet,
                'is_unread': 'UNREAD' in label_ids
            }
        except Exception as e:
            logger.warning(f"Error parsing email message {message_id}: {e}")
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
                    body = text_plain
                elif text_html:
                    body = self._html_to_text(text_html)
                elif body:
                    body = body
                else:
                    body = ""
            else:
                # Simple payload (not multipart)
                data = payload['body'].get('data', '')
                if data:
                    decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    body = self._html_to_text(decoded) if payload.get('mimeType') == 'text/html' else decoded
            
            return body if body else "Email body unavailable"
        except Exception as e:
            print(f"Error extracting email body: {str(e)}")
            return f"Error reading email: {str(e)[:100]}"

    def _get_attachments(self, payload):
        """Return downloadable attachment metadata from a Gmail MIME payload."""
        attachments = []

        def walk(part):
            body = part.get('body', {}) or {}
            attachment_id = body.get('attachmentId')
            filename = str(part.get('filename') or '').strip()
            if attachment_id and filename:
                attachments.append({
                    'id': attachment_id,
                    'filename': filename,
                    'mime_type': part.get('mimeType') or 'application/octet-stream',
                    'size': int(body.get('size') or 0),
                })

            for child in part.get('parts', []) or []:
                walk(child)

        walk(payload or {})
        return attachments

    def get_attachment(self, message_id, attachment_id):
        """Fetch one attachment after verifying it belongs to the message."""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            attachment = next(
                (
                    item for item in self._get_attachments(message.get('payload', {}) or {})
                    if item.get('id') == attachment_id
                ),
                None
            )
            if not attachment:
                return None

            result = self.service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            encoded = result.get('data') or ''
            padding = '=' * (-len(encoded) % 4)
            attachment['data'] = base64.urlsafe_b64decode(encoded + padding)
            return attachment
        except Exception as e:
            logger.warning(f"Error downloading Gmail attachment {message_id}: {e}")
            return None

    @staticmethod
    def _html_to_text(value):
        if not value:
            return ''
        text = re.sub(r'(?is)<(script|style).*?>.*?</\1>', ' ', value)
        text = re.sub(r'(?i)<br\s*/?>', '\n', text)
        text = re.sub(r'(?i)</p\s*>', '\n\n', text)
        text = re.sub(r'(?s)<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        return text.strip()
    
    def send_email(self, to, subject, body):
        """Send email reply"""
        try:
            message = self._create_message(to, subject, body)
            self.service.users().messages().send(
                userId='me',
                body=message
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
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
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
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
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            logger.info(f"Marked message {message_id} as unread")
            return True
        except Exception as e:
            logger.error(f"Error marking message as unread: {str(e)}")
            return False

    def archive_email(self, message_id):
        """Remove an email from the inbox without deleting it (Gmail archive)."""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['INBOX']}
            ).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            logger.info(f"Archived message {message_id}")
            return True
        except Exception as e:
            logger.error(f"Error archiving message: {str(e)}")
            return False

    def trash_email(self, message_id):
        """Move an email to Gmail trash (reversible, matches Gmail's own delete)."""
        try:
            self.service.users().messages().trash(userId='me', id=message_id).execute(num_retries=GMAIL_EXECUTE_RETRIES)
            logger.info(f"Trashed message {message_id}")
            return True
        except Exception as e:
            logger.error(f"Error trashing message: {str(e)}")
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
