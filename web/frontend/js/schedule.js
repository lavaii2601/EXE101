function setWeekStart(date) {
    currentWeekStart = getMonday(date);
}

function goToRelativeWeek(deltaWeeks) {
    const base = new Date(
        currentWeekStart.getFullYear(),
        currentWeekStart.getMonth(),
        currentWeekStart.getDate() + (deltaWeeks * 7)
    );
    setWeekStart(base);
    invalidateScheduleCaches();
    // Navigating to a week the app hasn't shown before must pull that week
    // live from Google Calendar (sync=1) -- the local SQLite mirror only
    // has whatever was synced on a previous visit/full sync, so a plain
    // reload here can render an empty week even when Google has events on it.
    return loadWeekSchedule({ sync: true });
}

function bindWeekNavigation() {
    const prevWeekBtn = document.getElementById('prevWeekBtn');
    if (prevWeekBtn && prevWeekBtn.dataset.weekNavReady !== 'true') {
        prevWeekBtn.dataset.weekNavReady = 'true';
        prevWeekBtn.addEventListener('click', () => {
            goToRelativeWeek(-1).catch(err => console.warn('Previous week load error:', err));
        });
    }

    const nextWeekBtn = document.getElementById('nextWeekBtn');
    if (nextWeekBtn && nextWeekBtn.dataset.weekNavReady !== 'true') {
        nextWeekBtn.dataset.weekNavReady = 'true';
        nextWeekBtn.addEventListener('click', () => {
            goToRelativeWeek(1).catch(err => console.warn('Next week load error:', err));
        });
    }

    const todayWeekBtn = document.getElementById('todayWeekBtn');
    if (todayWeekBtn && todayWeekBtn.dataset.weekNavReady !== 'true') {
        todayWeekBtn.dataset.weekNavReady = 'true';
        todayWeekBtn.addEventListener('click', () => {
            setWeekStart(new Date());
            invalidateScheduleCaches();
            loadWeekSchedule({ sync: true }).catch(err => console.warn('Current week load error:', err));
        });
    }
}

function formatWeekDate(date) {
    const dd = String(date.getDate()).padStart(2, '0');
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    return `${dd}/${mm}`;
}

function formatReadableDateTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString(currentLanguage === 'en' ? 'en-US' : 'vi-VN', {
        weekday: 'long',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatScheduleRange(startValue, endValue) {
    const start = startValue ? new Date(startValue) : null;
    const end = endValue ? new Date(endValue) : null;
    if (!start || Number.isNaN(start.getTime())) {
        return {
            date: ui('Chua xac dinh ngay', 'Date not set'),
            time: ui('Chua xac dinh thoi gian', 'Time not set'),
            full: ui('Chua xac dinh thoi gian', 'Time not set')
        };
    }
    const locale = currentLanguage === 'en' ? 'en-US' : 'vi-VN';
    const date = start.toLocaleDateString(locale, {
        weekday: 'long',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    });
    const startTime = start.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    const endTime = end && !Number.isNaN(end.getTime())
        ? end.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
        : '';
    const time = endTime ? `${startTime} - ${endTime}` : startTime;
    return { date, time, full: `${date}, ${time}` };
}

function updateDateTimePreview(inputOrId) {
    const input = typeof inputOrId === 'string' ? document.getElementById(inputOrId) : inputOrId;
    if (!input) return;
    const preview = document.querySelector(`[data-preview-for="${input.id}"]`);
    if (!preview) return;
    const text = formatReadableDateTime(input.value);
    preview.textContent = text || ui('Chua chon thoi gian', 'No time selected');
    preview.classList.toggle('has-value', !!text);
}

function updateConfirmSchedulePreview() {
    const dateInput = document.getElementById('confirmScheduleDate');
    const startInput = document.getElementById('confirmScheduleStartTime');
    const endInput = document.getElementById('confirmScheduleEndTime');
    const preview = document.getElementById('confirmSchedulePreview');
    if (!dateInput || !startInput || !preview) return;
    const start = dateInput.value && startInput.value ? `${dateInput.value}T${startInput.value}` : '';
    const end = dateInput.value && endInput?.value ? `${dateInput.value}T${endInput.value}` : '';
    const range = start ? formatScheduleRange(start, end) : null;
    preview.textContent = range ? range.full : ui('Chua chon thoi gian', 'No time selected');
    preview.classList.toggle('has-value', !!range);
}

function setupDateTimePreviews() {
    ['scheduleStartTime', 'scheduleEndTime', 'editScheduleTime'].forEach((id) => {
        const input = document.getElementById(id);
        if (!input || input.dataset.previewBound === 'true') return;
        input.dataset.previewBound = 'true';
        input.addEventListener('input', () => updateDateTimePreview(input));
        input.addEventListener('change', () => updateDateTimePreview(input));
        updateDateTimePreview(input);
    });

    ['confirmScheduleDate', 'confirmScheduleStartTime', 'confirmScheduleEndTime'].forEach((id) => {
        const input = document.getElementById(id);
        if (!input || input.dataset.previewBound === 'true') return;
        input.dataset.previewBound = 'true';
        input.addEventListener('input', updateConfirmSchedulePreview);
        input.addEventListener('change', updateConfirmSchedulePreview);
    });
    updateConfirmSchedulePreview();
}

function isSameDate(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function scheduleFingerprint(schedule) {
    const title = String(schedule?.title || '').trim().toLowerCase().replace(/\s+/g, ' ');
    const start = new Date(schedule?.start_time || '');
    const startKey = Number.isNaN(start.getTime())
        ? String(schedule?.start_time || '')
        : start.toISOString().slice(0, 16);
    return `${title}|${startKey}`;
}

function dedupeSchedules(schedules = []) {
    const byGoogleId = new Map();
    const byFingerprint = new Map();
    const result = [];
    const priority = (schedule) => (
        schedule?.calendar_event_id || schedule?.google_event_id || schedule?.source === 'synced'
            ? 2
            : schedule?.source === 'google' ? 1 : 0
    );

    schedules.forEach((schedule) => {
        if (!schedule) return;
        const googleId = schedule.calendar_event_id || schedule.google_event_id || '';
        const fingerprint = scheduleFingerprint(schedule);
        const existing = (googleId && byGoogleId.get(googleId)) || byFingerprint.get(fingerprint);
        if (!existing) {
            result.push(schedule);
            if (googleId) byGoogleId.set(googleId, schedule);
            byFingerprint.set(fingerprint, schedule);
            return;
        }

        if (priority(schedule) > priority(existing)) {
            const index = result.indexOf(existing);
            if (index >= 0) result[index] = schedule;
            if (googleId) byGoogleId.set(googleId, schedule);
            byFingerprint.set(fingerprint, schedule);
        }
    });

    return result;
}

function isUnsyncedLocalSchedule(schedule, googleConnected = true) {
    if (!googleConnected || !schedule) return false;
    const hasLocalId = schedule.local_id !== null && schedule.local_id !== undefined;
    const hasGoogleId = Boolean(schedule.calendar_event_id || schedule.google_event_id);
    return hasLocalId && !hasGoogleId && (schedule.source || 'local') !== 'google';
}

async function loadWeekSchedule(options = {}) {
    const headerRow = document.getElementById('weekTableHeader');
    const tableBody = document.getElementById('weekTableBody');
    const rangeLabel = document.getElementById('weekRangeLabel');
    if (!headerRow || !tableBody) return;

    const requestId = ++weekScheduleRequestId;
    const weekStartStr = `${currentWeekStart.getFullYear()}-${String(currentWeekStart.getMonth() + 1).padStart(2, '0')}-${String(currentWeekStart.getDate()).padStart(2, '0')}`;
    const today = new Date();
    headerRow.innerHTML = '';
    const timezoneHeader = document.createElement('th');
    timezoneHeader.className = 'week-timezone';
    timezoneHeader.textContent = 'GMT+7';
    headerRow.appendChild(timezoneHeader);

    for (let i = 0; i < 7; i++) {
        const dayDate = new Date(currentWeekStart);
        dayDate.setDate(dayDate.getDate() + i);
        const th = document.createElement('th');
        if (isSameDate(dayDate, today)) th.classList.add('is-today');
        th.innerHTML = `<span class="week-day-name">${weekDayNames()[i]}</span><span class="week-day-date">${formatWeekDate(dayDate)}</span>`;
        headerRow.appendChild(th);
    }

    if (rangeLabel) {
        const sunday = new Date(currentWeekStart);
        sunday.setDate(sunday.getDate() + 6);
        rangeLabel.textContent = `${formatWeekDate(currentWeekStart)} - ${formatWeekDate(sunday)}/${sunday.getFullYear()}`;
    }

    tableBody.innerHTML = `<tr><td colspan="8" class="week-loading">${ui('Đang tải...', 'Loading...')}</td></tr>`;

    try {
        const syncFlag = (options.sync || options.forceSync) ? 1 : 0;
        const forceParam = options.forceSync ? '&force=1' : '';
        const data = await fetchJsonCached(
            `schedule:week:${weekStartStr}:${syncFlag}:${options.forceSync ? 1 : 0}`,
            `${API_BASE}/schedule/week?start=${weekStartStr}&sync=${syncFlag}${forceParam}`,
            6000
        );
        if (requestId !== weekScheduleRequestId) return;

        if (!data.success) {
            tableBody.innerHTML = `<tr><td colspan="8" class="week-loading">${ui('Không thể tải lịch tuần', 'Unable to load weekly calendar')}</td></tr>`;
            return;
        }

        const googleConnected = Boolean(data.calendar_connected || data.google_calendar_connected);
        const days = (Array.isArray(data.days) ? data.days : []).map((dayEvents) =>
            dedupeSchedules(Array.isArray(dayEvents) ? dayEvents : [])
        );
        const eventHours = Array.from(new Set(
            days
                .flatMap((dayEvents) => Array.isArray(dayEvents) ? dayEvents : [])
                .map((schedule) => new Date(schedule.start_time))
                .filter((date) => !Number.isNaN(date.getTime()))
                .map((date) => date.getHours())
        )).sort((a, b) => a - b);

        tableBody.innerHTML = '';
        if (eventHours.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="8" class="week-loading">${ui('Tuần này chưa có lịch hẹn', 'No appointments this week')}</td></tr>`;
            return;
        }

        for (const hour of eventHours) {
            const row = document.createElement('tr');
            const timeCell = document.createElement('th');
            timeCell.className = 'week-time-label';
            timeCell.textContent = `${hour}:00`;
            row.appendChild(timeCell);

            for (let i = 0; i < 7; i++) {
                const dayDate = new Date(currentWeekStart);
                dayDate.setDate(dayDate.getDate() + i);
                const td = document.createElement('td');
                td.className = 'week-hour-cell';
                if (isSameDate(dayDate, today)) td.classList.add('is-today');

                const dayEvents = days[i] || [];
                dayEvents
                    .filter((schedule) => new Date(schedule.start_time).getHours() === hour)
                    .forEach((schedule) => {
                    const eventDiv = document.createElement('div');
                    eventDiv.className = 'week-event';
                    const unsyncedLocal = isUnsyncedLocalSchedule(schedule, googleConnected);
                    if (unsyncedLocal) eventDiv.classList.add('is-unsynced');
                    const range = formatScheduleRange(schedule.start_time, schedule.end_time);

                    eventDiv.innerHTML = `
                        <div class="week-event-title">${escapeHtml(schedule.title)}</div>
                        <div class="week-event-time">${escapeHtml(range.time)}</div>
                        ${unsyncedLocal ? `<div class="week-event-sync unsynced">${ui('Chưa đồng bộ Google', 'Not synced to Google')}</div>` : ''}
                    `;
                    eventDiv.addEventListener('click', () => openEditSchedule(schedule.id));
                    td.appendChild(eventDiv);
                });
                row.appendChild(td);
            }
            tableBody.appendChild(row);
        }

        if (data.calendar_sync_pending && (options.sync || options.forceSync)) {
            window.setTimeout(() => {
                invalidateScheduleCaches();
                loadWeekSchedule().catch(err => console.warn('Week schedule refresh error:', err));
                loadSchedules().catch(err => console.warn('Schedule refresh error:', err));
                refreshQuickScheduleSummary();
            }, 1800);
        }
    } catch (error) {
        tableBody.innerHTML = `<tr><td colspan="8" class="week-loading">${ui('Không thể tải lịch tuần', 'Unable to load weekly calendar')}</td></tr>`;
    }
}

function openNewScheduleModal(preserveSuggestion = false) {
    const modal = document.getElementById('newScheduleModal');
    const form = document.getElementById('scheduleForm');
    if (!preserveSuggestion && form) delete form.dataset.meetingSuggestionId;
    updateScheduleEndFromDuration();
    if (modal) modal.classList.add('show');
}

function closeNewScheduleModal() {
    const modal = document.getElementById('newScheduleModal');
    const form = document.getElementById('scheduleForm');
    if (form) delete form.dataset.meetingSuggestionId;
    if (modal) modal.classList.remove('show');
}

function addMinutesToDatetimeLocal(value, minutes) {
    if (!value || !Number.isFinite(minutes) || minutes <= 0) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    date.setMinutes(date.getMinutes() + minutes);
    return toDatetimeLocal(date);
}

function updateScheduleEndFromDuration() {
    const startInput = document.getElementById('scheduleStartTime');
    const durationInput = document.getElementById('scheduleDuration');
    const endInput = document.getElementById('scheduleEndTime');
    if (!startInput || !durationInput || !endInput) return;

    const duration = parseInt(durationInput.value || '60', 10);
    endInput.value = addMinutesToDatetimeLocal(
        startInput.value,
        Number.isFinite(duration) && duration > 0 ? duration : 60
    );
    updateDateTimePreview(startInput);
    updateDateTimePreview(endInput);
}

function bindScheduleTimeLogic() {
    const form = document.getElementById('scheduleForm');
    if (!form || form.dataset.timeLogicBound === 'true') return;

    const startInput = document.getElementById('scheduleStartTime');
    const durationInput = document.getElementById('scheduleDuration');
    if (startInput) startInput.addEventListener('change', updateScheduleEndFromDuration);
    if (durationInput) durationInput.addEventListener('input', updateScheduleEndFromDuration);

    form.dataset.timeLogicBound = 'true';
}

function openEditScheduleModal() {
    const modal = document.getElementById('editScheduleModal');
    if (!modal) return;
    modal.style.display = '';
    modal.classList.add('show');
}

function closeEditScheduleModal() {
    const modal = document.getElementById('editScheduleModal');
    if (!modal) return;
    modal.classList.remove('show');
    modal.style.display = '';
}

function bindEditScheduleModal() {
    const modal = document.getElementById('editScheduleModal');
    if (!modal || modal.dataset.bound === 'true') return;

    modal.querySelectorAll('.close[data-modal="editScheduleModal"], [data-close-edit-schedule]').forEach((el) => {
        el.addEventListener('click', closeEditScheduleModal);
    });

    const deleteButton = document.getElementById('deleteEditScheduleBtn');
    if (deleteButton) {
        deleteButton.addEventListener('click', handleDeleteEditSchedule);
    }

    modal.addEventListener('click', (event) => {
        if (event.target === modal) closeEditScheduleModal();
    });

    modal.dataset.bound = 'true';
}

// SCHEDULE FUNCTIONS
async function loadSchedules(options = {}) {
    const schedulesList = document.getElementById('schedulesList');
    if (!schedulesList) return;
    const requestId = ++scheduleListRequestId;

    schedulesList.innerHTML = `<p class="schedule-empty-state">${ui('Đang tải lịch tổng hợp...', 'Loading calendar...')}</p>`;

    try {
        const data = await fetchJsonCached(
            `schedule:unified:100:${options.liveGoogle ? 1 : 0}`,
            `${API_BASE}/schedule/unified?max_results=100&live=${options.liveGoogle ? 1 : 0}`,
            8000
        );
        if (requestId !== scheduleListRequestId) return;

        const calendarStatus = document.getElementById('calendarStatus');
        if (calendarStatus) {
            const connectedSources = [];
            if (data.calendar_connected || data.google_calendar_connected) connectedSources.push('Google');
            if (data.outlook_calendar_connected) connectedSources.push('Outlook');
            calendarStatus.textContent = connectedSources.length
                ? ui(`Đã kết nối ${connectedSources.join(' + ')} - ${data.count || 0} sự kiện`, `Connected ${connectedSources.join(' + ')} - ${data.count || 0} events`)
                : ui('Lịch FlowMate', 'FlowMate Calendar');
        }

        const googleConnected = Boolean(data.calendar_connected || data.google_calendar_connected);
        const schedules = Array.isArray(data.items) ? data.items : [];
        if (data.success && schedules.length > 0) {
            schedulesList.innerHTML = '';
            schedules.forEach(schedule => {
                const scheduleDiv = document.createElement('div');
                scheduleDiv.className = `schedule-item unified-schedule-item source-${schedule.source || 'local'}`;
                const range = formatScheduleRange(schedule.start_time, schedule.end_time);
                const durationMinutes = getDurationMinutes(schedule.start_time, schedule.end_time);
                const statusClass = schedule.status === 'completed' ? 'completed' : 'pending';
                const statusText = schedule.status === 'completed'
                    ? ui('Đã hoàn thành', 'Completed')
                    : ui('Chưa hoàn thành', 'Pending');
                const isLocal = schedule.local_id !== null && schedule.local_id !== undefined;
                const unsyncedLocal = isUnsyncedLocalSchedule(schedule, googleConnected);
                const sourceValue = schedule.provider || schedule.source || '';
                const sourceText = sourceValue === 'outlook' || sourceValue === 'microsoft'
                    ? 'Outlook Calendar'
                    : unsyncedLocal
                    ? ui('Chưa đồng bộ Google', 'Not synced to Google')
                    : schedule.source === 'synced'
                    ? 'FlowMate + Google'
                    : schedule.source === 'google' ? 'Google Calendar' : 'FlowMate';
                const sourceClass = sourceValue === 'outlook' || sourceValue === 'microsoft'
                    ? 'outlook'
                    : unsyncedLocal
                    ? 'local-unsynced'
                    : schedule.source === 'synced'
                    ? 'synced'
                    : schedule.source === 'google' ? 'google' : 'local';
                const attendees = Array.isArray(schedule.attendees)
                    ? schedule.attendees.join(', ')
                    : String(schedule.attendees || '');
                const description = plainTextFromHtml(schedule.description || '');
                const externalLink = schedule.html_link || schedule.web_link || schedule.calendar_event_link || '';
                const expectedUpdatedAt = JSON.stringify(schedule.updated_at || null);
                const localActions = isLocal
                    ? `
                        ${schedule.status === 'completed'
                            ? `<button class="btn-check" onclick='markScheduleIncomplete(${schedule.local_id}, ${expectedUpdatedAt})'>${ui('↩ Chưa xong', '↩ Mark pending')}</button>`
                            : `<button class="btn-check" onclick='markScheduleComplete(${schedule.local_id}, ${expectedUpdatedAt})'>${ui('✓ Hoàn thành', '✓ Complete')}</button>`}
                        ${unsyncedLocal ? `<button class="btn-sync-google" data-sync-google>${ui('Đồng bộ Google', 'Sync Google')}</button>` : ''}
                        <button class="btn-edit" onclick="openEditSchedule(${schedule.local_id})">${ui('Sửa', 'Edit')}</button>
                        <button class="btn-delete" onclick="deleteSchedule(${schedule.local_id})">${ui('Xóa', 'Delete')}</button>
                    `
                    : sourceClass === 'google' && schedule.google_event_id
                        ? `<button class="btn-delete" data-google-event-id="${escapeHtml(schedule.google_event_id || '')}">${ui('Xóa khỏi Google', 'Delete from Google')}</button>`
                        : externalLink
                            ? `<button class="btn-secondary" data-open-event-link="${escapeHtml(externalLink)}">${ui('Mở lịch', 'Open event')}</button>`
                            : '';

                scheduleDiv.innerHTML = `
                    <div class="schedule-item-main">
                        <div class="schedule-item-heading">
                            <div>
                                <div class="schedule-item-title">${escapeHtml(schedule.title || ui('Sự kiện', 'Event'))}</div>
                                <div class="schedule-item-time">
                                    <span class="schedule-time-date">${escapeHtml(range.date)}</span>
                                    <span class="schedule-time-clock">${escapeHtml(range.time)}</span>
                                </div>
                            </div>
                            <div class="schedule-item-badges">
                                ${isLocal ? `<span class="schedule-item-status ${statusClass}">${statusText}</span>` : ''}
                                <span class="schedule-source-badge ${sourceClass}">${sourceText}</span>
                            </div>
                        </div>
                        <div class="schedule-item-meta">
                            ${durationMinutes ? `<span>${ui('Thời lượng', 'Duration')}: ${durationMinutes} ${ui('phút', 'minutes')}</span>` : ''}
                            ${schedule.location ? `<span>${ui('Địa điểm', 'Location')}: ${escapeHtml(schedule.location)}</span>` : ''}
                            ${attendees ? `<span>${ui('Người tham dự', 'Attendees')}: ${escapeHtml(attendees)}</span>` : ''}
                        </div>
                        ${description ? `<div class="schedule-item-description">${escapeHtml(description)}</div>` : ''}
                    </div>
                    <div class="schedule-item-actions">${localActions}</div>
                `;

                const deleteGoogleButton = scheduleDiv.querySelector('[data-google-event-id]');
                if (deleteGoogleButton) {
                    deleteGoogleButton.addEventListener('click', () => {
                        deleteCalendarEvent(deleteGoogleButton.dataset.googleEventId);
                    });
                }
                const openEventButton = scheduleDiv.querySelector('[data-open-event-link]');
                if (openEventButton) {
                    openEventButton.addEventListener('click', () => openExternalUrl(openEventButton.dataset.openEventLink));
                }
                const syncGoogleButton = scheduleDiv.querySelector('[data-sync-google]');
                if (syncGoogleButton) {
                    syncGoogleButton.addEventListener('click', async () => {
                        syncGoogleButton.disabled = true;
                        syncGoogleButton.textContent = ui('Đang đồng bộ...', 'Syncing...');
                        await refreshCalendarScheduleData({ days: 365, notify: true, continueOnError: true });
                    });
                }
                schedulesList.appendChild(scheduleDiv);
            });
        } else {
            schedulesList.innerHTML = `<p class="schedule-empty-state">${ui('Không có sự kiện sắp tới', 'No upcoming events')}</p>`;
        }
    } catch (error) {
        schedulesList.innerHTML = `<p class="schedule-empty-state">${ui('Lỗi', 'Error')}: ${escapeHtml(error.message)}</p>`;
    } finally {
        scheduleMeetingSuggestionRefresh({ scan: false });
    }
}

async function markScheduleComplete(scheduleId, expectedUpdatedAt = null) {
    if (!confirm(ui('Đánh dấu lịch hẹn đã hoàn thành?', 'Mark this appointment as completed?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}/update-status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'completed', expected_updated_at: expectedUpdatedAt })
        });
        
        const data = await response.json();
        if (response.status === 409) {
            await refreshLocalScheduleViews();
            showNotification(ui(
                'Lịch đã thay đổi trên thiết bị khác. Đã tải lại bản mới nhất.',
                'This appointment changed on another device. The latest version was reloaded.'
            ), 'warning');
        } else if (data.success) {
            showNotification(ui('✓ Đã đánh dấu hoàn thành', '✓ Marked as completed'), 'success');
            await loadSchedules();
            await loadWeekSchedule();
            refreshQuickScheduleSummary();
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể cập nhật trạng thái', 'Unable to update status')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}

async function markScheduleIncomplete(scheduleId, expectedUpdatedAt = null) {
    if (!confirm(ui('Đánh dấu lịch hẹn chưa hoàn thành?', 'Mark this appointment as pending?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}/update-status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'pending', expected_updated_at: expectedUpdatedAt })
        });
        
        const data = await response.json();
        if (response.status === 409) {
            await refreshLocalScheduleViews();
            showNotification(ui(
                'Lịch đã thay đổi trên thiết bị khác. Đã tải lại bản mới nhất.',
                'This appointment changed on another device. The latest version was reloaded.'
            ), 'warning');
        } else if (data.success) {
            showNotification(ui('↩️ Đã cập nhật trạng thái', '↩️ Status updated'), 'success');
            await loadSchedules();
            await loadWeekSchedule();
            refreshQuickScheduleSummary();
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể cập nhật trạng thái', 'Unable to update status')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}

async function openEditSchedule(scheduleId) {
    if (!scheduleId || String(scheduleId).startsWith('google:')) {
        showNotification(ui('Chỉ có thể sửa lịch được tạo trong FlowMate. Sự kiện Google Calendar cần sửa trên Google Calendar.', 'Only FlowMate appointments can be edited here. Edit Google Calendar-only events in Google Calendar.'), 'info');
        return;
    }

    try {
        const response = await apiFetch(`${API_BASE}/schedule/${encodeURIComponent(scheduleId)}`);
        const data = await response.json();
        
        if (!response.ok || !data.success) {
            throw new Error(data.error || ui('Lỗi lấy dữ liệu', 'Unable to load data'));
        }
        
        const schedule = data.schedule;
        if (!schedule) throw new Error(ui('Lịch hẹn không tìm thấy', 'Appointment not found'));
        
        const editForm = document.getElementById('editScheduleForm');
        if (!editForm) throw new Error(ui('Không tìm thấy form chỉnh sửa', 'Edit form not found'));

        document.getElementById('editScheduleTitle').value = schedule.title;
        document.getElementById('editScheduleDesc').value = schedule.description || '';
        document.getElementById('editScheduleTime').value = toDatetimeLocal(schedule.start_time);
        updateDateTimePreview('editScheduleTime');
        const editDurationInput = document.getElementById('editScheduleDuration');
        if (editDurationInput) {
            editDurationInput.value = getDurationMinutes(schedule.start_time, schedule.end_time) || 60;
        }
        const editLocationInput = document.getElementById('editScheduleLocation');
        if (editLocationInput) editLocationInput.value = schedule.location || '';
        document.getElementById('editScheduleAttendees').value = Array.isArray(schedule.attendees)
            ? schedule.attendees.join(', ')
            : (schedule.attendees || '');
        editForm.dataset.scheduleId = String(schedule.id || scheduleId);
        editForm.dataset.scheduleUpdatedAt = String(schedule.updated_at || '');
        
        openEditScheduleModal();
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}

async function handleEditScheduleSubmit(e) {
    e.preventDefault();
    
    const editForm = document.getElementById('editScheduleForm');
    const scheduleId = editForm?.dataset.scheduleId;
    const expectedUpdatedAt = editForm?.dataset.scheduleUpdatedAt || null;
    const title = document.getElementById('editScheduleTitle').value.trim();
    const description = document.getElementById('editScheduleDesc').value.trim();
    const start_time = document.getElementById('editScheduleTime').value;
    const duration_minutes = parseInt(document.getElementById('editScheduleDuration')?.value || '60', 10);
    const location = document.getElementById('editScheduleLocation')?.value.trim() || '';
    const attendees_str = document.getElementById('editScheduleAttendees').value.trim();
    const attendees = attendees_str ? attendees_str.split(',').map(e => e.trim()) : [];

    if (!scheduleId) {
        showNotification(ui('❌ Không tìm thấy lịch cần cập nhật', '❌ Appointment ID is missing'), 'error');
        return;
    }

    if (!title || !start_time) {
        showNotification(ui('Vui lòng nhập tiêu đề và ngày giờ', 'Please enter title and date/time'), 'warning');
        return;
    }
    
    const submitButton = e.submitter || editForm?.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;

    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title,
                description,
                start_time,
                duration_minutes: Number.isFinite(duration_minutes) && duration_minutes > 0 ? duration_minutes : 60,
                location,
                attendees,
                expected_updated_at: expectedUpdatedAt
            })
        });
        
        const data = await response.json();
        if (response.ok && data.success) {
            showNotification(ui('✓ Đã cập nhật lịch hẹn', '✓ Appointment updated'), 'success');
            closeEditScheduleModal();
            refreshLocalScheduleViews().catch(err => console.warn('Schedule refresh after edit failed:', err));
        } else if (response.status === 409) {
            closeEditScheduleModal();
            await refreshLocalScheduleViews();
            showNotification(ui(
                'Lịch đã được cập nhật trên thiết bị khác. Đã tải lại bản mới nhất để tránh ghi đè.',
                'This appointment changed on another device. The latest version was reloaded to avoid overwriting it.'
            ), 'warning');
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể cập nhật lịch hẹn', 'Unable to update appointment')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    } finally {
        if (submitButton) submitButton.disabled = false;
    }
}

async function pollScheduleSync(scheduleId, timeoutMs = 30000, intervalMs = 2000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        try {
            const resp = await apiFetch(`${API_BASE}/schedule/list`);
            const data = await resp.json();
            if (data && data.success && Array.isArray(data.schedules)) {
                const found = data.schedules.find(s => s.id === scheduleId || s.id == scheduleId);
                if (found && found.calendar_event_id) {
                    return true;
                }
            }
        } catch (e) {
            console.warn('Poll error', e);
        }
        await new Promise(r => setTimeout(r, intervalMs));
    }
    return false;
}

async function deleteSchedule(scheduleId) {
    if (!confirm(ui('Xóa lịch hẹn này?', 'Delete this appointment?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification(ui('🗑️ Đã xóa', '🗑️ Deleted'), 'success');
            invalidateScheduleCaches();
            refreshLocalScheduleViews().catch(err => console.warn('Schedule refresh after delete failed:', err));
            return true;
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể xóa lịch hẹn', 'Unable to delete appointment')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
    return false;
}

async function handleDeleteEditSchedule() {
    const editForm = document.getElementById('editScheduleForm');
    const scheduleId = editForm?.dataset.scheduleId;
    const deleteButton = document.getElementById('deleteEditScheduleBtn');
    if (!scheduleId) {
        showNotification(ui('Khong tim thay lich can xoa', 'Appointment ID is missing'), 'error');
        return;
    }

    if (deleteButton) deleteButton.disabled = true;
    try {
        const deleted = await deleteSchedule(scheduleId);
        if (deleted) closeEditScheduleModal();
    } finally {
        if (deleteButton) deleteButton.disabled = false;
    }
}

async function handleScheduleSubmit(e) {
    e.preventDefault();
    
    const title = document.getElementById('scheduleTitle').value.trim();
    const description = document.getElementById('scheduleDesc').value.trim();
    const start_time = document.getElementById('scheduleStartTime').value;
    const rawDuration = parseInt(document.getElementById('scheduleDuration')?.value || '60', 10);
    const duration_minutes = Number.isFinite(rawDuration) && rawDuration > 0 ? rawDuration : 60;
    const end_time = addMinutesToDatetimeLocal(start_time, duration_minutes);
    const location = document.getElementById('scheduleLocation') ? document.getElementById('scheduleLocation').value.trim() : '';
    const attendees_str = document.getElementById('scheduleAttendees').value.trim();
    const attendees = attendees_str ? attendees_str.split(',').map(e => e.trim()) : [];

    if (!title || !start_time) {
        showNotification(ui('Vui lòng nhập tiêu đề và ngày giờ bắt đầu', 'Please enter title and start date/time'), 'warning');
        return;
    }

    updateScheduleEndFromDuration();
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, start_time, end_time, duration_minutes, location, attendees })
        });
        
        const data = await response.json();
        if (data.success) {
            const sid = data.schedule_id;
            const meetingSuggestionId = scheduleForm.dataset.meetingSuggestionId;
            if (meetingSuggestionId) {
                try {
                    await updateMeetingSuggestionStatus(meetingSuggestionId, 'created', sid);
                } catch (error) {
                    console.warn('Unable to mark meeting suggestion as created:', error);
                }
                delete scheduleForm.dataset.meetingSuggestionId;
            }
            if (data.calendar_event_id) {
                showNotification(ui('✅ Lịch hẹn đã được tạo và đồng bộ Google Calendar', '✅ Appointment created and synced with Google Calendar'), 'success');
            } else if (data.calendar_sync_error?.message) {
                showNotification(data.calendar_sync_error.message, 'warning');
            } else {
                showNotification(ui('✅ Đã tạo lịch hẹn. Đang đồng bộ với Google Calendar...', '✅ Appointment created. Syncing with Google Calendar...'), 'info');
            }
            scheduleForm.reset();
            closeNewScheduleModal();
            syncSchedulesAfterLocalCreate({
                id: sid,
                title,
                calendar_event_id: data.calendar_event_id,
                calendar_sync_pending: data.calendar_sync_pending
            });
            await refreshLocalScheduleViews();

            // If calendar_event_id not present, poll for status in background
            if (!data.calendar_event_id && sid && !data.calendar_sync_error) {
                pollScheduleSync(sid, 30000).then(synced => {
                    if (synced) {
                        showNotification(ui('✅ Lịch hẹn đã được đồng bộ với Google Calendar', '✅ Appointment synced with Google Calendar'), 'success');
                    } else {
                        showNotification(ui('⚠️ Đồng bộ lịch hẹn chưa hoàn tất - thử lại sau', '⚠️ Appointment sync is not complete - try again later'), 'info');
                    }
                    refreshLocalScheduleViews();
                }).catch(err => {
                    console.warn('Poll schedule sync error', err);
                });
            }
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể tạo lịch hẹn', 'Unable to create appointment')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}

// UTILITIES
function toDatetimeLocal(value) {
    if (!value) return '';
    try {
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return '';
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
    } catch (e) {
        return '';
    }
}

function getDurationMinutes(startTime, endTime) {
    if (!startTime || !endTime) return null;
    const start = new Date(startTime);
    const end = new Date(endTime);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
    const diff = Math.round((end.getTime() - start.getTime()) / 60000);
    return diff > 0 ? diff : null;
}

