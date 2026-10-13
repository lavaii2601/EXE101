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
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

# bleach.clean() strips a disallowed TAG but keeps its inner text (so a
# disallowed <div class="weird">hello</div> correctly becomes just
# "hello") -- but <head>/<style>/<script>/<title> are opaque-content
# elements whose "text" (CSS rules, JS source, page title) was never part
# of the message a reader should see. Left to bleach alone, a real HTML
# newsletter's <head><style>...hundreds of CSS rules...</style></head>
# (common -- most ESP templates inline their CSS this way) would dump
# that raw CSS as the first thing visible in the rendered email body.
# Stripped here, before bleach ever sees them, tag and all.
_OPAQUE_BLOCK_RE = re.compile(r'(?is)<(head|style|script|title)\b[^>]*>.*?</\1>')

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
# 'cid' matters for both directions: on receive, _rewrite_inline_image_refs
# (gmail_service.py) already turns every *resolvable* cid: into a real URL
# before this ever runs, so any cid: still present here is one with no
# matching attachment -- harmless either way, since a browser can't
# resolve a bare cid: scheme regardless. On send (routes/email/compose.py),
# the composer's own trusted inline-image flow needs its cid:<content_id>
# placeholders to survive sanitization so they still match the inline
# image part Gmail attaches alongside the HTML.
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'cid']
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
        without_opaque_blocks = _OPAQUE_BLOCK_RE.sub('', str(html_content))
        cleaned = bleach.clean(
            without_opaque_blocks,
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
