// HISTORY FUNCTIONS
async function loadActivityHistory() {
    const historyList = document.getElementById('historyList');
    if (!historyList) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/chat/history?limit=50`);
        const data = await response.json();
        
        if (data.success && data.history.length > 0) {
            historyList.innerHTML = '';
            data.history.forEach(record => {
                const historyDiv = document.createElement('div');
                historyDiv.className = 'history-item';
                const date = new Date(record.created_at).toLocaleString(
                    currentLanguage === 'en' ? 'en-US' : 'vi-VN',
                    { dateStyle: 'medium', timeStyle: 'medium' }
                );
                const userMessage = String(record.user_message || '').trim();
                const assistantResponse = String(record.assistant_response || '').trim();
                const relatedId = String(record.related_id || '').trim();
                historyDiv.innerHTML = `
                    <div class="history-item-header">
                        <div>
                            <div class="history-item-title">${getActionLabel(record.action_type)}</div>
                            <div class="history-item-time">${escapeHtml(date)}</div>
                        </div>
                        ${relatedId ? `<span class="history-related-id">ID: ${escapeHtml(relatedId)}</span>` : ''}
                    </div>
                    ${userMessage ? `
                        <div class="history-detail-block">
                            <span>${getHistoryInputLabel(record.action_type)}</span>
                            <div>${formatEmailText(userMessage)}</div>
                        </div>
                    ` : ''}
                    ${assistantResponse ? `
                        <div class="history-detail-block history-detail-result">
                            <span>${getHistoryResultLabel(record.action_type)}</span>
                            <div>${formatEmailText(assistantResponse)}</div>
                        </div>
                    ` : ''}
                `;
                const contentLength = userMessage.length + assistantResponse.length;
                if (contentLength > 700) {
                    historyDiv.classList.add('is-collapsed');
                    const toggle = document.createElement('button');
                    toggle.type = 'button';
                    toggle.className = 'history-toggle btn-secondary';
                    toggle.textContent = ui('Xem đầy đủ', 'Show details');
                    toggle.addEventListener('click', () => {
                        const collapsed = historyDiv.classList.toggle('is-collapsed');
                        toggle.textContent = collapsed
                            ? ui('Xem đầy đủ', 'Show details')
                            : ui('Thu gọn', 'Collapse');
                    });
                    historyDiv.appendChild(toggle);
                }
                historyList.appendChild(historyDiv);
            });
        } else {
            historyList.innerHTML = `<p>${ui('Không có lịch sử', 'No activity history')}</p>`;
        }
    } catch (error) {
        historyList.innerHTML = `<p>${ui('❌ Lỗi', '❌ Error')}: ${escapeHtml(error.message)}</p>`;
    }
}

function getActionLabel(actionType) {
    const labels = {
        'chat': '💬 Chat',
        'email_summary': ui('📧 Tóm tắt', '📧 Summary'),
        'email_daily_summary': ui('📊 Báo cáo email theo ngày', '📊 Daily email report'),
        'email_reply': ui('✍️ Soạn trả lời email', '✍️ Email reply drafted'),
        'email_sent': ui('📤 Đã gửi email', '📤 Email sent'),
        'schedule_created': ui('📅 Tạo lịch', '📅 Event created'),
        'schedule_updated': ui('📝 Cập nhật lịch', '📝 Event updated'),
        'schedule_deleted': ui('🗑️ Xóa lịch', '🗑️ Event deleted'),
        'calendar_event_created': ui('📅 Tạo sự kiện Google Calendar', '📅 Google Calendar event created'),
        'calendar_event_updated': ui('📝 Cập nhật Google Calendar', '📝 Google Calendar event updated'),
        'calendar_event_deleted': ui('🗑️ Xóa sự kiện Google Calendar', '🗑️ Google Calendar event deleted')
    };
    return labels[actionType] || ui('📌 Hoạt động', '📌 Activity');
}

function getHistoryInputLabel(actionType) {
    const labels = {
        chat: ui('Tin nhắn của bạn', 'Your message'),
        email_summary: ui('Email được tóm tắt', 'Summarized email'),
        email_daily_summary: ui('Yêu cầu báo cáo', 'Report request'),
        email_reply: ui('Yêu cầu soạn thư', 'Draft request'),
        email_sent: ui('Thông tin gửi', 'Send details')
    };
    return labels[actionType] || ui('Nội dung thực hiện', 'Action details');
}

function getHistoryResultLabel(actionType) {
    const labels = {
        chat: ui('Phản hồi của FlowMate', 'FlowMate response'),
        email_summary: ui('Bản tóm tắt chi tiết', 'Detailed summary'),
        email_daily_summary: ui('Kết quả báo cáo', 'Report result'),
        email_reply: ui('Nội dung thư đề xuất', 'Suggested reply'),
        email_sent: ui('Nội dung email', 'Email content')
    };
    return labels[actionType] || ui('Kết quả', 'Result');
}
