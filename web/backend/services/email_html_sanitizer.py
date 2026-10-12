"""Strict allow-list HTML sanitizer for raw email bodies.

An email's HTML is attacker-controlled -- any sender can shape it -- but it
still needs to render with real formatting (bold, headings, lists, tables,
inline images, colors) across a real browser (web, genuine innerHTML in a
JS engine) and two non-WebView renderers (flutter_html, react-native-
render-html -- neither executes script or runs a layout/CSS engine capable
of side effects). This strips every tag, attribute, and CSS property
capable of running script or disguising a dangerous URL (script/style
tags, on*-handlers, javascript:/data: URLs, CSS position/behavior/etc.)
while keeping everything that actually affects how an email *looks*, so
the result still resembles the original message instead of flattened
plain text.

Replaces the previous regex-only strip (script/style/comments) in
gmail_service.py, which left onerror=/onclick=/javascript: hrefs
completely untouched -- safe only by accident, since nothing rendered that
HTML to a client before.
"""
import bleach
from bleach.css_sanitizer import CSSSanitizer

ALLOWED_TAGS = [
    'a', 'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'p', 'br', 'div', 'span',
    'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'hr',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'img', 'font',
    'pre', 'code', 'small', 'sub', 'sup',
]
ALLOWED_ATTRS = {
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'width', 'height'],
    'font': ['color', 'size', 'face'],
    'td': ['colspan', 'rowspan', 'align', 'valign'],
    'th': ['colspan', 'rowspan', 'align', 'valign'],
    'table': ['border', 'cellpadding', 'cellspacing'],
    '*': ['style', 'align'],
}
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']
# No 'position'/'behavior'/'float'/etc -- layout/escape-prone properties a
# sender has no legitimate formatting reason to need in an email body.
ALLOWED_CSS_PROPERTIES = [
    'color', 'background-color', 'font-weight', 'font-style', 'font-size',
    'font-family', 'text-decoration', 'text-align', 'line-height',
    'padding', 'margin', 'border', 'border-collapse', 'width', 'height',
]

_css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)


def sanitize_email_html(html_content):
    """Allow-list sanitize a raw email HTML body for safe client rendering.

    Returns '' for empty input. Never raises -- a malformed fragment just
    comes back with whatever bleach could still parse, which is always
    safer than the untouched original.
    """
    if not html_content:
        return ''
    try:
        cleaned = bleach.clean(
            str(html_content),
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRS,
            protocols=ALLOWED_PROTOCOLS,
            css_sanitizer=_css_sanitizer,
            strip=True,
            strip_comments=True,
        )
    except Exception:
        return ''
    return cleaned.strip()
