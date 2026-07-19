import base64
import html
import ipaddress
import logging
import re
import socket
import unicodedata
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests

from config import Config

logger = logging.getLogger(__name__)


def _normalize_text(value):
    value = unicodedata.normalize('NFD', str(value or '').lower())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn')
    return value.replace('đ', 'd')


def _clean_text(value, limit=None):
    text = html.unescape(str(value or ''))
    text = re.sub(r'(?is)<(script|style|noscript|svg|form).*?</\1>', ' ', text)
    text = re.sub(r'(?is)<!--.*?-->', ' ', text)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(p|div|li|h[1-6]|tr)>', '\n', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    if limit and len(text) > limit:
        return text[:limit].rsplit(' ', 1)[0].strip() + '...'
    return text


class WebResearchService:
    """Small, bounded web research helper for Bob.

    It intentionally does not run as a crawler. The chat agent calls it only
    for prompts that ask for web/current information, and every fetch is
    time, byte, result, and network-scope limited.
    """

    SEARCH_URL = 'https://duckduckgo.com/html/'
    INSTANT_ANSWER_URL = 'https://api.duckduckgo.com/'
    BING_SEARCH_URL = 'https://www.bing.com/search'
    USER_AGENT = (
        'FlowMateBob/1.0 (+https://flowmate.local) '
        'Mozilla/5.0 compatible web research'
    )

    _EXPLICIT_WEB_TERMS = (
        'internet', 'tren mang', 'len mang', 'web', 'website', 'google',
        'tim tren mang', 'tim kiem tren mang', 'tim kiem web', 'tra cuu web',
        'search web', 'web search', 'browse', 'research online', 'online',
        'nguon tren mang', 'link tham khao', 'nguon tham khao',
    )
    _CURRENT_INFO_TERMS = (
        'moi nhat', 'gan day', 'cap nhat', 'hien nay', 'bay gio', 'hom nay',
        'tin moi', 'tin tuc', 'xu huong', 'phien ban moi', 'latest', 'newest',
        'recent', 'current', 'today', 'news', 'trending', 'updated',
    )
    _SEARCH_COMMAND_TERMS = (
        'hay tim hieu', 'tim hieu ve', 'tim giup', 'tim thong tin',
        'tra cuu', 'tim kiem', 'kiem tra', 'kiem chung', 'xac minh',
        'xem giup thong tin', 'check giup', 'look up', 'search for',
        'find information', 'find out', 'verify', 'fact check', 'research',
    )
    _PRIVATE_WORKSPACE_SOURCES = {'email', 'calendar', 'history', 'profile'}

    # Short greetings/acks that would otherwise look like a "knowledge gap"
    # (the TF-IDF knowledge base has no document about "chao"/"hi" either)
    # and wrongly trigger a web search. Anchored + bounded to a couple of
    # trailing words so a real question that merely starts with "cam on
    # nhung..." still falls through to the knowledge-gap check below.
    _SMALLTALK_PATTERNS = tuple(re.compile(p) for p in (
        r'^(xin\s+)?chao(\s+\w+){0,2}$',
        r'^hi(\s+\w+){0,2}$',
        r'^hello(\s+\w+){0,2}$',
        r'^(cam\s+on|thank\s?s?|thank\s+you)(\s+\w+){0,3}$',
        r'^(tam\s+biet|bye|goodbye)(\s+\w+){0,2}$',
        r'^(ok|oke|okay|uh|um|da|vang)$',
        r'^ban\s+khoe\s+khong\??$',
    ))

    def __init__(self):
        self.session = requests.Session()

    def _looks_like_smalltalk(self, normalized_stripped):
        return any(pattern.match(normalized_stripped) for pattern in self._SMALLTALK_PATTERNS)

    def should_research(self, message, workspace_sources=None, knowledge_gap=False):
        if not getattr(Config, 'WEB_RESEARCH_ENABLED', True):
            return False

        normalized = _normalize_text(message)
        stripped = normalized.strip()
        if len(stripped) < 4:
            return False

        sources = set(workspace_sources or [])
        explicit_web = any(term in normalized for term in self._EXPLICIT_WEB_TERMS)
        current_info = any(term in normalized for term in self._CURRENT_INFO_TERMS)
        search_command = any(term in normalized for term in self._SEARCH_COMMAND_TERMS)
        private_workspace = bool(sources & self._PRIVATE_WORKSPACE_SOURCES)

        # Do not send private workspace tasks to the public web unless the
        # user explicitly asks Bob to go online for that turn.
        if private_workspace and not explicit_web:
            return False

        if explicit_web or search_command or current_info:
            return True

        # Bob's own knowledge base (docs/bob-training + auto-learned memory)
        # came up empty for this question -- that is the actual "information
        # Bob wasn't trained on" case, so fall back to a public web lookup
        # instead of guessing/hallucinating, unless this just looks like
        # small talk that never needed an answer from anywhere.
        if knowledge_gap and not self._looks_like_smalltalk(stripped):
            return True

        return False

    def research(self, message, workspace_sources=None, knowledge_gap=False):
        if not self.should_research(message, workspace_sources=workspace_sources, knowledge_gap=knowledge_gap):
            return {'query': '', 'results': [], 'context': ''}

        query = self._build_query(message)
        if not query:
            return {'query': '', 'results': [], 'context': ''}

        try:
            results = self._search_duckduckgo(query)
            if not results:
                results = self._search_bing(query)
            if not results:
                results = self._instant_answer_fallback(query)
        except Exception:
            logger.warning("Web research search failed for query: %s", query, exc_info=True)
            results = []

        if not results:
            return {'query': query, 'results': [], 'context': ''}

        max_results = max(1, min(int(getattr(Config, 'WEB_RESEARCH_MAX_RESULTS', 3)), 5))
        max_fetch_pages = max(0, min(int(getattr(Config, 'WEB_RESEARCH_FETCH_PAGES', 2)), max_results))

        enriched = []
        fetched = 0
        for result in results[:max_results]:
            item = dict(result)
            if fetched < max_fetch_pages and item.get('url'):
                page = self._fetch_page(item['url'])
                fetched += 1
                if page:
                    item['url'] = page.get('url') or item.get('url')
                    if page.get('title') and len(page['title']) > len(item.get('title') or ''):
                        item['title'] = page['title']
                    if page.get('snippet'):
                        item['snippet'] = page['snippet']
            enriched.append(item)

        context = self._format_context(query, enriched)
        return {'query': query, 'results': enriched, 'context': context}

    def _build_query(self, message):
        text = _normalize_text(message)
        removable_phrases = sorted(
            self._EXPLICIT_WEB_TERMS + self._SEARCH_COMMAND_TERMS,
            key=len,
            reverse=True,
        )
        for phrase in removable_phrases:
            text = text.replace(phrase, ' ')
        text = re.sub(r'[\w.+-]+@[\w.-]+\.\w+', ' ', text)
        text = re.sub(r'\b(?:\+?\d[\d\s().-]{7,}\d)\b', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip(' ?!.,;:')
        if len(text) < 3:
            text = _normalize_text(message).strip(' ?!.,;:')
        return text[:180]

    def _search_duckduckgo(self, query):
        response = self.session.get(
            self.SEARCH_URL,
            params={'q': query},
            headers={'User-Agent': self.USER_AGENT},
            timeout=self._timeout(),
        )
        response.raise_for_status()
        body = response.text
        matches = list(re.finditer(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        ))
        results = []
        seen = set()
        for index, match in enumerate(matches):
            raw_url = match.group(1)
            url = self._normalize_result_url(raw_url)
            if not self._is_public_http_url(url) or url in seen:
                continue
            title = _clean_text(match.group(2), limit=180)
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else start + 2200
            window = body[start:end]
            snippet_match = re.search(
                r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                window,
                flags=re.IGNORECASE | re.DOTALL,
            ) or re.search(
                r'<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
                window,
                flags=re.IGNORECASE | re.DOTALL,
            )
            snippet = _clean_text(snippet_match.group(1), limit=360) if snippet_match else ''
            results.append({'title': title or url, 'url': url, 'snippet': snippet})
            seen.add(url)
            if len(results) >= 8:
                break
        return results

    def _search_bing(self, query):
        response = self.session.get(
            self.BING_SEARCH_URL,
            params={'q': query, 'mkt': 'en-US'},
            headers={'User-Agent': self.USER_AGENT},
            timeout=self._timeout(),
        )
        response.raise_for_status()
        body = response.text
        blocks = re.findall(
            r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"[^>]*>(.*?)</li>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        results = []
        seen = set()
        for block in blocks:
            link_match = re.search(
                r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not link_match:
                continue
            url = self._normalize_bing_url(html.unescape(link_match.group(1)).strip())
            if not self._is_public_http_url(url) or url in seen:
                continue
            title = _clean_text(link_match.group(2), limit=180)
            snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.IGNORECASE | re.DOTALL)
            snippet = _clean_text(snippet_match.group(1), limit=360) if snippet_match else ''
            results.append({'title': title or url, 'url': url, 'snippet': snippet})
            seen.add(url)
            if len(results) >= 8:
                break
        return results

    def _normalize_bing_url(self, url):
        parsed = urlparse(url)
        if not parsed.netloc.endswith('bing.com'):
            return url
        query = parse_qs(parsed.query)
        target = (query.get('url') or query.get('u') or [''])[0]
        if not target:
            return url
        if target.startswith(('http://', 'https://')):
            return target
        if target.startswith('a1'):
            payload = target[2:]
            padding = '=' * (-len(payload) % 4)
            try:
                decoded = base64.urlsafe_b64decode(payload + padding).decode('utf-8', errors='ignore')
                if decoded.startswith(('http://', 'https://')):
                    return decoded
            except Exception:
                return url
        return url

    def _instant_answer_fallback(self, query):
        response = self.session.get(
            self.INSTANT_ANSWER_URL,
            params={'q': query, 'format': 'json', 'no_redirect': 1, 'no_html': 1},
            headers={'User-Agent': self.USER_AGENT},
            timeout=self._timeout(),
        )
        response.raise_for_status()
        data = response.json()
        results = []
        abstract = _clean_text(data.get('AbstractText'), limit=900)
        abstract_url = data.get('AbstractURL') or f'https://duckduckgo.com/?q={quote_plus(query)}'
        if abstract and self._is_public_http_url(abstract_url):
            results.append({
                'title': data.get('Heading') or query,
                'url': abstract_url,
                'snippet': abstract,
            })

        def add_related(items):
            for item in items or []:
                if 'Topics' in item:
                    add_related(item.get('Topics'))
                    continue
                text = _clean_text(item.get('Text'), limit=360)
                url = item.get('FirstURL') or ''
                if text and self._is_public_http_url(url):
                    results.append({'title': text.split(' - ', 1)[0][:160], 'url': url, 'snippet': text})
                if len(results) >= 5:
                    return

        add_related(data.get('RelatedTopics'))
        return results

    def _fetch_page(self, url):
        if not self._is_public_http_url(url):
            return None
        try:
            with self.session.get(
                url,
                headers={'User-Agent': self.USER_AGENT},
                timeout=self._timeout(),
                allow_redirects=True,
                stream=True,
            ) as response:
                response.raise_for_status()
                final_url = response.url
                if not self._is_public_http_url(final_url):
                    return None
                content_type = (response.headers.get('Content-Type') or '').lower()
                if content_type and not (
                    'text/html' in content_type
                    or 'text/plain' in content_type
                    or 'application/xhtml' in content_type
                ):
                    return None
                raw = bytearray()
                max_bytes = max(16384, int(getattr(Config, 'WEB_RESEARCH_MAX_BYTES', 180000)))
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    remaining = max_bytes - len(raw)
                    if remaining <= 0:
                        break
                    raw.extend(chunk[:remaining])
                    if len(raw) >= max_bytes:
                        break
                encoding = response.encoding or 'utf-8'
                body = bytes(raw).decode(encoding, errors='ignore')
        except Exception:
            logger.debug("Skipping web page fetch: %s", url, exc_info=True)
            return None

        title_match = re.search(r'(?is)<title[^>]*>(.*?)</title>', body)
        title = _clean_text(title_match.group(1), limit=180) if title_match else ''
        readable = re.sub(r'(?is)<(head|script|style|noscript|svg|nav|footer|aside|form).*?</\1>', ' ', body)
        snippet = _clean_text(readable, limit=int(getattr(Config, 'WEB_RESEARCH_MAX_CHARS', 1800)))
        return {'url': final_url, 'title': title, 'snippet': snippet}

    def _normalize_result_url(self, raw_url):
        url = html.unescape(raw_url or '').strip()
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/'):
            url = urljoin('https://duckduckgo.com', url)

        parsed = urlparse(url)
        if parsed.netloc.endswith('duckduckgo.com'):
            target = parse_qs(parsed.query).get('uddg')
            if target:
                url = unquote(target[0])
        return url

    def _is_public_http_url(self, url):
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {'http', 'https'}:
                return False
            hostname = parsed.hostname
            if not hostname:
                return False
            host_lower = hostname.lower().rstrip('.')
            if host_lower in {'localhost'} or host_lower.endswith('.local'):
                return False
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            infos = socket.getaddrinfo(host_lower, port, proto=socket.IPPROTO_TCP)
            if not infos:
                return False
            for family, _, _, _, sockaddr in infos:
                ip = ipaddress.ip_address(sockaddr[0])
                if not ip.is_global:
                    return False
            return True
        except Exception:
            return False

    def _format_context(self, query, results):
        lines = [
            "INTERNET RESEARCH",
            f"Query: {query}",
            f"Retrieved at: {datetime.utcnow().replace(microsecond=0).isoformat()}Z",
            "Use these external sources only for public web facts. Cite titles or URLs when answering.",
        ]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. {result.get('title') or result.get('url')}")
            lines.append(f"   URL: {result.get('url')}")
            snippet = _clean_text(result.get('snippet'), limit=1200)
            if snippet:
                lines.append(f"   Snippet: {snippet}")
        return "\n".join(lines)

    def _timeout(self):
        value = int(getattr(Config, 'WEB_RESEARCH_TIMEOUT', 8))
        return max(2, min(value, 15))


web_research_service = WebResearchService()
