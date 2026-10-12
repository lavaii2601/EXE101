async function apiFetch(url, options = {}) {
    try {
        const method = String(options.method || 'GET').toUpperCase();
        // Every /api/ call carries the active Business workspace (if any) so
        // workspace-scoped routes (Phase 3+) can resolve tenant context
        // without every call site doing it individually. Routes that don't
        // scope by workspace yet simply ignore the header.
        const headers = { ...(options.headers || {}) };
        if (currentOrgWorkspaceId && String(url).startsWith(API_BASE)) {
            headers['X-Workspace-Id'] = currentOrgWorkspaceId;
        }
        const resp = await fetch(url, {
            credentials: 'include',
            ...options,
            headers,
        });

        if (resp.status === 401) {
            let authError = {};
            try {
                authError = await resp.clone().json();
            } catch (_) {
                authError = {};
            }
            // A valid FlowMate session may still need its Google integration
            // reconnected. That must not hide the whole workspace on web while
            // the APK (or another worker) still has valid app authentication.
            if (authError.auth_scope !== 'google') {
                isAuthenticated = false;
                lastAuthStatus = null;
                stopWorkspaceSyncWatcher();
                showAuthGate(ui(
                    'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
                    'Your session has expired. Please sign in again.'
                ));
            }
        }

        if (method !== 'GET' && String(url).includes(`${API_BASE}/schedule`)) {
            invalidateScheduleCaches();
        }

        return resp;
    } catch (err) {
        throw err;
    }
}


const TOAST_COLORS = {
    success: '#4CAF50',
    error: '#e53935',
    warning: '#f39c12',
    info: '#2196F3',
    mail: '#7C4DFF'
};

let toastStackEl = null;
function getToastStack() {
    if (!toastStackEl || !document.body.contains(toastStackEl)) {
        toastStackEl = document.createElement('div');
        toastStackEl.id = 'toastStack';
        toastStackEl.setAttribute('aria-live', 'polite');
        toastStackEl.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: min(360px, calc(100vw - 32px));
            pointer-events: none;
        `;
        document.body.appendChild(toastStackEl);
    }
    return toastStackEl;
}

function showNotification(message, type = 'info', options = {}) {
    const stack = getToastStack();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
        pointer-events: auto;
        background: ${TOAST_COLORS[type] || TOAST_COLORS.info};
        color: white;
        padding: 14px 16px;
        border-radius: 10px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.2);
        font-size: 14px;
        line-height: 1.4;
        display: flex;
        align-items: flex-start;
        gap: 10px;
        animation: toastSlideIn 0.25s ease-out;
    `;

    const textEl = document.createElement('div');
    textEl.style.cssText = 'flex: 1; word-break: break-word;';
    textEl.textContent = message;
    toast.appendChild(textEl);

    const dismiss = () => {
        toast.style.animation = 'toastSlideOut 0.2s ease-in forwards';
        setTimeout(() => toast.remove(), 200);
    };

    if (options.actionLabel && typeof options.onAction === 'function') {
        const actionBtn = document.createElement('button');
        actionBtn.type = 'button';
        actionBtn.textContent = options.actionLabel;
        actionBtn.style.cssText = `
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 13px;
            cursor: pointer;
            white-space: nowrap;
        `;
        actionBtn.addEventListener('click', () => {
            options.onAction();
            dismiss();
        });
        toast.appendChild(actionBtn);
    }

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Dismiss');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = `
        background: none;
        border: none;
        color: white;
        opacity: 0.8;
        font-size: 18px;
        line-height: 1;
        cursor: pointer;
        padding: 0 2px;
    `;
    closeBtn.addEventListener('click', dismiss);
    toast.appendChild(closeBtn);

    stack.appendChild(toast);
    setTimeout(dismiss, options.autoDismissMs || 4500);
    return toast;
}


function openExternalUrl(url) {
    const popup = window.open(url, '_blank', 'noopener,noreferrer');
    if (popup) popup.opener = null;
}


function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function renderMarkdown(text) {
    let result = text;
    result = result.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
    result = result.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
    result = result.replace(/\[([^\]]+)\]\(([^\)]+)\)/g, (match, label, url) => {
        const safeUrl = sanitizeExternalUrl(url);
        return safeUrl
            ? `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>`
            : label;
    });
    result = result.replace(/\n/g, '<br>');
    return result;
}


function sanitizeExternalUrl(value) {
    try {
        const parsed = new URL(String(value || '').trim(), window.location.origin);
        if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol)) return '';
        return escapeHtml(parsed.href);
    } catch (error) {
        return '';
    }
}

function formatEmailText(text) {
    const tagTokens = {
        '\u0001EMAIL_BOLD_OPEN\u0001': '<strong>',
        '\u0001EMAIL_BOLD_CLOSE\u0001': '</strong>'
    };
    const normalized = String(text == null ? '' : text)
        .replace(/\r\n?/g, '\n')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<(?:b|strong)\s*>/gi, '\u0001EMAIL_BOLD_OPEN\u0001')
        .replace(/<\/(?:b|strong)\s*>/gi, '\u0001EMAIL_BOLD_CLOSE\u0001')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    let escaped = escapeHtml(normalized);
    Object.entries(tagTokens).forEach(([token, html]) => {
        escaped = escaped.split(token).join(html);
    });
    const linked = escaped.replace(
        /(https?:\/\/[^\s<]+)/gi,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    return linked
        .split(/\n{2,}/)
        .map(block => `<p>${block.replace(/\n/g, '<br>')}</p>`)
        .join('');
}


// -- Raw HTML email body rendering -----------------------------------
// The backend already allow-list-sanitizes html_body (services/
// email_html_sanitizer.py) before it ever reaches a client, but this is
// the one client with a real browser + JS engine behind innerHTML
// (unlike flutter_html/react-native-render-html, which can't execute
// script at all) -- DOMPurify is a second, independent sanitizer pass
// right before render. If it failed to load (CDN hiccup), we render the
// plain-text body instead of ever trusting unsanitized HTML to innerHTML.
function sanitizeEmailHtmlForRender(html) {
    if (!html || typeof window.DOMPurify === 'undefined') return '';
    try {
        return window.DOMPurify.sanitize(html, {
            ALLOWED_TAGS: [
                'a', 'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'p', 'br', 'div', 'span',
                'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'hr',
                'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'img', 'font',
                'pre', 'code', 'small', 'sub', 'sup',
            ],
            ALLOWED_ATTR: [
                'href', 'title', 'src', 'alt', 'width', 'height', 'color', 'size', 'face',
                'colspan', 'rowspan', 'align', 'valign', 'border', 'cellpadding', 'cellspacing', 'style',
            ],
            ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
        }).trim();
    } catch (error) {
        return '';
    }
}

function emailHtmlBodyIsRenderable(html) {
    const visibleText = String(html || '')
        .replace(/<[^>]*>/g, ' ')
        .replace(/&[a-zA-Z#0-9]+;/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    return visibleText.length >= 20;
}


// -- Structured AI/extractive email summary rendering -----------------
// Mirrors the exact section headers services/extractive_summary.py's
// summarize_structured() and ai_service.py's _EMAIL_SUMMARY_SYSTEM_PROMPT
// both emit, so AI-generated and local-fallback summaries render through
// the same card UI without the caller needing to know which one ran.
const EMAIL_SUMMARY_SECTION_ORDER = ['TÓM TẮT', 'ĐIỂM CHÍNH', 'CẦN LÀM', 'THỜI HẠN', 'TÀI LIỆU'];
const EMAIL_SUMMARY_SECTION_META = {
    'TÓM TẮT': { icon: '📝', vi: 'Tóm tắt', en: 'Summary' },
    'ĐIỂM CHÍNH': { icon: '📌', vi: 'Điểm chính', en: 'Key points' },
    'CẦN LÀM': { icon: '✅', vi: 'Cần làm', en: 'Action items' },
    'THỜI HẠN': { icon: '⏰', vi: 'Thời hạn', en: 'Deadlines' },
    'TÀI LIỆU': { icon: '📎', vi: 'Tài liệu', en: 'Documents' },
};

function parseEmailSummarySections(summaryText) {
    const text = String(summaryText || '').replace(/\r\n/g, '\n').trim();
    if (!text) return [];
    const blocks = text.split(/\n{2,}/);
    const sections = [];
    blocks.forEach((block) => {
        const lines = block.split('\n');
        const firstLine = (lines[0] || '').trim();
        // Case-insensitive: the backend always emits exact uppercase
        // headers, but an AI call that drifts on casing (e.g. "Cần làm")
        // must still be recognized as its section instead of silently
        // glomming onto whichever section came before it.
        const matchedHeader = EMAIL_SUMMARY_SECTION_ORDER.find(
            (header) => header.toUpperCase() === firstLine.toUpperCase()
        );
        if (matchedHeader) {
            sections.push({ title: matchedHeader, body: lines.slice(1).join('\n').trim() });
        } else if (sections.length) {
            // A stray blank line inside one section's own body must not be
            // mistaken for the start of a new, untitled section.
            sections[sections.length - 1].body += `\n\n${block}`;
        } else {
            sections.push({ title: null, body: block });
        }
    });
    return sections.filter((section) => section.body);
}

function emailSummaryOverviewText(summaryText) {
    const sections = parseEmailSummarySections(summaryText);
    const overview = sections.find((section) => section.title === 'TÓM TẮT') || sections[0];
    return overview ? overview.body.replace(/\s+/g, ' ').trim() : '';
}

function formatEmailSummaryBodyHtml(body) {
    const lines = String(body || '').split('\n').map((line) => line.trim()).filter(Boolean);
    if (!lines.length) return '';
    const isBulletList = lines.every((line) => line.startsWith('-'));
    const linkify = (escaped) => escaped.replace(
        /(https?:\/\/[^\s<]+)/gi,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    if (isBulletList) {
        const items = lines.map((line) => `<li>${linkify(escapeHtml(line.replace(/^-\s*/, '')))}</li>`).join('');
        return `<ul class="email-summary-list">${items}</ul>`;
    }
    return `<p>${linkify(escapeHtml(body.trim())).replace(/\n/g, '<br>')}</p>`;
}

function renderEmailSummaryCard(summaryText) {
    const sections = parseEmailSummarySections(summaryText);
    if (!sections.length) return '';
    return sections.map(({ title, body }) => {
        const meta = title && EMAIL_SUMMARY_SECTION_META[title];
        const bodyHtml = formatEmailSummaryBodyHtml(body);
        if (!meta) {
            return `<div class="email-summary-section email-summary-section--plain">${bodyHtml}</div>`;
        }
        return `<div class="email-summary-section">
            <div class="email-summary-section-title">
                <span class="email-summary-section-icon" aria-hidden="true">${meta.icon}</span>
                <span>${ui(meta.vi, meta.en)}</span>
            </div>
            ${bodyHtml}
        </div>`;
    }).join('');
}


function formatDateForApi(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function plainTextFromHtml(value) {
    let decoded = String(value || '').trim();
    for (let index = 0; index < 2; index += 1) {
        const container = document.createElement('div');
        container.innerHTML = decoded
            .replace(/<br\s*\/?>/gi, '\n')
            .replace(/<\/(?:p|div|li|h[1-6])>/gi, '\n');
        const next = container.textContent || container.innerText || '';
        if (next === decoded) break;
        decoded = next;
    }
    return decoded
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n[ \t]+/g, '\n')
        .replace(/[ \t]{2,}/g, ' ')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

function getMonday(date) {
    const d = new Date(date);
    const day = d.getDay(); // 0 = Sunday, 1 = Monday, ...
    const diff = (day === 0 ? -6 : 1) - day;
    d.setDate(d.getDate() + diff);
    d.setHours(0, 0, 0, 0);
    return d;
}

// WEEKLY SCHEDULE TABLE (Mon-Sun, synced with Google Calendar)
function weekDayNames() {
    return currentLanguage === 'en'
        ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        : ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'];
}
