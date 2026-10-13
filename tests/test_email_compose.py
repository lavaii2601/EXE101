import base64
import io
import sys
import unittest
from contextlib import ExitStack, contextmanager
from email import message_from_bytes
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes import email as email_route  # noqa: E402
from services.gmail_service import GmailService  # noqa: E402


def _decode_raw(sent_body):
    """Gmail API 'raw' field -> parsed email.message.Message, the same shape
    a real Gmail send request receives."""
    raw = sent_body['raw']
    padding = '=' * (-len(raw) % 4)
    return message_from_bytes(base64.urlsafe_b64decode(raw + padding))


class CreateMessageTests(unittest.TestCase):
    """GmailService._create_message builds the raw MIME payload Gmail's API
    actually sends -- these exercise it directly rather than through a live
    API call."""

    def test_plain_message_has_no_attachment_part(self):
        sent = GmailService._create_message('to@example.com', 'Hi', 'Hello there')
        parsed = _decode_raw(sent)

        self.assertEqual('to@example.com', parsed['to'])
        self.assertEqual('Hi', parsed['subject'])
        self.assertFalse(parsed.is_multipart())
        self.assertIn('Hello there', parsed.get_payload())

    def test_cc_bcc_headers_are_set_when_provided(self):
        sent = GmailService._create_message(
            'to@example.com', 'Hi', 'Body', cc='cc@example.com', bcc='bcc@example.com',
        )
        parsed = _decode_raw(sent)
        self.assertEqual('cc@example.com', parsed['cc'])
        self.assertEqual('bcc@example.com', parsed['bcc'])

    def test_cc_bcc_headers_absent_when_not_provided(self):
        sent = GmailService._create_message('to@example.com', 'Hi', 'Body')
        parsed = _decode_raw(sent)
        self.assertIsNone(parsed['cc'])
        self.assertIsNone(parsed['bcc'])

    def test_multiple_comma_separated_cc_recipients_survive_verbatim(self):
        sent = GmailService._create_message(
            'to@example.com', 'Hi', 'Body', cc='a@example.com, b@example.com',
        )
        parsed = _decode_raw(sent)
        self.assertEqual('a@example.com, b@example.com', parsed['cc'])

    def test_reply_threading_headers_use_rfc_message_id_not_gmail_id(self):
        sent = GmailService._create_message(
            'to@example.com', 'Re: Hi', 'Body',
            in_reply_to='<orig@mail.gmail.com>',
        )
        parsed = _decode_raw(sent)
        self.assertEqual('<orig@mail.gmail.com>', parsed['In-Reply-To'])
        # References defaults to in_reply_to when the original had none of
        # its own -- keeps this reply in the same thread for clients that
        # only look at References.
        self.assertEqual('<orig@mail.gmail.com>', parsed['References'])

    def test_references_chains_onto_the_original_references_header(self):
        sent = GmailService._create_message(
            'to@example.com', 'Re: Hi', 'Body',
            in_reply_to='<reply2@mail.gmail.com>',
            references='<orig@mail.gmail.com> <reply1@mail.gmail.com>',
        )
        parsed = _decode_raw(sent)
        self.assertEqual(
            '<orig@mail.gmail.com> <reply1@mail.gmail.com>',
            parsed['References'],
        )

    def test_attachment_bytes_and_filename_survive_the_round_trip(self):
        sent = GmailService._create_message(
            'to@example.com', 'Hi', 'See attached',
            attachments=[{
                'filename': 'notes.txt',
                'mime_type': 'text/plain',
                'data': b'hello world attachment bytes',
            }],
        )
        parsed = _decode_raw(sent)
        self.assertTrue(parsed.is_multipart())

        attachment_parts = [
            part for part in parsed.walk()
            if part.get_filename() == 'notes.txt'
        ]
        self.assertEqual(1, len(attachment_parts))
        self.assertEqual(b'hello world attachment bytes', attachment_parts[0].get_payload(decode=True))

    def test_malformed_mime_type_falls_back_to_octet_stream(self):
        # Defensive: a filename-derived mime type with no '/' must not crash
        # MIMEBase(*mime_type.split('/', 1)), which needs two positional args.
        sent = GmailService._create_message(
            'to@example.com', 'Hi', 'Body',
            attachments=[{'filename': 'weird', 'mime_type': 'not-a-mime-type', 'data': b'x'}],
        )
        parsed = _decode_raw(sent)
        attachment_parts = [p for p in parsed.walk() if p.get_filename() == 'weird']
        self.assertEqual(1, len(attachment_parts))
        self.assertEqual('application/octet-stream', attachment_parts[0].get_content_type())

    def test_body_html_adds_a_plain_text_alternative(self):
        sent = GmailService._create_message(
            'to@example.com', 'Hi', 'Plain fallback',
            body_html='<p>Rich <b>fallback</b></p>',
        )
        parsed = _decode_raw(sent)
        self.assertEqual('multipart/alternative', parsed.get_content_type())
        plain_parts = [p for p in parsed.walk() if p.get_content_type() == 'text/plain']
        html_parts = [p for p in parsed.walk() if p.get_content_type() == 'text/html']
        self.assertEqual(1, len(plain_parts))
        self.assertEqual(1, len(html_parts))
        self.assertIn('Plain fallback', plain_parts[0].get_payload(decode=True).decode())
        self.assertIn('<b>fallback</b>', html_parts[0].get_payload(decode=True).decode())

    def test_no_body_html_keeps_the_original_plain_only_shape(self):
        sent = GmailService._create_message('to@example.com', 'Hi', 'Just text')
        parsed = _decode_raw(sent)
        self.assertEqual('text/plain', parsed.get_content_type())

    def test_inline_image_gets_content_id_and_inline_disposition(self):
        sent = GmailService._create_message(
            'to@example.com', 'Hi', 'See image',
            body_html='<p>Look: <img src="cid:logo123"></p>',
            inline_images=[{
                'filename': 'logo.png',
                'mime_type': 'image/png',
                'data': b'fake-png-bytes',
                'content_id': 'logo123',
            }],
        )
        parsed = _decode_raw(sent)
        self.assertEqual('multipart/related', parsed.get_content_type())
        image_parts = [p for p in parsed.walk() if p.get_content_type() == 'image/png']
        self.assertEqual(1, len(image_parts))
        self.assertEqual('<logo123>', image_parts[0].get('Content-ID'))
        self.assertEqual('inline', image_parts[0].get_content_disposition())
        self.assertEqual(b'fake-png-bytes', image_parts[0].get_payload(decode=True))
        # The alternative part (plain+html) must still be nested one level in.
        self.assertTrue(any(p.get_content_type() == 'multipart/alternative' for p in parsed.walk()))

    def test_inline_images_and_regular_attachments_nest_correctly_together(self):
        sent = GmailService._create_message(
            'to@example.com', 'Hi', 'Body',
            body_html='<p>Inline: <img src="cid:pic1"></p>',
            inline_images=[{
                'filename': 'pic.png', 'mime_type': 'image/png',
                'data': b'inline-bytes', 'content_id': 'pic1',
            }],
            attachments=[{
                'filename': 'report.pdf', 'mime_type': 'application/pdf', 'data': b'pdf-bytes',
            }],
        )
        parsed = _decode_raw(sent)
        self.assertEqual('multipart/mixed', parsed.get_content_type())
        attachment_parts = [p for p in parsed.walk() if p.get_filename() == 'report.pdf']
        self.assertEqual(1, len(attachment_parts))
        self.assertEqual('attachment', attachment_parts[0].get_content_disposition())
        inline_parts = [p for p in parsed.walk() if p.get_filename() == 'pic.png']
        self.assertEqual(1, len(inline_parts))
        self.assertEqual('inline', inline_parts[0].get_content_disposition())


class SendEmailTests(unittest.TestCase):
    """GmailService.send_email wires _create_message's output (plus
    threadId, which Gmail requires separately from MIME headers to group a
    reply into the original conversation) into the actual API call."""

    def _service_with_mock_api(self):
        service = GmailService.__new__(GmailService)
        service.service = MagicMock()
        return service

    def test_thread_id_is_attached_to_the_api_request_body(self):
        service = self._service_with_mock_api()
        service.send_email('to@example.com', 'Re: Hi', 'Body', thread_id='thread-123')

        send_call = service.service.users().messages().send
        sent_body = send_call.call_args.kwargs['body']
        self.assertEqual('thread-123', sent_body['threadId'])

    def test_no_thread_id_means_no_thread_id_key(self):
        service = self._service_with_mock_api()
        service.send_email('to@example.com', 'Hi', 'Body')

        send_call = service.service.users().messages().send
        sent_body = send_call.call_args.kwargs['body']
        self.assertNotIn('threadId', sent_body)

    def test_failure_returns_false_by_default(self):
        service = self._service_with_mock_api()
        service.service.users().messages().send().execute.side_effect = RuntimeError('boom')
        self.assertFalse(service.send_email('to@example.com', 'Hi', 'Body'))

    def test_failure_raises_when_raise_errors_is_set(self):
        service = self._service_with_mock_api()
        service.service.users().messages().send().execute.side_effect = RuntimeError('boom')
        with self.assertRaises(RuntimeError):
            service.send_email('to@example.com', 'Hi', 'Body', raise_errors=True)


class GetAttachmentTests(unittest.TestCase):
    """get_attachment's local walk over messages.get()'s own payload (used
    to enrich the result with a real filename/mime_type) is enrichment
    only, never a gate on the download itself -- confirmed live against
    flowmate.pro that a real, already-known attachmentId can fail to find
    an exact match when the message is re-fetched fresh, even though the
    very call that handed out that id came from this same kind of walk
    moments earlier. Gmail's attachments.get() call already scopes
    attachment_id to messageId server-side, so a local walk miss must not
    block a download that would otherwise succeed."""

    def _service_with_mock_api(self):
        service = GmailService.__new__(GmailService)
        service.service = MagicMock()
        service.last_error = None
        service.last_error_status = None
        service.last_error_reason = None
        return service

    @staticmethod
    def _b64(data):
        return base64.urlsafe_b64encode(data).decode().rstrip('=')

    def test_downloads_successfully_even_when_local_walk_finds_no_match(self):
        service = self._service_with_mock_api()
        service.service.users().messages().get().execute.return_value = {
            'payload': {'parts': [{
                'filename': 'other.pdf',
                'mimeType': 'application/pdf',
                'body': {'attachmentId': 'some-other-id', 'size': 100},
            }]},
        }
        service.service.users().messages().attachments().get().execute.return_value = {
            'data': self._b64(b'pdf bytes here'),
        }
        result = service.get_attachment('msg-1', 'the-requested-id')
        self.assertIsNotNone(result)
        self.assertEqual(b'pdf bytes here', result['data'])
        self.assertEqual('attachment', result['filename'])  # generic fallback, no local match
        self.assertEqual('application/octet-stream', result['mime_type'])

    def test_uses_the_real_filename_when_the_local_walk_does_match(self):
        service = self._service_with_mock_api()
        service.service.users().messages().get().execute.return_value = {
            'payload': {'parts': [{
                'filename': 'invoice.pdf',
                'mimeType': 'application/pdf',
                'body': {'attachmentId': 'att-1', 'size': 100},
            }]},
        }
        service.service.users().messages().attachments().get().execute.return_value = {
            'data': self._b64(b'pdf bytes'),
        }
        result = service.get_attachment('msg-1', 'att-1')
        self.assertEqual('invoice.pdf', result['filename'])
        self.assertEqual('application/pdf', result['mime_type'])

    def test_returns_none_when_the_live_download_call_itself_fails(self):
        service = self._service_with_mock_api()
        service.service.users().messages().get().execute.return_value = {'payload': {}}
        service.service.users().messages().attachments().get().execute.side_effect = RuntimeError('boom')
        self.assertIsNone(service.get_attachment('msg-1', 'att-1'))
        self.assertEqual('boom', service.last_error)


class SendReplyRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test-secret')
        self.app.register_blueprint(email_route.email_bp)
        self.client = self.app.test_client()

    @contextmanager
    def _patched(self, service, *extra):
        with ExitStack() as stack:
            stack.enter_context(patch.object(email_route.compose, 'get_current_user_id', return_value='alice'))
            stack.enter_context(patch.object(email_route.compose, 'get_user_db_path', return_value='alice.db'))
            stack.enter_context(patch.object(email_route.compose, '_load_gmail_service', return_value=service))
            stack.enter_context(patch.object(email_route.compose.History, 'create'))
            for cm in extra:
                stack.enter_context(cm)
            yield

    def test_plain_json_request_still_works_without_attachments(self):
        service = MagicMock()
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post('/api/email/send-reply', json={
                'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
            })
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()['success'])
        service.send_email.assert_called_once()
        self.assertEqual([], service.send_email.call_args.kwargs['attachments'])

    def test_multipart_request_forwards_the_uploaded_file_as_an_attachment(self):
        service = MagicMock()
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post(
                '/api/email/send-reply',
                content_type='multipart/form-data',
                data={
                    'to': 'friend@example.com',
                    'subject': 'Hi',
                    'body': 'Hello',
                    'cc': 'cc@example.com',
                    'attachments': (self._fake_file(b'file bytes'), 'doc.txt'),
                },
            )
        self.assertEqual(200, response.status_code)
        kwargs = service.send_email.call_args.kwargs
        self.assertEqual('cc@example.com', kwargs['cc'])
        self.assertEqual(1, len(kwargs['attachments']))
        self.assertEqual('doc.txt', kwargs['attachments'][0]['filename'])
        self.assertEqual(b'file bytes', kwargs['attachments'][0]['data'])

    def test_no_in_reply_to_id_never_looks_up_an_original_message(self):
        # A plain new-compose send must not pay for (or risk failing on) a
        # get_email_details lookup it has no use for.
        service = MagicMock()
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post('/api/email/send-reply', json={
                'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
            })
        self.assertEqual(200, response.status_code)
        service.get_email_details.assert_not_called()
        kwargs = service.send_email.call_args.kwargs
        self.assertIsNone(kwargs['thread_id'])
        self.assertIsNone(kwargs['in_reply_to'])

    def test_in_reply_to_id_resolves_thread_and_rfc_headers(self):
        service = MagicMock()
        service.send_email.return_value = True
        service.get_email_details.return_value = {
            'thread_id': 'thread-1',
            'rfc_message_id': '<orig@mail.gmail.com>',
            'references': '',
        }
        with self._patched(service):
            response = self.client.post('/api/email/send-reply', json={
                'to': 'friend@example.com', 'subject': 'Re: Hi', 'body': 'Hello',
                'in_reply_to_id': 'gmail-msg-1',
            })
        self.assertEqual(200, response.status_code)
        service.get_email_details.assert_called_once_with('gmail-msg-1', lazy=True)
        kwargs = service.send_email.call_args.kwargs
        self.assertEqual('thread-1', kwargs['thread_id'])
        self.assertEqual('<orig@mail.gmail.com>', kwargs['in_reply_to'])

    def test_too_many_attachments_is_rejected_before_sending(self):
        service = MagicMock()
        with self._patched(service):
            response = self.client.post(
                '/api/email/send-reply',
                content_type='multipart/form-data',
                data={
                    'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
                    'attachments': [
                        (self._fake_file(b'x'), f'f{i}.txt')
                        for i in range(email_route.compose.MAX_ATTACHMENTS_PER_MESSAGE + 1)
                    ],
                },
            )
        self.assertEqual(400, response.status_code)
        service.send_email.assert_not_called()

    def test_oversized_attachments_are_rejected_before_sending(self):
        service = MagicMock()
        with self._patched(service, patch.object(email_route.compose, 'MAX_ATTACHMENT_BYTES_TOTAL', 4)):
            response = self.client.post(
                '/api/email/send-reply',
                content_type='multipart/form-data',
                data={
                    'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
                    'attachments': (self._fake_file(b'way more than four bytes'), 'big.txt'),
                },
            )
        self.assertEqual(400, response.status_code)
        service.send_email.assert_not_called()

    def test_not_authenticated_returns_401(self):
        with patch.object(email_route.compose, '_load_gmail_service', return_value=None):
            response = self.client.post('/api/email/send-reply', json={
                'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
            })
        self.assertEqual(401, response.status_code)

    def test_body_html_is_sanitized_before_being_forwarded(self):
        service = MagicMock()
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post('/api/email/send-reply', json={
                'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
                'body_html': '<p>Hi <b>there</b></p><script>alert(1)</script>',
            })
        self.assertEqual(200, response.status_code)
        kwargs = service.send_email.call_args.kwargs
        self.assertIn('<b>there</b>', kwargs['body_html'])
        self.assertNotIn('<script', kwargs['body_html'])
        self.assertNotIn('alert(1)', kwargs['body_html'])

    def test_image_only_message_derives_a_plain_text_fallback(self):
        """No typed body text, only an embedded image -- must not be
        rejected as "missing email details", and the plain-text
        alternative part must not end up empty."""
        service = MagicMock()
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post('/api/email/send-reply', json={
                'to': 'friend@example.com', 'subject': 'Hi',
                'body_html': '<p>Xem ảnh đính kèm</p>',
            })
        self.assertEqual(200, response.status_code)
        plain_body = service.send_email.call_args.args[2]
        self.assertIn('Xem ảnh đính kèm', plain_body)

    def test_inline_images_are_forwarded_with_matching_content_ids(self):
        service = MagicMock()
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post(
                '/api/email/send-reply',
                content_type='multipart/form-data',
                data={
                    'to': 'friend@example.com', 'subject': 'Hi',
                    'body_html': '<p>Look: <img src="cid:pic1"></p>',
                    'inline_images': (self._fake_file(b'png-bytes'), 'pic.png'),
                    'inline_image_ids': 'pic1',
                },
            )
        self.assertEqual(200, response.status_code)
        kwargs = service.send_email.call_args.kwargs
        self.assertEqual(1, len(kwargs['inline_images']))
        self.assertEqual('pic1', kwargs['inline_images'][0]['content_id'])
        self.assertEqual(b'png-bytes', kwargs['inline_images'][0]['data'])

    def test_mismatched_inline_image_ids_count_is_rejected(self):
        service = MagicMock()
        with self._patched(service):
            response = self.client.post(
                '/api/email/send-reply',
                content_type='multipart/form-data',
                data={
                    'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
                    'inline_images': (self._fake_file(b'png-bytes'), 'pic.png'),
                    # no matching inline_image_ids entry
                },
            )
        self.assertEqual(400, response.status_code)
        service.send_email.assert_not_called()

    def test_combined_attachment_and_inline_image_budget_is_enforced(self):
        service = MagicMock()
        with self._patched(service, patch.object(email_route.compose, 'MAX_ATTACHMENT_BYTES_TOTAL', 10)):
            response = self.client.post(
                '/api/email/send-reply',
                content_type='multipart/form-data',
                data={
                    'to': 'friend@example.com', 'subject': 'Hi', 'body': 'Hello',
                    'attachments': (self._fake_file(b'123456'), 'a.txt'),
                    'body_html': '<p>x</p>',
                    'inline_images': (self._fake_file(b'123456'), 'pic.png'),
                    'inline_image_ids': 'pic1',
                },
            )
        self.assertEqual(400, response.status_code)
        service.send_email.assert_not_called()

    @staticmethod
    def _fake_file(data):
        import io
        return io.BytesIO(data)


class ForwardEmailRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test-secret')
        self.app.register_blueprint(email_route.email_bp)
        self.client = self.app.test_client()

    @contextmanager
    def _patched(self, service):
        with ExitStack() as stack:
            stack.enter_context(patch.object(email_route.compose, 'get_current_user_id', return_value='alice'))
            stack.enter_context(patch.object(email_route.compose, 'get_user_db_path', return_value='alice.db'))
            stack.enter_context(patch.object(email_route.compose, '_load_gmail_service', return_value=service))
            stack.enter_context(patch.object(email_route.compose.History, 'create'))
            yield

    def test_forward_reattaches_original_attachments(self):
        service = MagicMock()
        service.get_email_details.return_value = {
            'subject': 'Invoice', 'sender': 'bill@example.com', 'date': 'Mon',
            'to': 'alice@example.com', 'body': 'Please pay',
            'attachments': [{'id': 'att-1', 'filename': 'invoice.pdf', 'mime_type': 'application/pdf', 'size': 100}],
        }
        service.get_attachment.return_value = {
            'id': 'att-1', 'filename': 'invoice.pdf', 'mime_type': 'application/pdf', 'data': b'%PDF-1.4 fake',
        }
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post('/api/email/forward', json={
                'message_id': 'msg-1', 'to': 'other@example.com', 'body': 'FYI',
            })
        self.assertEqual(200, response.status_code)
        kwargs = service.send_email.call_args.kwargs
        self.assertEqual('Fwd: Invoice', service.send_email.call_args.args[1])
        self.assertIn('FYI', service.send_email.call_args.args[2])
        self.assertIn('Please pay', service.send_email.call_args.args[2])
        self.assertEqual(1, len(kwargs['attachments']))
        self.assertEqual('invoice.pdf', kwargs['attachments'][0]['filename'])

    def test_forward_does_not_double_prefix_an_already_forwarded_subject(self):
        service = MagicMock()
        service.get_email_details.return_value = {
            'subject': 'Fwd: Invoice', 'sender': 'bill@example.com', 'date': 'Mon',
            'to': 'alice@example.com', 'body': 'Please pay', 'attachments': [],
        }
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post('/api/email/forward', json={
                'message_id': 'msg-1', 'to': 'other@example.com',
            })
        self.assertEqual(200, response.status_code)
        self.assertEqual('Fwd: Invoice', service.send_email.call_args.args[1])

    def test_forward_combines_a_new_upload_with_the_reattached_original(self):
        service = MagicMock()
        service.get_email_details.return_value = {
            'subject': 'Invoice', 'sender': 'bill@example.com', 'date': 'Mon',
            'to': 'alice@example.com', 'body': 'Please pay',
            'attachments': [{'id': 'att-1', 'filename': 'invoice.pdf', 'mime_type': 'application/pdf', 'size': 100}],
        }
        service.get_attachment.return_value = {
            'id': 'att-1', 'filename': 'invoice.pdf', 'mime_type': 'application/pdf', 'data': b'%PDF-1.4 fake',
        }
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post(
                '/api/email/forward',
                content_type='multipart/form-data',
                data={
                    'message_id': 'msg-1', 'to': 'other@example.com',
                    'attachments': (io.BytesIO(b'new note'), 'note.txt'),
                },
            )
        self.assertEqual(200, response.status_code)
        kwargs = service.send_email.call_args.kwargs
        filenames = {a['filename'] for a in kwargs['attachments']}
        self.assertEqual({'note.txt', 'invoice.pdf'}, filenames)

    def test_forward_stops_reattaching_once_the_attachment_cap_is_reached(self):
        service = MagicMock()
        original_attachments = [
            {'id': f'att-{i}', 'filename': f'file{i}.pdf', 'mime_type': 'application/pdf', 'size': 10}
            for i in range(email_route.compose.MAX_ATTACHMENTS_PER_MESSAGE + 3)
        ]
        service.get_email_details.return_value = {
            'subject': 'Many files', 'sender': 'bill@example.com', 'date': 'Mon',
            'to': 'alice@example.com', 'body': 'See attached',
            'attachments': original_attachments,
        }
        service.get_attachment.side_effect = lambda message_id, attachment_id: {
            'id': attachment_id, 'filename': f'{attachment_id}.pdf',
            'mime_type': 'application/pdf', 'data': b'x',
        }
        service.send_email.return_value = True
        with self._patched(service):
            response = self.client.post('/api/email/forward', json={
                'message_id': 'msg-1', 'to': 'other@example.com',
            })
        self.assertEqual(200, response.status_code)
        kwargs = service.send_email.call_args.kwargs
        self.assertLessEqual(len(kwargs['attachments']), email_route.compose.MAX_ATTACHMENTS_PER_MESSAGE)

    def test_missing_original_email_returns_404(self):
        service = MagicMock()
        service.get_email_details.return_value = None
        with self._patched(service):
            response = self.client.post('/api/email/forward', json={
                'message_id': 'missing', 'to': 'other@example.com',
            })
        self.assertEqual(404, response.status_code)


if __name__ == '__main__':
    unittest.main()
