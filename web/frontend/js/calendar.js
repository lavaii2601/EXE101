// GOOGLE CALENDAR FUNCTIONS
async function loadCalendarEvents() {
    const eventsList = document.getElementById('calendarEventsList');
    if (!eventsList) return;
    
    eventsList.innerHTML = `<p style="padding: 20px; text-align: center; color: #666;">${ui('⏳ Đang tải sự kiện Google Calendar...', '⏳ Loading Google Calendar events...')}</p>`;
    
    try {
        const response = await apiFetch(`${API_BASE}/calendar/events?max_results=10`);
        const data = await response.json();
        
        const calendarStatus = document.getElementById('calendarStatus');
        
        if (data && data.error === 'not_authenticated') {
            eventsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #FFF3E0; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #E65100; margin-bottom: 15px;">${ui('⚠️ Chưa kết nối Google Calendar', '⚠️ Google Calendar not connected')}</p>
                    <p style="color: #666; font-size: 14px; margin-bottom: 15px;">${ui('Vui lòng đăng nhập Gmail để truy cập Google Calendar', 'Please sign in to Gmail to access Google Calendar.')}</p>
                    <button id="calendarLoginBtn" class="btn-primary">${ui('Đăng nhập Gmail', 'Sign in to Gmail')}</button>
                </div>
            `;
            if (calendarStatus) calendarStatus.textContent = ui('Chưa kết nối Google Calendar', 'Google Calendar not connected');
            
            const calendarLoginBtn = document.getElementById('calendarLoginBtn');
            if (calendarLoginBtn) {
                calendarLoginBtn.addEventListener('click', gmailLogin);
            }
            return;
        }
        
        if (!data.success) {
            eventsList.innerHTML = `
                <div style="padding: 20px; background: #FFEBEE; border-radius: 8px; margin: 20px;">
                    <p style="color: #C62828; font-weight: bold;">${ui('❌ Lỗi', '❌ Error')}: ${escapeHtml(data.error || 'Unknown error')}</p>
                    <button onclick="loadCalendarEvents()" class="btn-primary" style="margin-top: 10px;">${ui('🔄 Thử lại', '🔄 Try again')}</button>
                </div>
            `;
            if (calendarStatus) calendarStatus.textContent = ui('Lỗi tải sự kiện', 'Unable to load events');
            return;
        }
        
        if (!data.events || data.events.length === 0) {
            eventsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #E8F5E9; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #2E7D32; margin-bottom: 10px;">${ui('📭 Không có sự kiện sắp tới', '📭 No upcoming events')}</p>
                    <p style="color: #666; font-size: 14px; margin-bottom: 15px;">${ui('Hãy tạo sự kiện mới hoặc kiểm tra Google Calendar', 'Create a new event or check Google Calendar.')}</p>
                </div>
            `;
            if (calendarStatus) calendarStatus.textContent = ui('Đã kết nối - Không có sự kiện', 'Connected - No events');
            return;
        }
        
        console.log(`✅ Loaded ${data.events.length} calendar events`);
        
        eventsList.innerHTML = '';
        data.events.forEach(event => {
            const eventDiv = document.createElement('div');
            eventDiv.className = 'event-item';
            const locale = currentLanguage === 'en' ? 'en-US' : 'vi-VN';
            const startTime = new Date(event.start).toLocaleString(locale);
            const endTime = new Date(event.end).toLocaleString(locale);
            const attendeeList = event.attendees && event.attendees.length > 0
                ? `<div style="margin-top: 8px; font-size: 12px; color: #666;"><strong>${ui('Người tham dự', 'Attendees')}:</strong> ${event.attendees.map(escapeHtml).join(', ')}</div>`
                : '';
            
            eventDiv.innerHTML = `
                <div style="padding: 16px; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; background: white;">
                    <div class="event-item-title" style="font-weight: 600; font-size: 16px; margin-bottom: 8px;">📆 ${escapeHtml(event.title)}</div>
                    <div style="font-size: 13px; color: #666; margin-bottom: 6px;">
                        <strong>${ui('Bắt đầu', 'Start')}:</strong> ${startTime}
                    </div>
                    <div style="font-size: 13px; color: #666; margin-bottom: 6px;">
                        <strong>${ui('Kết thúc', 'End')}:</strong> ${endTime}
                    </div>
                    ${event.location ? `<div style="font-size: 13px; color: #666; margin-bottom: 6px;"><strong>${ui('Địa điểm', 'Location')}:</strong> ${escapeHtml(event.location)}</div>` : ''}
                    ${event.description ? `<div style="font-size: 13px; color: #666; margin-bottom: 6px; margin-top: 8px;"><strong>${ui('Mô tả', 'Description')}:</strong> ${escapeHtml(event.description)}</div>` : ''}
                    ${attendeeList}
                    <div style="margin-top: 12px; display: flex; gap: 6px;">
                        <button class="event-delete-btn" data-event-id="${event.id}" style="padding: 6px 12px; font-size: 12px; background: #F44336; color: white; border: none; border-radius: 4px; cursor: pointer;">${ui('🗑️ Xóa', '🗑️ Delete')}</button>
                    </div>
                </div>
            `;
            
            const deleteBtn = eventDiv.querySelector('.event-delete-btn');
            deleteBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await deleteCalendarEvent(event.id);
            });
            
            eventsList.appendChild(eventDiv);
        });
        
        if (calendarStatus) calendarStatus.textContent = ui(`Đã kết nối - ${data.count} sự kiện sắp tới`, `Connected - ${data.count} upcoming events`);
    } catch (error) {
        console.error('Calendar load error:', error);
        eventsList.innerHTML = `<p>${ui('❌ Lỗi', '❌ Error')}: ${escapeHtml(error.message)}</p>`;
        const calendarStatus = document.getElementById('calendarStatus');
        if (calendarStatus) calendarStatus.textContent = ui('Lỗi kết nối', 'Connection error');
    }
}

async function handleCalendarEventSubmit(e) {
    e.preventDefault();
    
    const title = document.getElementById('eventTitle').value.trim();
    const description = document.getElementById('eventDescription').value.trim();
    const start_time = document.getElementById('eventStartTime').value;
    const end_time = document.getElementById('eventEndTime').value;
    const location = document.getElementById('eventLocation').value.trim();
    const attendees_str = document.getElementById('eventAttendees').value.trim();
    const attendees = attendees_str ? attendees_str.split(',').map(e => e.trim()).filter(e => e) : [];
    
    if (!title || !start_time || !end_time) {
        showNotification(ui('❌ Vui lòng điền đầy đủ thông tin bắt buộc', '❌ Please complete all required fields'), 'error');
        return;
    }
    
    try {
        const response = await apiFetch(`${API_BASE}/calendar/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                title, 
                description, 
                start_time, 
                end_time, 
                location,
                attendees 
            })
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification(ui(`✅ Sự kiện "${title}" đã được tạo`, `✅ Event "${title}" created`), 'success');
            document.getElementById('calendarEventForm').reset();
            await refreshCalendarScheduleData({ silent: true, continueOnError: true });
        } else {
            showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${data.error || ui('Không thể tạo sự kiện', 'Unable to create event')}`, 'error');
        }
    } catch (error) {
        showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${error.message}`, 'error');
    }
}

async function deleteCalendarEvent(eventId) {
    if (!confirm(ui('Xóa sự kiện này?', 'Delete this event?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/calendar/delete/${eventId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification(ui('🗑️ Đã xóa sự kiện', '🗑️ Event deleted'), 'success');
            invalidateScheduleCaches();
            await loadSchedules();
            await loadWeekSchedule();
            refreshQuickScheduleSummary();
        } else {
            showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${data.error || ui('Không thể xóa sự kiện', 'Unable to delete event')}`, 'error');
        }
    } catch (error) {
        showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${error.message}`, 'error');
    }
}
