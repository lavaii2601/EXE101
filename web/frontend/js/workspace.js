function setupWorkspaceShell() {
    renderQuickActions(currentPage);
}

let quickScheduleSummaryRequestId = 0;
let weekScheduleRequestId = 0;
let scheduleListRequestId = 0;
const runtimeApiCache = new Map();
const runtimeApiInflight = new Map();

function clearRuntimeCache(prefix = '') {
    Array.from(runtimeApiCache.keys()).forEach((key) => {
        if (!prefix || key.startsWith(prefix)) runtimeApiCache.delete(key);
    });
}

async function fetchJsonCached(cacheKey, url, ttlMs = 10000) {
    const now = Date.now();
    const cached = runtimeApiCache.get(cacheKey);
    if (cached && now - cached.timestamp < ttlMs) {
        return cached.value;
    }
    if (runtimeApiInflight.has(cacheKey)) {
        return runtimeApiInflight.get(cacheKey);
    }

    const promise = apiFetch(url)
        .then(async (response) => {
            const value = await response.json();
            runtimeApiCache.set(cacheKey, { timestamp: Date.now(), value });
            return value;
        })
        .finally(() => runtimeApiInflight.delete(cacheKey));

    runtimeApiInflight.set(cacheKey, promise);
    return promise;
}

function invalidateScheduleCaches() {
    clearRuntimeCache('schedule:');
}

async function refreshLocalScheduleViews() {
    invalidateScheduleCaches();
    await Promise.allSettled([
        loadSchedules(),
        loadWeekSchedule(),
        refreshQuickScheduleSummary()
    ]);
}

async function refreshCalendarScheduleData(options = {}) {
    invalidateScheduleCaches();
    let syncedGoogle = false;
    let syncResult = null;
    try {
        const syncDays = Number.isFinite(options.days) ? options.days : 90;
        const response = await apiFetch(`${API_BASE}/schedule/sync?days=${syncDays}`, { method: 'POST' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || (data && data.success === false)) {
            if (data.error === 'not_authenticated') {
                if (!options.silent) {
                    showNotification(ui('Chưa kết nối Google Calendar', 'Google Calendar is not connected'), 'info');
                }
            } else {
                throw new Error(data.message || data.error || ui('Không thể cập nhật lịch', 'Unable to refresh calendar'));
            }
        } else {
            syncedGoogle = true;
            syncResult = data;
        }
    } catch (error) {
        if (!options.silent) {
            showNotification(ui('❌ Không thể cập nhật lịch: ', '❌ Unable to refresh calendar: ') + error.message, 'error');
        }
        if (!options.continueOnError) return;
    }

    await Promise.allSettled([
        loadSchedules(),
        loadWeekSchedule(),
        loadCalendarEvents(),
        refreshQuickScheduleSummary()
    ]);

    if (options.notify && syncedGoogle) {
        if (syncResult?.calendar_sync_error?.message) {
            showNotification(syncResult.calendar_sync_error.message, 'warning');
        } else if (syncResult?.push_failed_count > 0) {
            showNotification(ui('⚠️ Chưa đẩy được một số lịch lên Google Calendar. Hãy đăng nhập lại Google rồi thử đồng bộ.', '⚠️ Some events could not be pushed to Google Calendar. Reconnect Google and try syncing again.'), 'warning');
        } else if (syncResult?.pushed_count > 0) {
            showNotification(ui(`✅ Đã đồng bộ ${syncResult.pushed_count} lịch lên Google Calendar`, `✅ Synced ${syncResult.pushed_count} event(s) to Google Calendar`), 'success');
        } else {
            showNotification(ui('✅ Đã cập nhật lịch', '✅ Calendar refreshed'), 'success');
        }
    }
}

function syncSchedulesAfterLocalCreate(scheduleCreated = {}) {
    const shouldRetry = scheduleCreated.calendar_sync_pending || !scheduleCreated.calendar_event_id;
    if (!shouldRetry) return;
    window.setTimeout(() => {
        refreshCalendarScheduleData({
            days: 365,
            silent: true,
            continueOnError: true
        }).catch(err => console.warn('Post-create calendar sync retry failed', err));
    }, 4800);
}

const QUICK_ACTIONS = {
    chat: {
        icon: 'AI',
        title: 'Chat',
        description: 'Trò chuyện với FlowMate cho yêu cầu cần phân tích hoặc xử lý nhiều bước.',
        tip: 'Các thao tác ngắn đã được tách sang panel này để Chat tập trung vào hội thoại.',
        actions: [
            { icon: '+', label: 'Chat mới', detail: 'Bắt đầu hội thoại sạch', action: 'new-chat' },
            { icon: '✉', label: 'Mở hộp thư', detail: 'Xem và xử lý email', action: 'open-email' },
            { icon: '▣', label: 'Mở lịch tuần', detail: 'Kiểm tra lịch và cuộc họp', action: 'open-calendar' }
        ]
    },
    overview: {
        icon: 'AI',
        title: 'Tổng hợp',
        description: 'Xem nhanh email, deadline và task quan trọng trong ngày.',
        tip: 'Mở Tổng hợp vào đầu ngày để biết việc cần ưu tiên trước khi vào Chat.',
        actions: [
            { icon: '↻', label: 'Tổng hợp lại', detail: 'Cập nhật dữ liệu hôm nay', action: 'refresh-overview' },
            { icon: '✉', label: 'Xem email', detail: 'Mở hộp thư đến', action: 'open-email' },
            { icon: '▣', label: 'Xem lịch', detail: 'Mở lịch tuần', action: 'open-calendar' }
        ]
    },
    emails: {
        icon: '✉',
        title: 'Email',
        description: 'Thao tác nhanh với hộp thư mà không cần mở hội thoại AI.',
        tip: 'Chỉ dùng Chat khi cần phân tích nội dung nhiều email hoặc soạn phản hồi phức tạp.',
        actions: [
            { icon: '↻', label: 'Làm mới hộp thư', detail: 'Tải email mới nhất', action: 'refresh-email' },
            { icon: '▤', label: 'Báo cáo theo ngày', detail: 'Mở công cụ tổng hợp email', action: 'daily-report' },
            { icon: '+', label: 'Soạn email', detail: 'Tạo thư mới', action: 'compose-email' }
        ]
    },
    schedule: {
        icon: '▣',
        title: 'Calendar',
        description: 'Tạo và điều hướng lịch trực tiếp, không cần gửi lệnh qua Chat.',
        tip: 'Dùng Chat khi lịch cần suy luận từ ngôn ngữ tự nhiên hoặc nhiều điều kiện.',
        actions: [
            { icon: '+', label: 'Tạo sự kiện', detail: 'Mở biểu mẫu lịch mới', action: 'create-event' },
            { icon: '↻', label: 'Cập nhật', detail: 'Quét lại Google Calendar', action: 'refresh-calendar' },
            { icon: '◎', label: 'Về tuần này', detail: 'Hiển thị tuần hiện tại', action: 'this-week' }
        ]
    },
    history: {
        icon: '↶',
        title: 'Activity',
        description: 'Theo dõi các thao tác FlowMate đã thực hiện cho tài khoản này.',
        tip: 'Lịch sử giúp kiểm tra lại email, lịch và phản hồi AI đã xử lý.',
        actions: [
            { icon: '↻', label: 'Làm mới hoạt động', detail: 'Tải lại lịch sử mới nhất', action: 'refresh-history' }
        ]
    },
    settings: {
        icon: '⚙',
        title: 'Settings',
        description: 'Quản lý chế độ làm việc, tài khoản và tùy chọn hiển thị.',
        tip: 'Mode được lưu theo tài khoản và áp dụng cho cách FlowMate ưu tiên công việc.',
        actions: [
            { icon: '◈', label: 'Đổi chế độ', detail: 'Chọn mode làm việc khác', action: 'change-mode' },
            { icon: '↻', label: 'Đồng bộ trạng thái', detail: 'Làm mới thông tin tài khoản', action: 'refresh-settings' }
        ]
    }
};

function renderQuickActions(page) {
    const config = QUICK_ACTIONS[page] || QUICK_ACTIONS.chat;
    const icon = document.getElementById('quickContextIcon');
    const title = document.getElementById('quickContextTitle');
    const description = document.getElementById('quickContextDescription');
    const tip = document.getElementById('quickTipText');
    const list = document.getElementById('quickActionsList');
    if (!list) return;

    if (icon) icon.textContent = config.icon;
    if (title) title.textContent = config.title;
    if (description) description.textContent = config.description;
    if (tip) tip.textContent = config.tip;
    list.innerHTML = config.actions.map((item) => `
        <button type="button" class="quick-action-button" data-quick-action="${item.action}">
            <span class="quick-action-icon">${item.icon}</span>
            <span class="quick-action-copy">
                <strong>${item.label}</strong>
                <small>${item.detail}</small>
            </span>
            <span class="quick-action-arrow">→</span>
        </button>
    `).join('');
    list.querySelectorAll('[data-quick-action]').forEach((button) => {
        button.addEventListener('click', () => runQuickAction(button.dataset.quickAction));
    });

    document.getElementById('quickScheduleSummary')?.remove();
    if (page === 'schedule') {
        const summary = document.createElement('div');
        summary.id = 'quickScheduleSummary';
        summary.className = 'quick-schedule-summary';
        summary.innerHTML = `<div class="quick-schedule-loading">${ui('Đang tổng hợp lịch...', 'Loading schedule summary...')}</div>`;
        list.insertAdjacentElement('afterend', summary);
        loadQuickScheduleSummary(summary);
    }
}

async function runQuickAction(action) {
    const pageButton = (page) => document.querySelector(`.sidebar-nav [data-page="${page}"]`);
    if (action === 'new-chat') return startNewChat();
    if (action === 'open-email') return handlePageChange(pageButton('emails'));
    if (action === 'open-calendar') return handlePageChange(pageButton('schedule'));
    if (action === 'refresh-overview') return loadOverviewPage({ force: true });
    if (action === 'refresh-email') return document.getElementById('refreshEmailsBtn')?.click();
    if (action === 'daily-report') return document.querySelector('#emails-page [data-tab="daily-report"]')?.click();
    if (action === 'compose-email') return document.querySelector('#emails-page [data-tab="compose"]')?.click();
    if (action === 'create-event') return openNewScheduleModal();
    if (action === 'refresh-calendar') return refreshCalendarScheduleData({ notify: true, continueOnError: true });
    if (action === 'this-week') return document.getElementById('todayWeekBtn')?.click();
    if (action === 'refresh-history') return loadActivityHistory();
    if (action === 'change-mode') return openUserModeModal(false);
    if (action === 'refresh-settings') return loadSettingsPage();
}

async function refreshWorkspaceTargets(targets = []) {
    const uniqueTargets = Array.from(new Set(Array.isArray(targets) ? targets : []));
    if (!uniqueTargets.length) return;

    if (uniqueTargets.includes('overview')) {
        try { await loadOverviewPage({ force: false }); } catch (e) { /* ignore refresh errors */ }
    }
    if (uniqueTargets.includes('schedule')) {
        await refreshCalendarScheduleData({ silent: true, continueOnError: true });
    }
    if (uniqueTargets.includes('calendar') && !uniqueTargets.includes('schedule')) {
        await refreshCalendarScheduleData({ silent: true, continueOnError: true });
    }
    if (uniqueTargets.includes('email')) {
        try { await loadEmails(currentEmailPage || 1, { cacheOnly: true, silent: true }); } catch (e) { /* ignore refresh errors */ }
    }
    if (uniqueTargets.includes('history')) {
        try { await loadActivityHistory(); } catch (e) { /* ignore refresh errors */ }
    }
    if (uniqueTargets.includes('settings') || uniqueTargets.includes('profile')) {
        try { await loadSettingsPage(); } catch (e) { /* ignore refresh errors */ }
        try { await loadUserProfile(); } catch (e) { /* ignore refresh errors */ }
    }
    if (uniqueTargets.includes('providers')) {
        try { await checkRuntimeConfig(); } catch (e) { /* ignore refresh errors */ }
        try { await loadAgentProfile(); } catch (e) { /* ignore refresh errors */ }
    }
}

function getWorkspaceSyncOwner() {
    return String(lastAuthStatus?.user_id || lastAuthStatus?.gmail_email || '').trim().toLowerCase();
}

function getWorkspaceSyncStorageKey(ownerId) {
    return `flowmate-sync-revision:${ownerId}`;
}

function parseWorkspaceSyncRevision(value) {
    const revision = Number.parseInt(value, 10);
    return Number.isSafeInteger(revision) && revision >= 0 ? revision : null;
}

function clampWorkspaceSyncPollDelay(value) {
    const delay = Number.parseInt(value, 10);
    if (!Number.isFinite(delay)) return 12000;
    return Math.min(Math.max(delay, WORKSPACE_SYNC_POLL_MIN_MS), WORKSPACE_SYNC_POLL_MAX_MS);
}

function configureWorkspaceSyncOwner() {
    const nextOwnerId = getWorkspaceSyncOwner();
    if (!nextOwnerId) return false;
    if (workspaceSyncOwnerId === nextOwnerId) return true;

    workspaceSyncGeneration += 1;
    workspaceSyncAbortController?.abort();
    workspaceSyncAbortController = null;
    workspaceSyncInFlight = false;
    workspaceSyncOwnerId = nextOwnerId;

    const storedRevision = parseWorkspaceSyncRevision(
        localStorage.getItem(getWorkspaceSyncStorageKey(nextOwnerId))
    );
    workspaceSyncRevision = storedRevision;
    workspaceSyncHasBaseline = storedRevision !== null;
    return true;
}

function pauseWorkspaceSyncWatcher() {
    if (workspaceSyncPollTimer) {
        window.clearTimeout(workspaceSyncPollTimer);
        workspaceSyncPollTimer = null;
    }
}

function stopWorkspaceSyncWatcher() {
    pauseWorkspaceSyncWatcher();
    workspaceSyncGeneration += 1;
    workspaceSyncAbortController?.abort();
    workspaceSyncAbortController = null;
    workspaceSyncInFlight = false;
    workspaceSyncRevision = null;
    workspaceSyncOwnerId = '';
    workspaceSyncHasBaseline = false;
    workspaceSyncPollAfterMs = 12000;
}

function workspaceSyncChangedDomains(data, sinceRevision) {
    if (Array.isArray(data?.changed)) {
        return Array.from(new Set(data.changed.map((item) => String(item || '').trim()).filter(Boolean)));
    }

    // Tolerate older/pre-release field names without weakening the canonical
    // server contract (`changed`). The domains fallback is also useful during
    // rolling deploys where a newer frontend can briefly hit an older worker.
    const aliases = data?.changed_targets || data?.targets || data?.refresh_targets;
    if (Array.isArray(aliases)) {
        return Array.from(new Set(aliases.map((item) => String(item || '').trim()).filter(Boolean)));
    }
    if (data?.domains && typeof data.domains === 'object') {
        return Object.entries(data.domains)
            .filter(([, revision]) => {
                const parsed = parseWorkspaceSyncRevision(revision);
                return parsed !== null && parsed > sinceRevision;
            })
            .map(([domain]) => domain);
    }
    return [];
}

async function refreshVisibleWorkspaceChanges(changedDomains = []) {
    const changed = new Set(changedDomains);
    if (!changed.size || !isAuthenticated) return;
    const affects = (...domains) => domains.some((domain) => changed.has(domain));
    const refreshes = [];

    // Profile is visible in the workspace shell on every page. Settings and
    // provider changes also affect global connection/status controls.
    if (affects('profile', 'settings')) {
        refreshes.push(loadUserProfile());
        refreshes.push(refreshAuthButtons());
    }
    if (affects('providers')) {
        refreshes.push(checkRuntimeConfig());
        refreshes.push(loadAgentProfile());
    }

    if (currentPage === 'chat' && affects('chat', 'history')) {
        refreshes.push(loadChatSessions());
        refreshes.push(loadChatHistory());
    } else if (
        currentPage === 'overview'
        && affects('overview', 'email', 'schedule', 'calendar')
    ) {
        refreshes.push(loadOverviewPage({ background: true }));
    } else if (currentPage === 'emails' && affects('email')) {
        refreshes.push(loadEmails(currentEmailPage || 1, { cacheOnly: true, silent: true }));
        refreshes.push(loadMeetingSuggestions());
    } else if (currentPage === 'schedule') {
        if (affects('schedule', 'calendar')) {
            // The remote mutation already updated FlowMate's shared local
            // schedule state. Read that state directly; a full Google sync
            // here would be expensive and can create a cross-device loop.
            invalidateScheduleCaches();
            refreshes.push(loadSchedules());
            refreshes.push(loadWeekSchedule());
            refreshes.push(refreshQuickScheduleSummary());
        }
        if (affects('email')) {
            refreshes.push(loadMeetingSuggestions());
        }
    } else if (currentPage === 'history' && affects('history')) {
        refreshes.push(loadActivityHistory());
    } else if (
        currentPage === 'settings'
        && affects('profile', 'settings', 'email', 'providers')
    ) {
        refreshes.push(loadSettingsPage());
    }

    await Promise.allSettled(refreshes);
}

async function checkWorkspaceSyncState() {
    if (
        workspaceSyncInFlight
        || !isAuthenticated
        || document.visibilityState !== 'visible'
        || !configureWorkspaceSyncOwner()
    ) {
        return;
    }

    workspaceSyncInFlight = true;
    const generation = workspaceSyncGeneration;
    const ownerId = workspaceSyncOwnerId;
    const sinceRevision = workspaceSyncRevision ?? 0;
    const hadBaseline = workspaceSyncHasBaseline;
    const controller = new AbortController();
    workspaceSyncAbortController = controller;
    const abortTimer = window.setTimeout(() => controller.abort(), 8000);

    try {
        const response = await fetch(
            `${API_BASE}/sync/state?since=${encodeURIComponent(sinceRevision)}`,
            {
                credentials: 'include',
                headers: { Accept: 'application/json' },
                signal: controller.signal
            }
        );

        if (response.status === 401) {
            isAuthenticated = false;
            lastAuthStatus = null;
            stopWorkspaceSyncWatcher();
            showAuthGate(ui(
                'PhiÃªn Ä‘Äƒng nháº­p Ä‘Ã£ háº¿t háº¡n. Vui lÃ²ng Ä‘Äƒng nháº­p láº¡i.',
                'Your session has expired. Please sign in again.'
            ));
            return;
        }

        const data = await response.json().catch(() => ({}));
        if (
            !response.ok
            || !data.success
            || generation !== workspaceSyncGeneration
            || ownerId !== workspaceSyncOwnerId
        ) {
            return;
        }

        const nextRevision = parseWorkspaceSyncRevision(data.revision);
        if (nextRevision === null) return;
        const changedDomains = workspaceSyncChangedDomains(data, sinceRevision);

        workspaceSyncRevision = nextRevision;
        workspaceSyncHasBaseline = true;
        workspaceSyncPollAfterMs = clampWorkspaceSyncPollDelay(data.poll_after_ms);
        localStorage.setItem(getWorkspaceSyncStorageKey(ownerId), String(nextRevision));

        // A first-time browser has no meaningful cursor. Establish its
        // baseline without replaying every historical domain change.
        if (hadBaseline && changedDomains.length) {
            await refreshVisibleWorkspaceChanges(changedDomains);
        }
    } catch (error) {
        if (error?.name !== 'AbortError') {
            console.warn('Workspace sync check failed:', error);
        }
    } finally {
        window.clearTimeout(abortTimer);
        if (workspaceSyncAbortController === controller) {
            workspaceSyncAbortController = null;
        }
        if (generation === workspaceSyncGeneration) {
            workspaceSyncInFlight = false;
        }
    }
}

function scheduleWorkspaceSyncPoll() {
    pauseWorkspaceSyncWatcher();
    if (!isAuthenticated || document.visibilityState !== 'visible') return;
    workspaceSyncPollTimer = window.setTimeout(async () => {
        workspaceSyncPollTimer = null;
        await checkWorkspaceSyncState();
        scheduleWorkspaceSyncPoll();
    }, workspaceSyncPollAfterMs);
}

function startWorkspaceSyncWatcher({ immediate = true } = {}) {
    if (!isAuthenticated || !configureWorkspaceSyncOwner()) return;
    if (!workspaceSyncListenersBound) {
        workspaceSyncListenersBound = true;
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                startWorkspaceSyncWatcher({ immediate: true });
            } else {
                pauseWorkspaceSyncWatcher();
            }
        });
        window.addEventListener('focus', () => {
            if (document.visibilityState === 'visible') {
                startWorkspaceSyncWatcher({ immediate: true });
            }
        });
    }

    pauseWorkspaceSyncWatcher();
    if (document.visibilityState !== 'visible') return;
    const immediateCheck = immediate ? checkWorkspaceSyncState() : Promise.resolve();
    return immediateCheck.finally(scheduleWorkspaceSyncPoll);
}

function formatQuickScheduleDate(date) {
    return currentLanguage === 'en'
        ? date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
        : date.toLocaleDateString('vi-VN', { weekday: 'short', day: '2-digit', month: '2-digit' });
}

function formatQuickScheduleTime(schedule) {
    const start = new Date(schedule.start_time);
    if (Number.isNaN(start.getTime())) return ui('Chưa rõ giờ', 'Time unknown');
    const startText = start.toLocaleTimeString(resolveDateLocale(), {
        hour: '2-digit',
        minute: '2-digit'
    });
    if (!schedule.end_time) return startText;
    const end = new Date(schedule.end_time);
    if (Number.isNaN(end.getTime())) return startText;
    const endText = end.toLocaleTimeString(resolveDateLocale(), {
        hour: '2-digit',
        minute: '2-digit'
    });
    return `${startText} - ${endText}`;
}

function flattenWeekSchedules(days) {
    return dedupeSchedules((days || [])
        .flatMap((dayEvents) => Array.isArray(dayEvents) ? dayEvents : [])
        .filter((schedule) => schedule && schedule.start_time))
        .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
}

function renderQuickScheduleWeek(title, schedules) {
    const preview = schedules.slice(0, 4);
    const countText = schedules.length === 1
        ? ui('1 lịch hẹn', '1 event')
        : ui(`${schedules.length} lịch hẹn`, `${schedules.length} events`);

    if (!schedules.length) {
        return `
            <section class="quick-schedule-week is-empty">
                <div class="quick-schedule-week-head">
                    <strong>${escapeHtml(title)}</strong>
                    <span>${escapeHtml(countText)}</span>
                </div>
                <p>${ui('Chưa có lịch hẹn trong tuần này.', 'No events scheduled for this week.')}</p>
            </section>
        `;
    }

    return `
        <section class="quick-schedule-week">
            <div class="quick-schedule-week-head">
                <strong>${escapeHtml(title)}</strong>
                <span>${escapeHtml(countText)}</span>
            </div>
            <div class="quick-schedule-items">
                ${preview.map((schedule) => {
                    const start = new Date(schedule.start_time);
                    const dateText = Number.isNaN(start.getTime()) ? '' : formatQuickScheduleDate(start);
                    return `
                        <div class="quick-schedule-item">
                            <div class="quick-schedule-item-time">${escapeHtml(dateText)}${dateText ? ' · ' : ''}${escapeHtml(formatQuickScheduleTime(schedule))}</div>
                            <div class="quick-schedule-item-title">${escapeHtml(schedule.title || ui('Sự kiện', 'Event'))}</div>
                            ${schedule.location ? `<div class="quick-schedule-item-meta">${escapeHtml(schedule.location)}</div>` : ''}
                        </div>
                    `;
                }).join('')}
            </div>
            ${schedules.length > preview.length ? `<div class="quick-schedule-more">${ui(`+${schedules.length - preview.length} lịch hẹn khác`, `+${schedules.length - preview.length} more`)}</div>` : ''}
        </section>
    `;
}

async function loadQuickScheduleSummary(container) {
    const requestId = ++quickScheduleSummaryRequestId;
    const thisWeekStart = getMonday(new Date());
    const nextWeekStart = new Date(thisWeekStart);
    nextWeekStart.setDate(nextWeekStart.getDate() + 7);

    try {
        const [thisWeekData, nextWeekData] = await Promise.all([
            fetchJsonCached(
                `schedule:week:${formatDateForApi(thisWeekStart)}:0`,
                `${API_BASE}/schedule/week?start=${formatDateForApi(thisWeekStart)}&sync=0`
            ),
            fetchJsonCached(
                `schedule:week:${formatDateForApi(nextWeekStart)}:0`,
                `${API_BASE}/schedule/week?start=${formatDateForApi(nextWeekStart)}&sync=0`
            )
        ]);

        if (requestId !== quickScheduleSummaryRequestId || !container.isConnected) return;
        if (!thisWeekData.success || !nextWeekData.success) {
            throw new Error(ui('Không thể tải lịch', 'Unable to load schedule'));
        }

        const thisWeekSchedules = flattenWeekSchedules(thisWeekData.days);
        const nextWeekSchedules = flattenWeekSchedules(nextWeekData.days);
        const total = thisWeekSchedules.length + nextWeekSchedules.length;

        container.innerHTML = `
            <div class="quick-schedule-summary-head">
                <strong>${ui('Tổng hợp lịch hẹn', 'Schedule summary')}</strong>
                <span>${ui(`${total} sự kiện`, `${total} events`)}</span>
            </div>
            ${renderQuickScheduleWeek(ui('Tuần hiện tại', 'This week'), thisWeekSchedules)}
            ${renderQuickScheduleWeek(ui('Tuần tới', 'Next week'), nextWeekSchedules)}
        `;
    } catch (error) {
        if (requestId !== quickScheduleSummaryRequestId || !container.isConnected) return;
        container.innerHTML = `
            <div class="quick-schedule-loading is-error">
                ${escapeHtml(error.message || ui('Không thể tổng hợp lịch.', 'Unable to summarize schedule.'))}
            </div>
        `;
    }
}

function refreshQuickScheduleSummary() {
    const container = document.getElementById('quickScheduleSummary');
    if (currentPage === 'schedule' && container) {
        container.innerHTML = `<div class="quick-schedule-loading">${ui('Đang tổng hợp lịch...', 'Loading schedule summary...')}</div>`;
        loadQuickScheduleSummary(container);
    }
}

// PAGE MANAGEMENT (CRITICAL FIX)
async function handlePageChange(btn) {
    if (!btn) return;
    if (!isAuthenticated) {
        showAuthGate(ui(
            'Vui lòng đăng nhập để tiếp tục.',
            'Please sign in to continue.'
        ));
        return;
    }
    if (userModeRequired) {
        openUserModeModal(true);
        return;
    }
    const page = btn.dataset.page;
    console.log(`🔄 Changing page to: ${page}`);
    
    // Update nav buttons across desktop sidebar and mobile bottom navigation.
    navBtns.forEach(b => b.classList.remove('active'));
    navBtns.forEach(b => {
        if (b.dataset.page === page) b.classList.add('active');
    });
    syncSidebarIndicator();
    
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => {
        p.style.display = 'none';
        p.classList.remove('active');
    });
    
    // Show target page - Try both ID variants for robustness
    let targetPage = document.getElementById(`${page}-page`);
    if (!targetPage) targetPage = document.querySelector(`[data-page="${page}"]`);
    
    if (targetPage) {
        targetPage.style.display = 'flex';
        targetPage.classList.add('active');
        console.log(`✅ Page ${page} displayed`);
    } else {
        console.error(`❌ Page element not found for: ${page}`);
        return;
    }
    
    currentPage = page;
    document.getElementById('workspaceApp')?.setAttribute('data-current-page', page);
    renderQuickActions(page);
    
    // Load page data
    if (page === 'chat') {
        loadChatSessions().catch(err => console.error('Chat sessions load error:', err));
        loadChatHistory().catch(err => console.error('Chat history load error:', err));
    } else if (page === 'overview') {
        loadOverviewPage().catch(err => console.error('Overview load error:', err));
    } else if (page === 'emails') {
        // Previously this awaited a separate /email/auth-status call (which
        // can itself trigger a live Google token refresh) before ever
        // starting loadEmails -- that forced every single Email tab click
        // to pay a full extra round trip on the critical path. loadEmails
        // already renders the same "please sign in to Gmail" prompt itself
        // once it discovers not_authenticated (see its !response.ok
        // handling below), so the pre-check was redundant for the common
        // case of an already-connected user and only slowed it down.
        loadEmails(1, { cacheOnly: true })
            .then(() => loadMeetingSuggestions())
            .catch(err => console.error('Email load error:', err));
    } else if (page === 'schedule') {
        loadWeekSchedule().catch(err => console.error('Week schedule load error:', err));
        loadSchedules().catch(err => console.error('Schedule load error:', err));
        refreshCalendarScheduleData({ days: 365, silent: true, continueOnError: true })
            .catch(err => console.warn('Calendar background sync error:', err));
    } else if (page === 'history') {
        loadActivityHistory().catch(err => console.error('History load error:', err));
    } else if (page === 'settings') {
        loadSettingsPage().catch(err => console.error('Settings load error:', err));
    }
}

function syncSidebarIndicator({ instant = false } = {}) {
    const navigation = document.querySelector('.sidebar-nav');
    const activeButton = navigation?.querySelector('.nav-btn.active');
    if (!navigation || !activeButton) return;

    if (instant) navigation.classList.add('indicator-no-transition');
    navigation.style.setProperty('--nav-indicator-y', `${activeButton.offsetTop}px`);
    navigation.style.setProperty('--nav-indicator-height', `${activeButton.offsetHeight}px`);
    const mobileIndicatorSize = 58;
    const mobileIndicatorX = activeButton.offsetLeft + ((activeButton.offsetWidth - mobileIndicatorSize) / 2);
    navigation.style.setProperty('--mobile-indicator-x', `${Math.max(0, mobileIndicatorX)}px`);
    navigation.dataset.indicatorReady = 'true';

    if (instant) {
        requestAnimationFrame(() => navigation.classList.remove('indicator-no-transition'));
    }
}

function setupSidebarMenu() {
    const container = document.querySelector('.container');
    const sidebar = document.querySelector('.sidebar');
    const menuToggle = document.getElementById('menuToggle');
    if (!container || !sidebar || !menuToggle || menuToggle.dataset.ready === 'true') return;

    menuToggle.dataset.ready = 'true';
    let overlay = document.getElementById('sidebarOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'sidebarOverlay';
        overlay.className = 'overlay';
        document.body.appendChild(overlay);
    }

    const storageKey = 'flowmate-sidebar-collapsed';
    const isMobile = () => window.innerWidth <= 860;
    const updateToggle = () => {
        const mobileOpen = sidebar.classList.contains('open');
        const collapsed = container.classList.contains('sidebar-collapsed');
        const expanded = isMobile() ? mobileOpen : !collapsed;
        menuToggle.setAttribute('aria-expanded', String(expanded));
        menuToggle.setAttribute('aria-label', isMobile()
            ? ui(mobileOpen ? 'Đóng menu' : 'Mở menu', mobileOpen ? 'Close menu' : 'Open menu')
            : ui(collapsed ? 'Mở rộng thanh điều hướng' : 'Thu gọn thanh điều hướng', collapsed ? 'Expand navigation' : 'Collapse navigation'));
        menuToggle.classList.toggle('is-collapsed', collapsed);
    };

    const closeMobileSidebar = () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
        updateToggle();
    };

    const applyResponsiveState = ({ instant = false } = {}) => {
        if (isMobile()) {
            container.classList.remove('sidebar-collapsed');
            closeMobileSidebar();
        } else {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
            container.classList.toggle('sidebar-collapsed', localStorage.getItem(storageKey) === 'true');
            updateToggle();
        }
        requestAnimationFrame(() => syncSidebarIndicator({ instant }));
    };

    menuToggle.addEventListener('click', (event) => {
        event.stopPropagation();
        if (isMobile()) {
            const shouldOpen = !sidebar.classList.contains('open');
            sidebar.classList.toggle('open', shouldOpen);
            overlay.classList.toggle('show', shouldOpen);
        } else {
            const collapsed = !container.classList.contains('sidebar-collapsed');
            container.classList.toggle('sidebar-collapsed', collapsed);
            localStorage.setItem(storageKey, String(collapsed));
            requestAnimationFrame(() => syncSidebarIndicator());
        }
        updateToggle();
    });

    overlay.addEventListener('click', closeMobileSidebar);
    navBtns.forEach((button) => {
        button.addEventListener('click', () => {
            if (isMobile()) closeMobileSidebar();
        });
    });
    let resizeFrame = 0;
    window.addEventListener('resize', () => {
        cancelAnimationFrame(resizeFrame);
        resizeFrame = requestAnimationFrame(() => applyResponsiveState({ instant: true }));
    });
    container.addEventListener('transitionend', (event) => {
        if (event.propertyName === 'grid-template-columns') {
            syncSidebarIndicator({ instant: true });
        }
    });
    applyResponsiveState({ instant: true });
}

// TAB MANAGEMENT
function handleTabChange(btn) {
    const tabName = btn.dataset.tab;
    console.log(`🔄 Changing tab to: ${tabName}`);
    
    const tabsContainer = btn.closest('.tabs');
    if (!tabsContainer) {
        console.error('❌ Tabs container not found');
        return;
    }
    
    // Update tab buttons
    tabsContainer.querySelectorAll('[data-tab]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    // Hide all tabs in this container
    const pageContainer = tabsContainer.closest('.page');
    if (pageContainer) {
        pageContainer.querySelectorAll('.tab-content').forEach(content => {
            content.style.display = 'none';
        });
    }
    
    // Show target tab
    const tabContent = document.getElementById(`${tabName}-tab`);
    if (tabContent) {
        tabContent.style.display = 'block';
        console.log(`✅ Tab ${tabName} displayed`);
    } else {
        console.error(`❌ Tab content not found for: ${tabName}`);
    }
}

async function checkRuntimeConfig() {
    try {
        const response = await apiFetch(`${API_BASE}/chat/providers`);
        const data = await response.json();
        
        if (data.success && data.providers) {
            const providers = data.providers;
            console.log(
                providers.local_only
                    ? '✅ Bob local engine active'
                    : '✅ Bob runtime active'
            );
        }
    } catch (err) {
        console.error('Config check failed:', err);
    }
}
