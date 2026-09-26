// ---------------------------------------------------------------------------
// In-app notifications (Phase 6, design doc section 9.9/15) -- renewal
// reminders and grace/read-only transitions from
// services/subscription_lifecycle_scheduler.py.
// ---------------------------------------------------------------------------

let notificationPollTimer = null;
const NOTIFICATION_POLL_INTERVAL_MS = 5 * 60 * 1000;

function setupNotificationUI() {
    const bellBtn = document.getElementById('notificationBellBtn');
    const popup = document.getElementById('notificationPopup');
    bellBtn?.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleNotificationPopup();
    });
    document.addEventListener('click', () => closeNotificationPopup());
    popup?.addEventListener('click', (event) => event.stopPropagation());

    loadNotifications({ silent: true });
    if (notificationPollTimer) clearInterval(notificationPollTimer);
    notificationPollTimer = setInterval(() => loadNotifications({ silent: true }), NOTIFICATION_POLL_INTERVAL_MS);
}

function toggleNotificationPopup() {
    const popup = document.getElementById('notificationPopup');
    const btn = document.getElementById('notificationBellBtn');
    if (!popup || !btn) return;
    const isOpen = popup.classList.toggle('show');
    btn.setAttribute('aria-expanded', String(isOpen));
    if (isOpen) loadNotifications();
}

function closeNotificationPopup() {
    document.getElementById('notificationPopup')?.classList.remove('show');
    document.getElementById('notificationBellBtn')?.setAttribute('aria-expanded', 'false');
}

async function loadNotifications({ silent = false } = {}) {
    if (!isAuthenticated) return;
    try {
        const resp = await apiFetch(`${API_BASE}/notifications`);
        const data = await resp.json();
        if (!resp.ok || !data.success) return;
        renderNotifications(data.notifications || [], data.unread_count || 0);
    } catch (err) {
        if (!silent) console.warn('loadNotifications failed', err);
    }
}

function renderNotifications(notifications, unreadCount) {
    const badge = document.getElementById('notificationBadge');
    if (badge) {
        badge.textContent = unreadCount > 99 ? '99+' : String(unreadCount);
        badge.hidden = unreadCount <= 0;
    }
    const listEl = document.getElementById('notificationList');
    if (!listEl) return;
    if (!notifications.length) {
        listEl.innerHTML = `<div class="notification-empty">${ui('Chưa có thông báo nào.', 'No notifications yet.')}</div>`;
        return;
    }
    listEl.innerHTML = notifications.map((item) => `
        <button type="button" class="notification-item severity-${escapeHtml(item.severity || 'info')}${!item.read_at ? ' is-unread' : ''}" data-notification-id="${escapeHtml(item.id)}" data-action-url="${escapeHtml(item.action_url || '')}">
            <strong>${escapeHtml(item.title)}</strong>
            ${item.body ? `<p>${escapeHtml(item.body)}</p>` : ''}
            <small>${escapeHtml(formatEmailListDate(item.created_at))}</small>
        </button>
    `).join('');
    listEl.querySelectorAll('[data-notification-id]').forEach((btn) => {
        btn.addEventListener('click', () => handleNotificationClick(btn));
    });
}

async function handleNotificationClick(btn) {
    const id = btn.getAttribute('data-notification-id');
    const actionUrl = btn.getAttribute('data-action-url') || '';
    try {
        await apiFetch(`${API_BASE}/notifications/${id}/read`, { method: 'POST' });
    } catch (err) {
        console.warn('mark notification read failed', err);
    }
    closeNotificationPopup();
    loadNotifications({ silent: true });
    if (actionUrl.includes('page=settings')) {
        const settingsNavBtn = document.querySelector('[data-page="settings"]');
        if (settingsNavBtn) handlePageChange(settingsNavBtn);
    }
}
