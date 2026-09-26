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
