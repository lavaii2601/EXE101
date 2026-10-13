import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.email_html_sanitizer import sanitize_email_html  # noqa: E402


class EmailHtmlSanitizerTests(unittest.TestCase):
    """sanitize_email_html feeds attacker-controlled HTML (any email sender)
    straight into a real browser's innerHTML on web -- unlike flutter_html/
    react-native-render-html, which don't execute script at all, a browser
    genuinely runs onerror=/javascript:/<script> content. Every XSS vector
    here must come back neutralized; every plain formatting case must
    still look like the original message, or the 'professional like
    Gmail' rendering this unlocks has nothing real to render."""

    def test_strips_script_tag(self):
        result = sanitize_email_html('<script>alert(1)</script><p>hello</p>')
        self.assertNotIn('<script', result)
        self.assertIn('hello', result)

    def test_script_tag_content_is_discarded_not_unwrapped(self):
        """A disallowed tag normally keeps its inner text when unwrapped
        (bleach's default) -- but <script>'s "text" is JS source, not
        message content, so it must disappear with the tag, not leak out
        as a visible wall of code."""
        result = sanitize_email_html('<script>var x = 1; alert(x);</script><p>hello</p>')
        self.assertNotIn('alert', result)
        self.assertIn('hello', result)

    def test_style_tag_content_is_discarded_not_unwrapped(self):
        """Same as script, but for a <head><style> block -- a real,
        common shape for HTML newsletter templates. Left unwrapped, the
        raw CSS rules would be the first thing a reader sees."""
        html = (
            '<html><head><style>body { margin:0; color:#000; } '
            '.deviceWidth { width:300px !important; }</style></head>'
            '<body><p>Hello <b>world</b></p></body></html>'
        )
        result = sanitize_email_html(html)
        self.assertNotIn('margin', result)
        self.assertNotIn('deviceWidth', result)
        self.assertIn('Hello', result)
        self.assertIn('<b>world</b>', result)

    def test_title_tag_content_is_discarded(self):
        result = sanitize_email_html('<head><title>Secret internal subject line</title></head><p>hi</p>')
        self.assertNotIn('Secret internal subject line', result)
        self.assertIn('hi', result)

    def test_strips_event_handler_attributes(self):
        result = sanitize_email_html('<img src="https://x.com/a.png" onerror="alert(1)">')
        self.assertNotIn('onerror', result)
        self.assertIn('https://x.com/a.png', result)

    def test_strips_javascript_href(self):
        result = sanitize_email_html('<a href="javascript:alert(1)">click</a>')
        self.assertNotIn('javascript:', result)
        self.assertIn('click', result)

    def test_strips_data_uri_image(self):
        result = sanitize_email_html('<img src="data:text/html,<script>alert(1)</script>">')
        self.assertNotIn('data:text/html', result)
        self.assertNotIn('<script', result)

    def test_strips_onclick_attribute(self):
        result = sanitize_email_html('<p onclick="alert(1)">click me</p>')
        self.assertNotIn('onclick', result)
        self.assertIn('click me', result)

    def test_strips_dangerous_css_properties(self):
        result = sanitize_email_html('<div style="position:fixed; behavior:url(evil.htc)">x</div>')
        self.assertNotIn('position', result)
        self.assertNotIn('behavior', result)

    def test_strips_html_comments(self):
        result = sanitize_email_html('<!-- [if mso] --><p>hello</p>')
        self.assertNotIn('<!--', result)
        self.assertIn('hello', result)

    def test_keeps_safe_links(self):
        result = sanitize_email_html('<a href="https://example.com">ok</a>')
        self.assertIn('href="https://example.com"', result)

    def test_keeps_basic_formatting(self):
        result = sanitize_email_html('<p style="color:red; font-weight:bold">Hello <b>world</b></p>')
        self.assertIn('color:red', result)
        self.assertIn('font-weight:bold', result)
        self.assertIn('<b>world</b>', result)

    def test_keeps_tables(self):
        result = sanitize_email_html(
            '<table><tr><td style="background-color:#eee">cell</td></tr></table>'
        )
        self.assertIn('<table>', result)
        self.assertIn('cell', result)
        self.assertIn('background-color:#eee', result)

    def test_empty_input_returns_empty_string(self):
        self.assertEqual('', sanitize_email_html(''))
        self.assertEqual('', sanitize_email_html(None))

    def test_malformed_input_never_raises(self):
        sanitize_email_html('<div><p>unclosed')  # must not raise


if __name__ == '__main__':
    unittest.main()
