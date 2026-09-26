function formatOverviewDateForReport(value) {
    const date = value ? new Date(`${value}T00:00:00`) : new Date();
    if (Number.isNaN(date.getTime())) return '';
    return `${String(date.getDate()).padStart(2, '0')}/${String(date.getMonth() + 1).padStart(2, '0')}/${date.getFullYear()}`;
}

function isSameOverviewDay(value, selectedDate) {
    if (!value || !selectedDate) return false;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return false;
    return formatDateForApi(date) === selectedDate;
}

function getOverviewPriority(schedule) {
    const text = `${schedule?.title || ''} ${schedule?.description || ''}`.toLowerCase();
    if (/(deadline|hạn|nộp|due|submit|bàn giao)/i.test(text)) return ui('Deadline', 'Deadline');
    if (schedule?.status === 'completed') return ui('Đã xong', 'Done');
    return ui('Task', 'Task');
}

function buildOverviewInsight({ schedules, emails, selectedDate }) {
    const deadlines = schedules.filter((item) => getOverviewPriority(item) === ui('Deadline', 'Deadline'));
    const pendingTasks = schedules.filter((item) => item.status !== 'completed');
    const meetingEmails = emails.filter((item) => item.is_meeting);
    const firstSchedule = schedules[0];
    const firstEmail = emails[0];

    if (!schedules.length && !emails.length) {
        return ui(
            `Ngày ${formatOverviewDateForReport(selectedDate)} chưa có email, deadline hoặc task nổi bật. Bạn có thể dùng thời gian này để xử lý việc tồn đọng hoặc lên kế hoạch trước.`,
            `No notable email, deadlines, or tasks were found for ${formatOverviewDateForReport(selectedDate)}. You can use the space to clear backlog or plan ahead.`
        );
    }

    const parts = [];
    parts.push(ui(
        `Ngày này có ${emails.length} email được tổng hợp, ${schedules.length} mục lịch/task và ${deadlines.length} deadline cần chú ý.`,
        `This day has ${emails.length} summarized emails, ${schedules.length} calendar/task items, and ${deadlines.length} deadlines to watch.`
    ));
    if (firstSchedule) {
        const range = formatScheduleRange(firstSchedule.start_time, firstSchedule.end_time);
        parts.push(ui(
            `Ưu tiên đầu tiên là "${firstSchedule.title || 'Sự kiện'}" vào ${range.time || range.date}.`,
            `First priority is "${firstSchedule.title || 'Event'}" at ${range.time || range.date}.`
        ));
    }
    if (firstEmail) {
        parts.push(ui(
            `Email đáng xem trước: "${firstEmail.subject || 'Không tiêu đề'}"${firstEmail.is_meeting ? ' vì có khả năng liên quan đến lịch hẹn' : ''}.`,
            `Email to review first: "${firstEmail.subject || 'No subject'}"${firstEmail.is_meeting ? ' because it may affect scheduling' : ''}.`
        ));
    }
    if (pendingTasks.length) {
        parts.push(ui(
            `Còn ${pendingTasks.length} task chưa đánh dấu hoàn thành.`,
            `${pendingTasks.length} tasks are not marked done.`
        ));
    }
    if (meetingEmails.length) {
        parts.push(ui(
            `${meetingEmails.length} email có tín hiệu cuộc họp, nên kiểm tra để tạo lịch nếu cần.`,
            `${meetingEmails.length} emails look meeting-related, so review them for possible calendar events.`
        ));
    }
    return parts.join(' ');
}

function renderOverviewList(items, type) {
    if (!items.length) {
        return `<div class="overview-empty">${type === 'email'
            ? ui('Không có email nổi bật trong ngày này.', 'No notable emails for this day.')
            : ui('Không có deadline hoặc task trong ngày này.', 'No deadlines or tasks for this day.')
        }</div>`;
    }

    return items.slice(0, 6).map((item, index) => {
        if (type === 'email') {
            return `
                <article class="overview-list-item is-clickable" data-email-index="${index}" tabindex="0" role="button">
                    <span class="overview-item-index">${index + 1}</span>
                    <div>
                        <strong>${escapeHtml(item.subject || ui('Email không tiêu đề', 'Untitled email'))}</strong>
                        <small>${escapeHtml(item.sender || '')}</small>
                        <p>${escapeHtml(item.summary || ui('Chưa có tóm tắt.', 'No summary available.'))}</p>
                    </div>
                    ${item.is_meeting ? `<span class="overview-chip is-meeting">${ui('Cuộc họp', 'Meeting')}</span>` : ''}
                </article>
            `;
        }

        const range = formatScheduleRange(item.start_time, item.end_time);
        const priority = getOverviewPriority(item);
        return `
            <article class="overview-list-item">
                <span class="overview-item-index">${index + 1}</span>
                <div>
                    <strong>${escapeHtml(item.title || ui('Task không tiêu đề', 'Untitled task'))}</strong>
                    <small>${escapeHtml(range.time || range.date || ui('Chưa rõ thời gian', 'Time unknown'))}</small>
                    ${item.description ? `<p>${escapeHtml(plainTextFromHtml(item.description))}</p>` : ''}
                </div>
                <span class="overview-chip">${escapeHtml(priority)}</span>
            </article>
        `;
    }).join('');
}

function normalizeOverviewChecklist(value) {
    return {
        revision: Math.max(0, Number(value?.revision) || 0),
        completed: value?.completed && typeof value.completed === 'object' ? value.completed : {},
        custom_items: Array.isArray(value?.custom_items) ? value.custom_items : []
    };
}

function formatOverviewDueLabel(item) {
    if (!item) return '';
    const dueDate = item.due_date || (item.due_at ? String(item.due_at).slice(0, 10) : '');
    if (!dueDate) return item.ai_reason || ui('Chưa có hạn rõ ràng', 'No clear deadline');
    try {
        const date = new Date(`${dueDate}T00:00:00`);
        if (Number.isNaN(date.getTime())) return item.ai_reason || dueDate;
        const label = date.toLocaleDateString(currentLanguage === 'en' ? 'en-US' : 'vi-VN', {
            weekday: 'short',
            day: '2-digit',
            month: '2-digit'
        });
        return item.ai_reason ? `${label} · ${item.ai_reason}` : label;
    } catch (error) {
        return item.ai_reason || dueDate;
    }
}

function overviewChecklistDateValue(item) {
    const raw = item.due_at || item.start_time || item.due_date || '';
    if (!raw) return Number.MAX_SAFE_INTEGER;
    const normalized = String(raw).includes('T') ? String(raw) : `${raw}T23:59:59`;
    const time = new Date(normalized).getTime();
    return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time;
}

function compareOverviewChecklistItems(a, b) {
    const completedDiff = Number(Boolean(a.completed)) - Number(Boolean(b.completed));
    if (completedDiff) return completedDiff;
    const pinnedDiff = Number(!a.pinned) - Number(!b.pinned);
    if (pinnedDiff) return pinnedDiff;
    const dateDiff = overviewChecklistDateValue(a) - overviewChecklistDateValue(b);
    if (dateDiff) return dateDiff;
    const priorityDiff = Number(b.priority_score || 0) - Number(a.priority_score || 0);
    if (priorityDiff) return priorityDiff;
    return String(a.created_at || '').localeCompare(String(b.created_at || ''));
}

function buildOverviewChecklistItems(schedules, checklistState) {
    const completed = checklistState.completed || {};
    const scheduleItems = schedules
        .filter((item) => item.status !== 'cancelled' && item.status !== 'dismissed')
        .map((item) => {
            const id = `schedule:${scheduleFingerprint(item)}`;
            const range = formatScheduleRange(item.start_time, item.end_time);
            return {
                id,
                kind: 'schedule',
                sourceLabel: ui('Lịch', 'Schedule'),
                title: item.title || ui('Task không tiêu đề', 'Untitled task'),
                meta: range.time || range.date || ui('Chưa rõ thời gian', 'Time unknown'),
                start_time: item.start_time || '',
                priority_score: getOverviewPriority(item) === ui('Deadline', 'Deadline') ? 80 : 55,
                completed: Boolean(completed[id] || item.status === 'completed')
            };
        });
    const customItems = (checklistState.custom_items || [])
        .filter((item) => item && item.id && item.title)
        .map((item) => ({
            ...item,
            kind: item.item_type || 'task',
            sourceLabel: item.source === 'ai' ? 'AI' : ui('Tự thêm', 'Manual'),
            meta: formatOverviewDueLabel(item),
            completed: Boolean(item.completed),
            priority_score: Number(item.priority_score || 0)
        }));
    return [...customItems, ...scheduleItems].sort(compareOverviewChecklistItems);
}

function renderOverviewQuickAdd() {
    return `
        <section class="overview-panel overview-quick-add">
            <form id="overviewQuickAddForm" class="overview-quick-add-form">
                <div>
                    <span class="overview-kicker">${ui('NHẬP NHANH', 'QUICK ADD')}</span>
                    <label for="overviewQuickInput">${ui('Thêm việc hoặc lịch', 'Add a task or activity')}</label>
                    <small>${ui('Ví dụ: "7h tối nay đi gym" hoặc "mai nộp báo cáo".', 'Example: "gym tonight at 7" or "submit report tomorrow".')}</small>
                </div>
                <div class="overview-quick-add-row">
                    <input id="overviewQuickInput" type="text" autocomplete="off" placeholder="${ui('Nhập việc/lịch bằng ngôn ngữ tự nhiên...', 'Type a task or activity naturally...')}">
                    <button id="overviewQuickAddBtn" type="submit" class="btn-primary">${ui('Thêm', 'Add')}</button>
                </div>
                <p id="overviewQuickAddStatus" class="overview-quick-add-status" aria-live="polite"></p>
                <div id="overviewPlanSuggestion" class="overview-plan-suggestion" hidden></div>
            </form>
        </section>
    `;
}

function renderOverviewChecklist(schedules, checklistState) {
    const items = buildOverviewChecklistItems(schedules, checklistState);
    const doneCount = items.filter((item) => item.completed).length;
    const progress = items.length ? Math.round((doneCount / items.length) * 100) : 0;
    const isStudent = currentUserMode === 'student';
    const rows = items.length
        ? items.map((item) => `
            <div class="overview-checklist-item">
                <button class="overview-check" type="button" data-checklist-toggle="${escapeHtml(item.id)}" aria-label="${ui('Đánh dấu hoàn thành', 'Toggle complete')}">
                    ${item.completed ? '✓' : ''}
                </button>
                <button class="overview-checklist-main ${item.completed ? 'is-done' : ''}" type="button" data-checklist-toggle="${escapeHtml(item.id)}">
                    <strong>${escapeHtml(item.title || ui('Việc cần làm', 'Task'))}</strong>
                    <span>${escapeHtml(item.meta || '')}</span>
                </button>
                ${isStudent && item.kind !== 'schedule' ? `
                    ${item.subject ? `<span class="overview-chip is-subject">${escapeHtml(item.subject)}</span>` : ''}
                    <button class="overview-checklist-subject-btn" type="button" data-checklist-subject="${escapeHtml(item.id)}" data-current-subject="${escapeAttr(item.subject || '')}">
                        ${item.subject ? ui('Đổi môn', 'Edit subject') : ui('+ Môn học', '+ Subject')}
                    </button>
                ` : ''}
                <div class="overview-checklist-actions">
                    <span class="overview-checklist-source ${item.kind === 'schedule' ? 'is-schedule' : 'is-manual'}">${escapeHtml(item.sourceLabel || '')}</span>
                    ${item.kind === 'schedule' ? '' : `<button class="overview-checklist-remove" type="button" data-checklist-remove="${escapeHtml(item.id)}" aria-label="${ui('Xóa khỏi checklist', 'Remove from checklist')}">×</button>`}
                </div>
            </div>
        `).join('')
        : `<div class="overview-empty">${ui('Checklist đang trống. Thêm việc hoặc lịch ở ô nhập nhanh phía trên.', 'Checklist is empty. Add a task or activity from the quick input above.')}</div>`;

    return `
        <section class="overview-panel overview-checklist-panel">
            <div class="overview-panel-head">
                <div>
                    <span class="overview-kicker">CHECKLIST</span>
                    <strong>${ui('Checklist hôm nay', 'Today checklist')}</strong>
                    <small>${doneCount}/${items.length} ${ui('hoàn thành', 'done')}</small>
                    <div class="overview-checklist-progress" aria-hidden="true">
                        <span style="width: ${progress}%"></span>
                    </div>
                </div>
                <div>
                    ${isStudent ? `<button class="overview-sort-btn" type="button" data-checklist-group-by-subject>${ui('Xem theo môn', 'View by subject')}</button>` : ''}
                    <button class="overview-sort-btn" type="button" data-checklist-sort>${ui('Sắp xếp', 'AI sort')}</button>
                </div>
            </div>
            <div class="overview-checklist-list">${rows}</div>
        </section>
    `;
}

function sortOverviewCustomItems(items = []) {
    return [...items].sort(compareOverviewChecklistItems);
}

function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderOverviewAnalytics(analytics) {
    if (analytics?.error === 'premium_required') {
        return `
            <section class="overview-panel overview-analytics overview-analytics-locked">
                <div class="overview-panel-head">
                    <span class="overview-kicker">${ui('PHÂN TÍCH TUẦN', 'WEEKLY ANALYTICS')}</span>
                    <strong>${ui('Xu hướng hoạt động', 'Activity trend')}</strong>
                </div>
                <p>${ui(
                    'Phân tích tuần là tính năng Premium. Nâng cấp để xem xu hướng hoàn thành task và email theo ngày.',
                    'Weekly analytics is a Premium feature. Upgrade to see your daily task and email trends.'
                )}</p>
                <button type="button" class="btn-primary" onclick="openSubscriptionModal()">${ui('Mở khóa Premium', 'Unlock Premium')}</button>
            </section>
        `;
    }

    const daily = Array.isArray(analytics?.daily) ? analytics.daily : [];
    if (!daily.length) return '';

    const totals = analytics.totals || {};
    const weekdayLabels = ui(
        ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'],
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    );
    const todayIso = formatDateForApi(new Date());
    const maxActivity = Math.max(1, ...daily.map((d) => Math.max(d.tasks_total || 0, d.emails_total || 0)));

    const bars = daily.map((d) => {
        const taskH = Math.round(((d.tasks_total || 0) / maxActivity) * 100);
        const emailH = Math.round(((d.emails_total || 0) / maxActivity) * 100);
        const label = weekdayLabels[d.weekday] ?? '';
        const isToday = d.date === todayIso;
        const tooltip = ui(
            `${d.date}: ${d.tasks_total || 0} task, ${d.emails_total || 0} email${d.has_email_data ? '' : ' (chưa có dữ liệu email)'}`,
            `${d.date}: ${d.tasks_total || 0} tasks, ${d.emails_total || 0} emails${d.has_email_data ? '' : ' (no email data yet)'}`
        );
        return `
            <div class="overview-bar-col${isToday ? ' is-today' : ''}" title="${escapeAttr(tooltip)}">
                <div class="overview-bar-track">
                    <div class="overview-bar overview-bar-task" style="height:${taskH}%"></div>
                    <div class="overview-bar overview-bar-email" style="height:${emailH}%"></div>
                </div>
                <span>${label}</span>
            </div>
        `;
    }).join('');

    const busiestEntry = daily.find((d) => d.date === totals.busiest_date);
    const busiestLabel = busiestEntry ? weekdayLabels[busiestEntry.weekday] : '—';
    const rangeDays = analytics.range?.days || daily.length;
    const emailNote = (totals.days_with_email_data ?? 0) < rangeDays
        ? `<p class="overview-analytics-note">${ui(
            'Số liệu email chỉ tính những ngày bạn đã từng mở Tổng hợp trước đó.',
            'Email figures only cover days you previously opened Overview for.'
        )}</p>`
        : '';

    return `
        <section class="overview-panel overview-analytics">
            <div class="overview-panel-head">
                <span class="overview-kicker">${ui(`PHÂN TÍCH ${rangeDays} NGÀY`, `${rangeDays}-DAY ANALYTICS`)}</span>
                <strong>${ui('Xu hướng hoạt động', 'Activity trend')}</strong>
            </div>
            <div class="overview-analytics-body">
                <div class="overview-kpi-grid">
                    <article>
                        <strong>${totals.completion_rate ?? 0}%</strong>
                        <span>${ui('Tỷ lệ hoàn thành task', 'Task completion rate')}</span>
                    </article>
                    <article>
                        <strong>${totals.emails_total ?? 0}</strong>
                        <span>${ui('Email đã xử lý', 'Emails processed')}</span>
                    </article>
                    <article>
                        <strong>${totals.deadlines_total ?? 0}</strong>
                        <span>${ui(`Deadline trong ${rangeDays} ngày`, `Deadlines in ${rangeDays} days`)}</span>
                    </article>
                    <article>
                        <strong>${busiestLabel}</strong>
                        <span>${ui('Ngày bận nhất', 'Busiest day')}</span>
                    </article>
                </div>
                <div class="overview-bar-chart">${bars}</div>
                <div class="overview-bar-legend">
                    <span><i class="overview-bar-task"></i>${ui('Task/Lịch', 'Tasks')}</span>
                    <span><i class="overview-bar-email"></i>Email</span>
                </div>
                ${emailNote}
            </div>
        </section>
    `;
}

function renderOverviewPlanSuggestion(plan) {
    const items = Array.isArray(plan?.items) ? plan.items : [];
    if (!items.length) return '';
    const rows = items.map((item, index) => {
        const range = formatScheduleRange(item.start_time, item.end_time);
        const startValue = toDatetimeLocal(item.start_time);
        const endValue = toDatetimeLocal(item.end_time);
        return `
            <div class="overview-plan-suggestion-item" data-plan-row data-plan-index="${index}">
                <label class="overview-plan-suggestion-check">
                    <input type="checkbox" data-plan-select checked>
                    <span>${escapeHtml(range.time || '')}</span>
                </label>
                <div class="overview-plan-suggestion-fields">
                    <input type="text" data-plan-title value="${escapeAttr(item.title || ui('Hoạt động', 'Activity'))}" aria-label="${ui('Tên hoạt động', 'Activity title')}">
                    <div class="overview-plan-time-grid">
                        <input type="datetime-local" data-plan-start value="${escapeAttr(startValue)}" aria-label="${ui('Bắt đầu', 'Start')}">
                        <input type="datetime-local" data-plan-end value="${escapeAttr(endValue)}" aria-label="${ui('Kết thúc', 'End')}">
                    </div>
                    <small>${escapeHtml(item.reason || '')}</small>
                </div>
            </div>
        `;
    }).join('');
    const dateLabel = (() => {
        try {
            const date = new Date(`${plan.date}T00:00:00`);
            if (Number.isNaN(date.getTime())) return plan.date || '';
            return date.toLocaleDateString(currentLanguage === 'en' ? 'en-US' : 'vi-VN', {
                weekday: 'long',
                day: '2-digit',
                month: '2-digit',
                year: 'numeric'
            });
        } catch (error) {
            return plan.date || '';
        }
    })();
    return `
        <div class="overview-plan-suggestion-head">
            <div>
                <span class="overview-kicker">${ui('GỢI Ý LỊCH', 'SUGGESTED PLAN')}</span>
                <strong>${escapeHtml(dateLabel)}</strong>
                <small>${ui('FlowMate chỉ tạo lịch sau khi bạn xác nhận.', 'FlowMate will only create events after you confirm.')}</small>
            </div>
        </div>
        <div class="overview-plan-suggestion-list">${rows}</div>
        <div class="overview-plan-suggestion-actions">
            <button type="button" class="btn-secondary" data-plan-dismiss>${ui('Bỏ qua', 'Dismiss')}</button>
            <button type="button" class="btn-primary" data-plan-apply>${ui('Áp dụng lịch này', 'Apply this plan')}</button>
        </div>
    `;
}

function bindOverviewChecklist(container, selectedDate, schedules, checklistState) {
    let state = normalizeOverviewChecklist(checklistState);

    const save = async (nextState) => {
        state = normalizeOverviewChecklist({
            ...nextState,
            revision: nextState?.revision ?? state.revision,
            custom_items: sortOverviewCustomItems(nextState.custom_items || [])
        });
        const response = await apiFetch(`${API_BASE}/schedule/checklist`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: selectedDate, ...state })
        });
        const data = await response.json();
        if (response.ok && data.success) {
            state = normalizeOverviewChecklist(data);
            return true;
        }
        if (response.status === 409) {
            state = normalizeOverviewChecklist(data);
            showNotification(ui(
                'Checklist đã thay đổi trên thiết bị khác. Đã tải lại bản mới nhất.',
                'The checklist changed on another device. The latest version was reloaded.'
            ), 'warning');
            return false;
        }
        throw new Error(data.error || ui('Không lưu được checklist', 'Unable to save checklist'));
    };

    const findItem = (id) => buildOverviewChecklistItems(schedules, state).find((item) => item.id === id);
    const rerender = () => {
        const panel = container.querySelector('.overview-checklist-panel');
        if (!panel) return;
        panel.outerHTML = renderOverviewChecklist(schedules, state);
        bindOverviewChecklist(container, selectedDate, schedules, state);
    };

    container.querySelectorAll('[data-checklist-toggle]').forEach((button) => {
        button.addEventListener('click', async () => {
            const id = button.getAttribute('data-checklist-toggle');
            const item = findItem(id);
            if (!item) return;
            if (item.kind === 'schedule') {
                const nextCompleted = { ...state.completed, [id]: !item.completed };
                await save({ completed: nextCompleted, custom_items: state.custom_items || [] });
            } else {
                const nextCustomItems = (state.custom_items || []).map((customItem) => (
                    customItem.id === id ? { ...customItem, completed: !item.completed } : customItem
                ));
                await save({ completed: state.completed || {}, custom_items: nextCustomItems });
            }
            rerender();
        });
    });

    container.querySelectorAll('[data-checklist-remove]').forEach((button) => {
        button.addEventListener('click', async () => {
            const id = button.getAttribute('data-checklist-remove');
            const nextCustomItems = (state.custom_items || []).filter((item) => item.id !== id);
            await save({ completed: state.completed || {}, custom_items: nextCustomItems });
            rerender();
        });
    });

    const sortButton = container.querySelector('[data-checklist-sort]');
    if (sortButton) {
        sortButton.addEventListener('click', async () => {
            await save({ completed: state.completed || {}, custom_items: sortOverviewCustomItems(state.custom_items || []) });
            rerender();
            showNotification(ui('Đã sắp xếp checklist theo ưu tiên', 'Checklist sorted by priority'), 'success');
        });
    }

    container.querySelectorAll('[data-checklist-subject]').forEach((button) => {
        button.addEventListener('click', async () => {
            const id = button.getAttribute('data-checklist-subject');
            const current = button.getAttribute('data-current-subject') || '';
            const next = window.prompt(ui('Nhập tên môn học:', 'Enter subject name:'), current);
            if (next === null || next.trim() === current) return;
            const nextCustomItems = (state.custom_items || []).map((customItem) => (
                customItem.id === id ? { ...customItem, subject: next.trim().slice(0, 60) } : customItem
            ));
            await save({ completed: state.completed || {}, custom_items: nextCustomItems });
            rerender();
        });
    });

    const groupBySubjectButton = container.querySelector('[data-checklist-group-by-subject]');
    if (groupBySubjectButton) {
        groupBySubjectButton.addEventListener('click', async () => {
            if (!isCurrentUserPremium()) {
                showNotification(ui(
                    'Xem checklist theo môn là tính năng Premium.',
                    'Grouping the checklist by subject is a Premium feature.'
                ), 'error');
                openSubscriptionModal();
                return;
            }
            try {
                const response = await apiFetch(`${API_BASE}/schedule/checklist?date=${encodeURIComponent(selectedDate)}&group_by=subject`);
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.error || ui('Không tải được danh sách theo môn', 'Unable to load subject groups'));
                }
                const groups = Array.isArray(data.grouped_by_subject) ? data.grouped_by_subject : [];
                const body = groups.length
                    ? groups.map((group) => `
                        <p style="margin: 12px 0 4px; font-weight: 700;">${escapeHtml(group.subject)}</p>
                        ${group.items.map((item) => `
                            <div class="overview-countdown-item">
                                <span class="overview-countdown-title">${escapeHtml(item.title || '')}</span>
                                <span class="overview-countdown-days">${item.completed ? ui('Xong', 'Done') : ''}</span>
                            </div>
                        `).join('')}
                    `).join('')
                    : `<p>${ui('Checklist đang trống.', 'Checklist is empty.')}</p>`;
                openStudentToolsModal(ui('Checklist theo môn', 'Checklist by subject'), body + `
                    <div class="student-tools-actions">
                        <button type="button" class="btn-secondary" onclick="closeStudentToolsModal()">${ui('Đóng', 'Close')}</button>
                    </div>
                `);
            } catch (error) {
                showNotification(error.message, 'error');
            }
        });
    }
}

function bindOverviewQuickAdd(container, selectedDate) {
    const form = container.querySelector('#overviewQuickAddForm');
    const input = container.querySelector('#overviewQuickInput');
    const button = container.querySelector('#overviewQuickAddBtn');
    const status = container.querySelector('#overviewQuickAddStatus');
    const suggestionBox = container.querySelector('#overviewPlanSuggestion');
    if (!form || !input) return;

    const showPlanSuggestion = (plan) => {
        if (!suggestionBox) return;
        suggestionBox.hidden = false;
        suggestionBox.innerHTML = renderOverviewPlanSuggestion(plan);
        const dismissButton = suggestionBox.querySelector('[data-plan-dismiss]');
        const applyButton = suggestionBox.querySelector('[data-plan-apply]');
        if (dismissButton) {
            dismissButton.addEventListener('click', () => {
                suggestionBox.hidden = true;
                suggestionBox.innerHTML = '';
            });
        }
        suggestionBox.querySelectorAll('[data-plan-row]').forEach((row) => {
            const checkbox = row.querySelector('[data-plan-select]');
            const startInput = row.querySelector('[data-plan-start]');
            const endInput = row.querySelector('[data-plan-end]');
            const titleInput = row.querySelector('[data-plan-title]');
            const index = Number(row.getAttribute('data-plan-index'));
            const original = plan.items?.[index] || {};
            const originalDuration = getDurationMinutes(original.start_time, original.end_time) || original.duration_minutes || 60;
            const updateDisabledState = () => {
                const disabled = !checkbox?.checked;
                row.classList.toggle('is-disabled', disabled);
                [titleInput, startInput, endInput].forEach((input) => {
                    if (input) input.disabled = disabled;
                });
            };
            if (checkbox) {
                checkbox.addEventListener('change', updateDisabledState);
                updateDisabledState();
            }
            if (startInput && endInput) {
                startInput.addEventListener('change', () => {
                    const nextEnd = addMinutesToDatetimeLocal(startInput.value, originalDuration);
                    if (nextEnd) endInput.value = nextEnd;
                });
            }
        });
        if (applyButton) {
            applyButton.addEventListener('click', async () => {
                const selectedItems = Array.from(suggestionBox.querySelectorAll('[data-plan-row]'))
                    .filter((row) => row.querySelector('[data-plan-select]')?.checked)
                    .map((row) => {
                        const index = Number(row.getAttribute('data-plan-index'));
                        const original = plan.items?.[index] || {};
                        const title = row.querySelector('[data-plan-title]')?.value?.trim() || original.title || '';
                        const startTime = row.querySelector('[data-plan-start]')?.value || original.start_time || '';
                        const endTime = row.querySelector('[data-plan-end]')?.value || original.end_time || '';
                        return {
                            ...original,
                            title,
                            start_time: startTime,
                            end_time: endTime,
                            duration_minutes: getDurationMinutes(startTime, endTime) || original.duration_minutes || 60
                        };
                    })
                    .filter((item) => item.title && item.start_time);
                if (!selectedItems.length) {
                    if (status) status.textContent = ui('Hãy chọn ít nhất một hoạt động để tạo lịch.', 'Select at least one activity to create events.');
                    return;
                }
                applyButton.disabled = true;
                if (status) status.textContent = ui('Đang tạo lịch từ gợi ý...', 'Creating events from suggestion...');
                try {
                    const response = await apiFetch(`${API_BASE}/schedule/plan-day/apply`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ date: plan.date || selectedDate, items: selectedItems })
                    });
                    const data = await response.json();
                    if (!response.ok || !data.success) {
                        throw new Error(data.error || ui('Không thể áp dụng lịch gợi ý', 'Unable to apply suggested plan'));
                    }
                    clearRuntimeCache('schedule:');
                    suggestionBox.hidden = true;
                    suggestionBox.innerHTML = '';
                    showNotification(ui('Đã tạo lịch từ gợi ý', 'Suggested plan applied'), 'success');
                    await Promise.allSettled([
                        loadOverviewPage({ force: true }),
                        loadWeekSchedule({ forceSync: true }),
                        loadSchedules({ liveGoogle: true })
                    ]);
                } catch (error) {
                    if (status) status.textContent = error.message;
                    showNotification(`${ui('Lỗi', 'Error')}: ${error.message}`, 'error');
                } finally {
                    applyButton.disabled = false;
                }
            });
        }
    };

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) {
            input.focus();
            return;
        }
        if (button) button.disabled = true;
        if (status) status.textContent = ui('FlowMate đang phân loại...', 'FlowMate is classifying...');
        try {
            const response = await apiFetch(`${API_BASE}/schedule/quick-add`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, date: selectedDate })
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || ui('Không thể thêm mục này', 'Unable to add this item'));
            }
            input.value = '';
            if (data.kind === 'suggested_plan') {
                if (status) status.textContent = ui('FlowMate đã gợi ý giờ. Kiểm tra rồi áp dụng nếu hợp lý.', 'FlowMate suggested times. Review and apply if it looks right.');
                showPlanSuggestion(data);
                return;
            }
            if (data.kind === 'activity') {
                clearRuntimeCache('schedule:');
                showNotification(ui('Đã thêm vào lịch', 'Added to calendar'), 'success');
                await Promise.allSettled([
                    loadOverviewPage({ force: true }),
                    loadWeekSchedule({ force: true }),
                    loadSchedules({ force: true })
                ]);
                return;
            }
            showNotification(ui('Đã thêm vào checklist', 'Added to checklist'), 'success');
            await loadOverviewPage({ force: false });
        } catch (error) {
            if (status) status.textContent = error.message;
            showNotification(`${ui('Lỗi', 'Error')}: ${error.message}`, 'error');
        } finally {
            if (button) button.disabled = false;
        }
    });
}

// ---- Student-mode-only widgets (deadline countdown, study-material
// summarizer, GPA calculator, checklist-by-subject) -- all driven off
// currentUserMode/currentSubscription globals already set by
// updateUserModeUI/renderSubscriptionUI, and the same 'premium_required'
// locked-card pattern renderOverviewAnalytics already established. ----

function isCurrentUserPremium() {
    return !!(currentSubscription?.is_premium || currentSubscription?.tier === 'premium');
}

function renderOverviewCountdown(deadlines) {
    if (!Array.isArray(deadlines)) return ''; // backend omits this for non-Student modes
    const rows = deadlines.map((item) => {
        const urgency = item.days_until <= 3 ? 'is-urgent' : (item.days_until <= 7 ? 'is-soon' : '');
        const daysLabel = item.days_until <= 0
            ? ui('Hôm nay', 'Today')
            : ui(`Còn ${item.days_until} ngày`, `${item.days_until}d left`);
        return `
            <div class="overview-countdown-item ${urgency}">
                <span class="overview-countdown-days">${escapeHtml(daysLabel)}</span>
                <span class="overview-countdown-title">${escapeHtml(item.title || '')}</span>
            </div>
        `;
    }).join('');
    const upsell = !isCurrentUserPremium()
        ? `<p class="overview-countdown-upsell">${ui(
            'Free chỉ hiện deadline gần nhất. <a href="#" onclick="openSubscriptionModal();return false;">Nâng cấp Premium</a> để xem đầy đủ danh sách.',
            'Free shows only the nearest deadline. <a href="#" onclick="openSubscriptionModal();return false;">Upgrade to Premium</a> for the full list.'
        )}</p>`
        : '';
    return `
        <section class="overview-panel overview-countdown">
            <div class="overview-panel-head">
                <span class="overview-kicker">${ui('ĐẾM NGƯỢC', 'COUNTDOWN')}</span>
                <strong>${ui('Deadline sắp tới', 'Upcoming deadlines')}</strong>
            </div>
            ${rows || `<p class="overview-countdown-upsell">${ui('Chưa có deadline nào sắp tới.', 'No upcoming deadlines yet.')}</p>`}
            ${rows ? `<div class="overview-countdown-list">${rows}</div>` : ''}
            ${upsell}
        </section>
    `;
}

function renderStudentToolsPanel() {
    if (currentUserMode !== 'student') return '';
    return `
        <section class="overview-panel overview-student-tools">
            <div class="overview-panel-head">
                <span class="overview-kicker">${ui('CÔNG CỤ SINH VIÊN', 'STUDENT TOOLS')}</span>
                <strong>${ui('Học tập & điểm số', 'Study & grades')}</strong>
            </div>
            <div class="overview-quick-add-row" style="padding: 0 14px 14px;">
                <button type="button" id="studentToolSummarizeBtn" class="btn-secondary">${ui('Tóm tắt tài liệu học tập', 'Summarize study material')}</button>
                <button type="button" id="studentToolGpaBtn" class="btn-secondary">${ui('Tính GPA', 'Calculate GPA')}</button>
            </div>
        </section>
    `;
}

function openStudentToolsModal(title, bodyHtml) {
    const modal = document.getElementById('studentToolsModal');
    const titleEl = document.getElementById('studentToolsModalTitle');
    const bodyEl = document.getElementById('studentToolsModalBody');
    if (!modal || !bodyEl) return;
    if (titleEl) titleEl.textContent = title;
    bodyEl.innerHTML = bodyHtml;
    modal.classList.add('show');
    document.body.classList.add('modal-open');
}

function closeStudentToolsModal() {
    document.getElementById('studentToolsModal')?.classList.remove('show');
    document.body.classList.remove('modal-open');
}

function renderStudySummarizerBody() {
    return `
        <p>${ui('Dán bài giảng, ghi chú hoặc tài liệu học tập để Bob tóm tắt các ý chính.', 'Paste lecture notes or study material for Bob to summarize the key points.')}</p>
        <input type="text" id="studentSummaryTitle" placeholder="${ui('Tiêu đề (không bắt buộc)', 'Title (optional)')}" style="width:100%; margin-top:8px; padding:8px; border:1px solid var(--border); border-radius:8px; background:var(--panel); color:var(--text);">
        <textarea id="studentSummaryContent" class="student-tools-textarea" placeholder="${ui('Dán nội dung vào đây...', 'Paste content here...')}"></textarea>
        ${!isCurrentUserPremium() ? `<p class="student-tools-quota-note">${ui('Free: 5 lượt/ngày. Premium: không giới hạn.', 'Free: 5/day. Premium: unlimited.')}</p>` : ''}
        <div id="studentSummaryResult"></div>
        <div class="student-tools-actions">
            <button type="button" class="btn-secondary" onclick="closeStudentToolsModal()">${ui('Đóng', 'Close')}</button>
            <button type="button" id="studentSummarySubmitBtn" class="btn-primary">${ui('Tóm tắt', 'Summarize')}</button>
        </div>
    `;
}

function bindStudySummarizerBody() {
    const submitBtn = document.getElementById('studentSummarySubmitBtn');
    if (!submitBtn) return;
    submitBtn.addEventListener('click', async () => {
        const title = document.getElementById('studentSummaryTitle')?.value.trim() || '';
        const content = document.getElementById('studentSummaryContent')?.value.trim() || '';
        const resultBox = document.getElementById('studentSummaryResult');
        if (!content) {
            showNotification(ui('Hãy dán nội dung cần tóm tắt', 'Paste content to summarize first'), 'error');
            return;
        }
        submitBtn.disabled = true;
        submitBtn.textContent = ui('Đang tóm tắt...', 'Summarizing...');
        try {
            const response = await apiFetch(`${API_BASE}/chat/summarize-study`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, content })
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                if (data.error === 'ai_limit_reached') {
                    throw new Error(ui(
                        `Bạn đã dùng hết ${data.limit} lượt tóm tắt miễn phí hôm nay.`,
                        `You've used all ${data.limit} free summaries today.`
                    ));
                }
                throw new Error(data.error || ui('Không thể tóm tắt', 'Unable to summarize'));
            }
            if (resultBox) resultBox.innerHTML = `<div class="student-tools-summary">${escapeHtml(data.summary)}</div>`;
        } catch (error) {
            showNotification(error.message, 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = ui('Tóm tắt', 'Summarize');
        }
    });
}

function renderGpaRow(course) {
    const name = course?.name || '';
    const credits = course?.credits ?? '';
    const grade = course?.grade ?? '';
    return `
        <tr class="student-gpa-row">
            <td><input type="text" data-gpa-name value="${escapeAttr(name)}" placeholder="${ui('Tên môn', 'Course name')}"></td>
            <td><input type="number" data-gpa-credits value="${escapeAttr(credits)}" min="0" step="0.5" placeholder="${ui('TC', 'Cr')}"></td>
            <td><input type="number" data-gpa-grade value="${escapeAttr(grade)}" min="0" step="0.1" placeholder="${ui('Điểm', 'Grade')}"></td>
            <td><button type="button" class="overview-checklist-remove" data-gpa-remove aria-label="${ui('Xóa dòng', 'Remove row')}">×</button></td>
        </tr>
    `;
}

function renderGpaCalculatorBody() {
    const premium = isCurrentUserPremium();
    return `
        <p>${ui(
            'Nhập môn học, số tín chỉ và điểm (theo thang điểm bạn đang dùng) để tính GPA trung bình theo tín chỉ.',
            'Enter courses, credits, and grade (on whatever scale you use) to compute a credit-weighted GPA.'
        )}</p>
        ${!premium ? `<p class="student-tools-quota-note">${ui(
            'Free: tính tại chỗ, không lưu lại. <a href="#" onclick="openSubscriptionModal();return false;">Nâng cấp Premium</a> để lưu danh sách môn và xem lại sau.',
            'Free: computes on the spot, nothing is saved. <a href="#" onclick="openSubscriptionModal();return false;">Upgrade to Premium</a> to save your course list.'
        )}</p>` : ''}
        <table class="student-tools-gpa-table">
            <thead><tr><th>${ui('Môn', 'Course')}</th><th>${ui('Tín chỉ', 'Credits')}</th><th>${ui('Điểm', 'Grade')}</th><th></th></tr></thead>
            <tbody id="studentGpaRows">${renderGpaRow({})}${renderGpaRow({})}${renderGpaRow({})}</tbody>
        </table>
        <div class="student-tools-actions" style="justify-content: space-between;">
            <button type="button" class="btn-secondary" id="studentGpaAddRowBtn">${ui('+ Thêm môn', '+ Add course')}</button>
            <div>
                <button type="button" class="btn-secondary" onclick="closeStudentToolsModal()">${ui('Đóng', 'Close')}</button>
                <button type="button" id="studentGpaCalculateBtn" class="btn-primary">${ui('Tính GPA', 'Calculate')}</button>
            </div>
        </div>
        <div id="studentGpaResult"></div>
    `;
}

function bindGpaCalculatorBody() {
    const addRowBtn = document.getElementById('studentGpaAddRowBtn');
    const rowsBody = document.getElementById('studentGpaRows');
    const calculateBtn = document.getElementById('studentGpaCalculateBtn');
    if (!rowsBody || !calculateBtn) return;

    const bindRemoveButtons = () => {
        rowsBody.querySelectorAll('[data-gpa-remove]').forEach((button) => {
            button.onclick = () => {
                button.closest('.student-gpa-row')?.remove();
            };
        });
    };
    bindRemoveButtons();

    if (addRowBtn) {
        addRowBtn.addEventListener('click', () => {
            rowsBody.insertAdjacentHTML('beforeend', renderGpaRow({}));
            bindRemoveButtons();
        });
    }

    calculateBtn.addEventListener('click', async () => {
        const courses = Array.from(rowsBody.querySelectorAll('.student-gpa-row')).map((row) => ({
            name: row.querySelector('[data-gpa-name]')?.value.trim() || '',
            credits: row.querySelector('[data-gpa-credits]')?.value || '',
            grade: row.querySelector('[data-gpa-grade]')?.value || ''
        })).filter((course) => course.name && course.credits !== '' && course.grade !== '');

        if (!courses.length) {
            showNotification(ui('Hãy nhập ít nhất một môn hợp lệ', 'Enter at least one valid course'), 'error');
            return;
        }
        calculateBtn.disabled = true;
        try {
            const response = await apiFetch(`${API_BASE}/courses/calculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ courses })
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || ui('Không thể tính GPA', 'Unable to calculate GPA'));
            }
            const resultBox = document.getElementById('studentGpaResult');
            if (resultBox) {
                resultBox.innerHTML = data.gpa === null
                    ? `<div class="student-tools-gpa-result">${ui('Chưa đủ dữ liệu hợp lệ', 'Not enough valid data')}</div>`
                    : `<div class="student-tools-gpa-result">GPA: ${escapeHtml(String(data.gpa))}</div>`;
            }
        } catch (error) {
            showNotification(error.message, 'error');
        } finally {
            calculateBtn.disabled = false;
        }
    });
}

function bindStudentToolsPanel(container) {
    const summarizeBtn = container.querySelector('#studentToolSummarizeBtn');
    if (summarizeBtn) {
        summarizeBtn.addEventListener('click', () => {
            openStudentToolsModal(ui('Tóm tắt tài liệu học tập', 'Summarize study material'), renderStudySummarizerBody());
            bindStudySummarizerBody();
        });
    }
    const gpaBtn = container.querySelector('#studentToolGpaBtn');
    if (gpaBtn) {
        gpaBtn.addEventListener('click', () => {
            openStudentToolsModal(ui('Tính GPA', 'Calculate GPA'), renderGpaCalculatorBody());
            bindGpaCalculatorBody();
        });
    }
}

function bindOverviewEmailClicks(container, emails, selectedDate) {
    container.querySelectorAll('.overview-list-item[data-email-index]').forEach((article) => {
        const openDetail = () => {
            const email = emails[Number(article.dataset.emailIndex)];
            openOverviewEmail(email, selectedDate);
        };
        article.addEventListener('click', openDetail);
        article.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                openDetail();
            }
        });
    });
}

async function openOverviewEmail(email, selectedDate) {
    if (!email) return;
    if (email.id) {
        showFormattedEmailDetail(email);
        return;
    }

    // Cached overview predates storing the Gmail message id -- force one
    // refresh to pick up an id, then open the freshly matched row.
    try {
        const response = await apiFetch(
            `${API_BASE}/overview/daily?date=${encodeURIComponent(selectedDate)}&max_results=50&force=1`
        ).then((res) => res.json());
        const freshRows = Array.isArray(response.email_rows) ? response.email_rows : [];
        const match = freshRows.find((row) => row.subject === email.subject && row.sender === email.sender);
        if (match && match.id) {
            showFormattedEmailDetail(match);
            return;
        }
    } catch (error) {
        console.error('Overview email refresh failed:', error);
    }

    showFormattedEmailDetail({
        ...email,
        body: ui(
            'Không tải được nội dung gốc, vui lòng bấm "Tổng hợp lại" ở trên rồi thử lại.',
            'Could not load the original content -- tap "Refresh" above and try again.'
        ),
        attachments: []
    });
}

function clearOverviewRefreshTimer() {
    if (overviewRefreshTimer) {
        clearTimeout(overviewRefreshTimer);
        overviewRefreshTimer = null;
    }
}

function scheduleOverviewRefreshPoll(selectedDate, attempt = 0) {
    clearOverviewRefreshTimer();
    if (attempt >= OVERVIEW_REFRESH_MAX_POLLS) return;

    overviewRefreshTimer = setTimeout(() => {
        overviewRefreshTimer = null;
        const activeDate = document.getElementById('overviewDate')?.value;
        if (currentPage !== 'overview' || activeDate !== selectedDate) return;
        loadOverviewPage({ background: true, pollAttempt: attempt + 1 })
            .catch(error => console.warn('Overview background refresh error:', error));
    }, OVERVIEW_REFRESH_POLL_INTERVAL_MS);
}

async function loadOverviewPage(options = {}) {
    const container = document.getElementById('overviewContent');
    const dateInput = document.getElementById('overviewDate');
    const refreshBtn = document.getElementById('refreshOverviewBtn');
    if (!container) return;

    if (dateInput && !dateInput.value) {
        dateInput.value = formatDateForApi(new Date());
    }
    const selectedDate = dateInput?.value || formatDateForApi(new Date());
    const reportDate = formatOverviewDateForReport(selectedDate);
    const isBackground = options.background === true;

    if (!isBackground) clearOverviewRefreshTimer();
    if (!isBackground || !container.children.length) {
        container.innerHTML = `<div class="overview-loading">${ui('Đang tải bản tổng hợp...', 'Loading your overview...')}</div>`;
    }
    // #overviewContent scrolls independently of the static header/date-picker
    // above it, so replacing its content without resetting scroll leaves a
    // leftover scroll offset from before the refresh -- the new hero card
    // then renders starting mid-way (kicker/heading scrolled out of view)
    // instead of from the top, looking like its content got cut off.
    container.scrollTop = 0;
    if (refreshBtn && !isBackground) refreshBtn.disabled = true;

    try {
        if (options.force) {
            clearRuntimeCache('schedule:');
        }

        const [overviewResult, checklistResult, analyticsResult] = await Promise.allSettled([
            apiFetch(`${API_BASE}/overview/daily?date=${encodeURIComponent(selectedDate)}&max_results=50${options.force ? '&force=1' : ''}`).then((response) => response.json()),
            apiFetch(`${API_BASE}/schedule/checklist?date=${encodeURIComponent(selectedDate)}`).then((response) => response.json()),
            apiFetch(`${API_BASE}/overview/analytics?days=7&end_date=${encodeURIComponent(selectedDate)}`).then((response) => response.json())
        ]);

        const overviewData = overviewResult.status === 'fulfilled' ? overviewResult.value : {};
        const checklistData = checklistResult.status === 'fulfilled' ? checklistResult.value : {};
        const analyticsData = analyticsResult.status === 'fulfilled' ? analyticsResult.value : null;
        const schedules = dedupeSchedules(Array.isArray(overviewData.schedules) ? overviewData.schedules : [])
            .filter((item) => isSameOverviewDay(item.start_time, selectedDate))
            .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
        const emails = Array.isArray(overviewData.email_rows)
            ? overviewData.email_rows
            : (Array.isArray(overviewData.emails) ? overviewData.emails : []);
        const checklistState = normalizeOverviewChecklist(checklistData);
        const deadlines = schedules.filter((item) => getOverviewPriority(item) === ui('Deadline', 'Deadline'));
        const openTasks = schedules.filter((item) => item.status !== 'completed');
        const meetingEmails = emails.filter((item) => item.is_meeting);
        const insight = buildOverviewInsight({ schedules, emails, selectedDate });
        const refreshNote = overviewData.refreshing
            ? `<p class="overview-refresh-note">${overviewData.refresh_state === 'checking'
                ? ui('Đang kiểm tra thay đổi mới trong nền. Bản tổng hợp hiện tại vẫn dùng được ngay.', 'Checking for changes in the background. The current overview remains available.')
                : ui('AI đang cập nhật bản tổng hợp trong nền. Dữ liệu hiện có vẫn xem được ngay.', 'AI is updating the overview in the background. Existing data remains available.')}</p>`
            : '';

        container.innerHTML = `
            <section class="overview-hero">
                <div>
                    <span class="overview-kicker">${ui('TÓM TẮT AI', 'AI SUMMARY')}</span>
                    <h3>${escapeHtml(reportDate)}</h3>
                    <p>${escapeHtml(insight)}</p>
                    ${refreshNote}
                </div>
                <div class="overview-score">
                    <strong>${openTasks.length + emails.length}</strong>
                    <span>${ui('điểm cần xem', 'items to review')}</span>
                </div>
            </section>

            <div class="overview-stat-grid">
                <article><strong>${deadlines.length}</strong><span>${ui('Deadline', 'Deadlines')}</span></article>
                <article><strong>${emails.length}</strong><span>Email</span></article>
                <article><strong>${openTasks.length}</strong><span>${ui('Task mở', 'Open tasks')}</span></article>
                <article><strong>${meetingEmails.length}</strong><span>${ui('Mail họp', 'Meeting mail')}</span></article>
            </div>

            ${renderOverviewQuickAdd()}

            ${renderOverviewCountdown(overviewData.upcoming_deadlines)}

            ${renderStudentToolsPanel()}

            ${renderOverviewChecklist(schedules, checklistState)}

            ${renderOverviewAnalytics(analyticsData)}

            <div class="overview-grid">
                <section class="overview-panel">
                    <div class="overview-panel-head">
                        <span class="overview-kicker">${ui('DEADLINE & TASK', 'DEADLINES & TASKS')}</span>
                        <strong>${ui('Việc cần xử lý hôm nay', 'Today’s work')}</strong>
                    </div>
                    <div class="overview-list">${renderOverviewList(schedules, 'task')}</div>
                </section>
                <section class="overview-panel">
                    <div class="overview-panel-head">
                        <span class="overview-kicker">EMAIL</span>
                        <strong>${ui('Mail quan trọng trong ngày', 'Important mail today')}</strong>
                    </div>
                    <div class="overview-list">${renderOverviewList(emails, 'email')}</div>
                </section>
            </div>
        `;
        bindOverviewQuickAdd(container, selectedDate);
        bindOverviewChecklist(container, selectedDate, schedules, checklistState);
        bindOverviewEmailClicks(container, emails, selectedDate);
        bindStudentToolsPanel(container, selectedDate);
        if (overviewData.refreshing) {
            scheduleOverviewRefreshPoll(selectedDate, Number(options.pollAttempt || 0));
        } else {
            clearOverviewRefreshTimer();
        }
    } catch (error) {
        if (isBackground) {
            scheduleOverviewRefreshPoll(selectedDate, Number(options.pollAttempt || 0));
            return;
        }
        container.innerHTML = `
            <div class="overview-error">
                <strong>${ui('Không thể tổng hợp dữ liệu', 'Unable to build overview')}</strong>
                <p>${escapeHtml(error.message || ui('Vui lòng thử lại sau.', 'Please try again later.'))}</p>
            </div>
        `;
    } finally {
        if (refreshBtn && !isBackground) refreshBtn.disabled = false;
    }
}

// Ensure only the active page is visible. This fixes cases where multiple
// `.page` elements become visible due to cached CSS or inline styles.
