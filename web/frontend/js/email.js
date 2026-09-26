// Bob's "new mail" popup: a distinct toast variant so it reads as the
// assistant proactively flagging something, not just a generic status message.
function showNewMailPopup(mailInfo) {
    const sender = String(mailInfo.latest_sender || '').split('<')[0].trim();
    const subject = String(mailInfo.latest_subject || '').trim();
    const detail = sender || subject
        ? `${sender || ui('người gửi ẩn danh', 'an unknown sender')}${subject ? ` — "${subject}"` : ''}`
        : '';
    const hasMeetingSuggestion = !!mailInfo.meeting_suggestion;
    const message = hasMeetingSuggestion
        ? ui(`📅 Bob phát hiện một lịch hẹn trong email mới${detail ? ` từ ${detail}` : ''}`, `📅 Bob found an appointment in new mail${detail ? ` from ${detail}` : ''}`)
        : detail
        ? ui(`📬 Bob vừa phát hiện email mới từ ${detail}`, `📬 Bob just spotted new mail from ${detail}`)
        : ui('📬 Bob vừa phát hiện bạn có email mới', '📬 Bob just spotted new mail for you');

    showNotification(message, 'mail', {
        autoDismissMs: 8000,
        actionLabel: hasMeetingSuggestion ? ui('Xem gợi ý', 'View suggestion') : ui('Xem email', 'View email'),
        onAction: () => {
            const target = hasMeetingSuggestion ? 'schedule' : 'emails';
            const navBtn = document.querySelector(`[data-page="${target}"]`);
            if (navBtn) handlePageChange(navBtn);
            if (hasMeetingSuggestion) loadMeetingSuggestions().catch(() => {});
            else refreshEmailsFromGmail().catch(() => {});
        }
    });
}

// Background poll so Bob can flag new mail without the user opening the
// Email tab. Uses plain fetch (not apiFetch) so a 401 here -- expected for
// anyone who hasn't connected Gmail yet -- never triggers the session-expired
// auth gate; it should just silently retry on the next tick.
async function checkForNewMail() {
    try {
        const response = await fetch(`${API_BASE}/email/new-mail-check`, { credentials: 'include' });
        if (!response.ok) return;
        const data = await response.json();
        if (!data || !data.success || !data.latest_id) return;

        const isFirstCheck = lastSeenMailId === null;
        if (data.latest_id === lastSeenMailId) return;

        lastSeenMailId = data.latest_id;
        localStorage.setItem('flowmate-last-mail-id', lastSeenMailId);

        if (!isFirstCheck && currentPage === 'overview') {
            // The Overview endpoint returns the cached snapshot immediately,
            // then compares Gmail IDs and refreshes AI output only if needed.
            loadOverviewPage({ background: true })
                .catch(error => console.warn('Overview new-mail refresh failed:', error));
        }
        if (!isFirstCheck && currentPage === 'emails') {
            // The lightweight watcher saw a Gmail ID that cannot be present in
            // the current list cache. Refresh the visible inbox immediately
            // instead of showing a new-mail toast above stale rows.
            loadEmails(currentEmailPage || 1, { fresh: true })
                .then(() => loadMeetingSuggestions())
                .catch(error => console.warn('Visible inbox new-mail refresh failed:', error));
        }

        if (!isFirstCheck && data.unread_count > 0) {
            showNewMailPopup(data);
            if (data.meeting_suggestion) {
                loadMeetingSuggestions().catch(() => {});
            }
        }
    } catch (err) {
        console.warn('New mail check failed:', err);
    }
}

function startNewMailWatcher() {
    if (newMailPollTimer) return;
    checkForNewMail();
    newMailPollTimer = window.setInterval(checkForNewMail, NEW_MAIL_POLL_INTERVAL_MS);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') checkForNewMail();
    });
}

// Client-side email cache for fallback pagination
let emailsCache = [];
const notifiedMeetingSuggestionIds = new Set();
function loadAgentNotifiedMeetingSuggestionIds() {
    try {
        const parsed = JSON.parse(localStorage.getItem('flowmate-agent-meeting-suggestions') || '[]');
        return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
        return [];
    }
}
const agentNotifiedMeetingSuggestionIds = new Set(loadAgentNotifiedMeetingSuggestionIds());
let lastMeetingSuggestionScanAt = 0;
let meetingSuggestionRefreshTimer = null;


async function refreshEmailsFromGmail(page = 1) {
    await apiFetch(`${API_BASE}/email/cache/clear`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    });
    await loadEmails(page, { fresh: true });
    await scanMeetingSuggestions(true);
    await loadMeetingSuggestions();
}

async function loadEmails(page = 1, options = {}) {
    const emailsList = document.getElementById('emailsList');
    if (!emailsList) {
        console.error('❌ emailsList element not found');
        return;
    }
    
    if (!options.silent) {
        emailsList.innerHTML = `<p style="padding: 20px; text-align: center; color: #666;">${ui('⏳ Đang tải email...', '⏳ Loading email...')}</p>`;
    }
    const selectedFilter = emailFilterSelect ? emailFilterSelect.value : 'all';
    const includeReadCheckbox = document.getElementById('includeReadCheckbox');
    const includeRead = includeReadCheckbox ? includeReadCheckbox.checked : true;
    currentEmailPage = page;

    if (!options.silent) await refreshAuthButtons();
    let requestController;
    try {
        const search = emailSearchInput ? emailSearchInput.value.trim() : '';
        const params = new URLSearchParams({
            max_results: '20',
            page: String(page),
            filter: selectedFilter,
            include_read: String(includeRead),
            search
        });
        if (currentSmartBucketFilter) params.set('smart_bucket', currentSmartBucketFilter);
        if (options.fresh) params.set('fresh', 'true');
        if (options.cacheOnly) params.set('cache_only', 'true');
        const url = `${API_BASE}/email/get-unread?${params.toString()}`;
        console.log(`📧 Loading emails: ${url}`);
        console.log(`🔍 Filter: ${selectedFilter}, Page: ${page}, Include read: ${includeRead}`);
        
        if (emailLoadController) emailLoadController.abort();
        requestController = new AbortController();
        emailLoadController = requestController;
        const response = await apiFetch(url, { signal: requestController.signal });
        console.log(`📡 Response status: ${response.status}`);
        
        if (!response.ok) {
            let errorData = {};
            try {
                errorData = await response.json();
            } catch {
                errorData = {};
            }
            const detail = errorData.error || errorData.message || response.statusText || ui('Không rõ lỗi', 'Unknown error');
            const type = errorData.error_type ? ` (${errorData.error_type})` : '';
            throw new Error(`HTTP ${response.status}: ${detail}${type}`);
        }
        
        const data = await response.json();
        console.log('📦 Email data received:', data);
        
        if (data && data.error === 'not_authenticated') {
            emailsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #FFF3E0; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #E65100; margin-bottom: 15px;">${ui('⚠️ Chưa đăng nhập Gmail', '⚠️ Gmail not connected')}</p>
                    <button id="loginPromptBtn" class="btn-primary">${ui('Đăng nhập Gmail', 'Sign in to Gmail')}</button>
                </div>
            `;
            document.getElementById('loginPromptBtn').addEventListener('click', gmailLogin);
            return;
        }

        if (!data.success) {
            console.error('❌ API returned error:', data.error);
            emailsList.innerHTML = `
                <div style="padding: 20px; background: #FFEBEE; border-radius: 8px; margin: 20px;">
                    <p style="color: #C62828; font-weight: bold;">❌ Lỗi: ${escapeHtml(data.error || 'Unknown error')}</p>
                        <button onclick="loadEmails(1, { cacheOnly: true })" class="btn-primary" style="margin-top: 10px;">${ui('🔄 Thử lại', '🔄 Try again')}</button>
                </div>
            `;
            return;
        }

        notifyMeetingSuggestions(data.meeting_suggestions || []);
        
        if ((data.needs_refresh || data.cache_miss) && (!data.emails || data.emails.length === 0)) {
            if (!options.fresh && !options.autoRefreshAttempted) {
                if (options.silent) {
                    await loadEmails(page, {
                        fresh: true,
                        silent: true,
                        autoRefreshAttempted: true
                    });
                    return;
                }
                emailsList.innerHTML = `
                    <div style="padding: 30px; text-align: center; background: #EEF2FF; border-radius: 8px; margin: 20px;">
                        <p style="font-size: 16px; color: #312E81; margin-bottom: 10px;">${ui('Đang quét Gmail lần đầu...', 'Scanning Gmail for the first time...')}</p>
                        <p style="color: #666; font-size: 14px; margin-bottom: 0;">
                            ${ui('Cache chưa có dữ liệu nên FlowMate đang tự làm mới. Bạn không cần bấm nút làm mới.', 'No cached email was found, so FlowMate is refreshing automatically. No manual refresh needed.')}
                        </p>
                    </div>
                `;
                await loadEmails(page, { fresh: true, autoRefreshAttempted: true });
                scanMeetingSuggestions(true).catch(err => console.warn('Auto meeting scan failed:', err));
                return;
            }

            emailsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #EEF2FF; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #312E81; margin-bottom: 10px;">${ui('Chưa có email trong bộ nhớ đệm', 'No cached email yet')}</p>
                    <p style="color: #666; font-size: 14px; margin-bottom: 15px;">
                        ${ui('FlowMate đã thử tự quét Gmail nhưng chưa lấy được dữ liệu. Bạn có thể thử làm mới lại.', 'FlowMate tried scanning Gmail automatically but could not load data yet. You can try refreshing again.')}
                    </p>
                    <button onclick="refreshEmailsFromGmail(1)" class="btn-primary">${ui('Làm mới Gmail', 'Refresh Gmail')}</button>
                </div>
            `;
            return;
        }

        if (!data.emails || data.emails.length === 0) {
            console.warn('⚠️ No emails found');
            emailsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #E8F5E9; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #2E7D32; margin-bottom: 10px;">${ui('📭 Không tìm thấy email', '📭 No email found')}</p>
                    <p style="color: #666; font-size: 14px; margin-bottom: 15px;">
                        ${ui('Bộ lọc hiện tại', 'Current filter')}: <strong>${t(`filter.${selectedFilter}`)}</strong><br>
                        ${data.debug ? `${ui('Tổng email quét', 'Email scanned')}: ${data.debug.raw_email_count || 0}` : ''}
                    </p>
                    <div style="display: flex; gap: 10px; justify-content: center;">
                        <button onclick="emailFilterSelect.value='all'; updateEmailFilterUI(); loadEmails(1, { cacheOnly: true });" class="btn-primary">${ui('🔍 Xem tất cả', '🔍 View all')}</button>
                        <button onclick="refreshEmailsFromGmail(1)" class="btn-secondary">${ui('🔄 Làm mới', '🔄 Refresh')}</button>
                    </div>
                </div>
            `;
            return;
        }
        
        console.log(`✅ Loaded ${data.emails.length} emails`);

        emailsList.innerHTML = '';

        // If API provides pagination info, use server-side pages.
        if (data.pagination && data.pagination.total_pages > 0) {
            data.emails.forEach(email => {
                renderEnhancedEmailItem(email, emailsList);
            });

            const { current_page, total_pages } = data.pagination;
            if (total_pages > 1) {
                const paginationDiv = document.createElement('div');
                paginationDiv.style.cssText = 'padding: 16px; display: flex; justify-content: center; gap: 8px; margin-top: 16px;';
                const prevBtn = document.createElement('button');
                prevBtn.textContent = ui('◀ Trang trước', '◀ Previous');
                prevBtn.disabled = current_page === 1;
                prevBtn.addEventListener('click', () => loadEmails(current_page - 1));
                paginationDiv.appendChild(prevBtn);

                const pageInfo = document.createElement('span');
                pageInfo.textContent = ui(`Trang ${current_page} / ${total_pages}`, `Page ${current_page} / ${total_pages}`);
                pageInfo.style.cssText = 'font-weight: bold; padding: 0 16px;';
                paginationDiv.appendChild(pageInfo);

                const nextBtn = document.createElement('button');
                nextBtn.textContent = ui('Trang sau ▶', 'Next ▶');
                nextBtn.disabled = current_page === total_pages;
                nextBtn.addEventListener('click', () => loadEmails(current_page + 1));
                paginationDiv.appendChild(nextBtn);

                emailsList.appendChild(paginationDiv);
            }
        } else {
            // Client-side pagination fallback
            emailsCache = data.emails || [];
            const pageSize = 12;
            const total_pages = Math.max(1, Math.ceil(emailsCache.length / pageSize));
            const current_page = Math.max(1, Math.min(page, total_pages));
            const startIdx = (current_page - 1) * pageSize;
            const pageItems = emailsCache.slice(startIdx, startIdx + pageSize);

            pageItems.forEach(email => {
                renderEnhancedEmailItem(email, emailsList);
            });

            if (total_pages > 1) {
                const paginationDiv = document.createElement('div');
                paginationDiv.style.cssText = 'padding: 16px; display: flex; justify-content: center; gap: 8px; margin-top: 16px;';
                const prevBtn = document.createElement('button');
                prevBtn.textContent = ui('◀ Trang trước', '◀ Previous');
                prevBtn.disabled = current_page === 1;
                prevBtn.addEventListener('click', () => loadEmails(current_page - 1));
                paginationDiv.appendChild(prevBtn);

                const pageInfo = document.createElement('span');
                pageInfo.textContent = ui(`Trang ${current_page} / ${total_pages}`, `Page ${current_page} / ${total_pages}`);
                pageInfo.style.cssText = 'font-weight: bold; padding: 0 16px;';
                paginationDiv.appendChild(pageInfo);

                const nextBtn = document.createElement('button');
                nextBtn.textContent = ui('Trang sau ▶', 'Next ▶');
                nextBtn.disabled = current_page === total_pages;
                nextBtn.addEventListener('click', () => loadEmails(current_page + 1));
                paginationDiv.appendChild(nextBtn);

                emailsList.appendChild(paginationDiv);
            }
        }
        
    } catch (error) {
        if (error && error.name === 'AbortError') return;
        console.error('Email load error:', error);
        if (options.silent) {
            showNotification(
                `${ui('Không thể cập nhật danh sách email', 'Could not refresh the email list')}: ${error.message}`,
                'error'
            );
            return;
        }
        emailsList.innerHTML = `<p>${ui('❌ Lỗi', '❌ Error')}: ${escapeHtml(error.message)}</p>`;
    } finally {
        if (emailLoadController === requestController) {
            emailLoadController = undefined;
        }
    }
}

function updateEmailReadAppearance(emailDiv, email) {
    emailDiv.classList.toggle('is-unread', !!email.is_unread);
    emailDiv.classList.toggle('is-read', !email.is_unread);
    const state = emailDiv.querySelector('.email-read-state');
    if (state) state.textContent = email.is_unread ? ui('Chưa đọc', 'Unread') : ui('Đã đọc', 'Read');
    const button = emailDiv.querySelector('.email-read-toggle-btn');
    if (button) button.textContent = email.is_unread
        ? ui('Đánh dấu đã đọc', 'Mark as read')
        : ui('Đánh dấu chưa đọc', 'Mark as unread');
}

async function toggleEnhancedEmailReadStatus(email, emailDiv) {
    const wasUnread = !!email.is_unread;
    const endpoint = wasUnread ? 'mark-as-read' : 'mark-as-unread';
    try {
        const response = await apiFetch(`${API_BASE}/email/${endpoint}/${email.id}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || ui('Không thể cập nhật email', 'Unable to update email'));
        email.is_unread = !wasUnread;
        updateEmailReadAppearance(emailDiv, email);
        showNotification(ui(
            ui(`Đã đánh dấu ${wasUnread ? 'đã đọc' : 'chưa đọc'}`, `Marked as ${wasUnread ? 'read' : 'unread'}`),
            `Marked as ${wasUnread ? 'read' : 'unread'}`
        ), 'success');
    } catch (error) {
        showNotification(`${ui('Lỗi cập nhật email', 'Email update error')}: ${error.message}`, 'error');
    }
}

async function summarizeEnhancedEmail(email, emailDiv, button) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = ui('AI đang tóm tắt...', 'AI is summarizing...');
    try {
        const response = await apiFetch(`${API_BASE}/email/summary/${email.id}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || ui('Không thể tóm tắt email', 'Unable to summarize email'));
        email.summary = data.summary;
        let summary = emailDiv.querySelector('.email-item-summary');
        if (!summary) {
            summary = document.createElement('div');
            summary.className = 'email-item-summary';
            emailDiv.querySelector('.email-item-snippet')?.before(summary);
        }
        summary.textContent = data.summary;
        button.textContent = ui('Xem tóm tắt AI', 'View AI summary');
        showNotification(
            data.cache_hit ? ui('Đã tải tóm tắt AI', 'AI summary loaded') : ui('Đã tạo tóm tắt AI', 'AI summary created'),
            'success'
        );
    } catch (error) {
        button.textContent = originalText;
        showNotification(`${ui('Lỗi tóm tắt', 'Summary error')}: ${error.message}`, 'error');
    } finally {
        button.disabled = false;
    }
}

function formatEmailListDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString(currentLanguage === 'en' ? 'en-US' : 'vi-VN', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function renderEnhancedEmailItem(email, container) {
    const emailDiv = document.createElement('div');
    emailDiv.className = `email-item ${email.is_unread ? 'is-unread' : 'is-read'}`;
    const tagColors = {
        education: '#4CAF50',
        business: '#2196F3',
        ads: '#FF9800',
        notification: '#9C27B0',
        personal: '#F44336',
        social: '#00BCD4',
        other: '#757575'
    };
    const tagColor = tagColors[email.tag] || tagColors.other;
    const tagHTML = email.tag
        ? `<span style="display:inline-block;background:${tagColor};color:white;padding:2px 8px;border-radius:12px;font-size:11px;margin-right:6px;font-weight:bold;">${escapeHtml(email.tag)}</span>`
        : '';
    const smartBucketLabels = {
        action_required: ui('Cần xử lý', 'Action required'),
        waiting: ui('Đang chờ', 'Waiting'),
        fyi: ui('Tham khảo', 'FYI'),
        low_priority: ui('Ít quan trọng', 'Low priority'),
    };
    const smartBucketHTML = email.smart_bucket
        ? `<span class="email-smart-badge email-smart-badge-${escapeHtml(email.smart_bucket)}">${escapeHtml(smartBucketLabels[email.smart_bucket] || email.smart_bucket)}</span>`
        : '';
    const normalizedSummary = String(email.summary || '').replace(/\s+/g, ' ').trim();
    const normalizedSnippet = String(email.snippet || '').replace(/\s+/g, ' ').trim();
    const summaryHTML = normalizedSummary
        ? `<div class="email-item-summary">${escapeHtml(email.summary)}</div>`
        : '';
    const snippetHTML = normalizedSnippet && normalizedSnippet !== normalizedSummary
        ? `<div class="email-item-snippet">${escapeHtml(email.snippet)}</div>`
        : '';
    const dateText = formatEmailListDate(email.date);
    const dateHTML = dateText ? `<span class="email-item-date">${escapeHtml(dateText)}</span>` : '';

    emailDiv.innerHTML = `
        <div class="email-item-header">
            <span class="email-item-subject">
                <span class="email-read-state">${email.is_unread ? ui('Chưa đọc', 'Unread') : ui('Đã đọc', 'Read')}</span>
                ${tagHTML}${smartBucketHTML}${escapeHtml(email.subject || ui('(Không có tiêu đề)', '(No subject)'))}
            </span>
            ${dateHTML}
        </div>
        <div class="email-item-sender">${ui('Từ', 'From')}: ${escapeHtml(email.sender || ui('Không xác định', 'Unknown'))}</div>
        ${summaryHTML}
        ${snippetHTML}
        <div class="email-item-actions">
            <button class="email-view-detail-btn btn-secondary">${ui('Xem chi tiết', 'View details')}</button>
            <button class="email-summary-btn">${email.summary ? ui('Xem tóm tắt AI', 'View AI summary') : ui('Tóm tắt bằng AI', 'Summarize with AI')}</button>
            <button class="email-read-toggle-btn btn-secondary">${email.is_unread ? ui('Đánh dấu đã đọc', 'Mark as read') : ui('Đánh dấu chưa đọc', 'Mark as unread')}</button>
            ${orgWorkspaces.some((w) => w.type === 'business') && canShowBusinessFeatures() ? `<button class="email-share-btn btn-secondary">${ui('Chia sẻ', 'Share')}</button>` : ''}
        </div>
    `;

    emailDiv.querySelector('.email-view-detail-btn').addEventListener('click', (event) => {
        event.stopPropagation();
        showFormattedEmailDetail(email);
    });
    emailDiv.querySelector('.email-summary-btn').addEventListener('click', async (event) => {
        event.stopPropagation();
        if (email.summary) {
            showFormattedEmailDetail(email);
            return;
        }
        await summarizeEnhancedEmail(email, emailDiv, event.currentTarget);
    });
    emailDiv.querySelector('.email-read-toggle-btn').addEventListener('click', async (event) => {
        event.stopPropagation();
        await toggleEnhancedEmailReadStatus(email, emailDiv);
    });
    emailDiv.querySelector('.email-share-btn')?.addEventListener('click', (event) => {
        event.stopPropagation();
        openShareArtifactModal(email);
    });
    emailDiv.addEventListener('click', (event) => {
        if (!event.target.closest('button')) showFormattedEmailDetail(email);
    });
    container.appendChild(emailDiv);
}

function buildEmailDetailMarkup(email, bodyHtml, isLoading = false) {
    const tagColors = {
        education: '#4CAF50',
        business: '#2196F3',
        ads: '#FF9800',
        notification: '#9C27B0',
        personal: '#F44336',
        social: '#00BCD4',
        other: '#757575'
    };
    const tagColor = tagColors[email.tag] || tagColors.other;
    const tagHTML = email.tag
        ? `<span class="email-detail-tag" style="--email-tag-color: ${tagColor}">${escapeHtml(email.tag.toUpperCase())}</span>`
        : '';
    const summaryHTML = email.summary
        ? `<div class="email-detail-summary" style="--email-tag-color: ${tagColor}">
                <strong>${ui('Tóm tắt', 'Summary')}</strong>
                <div>${formatEmailText(email.summary)}</div>
           </div>`
        : '';
    const attachments = Array.isArray(email.attachments) ? email.attachments : [];
    const previewTypes = new Set([
        'application/pdf',
        'image/gif',
        'image/jpeg',
        'image/png',
        'image/webp',
        'text/plain'
    ]);
    const attachmentsHTML = attachments.length
        ? `<section class="email-attachments" aria-label="${ui('File đính kèm', 'Attachments')}">
                <div class="email-attachments-heading">
                    <strong>${ui('File đính kèm', 'Attachments')}</strong>
                    <span>${attachments.length} ${ui('file', 'file(s)')}</span>
                </div>
                <div class="email-attachment-list">
                    ${attachments.map((attachment) => {
                        const mimeType = String(attachment.mime_type || 'application/octet-stream').toLowerCase();
                        const baseUrl = `${API_BASE}/email/attachment/${encodeURIComponent(email.id)}/${encodeURIComponent(attachment.id)}`;
                        const previewButton = previewTypes.has(mimeType)
                            ? `<a class="email-attachment-action secondary" href="${baseUrl}?preview=1" target="_blank" rel="noopener">${ui('Xem', 'Preview')}</a>`
                            : '';
                        return `<article class="email-attachment-item">
                            <div class="email-attachment-icon" aria-hidden="true">FILE</div>
                            <div class="email-attachment-info">
                                <strong title="${escapeHtml(attachment.filename || ui('File đính kèm', 'Attachment'))}">${escapeHtml(attachment.filename || ui('File đính kèm', 'Attachment'))}</strong>
                                <span>${escapeHtml(mimeType)} · ${formatFileSize(attachment.size)}</span>
                            </div>
                            <div class="email-attachment-actions">
                                ${previewButton}
                                <a class="email-attachment-action" href="${baseUrl}" download>${ui('Tải xuống', 'Download')}</a>
                            </div>
                        </article>`;
                    }).join('')}
                </div>
           </section>`
        : '';

    return `
        <div class="email-detail-header">
            <div class="email-detail-heading">
                <div class="email-detail-label">${ui('Chi tiết email', 'Email details')}</div>
                <h2 id="emailDetailTitle" class="email-detail-subject">${escapeHtml(email.subject || ui('(Không có tiêu đề)', '(No subject)'))}</h2>
            </div>
            ${tagHTML}
        </div>
        ${summaryHTML}
        <div class="email-detail-meta">
            <div><span>${ui('Từ', 'From')}</span><strong>${escapeHtml(email.sender || ui('Không xác định', 'Unknown'))}</strong></div>
            <div><span>${ui('Ngày', 'Date')}</span><strong>${escapeHtml(email.date || ui('Không xác định', 'Unknown'))}</strong></div>
        </div>
        <div class="email-detail-body${isLoading ? ' email-detail-loading' : ''}">${bodyHtml}</div>
        ${isLoading ? '' : attachmentsHTML}
    `;
}

function formatFileSize(value) {
    const bytes = Number(value) || 0;
    if (bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB'];
    let size = bytes / 1024;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }
    return `${size >= 10 ? size.toFixed(0) : size.toFixed(1)} ${units[unitIndex]}`;
}

async function showFormattedEmailDetail(email) {
    const emailDetail = document.getElementById('emailDetail');
    if (!emailDetail || !emailDetailModal) return;

    currentDetailEmail = email;
    emailDetail.innerHTML = buildEmailDetailMarkup(email, ui('Đang tải nội dung...', 'Loading content...'), true);
    emailDetailModal.classList.add('show');
    emailDetailModal.querySelector('.email-detail-close')?.focus();

    if (!email.body || !Array.isArray(email.attachments)) {
        try {
            const response = await apiFetch(`${API_BASE}/email/get-email-body/${email.id}`);
            const data = await response.json();
            email.body = data.success ? data.body : ui('Không thể tải nội dung.', 'Unable to load content.');
            email.attachments = data.success && Array.isArray(data.email?.attachments)
                ? data.email.attachments
                : [];
        } catch (error) {
            email.body = `Lỗi: ${error.message}`;
            email.attachments = [];
        }
    }

    if (currentDetailEmail !== email || !emailDetailModal.classList.contains('show')) return;
    emailDetail.innerHTML = buildEmailDetailMarkup(
        email,
        formatEmailText(email.body || ui('Email không có nội dung.', 'This email has no content.'))
    );
}

// Note: Preview pane removed — email items open the modal showing full content.

function notifyMeetingSuggestions(suggestions) {
    const fresh = (suggestions || []).filter(item => {
        const id = String(item.id || '');
        if (!id || notifiedMeetingSuggestionIds.has(id)) return false;
        notifiedMeetingSuggestionIds.add(id);
        return true;
    });
    if (!fresh.length) return;

    showNotification(
        ui(
            `📅 Phát hiện ${fresh.length} email liên quan đến cuộc họp. Xem gợi ý trong tab Lịch.`,
            `📅 Found ${fresh.length} meeting-related email. Review suggestions in Calendar.`
        ),
        'info'
    );
    notifyMeetingSuggestionsInChat(fresh);
}

function rememberAgentMeetingSuggestions(items) {
    items.forEach((item) => agentNotifiedMeetingSuggestionIds.add(String(item.id)));
    const compact = Array.from(agentNotifiedMeetingSuggestionIds).slice(-200);
    localStorage.setItem('flowmate-agent-meeting-suggestions', JSON.stringify(compact));
}

function notifyMeetingSuggestionsInChat(suggestions = []) {
    if (currentPage === 'schedule' || !chatMessages) return;
    const fresh = suggestions.filter((item) => {
        const id = String(item.id || '');
        return id && !agentNotifiedMeetingSuggestionIds.has(id);
    });
    if (!fresh.length) return;

    rememberAgentMeetingSuggestions(fresh);
    const first = fresh[0] || {};
    const title = first.title || first.subject || ui('một email liên quan đến cuộc họp', 'a meeting-related email');
    const extra = fresh.length > 1
        ? ui(` và ${fresh.length - 1} email khác`, ` and ${fresh.length - 1} more email${fresh.length > 2 ? 's' : ''}`)
        : '';
    const message = ui(
        `AI Agent phát hiện ${fresh.length} email có thể liên quan đến lịch họp: "${title}"${extra}. Mình đã để gợi ý trong tab Lịch để bạn tạo lịch hoặc bỏ qua.`,
        `AI Agent found ${fresh.length} email${fresh.length > 1 ? 's' : ''} that may relate to meetings: "${title}"${extra}. I put the suggestion in Calendar so you can create or dismiss it.`
    );
    addMessage(message, 'assistant', '<span class="provider-badge workspace-source-badge">AI Agent</span>');
}

async function scanMeetingSuggestions(force = false) {
    const now = Date.now();
    if (!force && now - lastMeetingSuggestionScanAt < 5 * 60 * 1000) return [];
    lastMeetingSuggestionScanAt = now;

    const response = await apiFetch(`${API_BASE}/email/meeting-suggestions/scan`, {
        method: 'POST'
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        if (data.error === 'not_authenticated') return [];
        throw new Error(data.error || ui('Không thể quét email', 'Unable to scan email'));
    }
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    notifyMeetingSuggestions(suggestions);
    return suggestions;
}

function scheduleMeetingSuggestionRefresh(options = {}) {
    if (meetingSuggestionRefreshTimer) return;
    const scan = !!options.scan;
    const delay = Number.isFinite(options.delay) ? options.delay : 1500;
    meetingSuggestionRefreshTimer = window.setTimeout(() => {
        meetingSuggestionRefreshTimer = null;
        const loadExisting = () => loadMeetingSuggestions()
            .catch(error => console.warn('Meeting suggestion load error:', error));
        if (!scan) {
            loadExisting();
            return;
        }
        loadExisting()
            .finally(() => scanMeetingSuggestions(true)
                .then(() => loadMeetingSuggestions())
                .catch(error => console.warn('Meeting suggestion scan error:', error)));
    }, delay);
}

async function updateMeetingSuggestionStatus(suggestionId, status, scheduleId = null) {
    const response = await apiFetch(`${API_BASE}/email/meeting-suggestions/${suggestionId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, schedule_id: scheduleId })
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.error || ui('Không thể cập nhật gợi ý', 'Unable to update suggestion'));
    }
}

function openMeetingSuggestion(suggestion) {
    const form = document.getElementById('scheduleForm');
    if (!form) return;

    document.getElementById('scheduleTitle').value = suggestion.title || suggestion.subject || ui('Lịch hẹn từ email', 'Appointment from email');
    document.getElementById('scheduleDesc').value = suggestion.description || suggestion.snippet || '';
    document.getElementById('scheduleStartTime').value = toDatetimeLocal(suggestion.start_time);
    const endInput = document.getElementById('scheduleEndTime');
    if (endInput) endInput.value = toDatetimeLocal(suggestion.end_time);
    const durationInput = document.getElementById('scheduleDuration');
    if (durationInput) {
        durationInput.value = getDurationMinutes(suggestion.start_time, suggestion.end_time) || 60;
    }
    updateScheduleEndFromDuration();
    updateDateTimePreview('scheduleStartTime');
    updateDateTimePreview('scheduleEndTime');
    const locationInput = document.getElementById('scheduleLocation');
    if (locationInput) locationInput.value = suggestion.location || '';
    document.getElementById('scheduleAttendees').value = suggestion.attendees || '';
    form.dataset.meetingSuggestionId = suggestion.id;
    openNewScheduleModal(true);

    if (!suggestion.start_time) {
        showNotification(
            ui('Email chưa có ngày giờ rõ ràng. Vui lòng chọn thời gian trước khi tạo lịch.', 'The email has no clear date and time. Select one before creating the event.'),
            'info'
        );
    }
}

async function loadMeetingSuggestions() {
    const section = document.getElementById('emailMeetingSuggestions');
    const list = document.getElementById('meetingSuggestionsList');
    const count = document.getElementById('meetingSuggestionCount');
    if (!section || !list || !count) return;

    const response = await apiFetch(`${API_BASE}/email/meeting-suggestions`);
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.error || ui('Không thể tải gợi ý lịch', 'Unable to load calendar suggestions'));
    }

    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    const emailBanner = document.getElementById('emailMeetingSuggestionBanner');
    const emailBannerText = document.getElementById('emailMeetingBannerText');
    const emailBannerButton = document.getElementById('openEmailMeetingSuggestionsBtn');
    if (emailBanner) emailBanner.hidden = suggestions.length === 0;
    if (emailBannerText && suggestions.length) {
        emailBannerText.textContent = ui(
            `${suggestions.length} email có thể tạo thành lịch. Bob đang chờ bạn xác nhận.`,
            `${suggestions.length} email may become calendar events. Bob is waiting for confirmation.`
        );
    }
    if (emailBannerButton) {
        emailBannerButton.onclick = async () => {
            const scheduleNav = document.querySelector('[data-page="schedule"]');
            if (scheduleNav) await handlePageChange(scheduleNav);
            document.getElementById('emailMeetingSuggestions')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        };
    }
    section.hidden = suggestions.length === 0;
    count.textContent = String(suggestions.length);
    list.innerHTML = '';
    notifyMeetingSuggestions(suggestions);

    suggestions.forEach(suggestion => {
        const card = document.createElement('article');
        card.className = 'meeting-suggestion-card';
        const start = suggestion.start_time
            ? formatScheduleRange(suggestion.start_time, suggestion.end_time).full
            : ui('Chưa xác định thời gian', 'Time not detected');
        card.innerHTML = `
            <div class="meeting-suggestion-main">
                <div class="meeting-suggestion-title">${escapeHtml(suggestion.title || suggestion.subject || ui('Lịch hẹn từ email', 'Appointment from email'))}</div>
                <div class="meeting-suggestion-source">${ui('Từ', 'From')}: ${escapeHtml(suggestion.sender || ui('Không xác định', 'Unknown'))}</div>
                <div class="meeting-suggestion-time">${escapeHtml(start)}</div>
                ${suggestion.snippet ? `<p>${escapeHtml(suggestion.snippet)}</p>` : ''}
            </div>
            <div class="meeting-suggestion-actions">
                <button type="button" class="btn-primary meeting-suggestion-create">${ui('Tạo lịch', 'Create event')}</button>
                <button type="button" class="btn-secondary meeting-suggestion-dismiss">${ui('Bỏ qua', 'Dismiss')}</button>
            </div>
        `;
        card.querySelector('.meeting-suggestion-create').addEventListener('click', () => {
            openMeetingSuggestion(suggestion);
        });
        card.querySelector('.meeting-suggestion-dismiss').addEventListener('click', async () => {
            try {
                await updateMeetingSuggestionStatus(suggestion.id, 'dismissed');
                await loadMeetingSuggestions();
                showNotification(ui('Đã bỏ qua gợi ý lịch hẹn', 'Appointment suggestion dismissed'), 'info');
            } catch (error) {
                showNotification(`${ui('Lỗi', 'Error')}: ${error.message}`, 'error');
            }
        });
        list.appendChild(card);
    });
}

// MODAL
function closeModalWindow() {
    if (emailDetailModal) {
        emailDetailModal.classList.remove('show');
        currentDetailEmail = null;
    }
}

// Summarize the currently open email using AI
async function handleSummarizeEmail() {
    if (!currentDetailEmail) return;
    const btn = document.getElementById('summarizeBtn');
    const originalText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.textContent = ui('⏳ Đang tóm tắt...', '⏳ Summarizing...');
    }

    try {
        const response = await apiFetch(`${API_BASE}/email/summary/${currentDetailEmail.id}`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            currentDetailEmail.summary = data.summary;
            const emailDetail = document.getElementById('emailDetail');
            const bodyEl = emailDetail ? emailDetail.querySelector('.email-detail-body') : null;
            if (bodyEl) {
                const summaryEl = document.createElement('div');
                summaryEl.className = 'email-detail-summary';
                summaryEl.style.setProperty('--email-tag-color', '#2196F3');
                summaryEl.innerHTML = `<strong>${ui('Tóm tắt', 'Summary')}</strong><div>${formatEmailText(data.summary)}</div>`;
                bodyEl.parentNode.insertBefore(summaryEl, bodyEl);
            }
            showNotification(ui('✅ Đã tóm tắt email', '✅ Email summarized'), 'success');
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể tóm tắt email', 'Unable to summarize email')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

// Generate an automatic reply draft for the currently open email
async function handleAutoReply() {
    if (!currentDetailEmail) return;
    const btn = document.getElementById('replyBtn');
    const originalText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.textContent = ui('⏳ Đang soạn trả lời...', '⏳ Drafting reply...');
    }

    try {
        const context = `Tiêu đề: ${currentDetailEmail.subject}\nTừ: ${currentDetailEmail.sender}\nNội dung: ${currentDetailEmail.body || currentDetailEmail.summary || ''}`;
        const response = await apiFetch(`${API_BASE}/chat/generate-reply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                context,
                choice: 'Xác nhận đã nhận được email và sẽ phản hồi/xử lý sớm, văn phong lịch sự'
            })
        });
        const data = await response.json();

        if (data.success) {
            // Pre-fill the compose form with the AI-generated reply for review before sending
            const senderEmail = (currentDetailEmail.sender.match(/<(.+?)>/) || [null, currentDetailEmail.sender])[1];
            document.getElementById('emailTo').value = senderEmail || '';
            document.getElementById('emailSubject').value = currentDetailEmail.subject.startsWith('Re:')
                ? currentDetailEmail.subject
                : `Re: ${currentDetailEmail.subject}`;
            document.getElementById('emailBody').value = data.reply;

            closeModalWindow();

            // Switch to the compose tab on the emails page
            const composeTabBtn = document.querySelector('#emails-page [data-tab="compose"]');
            if (composeTabBtn) handleTabChange(composeTabBtn);

            showNotification(ui('✅ Đã tạo bản nháp trả lời. Vui lòng kiểm tra trước khi gửi.', '✅ Reply draft created. Please review it before sending.'), 'success');
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể tạo trả lời', 'Unable to create reply')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

// COMPOSE
async function handleComposeSubmit(e) {
    e.preventDefault();
    
    const to = document.getElementById('emailTo').value.trim();
    const subject = document.getElementById('emailSubject').value.trim();
    const body = document.getElementById('emailBody').value.trim();
    
    try {
        const response = await apiFetch(`${API_BASE}/email/send-reply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to, subject, body })
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification(ui('✅ Email đã gửi', '✅ Email sent'), 'success');
            composeForm.reset();
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể gửi email', 'Unable to send email')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}

// DAILY REPORT
async function generateDailyReport() {
    const dateInput = document.getElementById('reportDate');
    const container = document.getElementById('dailyReportContainer');
    const btn = document.getElementById('generateReportBtn');
    
    if (!dateInput || !container) return;

    if (!dateInput.value) {
        alert(ui('Vui lòng chọn ngày', 'Please select a date'));
        return;
    }

    const [yyyy, mm, dd] = dateInput.value.split('-');
    const dateForApi = `${dd}/${mm}/${yyyy}`;

    container.innerHTML = `<p style="padding: 20px; text-align: center; color: #666;">${ui('⏳ Đang tải email và tạo báo cáo...', '⏳ Loading email and generating report...')}</p>`;
    if (btn) btn.disabled = true;

    try {
        console.log(`📊 Generating report for: ${dateForApi}`);
        const response = await apiFetch(`${API_BASE}/email/summarize-by-date`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: dateForApi, max_results: 50 })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('Report data:', data);

        if (data && data.error === 'not_authenticated') {
            container.innerHTML = `
                <div style="padding: 20px; text-align: center; background: #FFF3E0; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #E65100; margin-bottom: 10px;">${ui('⚠️ Chưa đăng nhập Gmail', '⚠️ Gmail not connected')}</p>
                    <button onclick="gmailLogin()" class="btn-primary">${ui('Đăng nhập Gmail', 'Sign in to Gmail')}</button>
                </div>
            `;
            return;
        }

        if (!data.success) {
            container.innerHTML = `
                <div style="padding: 20px; background: #FFEBEE; border-radius: 8px; margin: 20px;">
                    <p style="color: #C62828; font-weight: bold;">${ui('❌ Lỗi', '❌ Error')}: ${escapeHtml(data.error || ui('Không thể tạo báo cáo', 'Unable to generate report'))}</p>
                    <p style="color: #666; font-size: 14px; margin-top: 10px;">${ui('Hãy thử: Kiểm tra kết nối Gmail, chọn ngày khác, hoặc xem F12 console', 'Try checking your Gmail connection, selecting another date, or reviewing the F12 console.')}</p>
                </div>
            `;
            return;
        }

        if (!data.rows || data.rows.length === 0) {
            container.innerHTML = `
                <div style="padding: 20px; text-align: center; background: #E8F5E9; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #2E7D32; margin-bottom: 10px;">${ui('📭 Không có email trong ngày', '📭 No email found for')} ${escapeHtml(data.date)}</p>
                    <p style="color: #666; font-size: 14px;">${ui('Hãy thử chọn ngày khác có nhiều email hơn', 'Try another date that contains more email.')}</p>
                </div>
            `;
            return;
        }

        const rowsHtml = data.rows.map((row, i) => {
            const isMeeting = !!row.is_meeting;
            const meetingNote = isMeeting && row.meeting_note ? row.meeting_note : '';
            const actionButtons = isMeeting
                ? `
                    <div class="daily-report-actions">
                        <button class="report-schedule-yes daily-report-action daily-report-action-primary" data-report-index="${i}">Yes</button>
                        <button class="report-schedule-no daily-report-action daily-report-action-secondary" data-report-index="${i}">No</button>
                    </div>
                `
                : '';

            return `
                <tr>
                    <td class="daily-report-index">${i + 1}</td>
                    <td class="daily-report-sender">
                        <div class="daily-report-sender-name">${escapeHtml(row.sender || 'N/A')}</div>
                        <div class="daily-report-subject">${escapeHtml(row.subject || '')}</div>
                    </td>
                    <td class="daily-report-summary">
                        <div>${escapeHtml(row.summary || ui('Không có tóm tắt', 'No summary available'))}</div>
                        ${meetingNote ? `<div class="daily-report-note">${escapeHtml(meetingNote)}</div>` : ''}
                    </td>
                    <td class="daily-report-action-cell">
                        <span class="daily-report-badge ${isMeeting ? 'is-meeting' : 'is-neutral'}">${isMeeting ? ui('Gợi ý tạo lịch', 'Event suggested') : ui('Không phải cuộc họp', 'Not a meeting')}</span>
                        ${actionButtons}
                    </td>
                </tr>
            `;
        }).join('');

        container.innerHTML = `
            <div class="daily-report">
                <div class="daily-report-header">
                    <strong>${ui('Báo cáo email ngày', 'Email report for')} ${escapeHtml(data.date)}</strong><br>
                    <span>${ui('Tổng', 'Total')}: ${data.total_emails} email</span>
                </div>
                <table class="daily-report-table">
                    <thead>
                        <tr>
                            <th class="daily-report-index">#</th>
                            <th>${ui('Người gửi', 'Sender')}</th>
                            <th>${ui('Nội dung tóm tắt', 'Summary')}</th>
                            <th class="daily-report-action-cell">${ui('Chú thích / Hành động', 'Notes / Actions')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rowsHtml}
                    </tbody>
                </table>
            </div>
        `;

        data.rows.forEach((row, i) => {
            const yesBtn = container.querySelector(`.report-schedule-yes[data-report-index="${i}"]`);
            const noBtn = container.querySelector(`.report-schedule-no[data-report-index="${i}"]`);
            if (yesBtn) yesBtn.addEventListener('click', () => createScheduleFromReportRow(row, data.date, yesBtn, noBtn));
            if (noBtn) noBtn.addEventListener('click', () => {
                showNotification(ui('Đã bỏ qua gợi ý tạo lịch hẹn', 'Appointment suggestion dismissed'), 'info');
                if (yesBtn) yesBtn.disabled = true;
                if (noBtn) noBtn.disabled = true;
            });
        });
        showNotification(ui(`✅ Đã tạo báo cáo ${data.total_emails} email`, `✅ Report generated for ${data.total_emails} email`), 'success');
    } catch (error) {
        console.error('❌ Report generation error:', error);
        container.innerHTML = `
            <div style="padding: 20px; background: #FFEBEE; border-radius: 8px; margin: 20px;">
                <p style="color: #C62828; font-weight: bold;">${ui('❌ Lỗi kết nối', '❌ Connection error')}: ${escapeHtml(error.message)}</p>
                <p style="color: #666; font-size: 14px; margin-top: 10px;">${ui('Kiểm tra', 'Check')}:</p>
                <ul style="color: #666; font-size: 14px; margin-left: 20px;">
                    <li>${ui('Server đang chạy', 'The server is running')} (http://localhost:5000)</li>
                    <li>${ui('Đã đăng nhập Gmail', 'You are signed in to Gmail')}</li>
                    <li>${ui('Console (F12) để xem chi tiết', 'Open the console (F12) for details')}</li>
                </ul>
            </div>
        `;
    } finally {
        if (btn) btn.disabled = false;
    }
}

function buildReportScheduleStart(reportDate, suggestedStartTime) {
    if (suggestedStartTime) return suggestedStartTime;
    if (!reportDate) return null;

    const [dd, mm, yyyy] = reportDate.split('/');
    if (!dd || !mm || !yyyy) return null;
    return `${yyyy}-${mm}-${dd}T09:00:00`;
}

function buildReportScheduleEnd(startTime, suggestedEndTime) {
    if (suggestedEndTime) return suggestedEndTime;
    if (!startTime) return null;

    const start = new Date(startTime);
    if (Number.isNaN(start.getTime())) return null;
    const end = new Date(start.getTime() + 60 * 60000);
    const yyyy = end.getFullYear();
    const mm = String(end.getMonth() + 1).padStart(2, '0');
    const dd = String(end.getDate()).padStart(2, '0');
    const hh = String(end.getHours()).padStart(2, '0');
    const min = String(end.getMinutes()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}T${hh}:${min}:00`;
}

async function createScheduleFromReportRow(row, reportDate, yesBtn, noBtn) {
    const startTime = buildReportScheduleStart(reportDate, row.suggested_start_time);
    const endTime = buildReportScheduleEnd(startTime, row.suggested_end_time);

    if (!startTime) {
        showNotification(ui('❌ Không xác định được thời gian để tạo lịch hẹn', '❌ Unable to determine an appointment time'), 'error');
        return;
    }

    const payload = {
        title: row.schedule_title || row.subject || ui('Lịch hẹn từ email', 'Appointment from email'),
        description: row.suggested_description || row.summary || '',
        start_time: startTime,
        end_time: endTime,
        attendees: []
    };

    if (yesBtn) yesBtn.disabled = true;
    if (noBtn) noBtn.disabled = true;

    try {
        const response = await apiFetch(`${API_BASE}/schedule/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        if (data.success) {
            showNotification(
                data.calendar_event_id
                    ? ui('✅ Đã tạo lịch hẹn và đồng bộ Google Calendar', '✅ Appointment created and synced with Google Calendar')
                    : ui('✅ Đã tạo lịch hẹn từ email', '✅ Appointment created from email'),
                'success'
            );
            invalidateScheduleCaches();
            await loadSchedules();
            await loadWeekSchedule();
        } else {
            showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${data.error || ui('Không thể tạo lịch hẹn', 'Unable to create appointment')}`, 'error');
            if (yesBtn) yesBtn.disabled = false;
            if (noBtn) noBtn.disabled = false;
        }
    } catch (error) {
        showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${error.message}`, 'error');
        if (yesBtn) yesBtn.disabled = false;
        if (noBtn) noBtn.disabled = false;
    }
}
