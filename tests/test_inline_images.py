import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.gmail_service import GmailService  # noqa: E402


class InlineImageAttachmentExtractionTests(unittest.TestCase):
    """_get_attachments must surface a part's Content-ID (used to match it
    against a src="cid:..." reference in the HTML body) without breaking
    the existing attachment list for parts that don't have one."""

    def test_extracts_content_id_when_present(self):
        payload = {
            'parts': [{
                'filename': 'logo.png',
                'mimeType': 'image/png',
                'body': {'attachmentId': 'att-1', 'size': 1234},
                'headers': [{'name': 'Content-ID', 'value': '<logo123@mail.gmail.com>'}],
            }],
        }
        attachments = GmailService._get_attachments(None, payload)
        self.assertEqual(1, len(attachments))
        self.assertEqual('logo123@mail.gmail.com', attachments[0]['content_id'])

    def test_content_id_defaults_to_empty_string_when_absent(self):
        payload = {
            'parts': [{
                'filename': 'report.pdf',
                'mimeType': 'application/pdf',
                'body': {'attachmentId': 'att-2', 'size': 5000},
                'headers': [],
            }],
        }
        attachments = GmailService._get_attachments(None, payload)
        self.assertEqual('', attachments[0]['content_id'])

    def test_nested_parts_are_still_walked(self):
        payload = {
            'parts': [{
                'mimeType': 'multipart/related',
                'parts': [{
                    'filename': 'inline.jpg',
                    'mimeType': 'image/jpeg',
                    'body': {'attachmentId': 'att-3', 'size': 777},
                    'headers': [{'name': 'Content-ID', 'value': '<deep@x>'}],
                }],
            }],
        }
        attachments = GmailService._get_attachments(None, payload)
        self.assertEqual(1, len(attachments))
        self.assertEqual('deep@x', attachments[0]['content_id'])


class InlineImageRewriteTests(unittest.TestCase):
    """_rewrite_inline_image_refs turns src="cid:xxx" into a fetchable
    /email/attachment/<message_id>/<attachment_id> URL -- without it, an
    inline-embedded image (very common for signatures/logos) is just a
    broken icon, since sanitize_email_html correctly drops bare cid:
    sources (they have no legitimate meaning to a web client)."""

    def test_rewrites_matching_cid_reference(self):
        html = '<img src="cid:logo123@mail.gmail.com">'
        attachments = [{'id': 'att-1', 'content_id': 'logo123@mail.gmail.com'}]
        result = GmailService._rewrite_inline_image_refs(html, 'msg-1', attachments)
        self.assertEqual('<img src="/email/attachment/msg-1/att-1?preview=1">', result)

    def test_unmatched_cid_is_left_untouched(self):
        html = '<img src="cid:unknown@mail.gmail.com">'
        attachments = [{'id': 'att-1', 'content_id': 'logo123@mail.gmail.com'}]
        result = GmailService._rewrite_inline_image_refs(html, 'msg-1', attachments)
        self.assertEqual(html, result)

    def test_no_attachments_with_content_id_returns_input_unchanged(self):
        html = '<img src="cid:x@y">'
        result = GmailService._rewrite_inline_image_refs(html, 'msg-1', [])
        self.assertEqual(html, result)

    def test_empty_html_returns_as_is(self):
        self.assertEqual('', GmailService._rewrite_inline_image_refs('', 'msg-1', []))

    def test_rewritten_url_survives_sanitization(self):
        """The whole point -- confirm the rewritten URL is still present
        after sanitize_email_html runs (a bare cid: would have been
        dropped by its protocol allow-list)."""
        from services.email_html_sanitizer import sanitize_email_html

        html = '<img src="cid:logo123@mail.gmail.com" alt="logo">'
        attachments = [{'id': 'att-1', 'content_id': 'logo123@mail.gmail.com'}]
        rewritten = GmailService._rewrite_inline_image_refs(html, 'msg-1', attachments)
        sanitized = sanitize_email_html(rewritten)
        self.assertIn('/email/attachment/msg-1/att-1?preview=1', sanitized)


if __name__ == '__main__':
    unittest.main()
