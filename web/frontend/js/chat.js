// Simple intent detection for scheduling prompts (Vietnamese + English keywords)
function isScheduleIntent(text) {
    if (!text) return false;
    const t = text.toLowerCase();
    const keywords = ['tạo lịch', 'lên lịch', 'đặt lịch', 'lên lịch hẹn', 'đặt lịch hẹn', 'lên lịch họp', 'xếp lịch', 'schedule', 'book', 'create meeting', 'create appointment', 'set up meeting'];
    return keywords.some(k => t.includes(k));
}

async function fetchScheduleDraft(message) {
    try {
        const resp = await apiFetch(`${API_BASE}/schedule/parse-draft`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'parse-draft failed');
        return {
            title: data.title || '',
            date: data.date || '',
            startTime: data.start_time || '',
            endTime: data.end_time || '',
            format: detectScheduleFormat(message),
            attendees: (Array.isArray(data.attendees) && data.attendees.length)
                ? data.attendees.join(', ')
                : detectAttendeesByName(message),
            content: message
        };
    } catch (err) {
        console.warn('⚠️ /schedule/parse-draft failed, using local draft guess', err);
        return extractScheduleDraft(message);
    }
}

// Meeting format isn't extracted by the backend -- only guess it when the
// message actually names one, otherwise leave it for the user to pick.
function detectScheduleFormat(text) {
    const lower = (text || '').toLowerCase();
    if (lower.includes('online') || lower.includes('trực tuyến') || lower.includes('truc tuyen')) return 'Online';
    if (lower.includes('điện thoại') || lower.includes('dien thoai') || lower.includes('phone')) return 'Điện thoại';
    if (lower.includes('trực tiếp') || lower.includes('truc tiep') || lower.includes('in person')) return 'Trực tiếp';
    return '';
}

// Best-effort "với <tên>" fallback when the message names someone without
// an email address. Only used when the backend found no email attendees.
function detectAttendeesByName(text) {
    const withMatch = (text || '').match(/(?:với|voi)\s+([^,.!?;:]+?)(?:\s+(?:lúc|vao|vào|ngày|ngay|tại|tai)\b|[,.!?;:]|$)/i);
    return withMatch ? withMatch[1].trim() : '';
}

// Offline fallback only (used when /schedule/parse-draft is unreachable) --
// the backend extractor above is the source of truth for date/time/title.
function extractScheduleDraft(text) {
    const source = (text || '').trim();
    const lower = source.toLowerCase();
    const draft = {
        title: '',
        date: '',
        startTime: '',
        endTime: '',
        format: detectScheduleFormat(source),
        attendees: '',
        content: source
    };

    const dateMatch = source.match(/(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})/);
    if (dateMatch) {
        let day = parseInt(dateMatch[1], 10);
        let month = parseInt(dateMatch[2], 10);
        let year = parseInt(dateMatch[3], 10);
        if (year < 100) year += 2000;
        if (day >= 1 && day <= 31 && month >= 1 && month <= 12) {
            draft.date = `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
        }
    } else if (lower.includes('ngày mai') || lower.includes('tomorrow')) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        draft.date = tomorrow.toISOString().slice(0, 10);
    } else if (lower.includes('hôm nay') || lower.includes('today')) {
        draft.date = new Date().toISOString().slice(0, 10);
    }

    // "sáng/chiều/tối/trưa" period-of-day words, applied the same way the
    // backend does: hour 1-11 + one of these => PM (+12).
    const periodRe = /(sáng|sang|chiều|chieu|tối|toi|trưa|trua)/;
    const applyPeriod = (hour) => (hour >= 1 && hour <= 11 && periodRe.test(lower)) ? hour + 12 : hour;

    const rangeMatch = source.match(/(\d{1,2})\s*(?::|h|giờ)\s*(\d{0,2})\s*(?:-|đến|toi|tới|to|->)\s*(\d{1,2})\s*(?::|h|giờ)\s*(\d{0,2})/i);
    if (rangeMatch) {
        const startHour = parseInt(rangeMatch[1], 10);
        const startMinute = parseInt(rangeMatch[2] || '0', 10) || 0;
        const endHour = parseInt(rangeMatch[3], 10);
        const endMinute = parseInt(rangeMatch[4] || '0', 10) || 0;
        if (!Number.isNaN(startHour)) draft.startTime = `${applyPeriod(startHour).toString().padStart(2, '0')}:${startMinute.toString().padStart(2, '0')}`;
        if (!Number.isNaN(endHour)) draft.endTime = `${applyPeriod(endHour).toString().padStart(2, '0')}:${endMinute.toString().padStart(2, '0')}`;
    } else {
        const timeMatch = source.match(/(\d{1,2})\s*(?::|h|giờ)\s*(\d{1,2})?/i);
        if (timeMatch) {
            const hour = parseInt(timeMatch[1], 10);
            const minute = parseInt(timeMatch[2] || '0', 10) || 0;
            if (!Number.isNaN(hour)) draft.startTime = `${applyPeriod(hour).toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
        }
    }

    const emailMatches = source.match(/[\w.-]+@[\w.-]+\.[A-Za-z]{2,}/g);
    if (emailMatches && emailMatches.length) {
        draft.attendees = Array.from(new Set(emailMatches)).join(', ');
    } else {
        draft.attendees = detectAttendeesByName(source);
    }

    // Drop date/time/content-marker clauses before using whatever remains
    // as the title, so "... lúc 7 giờ tối ngày 2/7/2026 nội dung là X"
    // doesn't dump the entire sentence into the title field.
    let titleSource = source
        .replace(/(?:nội dung|noi dung|ghi chú|ghi chu|mô tả|mo ta)\s*(?:là|la)?\s*[:\-]?\s*.*$/i, '')
        .replace(/\b(?:lúc|luc|vào|vao|at)\b/gi, ' ')
        .replace(/\d{1,2}[\/-]\d{1,2}(?:[\/-]\d{2,4})?/g, ' ')
        .replace(/\d{1,2}\s*(?::|h|giờ)\s*\d{0,2}\s*(?:sáng|sang|chiều|chieu|tối|toi|trưa|trua)?/gi, ' ')
        .replace(/\b(?:ngày mai|ngay mai|hôm nay|hom nay|tomorrow|today)\b/gi, ' ');
    const titleMatch = titleSource.match(/(?:tạo|lên|đặt)?\s*lịch(?:\s+hẹn)?\s*(?:cho|với|họp|hop|meeting)?\s*[:\-]?\s*([^,.!?;:]+)?/i);
    if (titleMatch && titleMatch[1] && titleMatch[1].trim()) {
        draft.title = titleMatch[1].trim().slice(0, 80);
    }
    if (!draft.title) {
        draft.title = 'Lịch hẹn';
    }

    return draft;
}

async function loadAgentProfile() {
    try {
        const response = await apiFetch(`${API_BASE}/chat/agent-profile`);
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || response.statusText);
        agentProfile = data.agent || null;
        renderAgentStatus(data.agent, data.providers);
        return data;
    } catch (error) {
        console.warn('Agent profile load failed:', error);
        renderAgentStatus(null, null);
        return null;
    }
}

function renderAgentStatus(agent, providers) {
    const el = document.getElementById('providerStatus');
    if (!el) return;
    if (!agent) {
        el.textContent = '';
        return;
    }
    const capabilityCount = Array.isArray(agent.capabilities) ? agent.capabilities.length : 0;
    const providerText = providers?.demo_mode
        ? ui('Demo provider', 'Demo provider')
        : ui('Provider sẵn sàng', 'Provider ready');
    el.innerHTML = `
        <span class="agent-pill">${escapeHtml(agent.name || 'Bob')}</span>
        <span>${escapeHtml(agent.version || '')}</span>
        <span>${capabilityCount} ${ui('năng lực', 'capabilities')}</span>
        <span>${escapeHtml(providerText)}</span>
        <span>${ui('Web/Mobile đồng bộ', 'Web/Mobile synced')}</span>
    `;
}

// CHAT FUNCTIONS (CRITICAL FIX)
// sendMessage wrapper: detect scheduling intent and prompt confirmation before sending
async function sendMessage() {
    const message = userInput.value.trim();
    if (!message) {
        console.warn('⚠️ Empty message');
        return;
    }

    if (isScheduleIntent(message)) {
        // show modal confirmation
        const modal = document.getElementById('scheduleConfirmModal');
        const body = document.getElementById('scheduleConfirmBody');
        const confirmBtn = document.getElementById('confirmScheduleCreate');
        const cancelBtn = document.getElementById('cancelScheduleConfirm');
        if (!modal || !body || !confirmBtn || !cancelBtn) {
            // fallback to sending directly
            sendMessageConfirmed(message);
            return;
        }

        // Ask the backend to parse the message with the same extractor the
        // chat flow uses (IntentOrchestrator.extract_schedule) instead of
        // guessing client-side -- this is what correctly turns "7 giờ tối"
        // into 19:00 and keeps a "nội dung là:" marker out of the title.
        // Falls back to the local heuristic only if the request fails.
        const draft = await fetchScheduleDraft(message);
        const titleEl = document.getElementById('confirmScheduleTitle');
        const dateEl = document.getElementById('confirmScheduleDate');
        const startEl = document.getElementById('confirmScheduleStartTime');
        const endEl = document.getElementById('confirmScheduleEndTime');
        const formatEl = document.getElementById('confirmScheduleFormat');
        const attendeesEl = document.getElementById('confirmScheduleAttendees');
        const contentEl = document.getElementById('confirmScheduleContent');
        if (titleEl) titleEl.value = draft.title;
        if (dateEl) dateEl.value = draft.date;
        if (startEl) startEl.value = draft.startTime;
        if (endEl) endEl.value = draft.endTime;
        if (formatEl) formatEl.value = draft.format;
        if (attendeesEl) attendeesEl.value = draft.attendees;
        if (contentEl) contentEl.value = draft.content;
        updateConfirmSchedulePreview();
        if (body) {
            body.innerHTML = `
                <div><strong>${ui('Nội dung phát hiện', 'Detected content')}:</strong> ${escapeHtml(draft.content)}</div>
                <div style="margin-top:8px; font-size:13px; line-height:1.5;">
                    ${ui('Ngày', 'Date')}: ${escapeHtml(draft.date || ui('Chưa xác định', 'Not specified'))}<br>
                    ${ui('Thời gian', 'Time')}: ${escapeHtml(draft.startTime ? (draft.endTime ? `${draft.startTime} - ${draft.endTime}` : draft.startTime) : ui('Chưa xác định', 'Not specified'))}<br>
                    ${ui('Hình thức', 'Format')}: ${escapeHtml(draft.format || ui('Chưa xác định', 'Not specified'))}<br>
                    ${ui('Đối tượng', 'Participants')}: ${escapeHtml(draft.attendees || ui('Chưa xác định', 'Not specified'))}
                </div>
            `;
        }
        modal.classList.add('show');
        // ensure previous handlers removed by cloning
        const newConfirm = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirm, confirmBtn);
        const newCancel = cancelBtn.cloneNode(true);
        cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

        newCancel.addEventListener('click', () => {
            modal.classList.remove('show');
        });

        newConfirm.addEventListener('click', () => {
            // gather override values
            const override = {};
            const t = document.getElementById('confirmScheduleTitle');
            const d = document.getElementById('confirmScheduleDate');
            const s = document.getElementById('confirmScheduleStartTime');
            const e = document.getElementById('confirmScheduleEndTime');
            const f = document.getElementById('confirmScheduleFormat');
            const a = document.getElementById('confirmScheduleAttendees');
            const c = document.getElementById('confirmScheduleContent');
            if (t) override.title = t.value.trim();
            if (c) override.description = c.value.trim();
            // build ISO datetimes if date and start provided
            try {
                if (d && s && d.value && s.value) {
                    const startDt = new Date(`${d.value}T${s.value}`);
                    override.start_time = startDt.toISOString();
                    if (e && e.value) {
                        const endDt = new Date(`${d.value}T${e.value}`);
                        override.end_time = endDt.toISOString();
                    } else {
                        const endDt = new Date(startDt.getTime() + 60*60000);
                        override.end_time = endDt.toISOString();
                    }
                }
            } catch (err) {
                console.warn('Invalid date/time in schedule confirm', err);
            }
            if (f) override.format = f.value;
            if (a) override.attendees = a.value.split(',').map(x=>x.trim()).filter(Boolean);

            modal.classList.remove('show');
            sendMessageConfirmed(message, { confirmedSchedule: true, scheduleOverride: override });
        });

        return;
    }

    // no scheduling intent, send directly
    sendMessageConfirmed(message);
}

async function sendMessageConfirmed(message, opts = {}) {
    const confirmed = !!opts.confirmedSchedule;
    const override = opts.scheduleOverride || null;
    const actionConfirmed = !!opts.confirmedAction;
    const actionOverride = opts.actionOverride || null;
    console.log(`📨 Sending message: ${message.substring(0, 50)}...`);
    addMessage(message, 'user');
    userInput.value = '';

    // Show loading
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message assistant';
    loadingDiv.innerHTML = `<div class="message-avatar bob-avatar" aria-hidden="true">${BOB_AVATAR_SVG}</div><div class="message-content"><div class="loading"></div></div>`;
    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        console.log(`🔗 POST ${API_BASE}/chat/message`);
        const response = await apiFetch(`${API_BASE}/chat/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                session_id: activeChatSessionId,
                mode: currentUserMode,
                confirmed_schedule: confirmed,
                schedule_override: override,
                confirmed_action: actionConfirmed,
                action_override: actionOverride
            })
        });

        console.log(`⚙️ Response status: ${response.status}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('✅ Response received:', data);
        if (data.session_id) {
            activeChatSessionId = data.session_id;
            persistChatSessionId();
        }
        if (!activeChatSessionTitle) {
            activeChatSessionTitle = message.slice(0, 80);
            persistChatSessionTitle();
            updateChatSessionTitle();
        }

        loadingDiv.remove();

        if (data.success) {
            const sourceLabels = {
                email: ui('Email', 'Email'),
                calendar: ui('Lịch', 'Calendar'),
                history: ui('Lịch sử', 'History'),
                profile: ui('Hồ sơ', 'Profile'),
                knowledge: ui('Kiến thức', 'Knowledge'),
                internet: ui('Internet', 'Internet'),
                time: ui('Thời gian hệ thống', 'System time')
            };
            const workspaceSources = Array.isArray(data.workspace_sources)
                ? data.workspace_sources.filter(source => ['email', 'calendar', 'internet'].includes(source))
                : [];
            const sourceBadge = workspaceSources.length
                ? `<span class="provider-badge workspace-source-badge">${workspaceSources.map(source => sourceLabels[source]).join(' + ')}</span>`
                : '';
            // agent_trace is diagnostic data. Do not expose internal intent
            // names or orchestration steps in the user's conversation.
            addMessage(data.response, 'assistant', sourceBadge);
            loadChatSessions().catch(() => {});

            await refreshWorkspaceTargets(data.refresh_targets);

            // Handle schedule results from server
            if (data.schedule_created) {
                // Server already created the schedule (user confirmed or server-side)
                try { await loadSchedules(); } catch (e) { /* ignore */ }
                try { await loadWeekSchedule(); } catch (e) { /* ignore */ }
                syncSchedulesAfterLocalCreate(data.schedule_created);
                showNotification(`${ui('✅ Đã tạo lịch', '✅ Event created')}: ${data.schedule_created.title || ui('Lịch hẹn', 'Appointment')}`, 'success');
            } else if (data.schedule_suggestion && (data.schedule_suggestion.action ? true : isScheduleIntent(message))) {
                const suggested = data.schedule_suggestion;
                const isMutation = suggested.action === 'update' || suggested.action === 'delete';

                const suggestionDiv = document.createElement('div');
                suggestionDiv.className = 'message assistant';
                if (isMutation) {
                    const isDelete = suggested.action === 'delete';
                    const currentLine = `${ui('Lịch hiện tại', 'Current event')}: ${escapeHtml(suggested.title || '')} - ${escapeHtml(suggested.start_time || '')}`;
                    const newLine = (!isDelete && suggested.new_start_time)
                        ? `<div style="color:var(--text-secondary); font-size:13px; margin-bottom:8px;">${ui('Thời gian mới', 'New time')}: ${escapeHtml(suggested.new_start_time)}</div>`
                        : '';
                    const confirmLabel = isDelete ? ui('Xóa lịch', 'Delete event') : ui('Cập nhật lịch', 'Update event');
                    suggestionDiv.innerHTML = `
                        <div class="message-content">
                            <div style="font-weight:700; margin-bottom:6px;">${isDelete ? ui('AI gợi ý xóa lịch', 'AI suggests deleting an event') : ui('AI gợi ý sửa lịch', 'AI suggests updating an event')}</div>
                            <div style="color:var(--text-secondary); font-size:13px; margin-bottom:4px;">${currentLine}</div>
                            ${newLine}
                            <div style="display:flex; gap:8px;">
                                <button class="btn-primary confirm-create-schedule">${confirmLabel}</button>
                                <button class="btn-secondary dismiss-schedule">${ui('Bỏ qua', 'Dismiss')}</button>
                            </div>
                        </div>
                    `;
                } else {
                    suggestionDiv.innerHTML = `
                        <div class="message-content">
                            <div style="font-weight:700; margin-bottom:6px;">${ui('AI gợi ý tạo lịch', 'AI suggested an event')}: ${escapeHtml(suggested.title || ui('Lịch hẹn', 'Appointment'))}</div>
                            <div style="color:var(--text-secondary); font-size:13px; margin-bottom:8px;">${escapeHtml(suggested.description || '')}</div>
                            <div style="display:flex; gap:8px;">
                                <button class="btn-primary confirm-create-schedule">${ui('Tạo lịch', 'Create event')}</button>
                                <button class="btn-secondary dismiss-schedule">${ui('Bỏ qua', 'Dismiss')}</button>
                            </div>
                        </div>
                    `;
                }
                chatMessages.appendChild(suggestionDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;

                suggestionDiv.querySelector('.dismiss-schedule').addEventListener('click', () => {
                    suggestionDiv.remove();
                    showNotification(ui('Đã bỏ qua gợi ý', 'Suggestion dismissed'), 'info');
                });

                if (isMutation) {
                    suggestionDiv.querySelector('.confirm-create-schedule').addEventListener('click', () => {
                        suggestionDiv.querySelectorAll('button').forEach(b => b.disabled = true);
                        sendMessageConfirmed(message, { confirmedSchedule: true, scheduleOverride: suggested });
                        suggestionDiv.remove();
                    });
                } else {
                    suggestionDiv.querySelector('.confirm-create-schedule').addEventListener('click', async () => {
                        // disable buttons while creating
                        suggestionDiv.querySelectorAll('button').forEach(b => b.disabled = true);
                        try {
                            const resp = await apiFetch(`${API_BASE}/schedule/create`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    title: suggested.title,
                                    description: suggested.description,
                                    start_time: suggested.start_time,
                                    end_time: suggested.end_time,
                                    attendees: suggested.attendees || []
                                })
                            });
                            const j = await resp.json();
                            if (resp.ok && j.success) {
                                syncSchedulesAfterLocalCreate({
                                    id: j.schedule_id,
                                    title: suggested.title,
                                    calendar_event_id: j.calendar_event_id,
                                    calendar_sync_pending: j.calendar_sync_pending
                                });
                                showNotification(`${ui('✅ Đã tạo lịch', '✅ Event created')}: ${j.calendar_event_id ? ui('đã đồng bộ Google Calendar', 'synced with Google Calendar') : suggested.title}`, 'success');
                                await refreshWorkspaceTargets(['schedule', 'calendar', 'overview', 'history']);
                                suggestionDiv.remove();
                            } else {
                                showNotification(ui('❌ Không thể tạo lịch: ', '❌ Could not create event: ') + (j.error || resp.statusText || ui('lỗi', 'error')), 'error');
                                suggestionDiv.querySelectorAll('button').forEach(b => b.disabled = false);
                            }
                        } catch (err) {
                            console.error('Create schedule error', err);
                            showNotification(ui('❌ Lỗi tạo lịch: ', '❌ Event creation error: ') + err.message, 'error');
                            suggestionDiv.querySelectorAll('button').forEach(b => b.disabled = false);
                        }
                    });
                }
            } else if (data.day_plan_suggestion) {
                const plan = data.day_plan_suggestion;
                const planDiv = document.createElement('div');
                planDiv.className = 'message assistant';
                planDiv.innerHTML = `<div class="message-content">${renderOverviewPlanSuggestion(plan)}</div>`;
                chatMessages.appendChild(planDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;

                const dismissButton = planDiv.querySelector('[data-plan-dismiss]');
                const applyButton = planDiv.querySelector('[data-plan-apply]');
                if (dismissButton) {
                    dismissButton.addEventListener('click', () => {
                        planDiv.remove();
                        showNotification(ui('Đã bỏ qua gợi ý', 'Suggestion dismissed'), 'info');
                    });
                }
                planDiv.querySelectorAll('[data-plan-row]').forEach((row) => {
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
                        const selectedItems = Array.from(planDiv.querySelectorAll('[data-plan-row]'))
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
                            showNotification(ui('Hãy chọn ít nhất một hoạt động để tạo lịch.', 'Select at least one activity to create events.'), 'error');
                            return;
                        }
                        applyButton.disabled = true;
                        try {
                            const response = await apiFetch(`${API_BASE}/schedule/plan-day/apply`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ date: plan.date, items: selectedItems })
                            });
                            const respData = await response.json();
                            if (!response.ok || !respData.success) {
                                throw new Error(respData.error || ui('Không thể áp dụng lịch gợi ý', 'Unable to apply suggested plan'));
                            }
                            clearRuntimeCache('schedule:');
                            showNotification(ui('Đã tạo lịch từ gợi ý', 'Suggested plan applied'), 'success');
                            planDiv.remove();
                            await Promise.allSettled([
                                loadOverviewPage({ force: true }),
                                loadWeekSchedule({ forceSync: true }),
                                loadSchedules({ liveGoogle: true })
                            ]);
                        } catch (error) {
                            showNotification(`${ui('Lỗi', 'Error')}: ${error.message}`, 'error');
                        } finally {
                            applyButton.disabled = false;
                        }
                    });
                }
            } else if (data.pending_action) {
                // Generic confirm card for any non-schedule write tool
                // (settings.update_mode, email.mark_read/unread,
                // checklist.create). data.response already carries the
                // proposal text, so this card only needs the buttons.
                const pending = data.pending_action;
                const pendingDiv = document.createElement('div');
                pendingDiv.className = 'message assistant';
                pendingDiv.innerHTML = `
                    <div class="message-content">
                        <div style="display:flex; gap:8px;">
                            <button class="btn-primary confirm-pending-action">${ui('Xác nhận', 'Confirm')}</button>
                            <button class="btn-secondary dismiss-pending-action">${ui('Bỏ qua', 'Dismiss')}</button>
                        </div>
                    </div>
                `;
                chatMessages.appendChild(pendingDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;

                pendingDiv.querySelector('.dismiss-pending-action').addEventListener('click', () => {
                    pendingDiv.remove();
                    showNotification(ui('Đã bỏ qua gợi ý', 'Suggestion dismissed'), 'info');
                });

                pendingDiv.querySelector('.confirm-pending-action').addEventListener('click', () => {
                    pendingDiv.querySelectorAll('button').forEach(b => b.disabled = true);
                    sendMessageConfirmed(message, {
                        confirmedAction: true,
                        actionOverride: { ...(pending.arguments || {}), tool: pending.tool }
                    });
                    pendingDiv.remove();
                });
            }

            if (Array.isArray(data.suggested_actions)) {
                data.suggested_actions.forEach(action => {
                    if (action.type !== 'draft_reply') return;

                    const actionDiv = document.createElement('div');
                    actionDiv.className = 'message assistant';
                    actionDiv.innerHTML = `
                        <div class="message-content">
                            <div style="font-weight:700; margin-bottom:6px;">${ui('AI gợi ý', 'AI suggestion')}: ${escapeHtml(action.label || '')}</div>
                            <div style="display:flex; gap:8px;">
                                <button class="btn-primary draft-reply-btn">${ui('Soạn trả lời', 'Draft reply')}</button>
                                <button class="btn-secondary dismiss-suggestion">${ui('Bỏ qua', 'Dismiss')}</button>
                            </div>
                        </div>
                    `;
                    chatMessages.appendChild(actionDiv);
                    chatMessages.scrollTop = chatMessages.scrollHeight;

                    actionDiv.querySelector('.dismiss-suggestion').addEventListener('click', () => {
                        actionDiv.remove();
                    });

                    actionDiv.querySelector('.draft-reply-btn').addEventListener('click', async () => {
                        actionDiv.querySelectorAll('button').forEach(b => b.disabled = true);
                        try {
                            const resp = await apiFetch(`${API_BASE}/chat/generate-reply`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    context: action.context,
                                    choice: 'Trả lời lịch sự, ngắn gọn, đúng trọng tâm'
                                })
                            });
                            const j = await resp.json();
                            if (resp.ok && j.success) {
                                addMessage(j.reply, 'assistant');
                                actionDiv.remove();
                                renderSendDraftedReplyCard(action.email_id, j.reply);
                            } else {
                                showNotification(ui('❌ Không tạo được trả lời: ', '❌ Could not draft reply: ') + (j.error || resp.statusText || ui('lỗi', 'error')), 'error');
                                actionDiv.querySelectorAll('button').forEach(b => b.disabled = false);
                            }
                        } catch (err) {
                            console.error('Draft reply error', err);
                            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + err.message, 'error');
                            actionDiv.querySelectorAll('button').forEach(b => b.disabled = false);
                        }
                    });
                });
            }
        } else {
            addMessage(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || 'Unknown error'), 'assistant');
            console.error('AI error:', data.error);
        }
    } catch (error) {
        loadingDiv.remove();
        console.error('❌ Message send error:', error);
        addMessage(ui('❌ Lỗi kết nối: ', '❌ Connection error: ') + error.message, 'assistant');

        // Detailed error message
        const errorMsg = `
Lỗi: ${error.message}
Endpoint: ${API_BASE}/chat/message
Status: Not reached
        `.trim();
        console.error(errorMsg);
    }
}

function renderSendDraftedReplyCard(emailId, replyText) {
    const card = document.createElement('div');
    card.className = 'message assistant';
    card.innerHTML = `
        <div class="message-content">
            <div style="display:flex; gap:8px;">
                <button class="btn-primary send-drafted-reply-btn">${ui('Gửi luôn', 'Send now')}</button>
                <button class="btn-secondary dismiss-suggestion">${ui('Không gửi', "Don't send")}</button>
            </div>
        </div>
    `;
    chatMessages.appendChild(card);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    card.querySelector('.dismiss-suggestion').addEventListener('click', () => card.remove());

    card.querySelector('.send-drafted-reply-btn').addEventListener('click', async () => {
        card.querySelectorAll('button').forEach(b => b.disabled = true);
        try {
            const resp = await apiFetch(`${API_BASE}/chat/send-drafted-reply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email_id: emailId, reply_text: replyText })
            });
            const j = await resp.json();
            if (resp.ok && j.success) {
                showNotification(ui('✅ Đã gửi email trả lời', '✅ Reply sent'), 'success');
                card.remove();
            } else {
                showNotification(ui('❌ Không gửi được email: ', '❌ Could not send email: ') + (j.error || resp.statusText || ui('lỗi', 'error')), 'error');
                card.querySelectorAll('button').forEach(b => b.disabled = false);
            }
        } catch (err) {
            console.error('Send drafted reply error', err);
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + err.message, 'error');
            card.querySelectorAll('button').forEach(b => b.disabled = false);
        }
    });
}

const BOB_AVATAR_SVG = `
<svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>
        <linearGradient id="bobAvatarGrad" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#34D399"/>
            <stop offset="100%" stop-color="#2563EB"/>
        </linearGradient>
    </defs>
    <circle cx="20" cy="20" r="20" fill="url(#bobAvatarGrad)"/>
    <line x1="20" y1="7" x2="20" y2="11" stroke="white" stroke-width="2" stroke-linecap="round" opacity="0.95"/>
    <circle cx="20" cy="6.5" r="1.7" fill="white"/>
    <rect x="11" y="11" width="18" height="15" rx="6" fill="white" opacity="0.95"/>
    <circle cx="16.5" cy="18.5" r="2.1" fill="#1f2937"/>
    <circle cx="23.5" cy="18.5" r="2.1" fill="#1f2937"/>
</svg>`;

function addMessage(text, role, badge = '') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    const avatar = role === 'assistant'
        ? `<div class="message-avatar bob-avatar" aria-hidden="true">${BOB_AVATAR_SVG}</div>`
        : '';
    messageDiv.innerHTML = `${avatar}<div class="message-content">${renderMarkdown(escapeHtml(text))}${badge}</div>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function loadChatHistory() {
    try {
        persistChatSessionId();
        const response = await apiFetch(`${API_BASE}/chat/history?limit=20&session_id=${encodeURIComponent(activeChatSessionId)}`);
        const data = await response.json();
        if (data.expired) {
            activeChatSessionId = createChatSessionId();
            activeChatSessionTitle = '';
            persistChatSessionId();
            persistChatSessionTitle();
            if (chatMessages) chatMessages.innerHTML = '';
            updateChatSessionTitle();
            await loadChatSessions();
            return;
        }
        if (data.session_id) {
            activeChatSessionId = data.session_id;
            persistChatSessionId();
        }
        if (chatMessages) chatMessages.innerHTML = '';
        if (data.success && data.history.length > 0) {
            data.history.reverse().forEach(record => {
                addMessage(record.user_message, 'user');
                addMessage(record.assistant_response, 'assistant');
            });
            // Scroll to the newest message after the entire history is rendered
            if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        updateChatSessionTitle();
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

function formatChatSessionTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString(currentLanguage === 'en' ? 'en-US' : 'vi-VN', {
        day: '2-digit',
        month: '2-digit',
        year: '2-digit'
    });
}

function updateChatSessionTitle() {
    const titleEl = document.getElementById('chatSessionTitle');
    const title = activeChatSessionTitle || ui('Bob', 'Bob');
    if (titleEl) titleEl.textContent = title;
    document.querySelectorAll('.chat-session-item').forEach((item) => {
        item.classList.toggle('active', item.dataset.sessionId === activeChatSessionId);
    });
}

function renderChatSessions(sessions = []) {
    if (!chatSessionsList) return;
    if (!sessions.length) {
        chatSessionsList.innerHTML = `<div class="chat-session-empty">${ui('Chưa có đoạn chat cũ.', 'No saved chats yet.')}</div>`;
        updateChatSessionTitle();
        return;
    }

    chatSessionsList.innerHTML = sessions.map((session) => {
        const title = escapeHtml(session.title || ui('Chat', 'Chat'));
        const lastMessage = escapeHtml(session.last_message || ui('Chưa có tin nhắn', 'No messages yet'));
        const time = escapeHtml(formatChatSessionTime(session.last_message_at || session.updated_at || session.created_at));
        const count = Number(session.message_count || 0);
        return `
            <div role="button" tabindex="0" class="chat-session-item ${session.id === activeChatSessionId ? 'active' : ''}" data-session-id="${escapeHtml(session.id)}" data-title="${title}" data-retention="${Number(session.retention_days || 90)}">
                <span class="chat-session-item-title">${title}</span>
                <span class="chat-session-item-preview">${lastMessage}</span>
                <span class="chat-session-item-meta">${time}${time ? ' · ' : ''}${count} ${ui('tin', 'msgs')}</span>
                <button type="button" class="chat-session-menu-btn" aria-label="${ui('Mo thao tac doan chat', 'Open chat actions')}">...</button>
            </div>
        `;
    }).join('');

    chatSessionsList.querySelectorAll('.chat-session-item').forEach((item) => {
        const session = sessions.find((entry) => entry.id === item.dataset.sessionId);
        item.addEventListener('click', () => openChatSession(item.dataset.sessionId, session?.title || '', item.dataset.retention));
        item.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                openChatSession(item.dataset.sessionId, session?.title || '', item.dataset.retention);
            }
        });
        const menuButton = item.querySelector('.chat-session-menu-btn');
        if (menuButton) {
            menuButton.addEventListener('click', (event) => {
                event.stopPropagation();
                openChatSessionMenu(item, session);
            });
        }
    });
    updateChatSessionTitle();
}

function closeChatSessionMenu() {
    document.querySelector('.chat-session-menu')?.remove();
}

function openChatSessionMenu(item, session) {
    closeChatSessionMenu();
    const menu = document.createElement('div');
    menu.className = 'chat-session-menu show';
    menu.innerHTML = `
        <button type="button" data-action="edit">${ui('Sua ten', 'Rename')}</button>
        <button type="button" data-action="delete">${ui('Xoa ngay', 'Delete now')}</button>
    `;
    document.body.appendChild(menu);
    const rect = item.querySelector('.chat-session-menu-btn')?.getBoundingClientRect() || item.getBoundingClientRect();
    menu.style.top = `${Math.min(rect.bottom + 6, window.innerHeight - 92)}px`;
    menu.style.left = `${Math.max(8, Math.min(rect.right - 128, window.innerWidth - 136))}px`;
    menu.addEventListener('click', async (event) => {
        const action = event.target?.dataset?.action;
        if (!action) return;
        event.stopPropagation();
        closeChatSessionMenu();
        if (action === 'edit') {
            await renameChatSession(item.dataset.sessionId, session?.title || item.dataset.title || '');
        } else if (action === 'delete') {
            await deleteChatSessionNow(item.dataset.sessionId);
        }
    });
    window.setTimeout(() => {
        document.addEventListener('click', closeChatSessionMenu, { once: true });
    }, 0);
}

async function renameChatSession(sessionId, currentTitle = '') {
    const nextTitle = window.prompt(ui('Nhap ten moi cho doan chat', 'Enter a new chat name'), currentTitle || ui('Chat', 'Chat'));
    if (nextTitle === null) return;
    const title = nextTitle.trim();
    if (!title) return;
    try {
        const response = await apiFetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'rename_failed');
        if (sessionId === activeChatSessionId) {
            activeChatSessionTitle = title;
            persistChatSessionTitle();
            updateChatSessionTitle();
        }
        await loadChatSessions();
        showNotification(ui('Da doi ten doan chat', 'Chat renamed'), 'success');
    } catch (error) {
        showNotification(ui('Khong the doi ten doan chat', 'Unable to rename chat'), 'error');
    }
}

async function deleteChatSessionNow(sessionId) {
    if (!sessionId) return;
    if (!window.confirm(ui('Xoa doan chat nay ngay bay gio?', 'Delete this chat now?'))) return;
    try {
        const response = await apiFetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'delete_failed');
        if (sessionId === activeChatSessionId) {
            activeChatSessionId = createChatSessionId();
            activeChatSessionTitle = '';
            persistChatSessionId();
            persistChatSessionTitle();
            if (chatMessages) chatMessages.innerHTML = '';
            updateChatSessionTitle();
        }
        await loadChatSessions();
        showNotification(ui('Da xoa doan chat', 'Chat deleted'), 'success');
    } catch (error) {
        showNotification(ui('Khong the xoa doan chat', 'Unable to delete chat'), 'error');
    }
}

async function loadChatSessions() {
    try {
        const response = await apiFetch(`${API_BASE}/chat/sessions?limit=40`);
        const data = await response.json();
        if (!data.success) return;
        const sessions = Array.isArray(data.sessions) ? data.sessions : [];
        const active = sessions.find((session) => session.id === activeChatSessionId);
        if (active) {
            activeChatSessionTitle = active.title || '';
            persistChatSessionTitle();
            if (chatRetentionSelect) chatRetentionSelect.value = String(active.retention_days || 90);
        }
        renderChatSessions(sessions);
    } catch (error) {
        console.error('Error loading chat sessions:', error);
    }
}

async function openChatSession(sessionId, title = '', retentionDays = 90) {
    if (!sessionId) return;
    activeChatSessionId = sessionId;
    activeChatSessionTitle = title || ui('Chat hiện tại', 'Current chat');
    persistChatSessionId();
    persistChatSessionTitle();
    if (chatRetentionSelect) chatRetentionSelect.value = String(retentionDays || 90);
    const chatButton = document.querySelector('.sidebar-nav [data-page="chat"]');
    if (currentPage !== 'chat' && chatButton) {
        await handlePageChange(chatButton);
    }
    await loadChatHistory();
    updateChatSessionTitle();
    if (userInput) userInput.focus();
}

async function updateChatRetention() {
    if (!chatRetentionSelect || !activeChatSessionId) return;
    try {
        await apiFetch(`${API_BASE}/chat/sessions/${encodeURIComponent(activeChatSessionId)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ retention_days: Number(chatRetentionSelect.value || 90) })
        });
        await loadChatSessions();
        showNotification(ui('Đã cập nhật thời hạn lưu chat', 'Chat retention updated'), 'success');
    } catch (error) {
        showNotification(ui('Không thể cập nhật thời hạn lưu chat', 'Unable to update chat retention'), 'error');
    }
}

async function startNewChat() {
    activeChatSessionId = createChatSessionId();
    activeChatSessionTitle = '';
    persistChatSessionId();
    persistChatSessionTitle();
    if (chatRetentionSelect) chatRetentionSelect.value = '90';
    const chatButton = document.querySelector('.sidebar-nav [data-page="chat"]');
    if (currentPage !== 'chat' && chatButton) {
        await handlePageChange(chatButton);
    }
    if (chatMessages) chatMessages.innerHTML = '';
    if (userInput) {
        userInput.value = '';
        userInput.focus();
    }
    document.querySelector('.sidebar')?.classList.remove('open');
    document.getElementById('sidebarOverlay')?.classList.remove('show');
    const menuToggle = document.getElementById('menuToggle');
    menuToggle?.setAttribute('aria-expanded', 'false');
    updateChatSessionTitle();
    await loadChatSessions();
    showNotification(ui('Đã bắt đầu chat mới', 'Started a new chat'), 'success');
}

async function clearConversation() {
    if (!confirm(ui('Bạn có chắc chắn muốn làm mới cuộc trò chuyện?', 'Are you sure you want to clear this conversation?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/chat/clear`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: activeChatSessionId })
        });
        
        const data = await response.json();
        if (data.success) {
            chatMessages.innerHTML = '';
            showNotification(ui('✅ Lịch sử đã bị xóa', '✅ History cleared'), 'success');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}
