// API Configuration
const API_BASE = '/api';

// DOM Elements - will be selected during initApp after DOM is ready
let chatMessages;
let userInput;
let sendBtn;
let navBtns;
let tabBtns;
let emailDetailModal;
let closeModal;
let clearBtn;
let composeForm;
let scheduleForm;
let gmailLoginBtn;
let gmailLogoutBtn;
let gmailAccountBadge;
let gmailProfileCard;
let gmailAvatar;
let gmailName;
let gmailEmail;
let openGmailBtn;
let emailFilterSelect;

// State
let currentPage = 'chat';
let currentEmailPage = 1;

// Initialize
document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
    console.log('🚀 Initializing app...');
    // Select DOM elements now that DOMContentLoaded fired
    chatMessages = document.getElementById('chatMessages');
    userInput = document.getElementById('userInput');
    sendBtn = document.getElementById('sendBtn');
    navBtns = document.querySelectorAll('[data-page]');
    tabBtns = document.querySelectorAll('[data-tab]');
    emailDetailModal = document.getElementById('emailDetailModal');
    closeModal = document.querySelector('.close');
    clearBtn = document.getElementById('clearBtn');
    composeForm = document.getElementById('composeForm');
    scheduleForm = document.getElementById('scheduleForm');
    gmailLoginBtn = document.getElementById('gmailLoginBtn');
    gmailLogoutBtn = document.getElementById('gmailLogoutBtn');
    gmailAccountBadge = document.getElementById('gmailAccountBadge');
    gmailProfileCard = document.getElementById('gmailProfileCard');
    gmailAvatar = document.getElementById('gmailAvatar');
    gmailName = document.getElementById('gmailName');
    gmailEmail = document.getElementById('gmailEmail');
    openGmailBtn = document.getElementById('openGmailBtn');
    emailFilterSelect = document.getElementById('emailFilterSelect');
    // Normalize page visibility on startup to avoid stale CSS/inline styles
    normalizePages();
    ensureFixedChatHeight();
    setupEventListeners();
    await loadUserProfile();
    await loadChatHistory();
    checkOAuthCallback();
    await refreshAuthButtons();
    checkRuntimeConfig();
    
    // Auto-load emails if user is on emails page and authenticated
    if (currentPage === 'emails') {
        console.log('📧 Auto-loading emails on init...');
        setTimeout(() => loadEmails(), 500);
    }
    
    console.log('✅ App initialized');
}

// Simple intent detection for scheduling prompts (Vietnamese + English keywords)
function isScheduleIntent(text) {
    if (!text) return false;
    const t = text.toLowerCase();
    const keywords = ['tạo lịch', 'lên lịch', 'đặt lịch', 'lên lịch hẹn', 'đặt lịch hẹn', 'lên lịch họp', 'xếp lịch', 'schedule', 'book', 'create meeting', 'create appointment', 'set up meeting'];
    return keywords.some(k => t.includes(k));
}

function extractScheduleDraft(text) {
    const source = (text || '').trim();
    const lower = source.toLowerCase();
    const draft = {
        title: '',
        date: '',
        startTime: '',
        endTime: '',
        format: 'Trực tiếp',
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

    const rangeMatch = source.match(/(\d{1,2})\s*(?::|h|giờ)\s*(\d{0,2})\s*(?:-|đến|toi|tới|to|->)\s*(\d{1,2})\s*(?::|h|giờ)\s*(\d{0,2})/i);
    if (rangeMatch) {
        const startHour = parseInt(rangeMatch[1], 10);
        const startMinute = parseInt(rangeMatch[2] || '0', 10) || 0;
        const endHour = parseInt(rangeMatch[3], 10);
        const endMinute = parseInt(rangeMatch[4] || '0', 10) || 0;
        if (!Number.isNaN(startHour)) draft.startTime = `${startHour.toString().padStart(2, '0')}:${startMinute.toString().padStart(2, '0')}`;
        if (!Number.isNaN(endHour)) draft.endTime = `${endHour.toString().padStart(2, '0')}:${endMinute.toString().padStart(2, '0')}`;
    } else {
        const timeMatch = source.match(/(\d{1,2})\s*(?::|h|giờ)\s*(\d{1,2})?/i);
        if (timeMatch) {
            const hour = parseInt(timeMatch[1], 10);
            const minute = parseInt(timeMatch[2] || '0', 10) || 0;
            if (!Number.isNaN(hour)) draft.startTime = `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
        }
    }

    if (lower.includes('online') || lower.includes('trực tuyến') || lower.includes('truc tuyen')) {
        draft.format = 'Online';
    } else if (lower.includes('điện thoại') || lower.includes('dien thoai') || lower.includes('phone')) {
        draft.format = 'Điện thoại';
    }

    const emailMatches = source.match(/[\w.-]+@[\w.-]+\.[A-Za-z]{2,}/g);
    if (emailMatches && emailMatches.length) {
        draft.attendees = Array.from(new Set(emailMatches)).join(', ');
    } else {
        const withMatch = source.match(/(?:với|voi)\s+([^,.!?;:]+?)(?:\s+(?:lúc|vao|vào|ngày|ngay|tại|tai)\b|[,.!?;:]|$)/i);
        if (withMatch) draft.attendees = withMatch[1].trim();
    }

    const titleMatch = source.match(/(?:tạo|lên|đặt)?\s*lịch(?:\s+hẹn)?\s*(?:cho|với|họp|hop|meeting)?\s*[:\-]?\s*([^,.!?;:]+)?/i);
    if (titleMatch && titleMatch[1]) {
        draft.title = titleMatch[1].trim().slice(0, 80);
    }
    if (!draft.title) {
        draft.title = 'Lịch hẹn';
    }

    return draft;
}

// Ensure only the active page is visible. This fixes cases where multiple
// `.page` elements become visible due to cached CSS or inline styles.
function normalizePages() {
    document.querySelectorAll('.page').forEach(p => {
        if (p.classList.contains('active')) {
            // make sure active page uses flex to match CSS
            p.style.display = 'flex';
        } else {
            p.style.display = 'none';
        }
    });
}

// Ensure chat container uses fixed-height variant so page doesn't grow.
function ensureFixedChatHeight() {
    const chatContainer = document.querySelector('.chat-container');
    if (chatContainer) {
        chatContainer.classList.add('fixed-height');
    }
}

async function apiFetch(url, options = {}) {
    try {
        const resp = await fetch(url, {
            credentials: 'include',
            ...options
        });

        if (resp.status === 401) {
            showNotification('⚠️ Chưa đăng nhập hoặc hết phiên. Vui lòng đăng nhập Gmail.', 'info');
            // If gmailLogin is available, open the login flow to help the user
            try { if (typeof gmailLogin === 'function') gmailLogin(); } catch (e) { /* ignore */ }
        }

        return resp;
    } catch (err) {
        throw err;
    }
}

function checkOAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('gmail_auth') === 'success') {
        console.log('✅ OAuth callback detected');
        
        const emailNavBtn = document.querySelector('[data-page="emails"]');
        if (emailNavBtn) {
            handlePageChange(emailNavBtn);
            showNotification('✅ Gmail đã kết nối thành công!', 'success');
            
            apiFetch(`${API_BASE}/user/gmail-connected`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).catch(err => console.error('Error marking Gmail connected:', err));
            
            setTimeout(() => {
                refreshAuthButtons();
                loadUserProfile();
                setTimeout(() => {
                    loadEmails().catch(err => {
                        console.error('First email load failed:', err);
                        setTimeout(() => loadEmails(), 1000);
                    });
                }, 300);
            }, 200);
        }
        window.history.replaceState({}, document.title, window.location.pathname);
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 24px;
        background: ${type === 'success' ? '#4CAF50' : '#2196F3'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    `;
    async function sendMessageConfirmed(message, opts = {}) {
        const confirmed = !!opts.confirmedSchedule;
        const override = opts.scheduleOverride || null;

        addMessage(message, 'user');
        userInput.value = '';

        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message assistant';
        loadingDiv.innerHTML = '<div class="message-content"><div class="loading"></div></div>';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const response = await apiFetch(`${API_BASE}/chat/message`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, confirmed_schedule: confirmed, schedule_override: override })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            const data = await response.json();

            loadingDiv.remove();

            if (!data.success) {
                addMessage('❌ Lỗi: ' + (data.error || 'Unknown error'), 'assistant');
                console.error('AI error:', data.error);
                return;
            }

            const providerBadge = data.provider ? `<span class="provider-badge" style="font-size:11px;padding:2px 8px;background:${data.demo_mode?'#FF9800':'#4CAF50'};color:white;border-radius:10px;margin-left:8px;">${data.demo_mode? '🎭 Demo' : ('🤖 '+data.provider.toUpperCase())}</span>` : '';
            addMessage(data.response, 'assistant', providerBadge);

            if (data.demo_mode) showNotification('⚠️ Demo Mode - Tất cả AI providers đang cooldown', 'info');

            // If server already created the schedule, just notify and refresh
            if (data.schedule_created) {
                try { await loadSchedules(); } catch (e) { /* ignore */ }
                showNotification(`✅ Đã tạo lịch: ${data.schedule_created.title || 'Lịch hẹn'}`, 'success');
                return;
            }

        } catch (error) {
            loadingDiv.remove();
            console.error('❌ Message send error:', error);
            addMessage('❌ Lỗi kết nối: ' + error.message, 'assistant');
            console.error(`Lỗi: ${error.message}\nEndpoint: ${API_BASE}/chat/message`);
        }
    }

function setupEventListeners() {
    console.log('📋 Setting up event listeners');

    const editModal = document.getElementById('editScheduleModal');
    const closeBtn = editModal ? editModal.querySelector('.close[data-modal="editScheduleModal"]') : null;
        if (closeBtn) closeBtn.addEventListener('click', () => editModal.style.display = 'none');
    }
    
    // Clear history
    if (clearBtn) {
        clearBtn.addEventListener('click', clearConversation);
    }
    
    // Gmail buttons
    const userAvatar = document.getElementById('userAvatar');
    if (userAvatar) userAvatar.addEventListener('click', gmailLogin);
    if (gmailLoginBtn) gmailLoginBtn.addEventListener('click', gmailLogin);
    if (gmailLogoutBtn) gmailLogoutBtn.addEventListener('click', gmailLogout);
    if (openGmailBtn) openGmailBtn.addEventListener('click', () => window.open('https://mail.google.com', '_blank'));
    
    // Email filter
    if (emailFilterSelect) {
        emailFilterSelect.addEventListener('change', () => {
            console.log(`🔍 Filter changed: ${emailFilterSelect.value}`);
            currentEmailPage = 1;
            loadEmails();
        });
    }
    
    // Include read checkbox
    const includeReadCheckbox = document.getElementById('includeReadCheckbox');
    if (includeReadCheckbox) {
        includeReadCheckbox.addEventListener('change', () => {
            console.log(`📬 Include read: ${includeReadCheckbox.checked}`);
            currentEmailPage = 1;
            loadEmails();
        });
    }
    
    // Refresh emails
    const refreshBtn = document.getElementById('refreshEmailsBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            console.log('🔄 Refreshing emails');
            // Clear cache before loading
            apiFetch(`${API_BASE}/email/cache/clear`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).then(() => {
                loadEmails();
            }).catch(err => console.error('Cache clear error:', err));
        });
    }
    
    // Generate report
    const reportBtn = document.getElementById('generateReportBtn');
    if (reportBtn) {
        reportBtn.addEventListener('click', generateDailyReport);
    }
    
    // Calendar form and buttons
    const calendarEventForm = document.getElementById('calendarEventForm');
    if (calendarEventForm) calendarEventForm.addEventListener('submit', handleCalendarEventSubmit);
    
    const refreshCalendarBtn = document.getElementById('refreshCalendarBtn');
    if (refreshCalendarBtn) {
        refreshCalendarBtn.addEventListener('click', () => {
            console.log('🔄 Refreshing calendar events');
            loadCalendarEvents();
        });
    }
    
    const openCalendarBtn = document.getElementById('openCalendarBtn');
    if (openCalendarBtn) {
        openCalendarBtn.addEventListener('click', () => window.open('https://calendar.google.com', '_blank'));
    }

    // Create event button (in merged schedule header)
    const createEventBtn = document.getElementById('createEventBtn');
    if (createEventBtn) {
        createEventBtn.addEventListener('click', () => {
            // switch to new-schedule tab
            const tabBtn = document.querySelector('.tab-btn[data-tab="new-schedule"]');
            if (tabBtn) tabBtn.click();
        });
    }

    // Listen for postMessage from OAuth popup to update UI without redirect
    window.addEventListener('message', (ev) => {
        try {
            if (ev.origin === window.location.origin && ev.data && ev.data.type === 'gmail_auth' && ev.data.status === 'success') {
                console.log('📥 Received gmail_auth success message');
                refreshAuthButtons();
                loadUserProfile();
                if (currentPage === 'emails') {
                    setTimeout(() => loadEmails(), 300);
                }
            }
        } catch (e) {
            console.warn('PostMessage handling error', e);
        }
    });

    // Responsive menu toggle (mobile)
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.querySelector('.sidebar');
    let overlay = document.getElementById('sidebarOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'sidebarOverlay';
        overlay.className = 'overlay';
        document.body.appendChild(overlay);
    }

    function openSidebar() {
        if (sidebar) sidebar.classList.add('open');
        overlay.classList.add('show');
    }
    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('open');
        overlay.classList.remove('show');
    }

    if (menuToggle) {
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            if (sidebar && sidebar.classList.contains('open')) closeSidebar(); else openSidebar();
        });
    }

    overlay.addEventListener('click', closeSidebar);

    // Close sidebar when navigating to a page on mobile
    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (window.innerWidth <= 860) closeSidebar();
        });
    });
}

async function refreshAuthButtons() {
    if (!gmailLoginBtn || !gmailLogoutBtn) return;
    try {
        // Get Gmail info from database first
        const gmailInfoResponse = await apiFetch(`${API_BASE}/user/gmail-info`);
        const gmailInfo = await gmailInfoResponse.json();
        
        // Fallback to auth-status endpoint
        const response = await apiFetch(`${API_BASE}/email/auth-status`);
        const data = await response.json();
        const isAuth = !!(data && data.success && data.authenticated);
        
        // Merge both sources for most complete info
        const profileName = gmailInfo.gmail_name || (data && data.gmail_name) || 'Google User';
        const profileEmail = gmailInfo.gmail_email || (data && data.gmail_email) || '';
        const profilePicture = gmailInfo.gmail_picture || (data && data.gmail_picture) || '';
        
        gmailLoginBtn.style.display = isAuth ? 'none' : 'inline-block';
        gmailLogoutBtn.style.display = isAuth ? 'inline-block' : 'none';
        if (openGmailBtn) openGmailBtn.style.display = isAuth ? 'inline-block' : 'none';

        if (gmailAccountBadge) {
            gmailAccountBadge.textContent = isAuth ? 'Đã kết nối Gmail' : 'Chưa đăng nhập Gmail';
            gmailAccountBadge.style.display = isAuth ? 'none' : 'inline-block';
        }

        if (gmailProfileCard) gmailProfileCard.style.display = isAuth ? 'inline-flex' : 'none';
        if (gmailName) gmailName.textContent = profileName;
        if (gmailEmail) gmailEmail.textContent = profileEmail;
        if (gmailAvatar) gmailAvatar.src = profilePicture || 'https://www.gravatar.com/avatar/?d=mp&s=64';

        updateSidebarUserProfile({
            name: profileName,
            email: profileEmail,
            avatarUrl: profilePicture,
            connected: isAuth
        });
    } catch (err) {
        console.error('Auth status check failed:', err);
        if (gmailLoginBtn) gmailLoginBtn.style.display = 'inline-block';
        if (gmailLogoutBtn) gmailLogoutBtn.style.display = 'none';
        if (openGmailBtn) openGmailBtn.style.display = 'none';
    }
}

async function gmailLogout() {
    if (!confirm('Bạn có chắc muốn đăng xuất Gmail?')) return;

    try {
        const response = await apiFetch(`${API_BASE}/email/logout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            showNotification('✅ Đã đăng xuất Gmail', 'success');
            apiFetch(`${API_BASE}/user/gmail-disconnected`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).catch(err => console.error('Error marking Gmail disconnected:', err));
            
            await refreshAuthButtons();
            await loadUserProfile();
            const emailsList = document.getElementById('emailsList');
            if (emailsList) emailsList.innerHTML = '<p>Đã đăng xuất Gmail. Vui lòng đăng nhập lại.</p>';
        }
    } catch (err) {
        alert('Lỗi: ' + err.message);
    }
}

// PAGE MANAGEMENT (CRITICAL FIX)
async function handlePageChange(btn) {
    const page = btn.dataset.page;
    console.log(`🔄 Changing page to: ${page}`);
    
    // Update nav buttons
    navBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
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
    
    // Load page data
    if (page === 'emails') {
        // Check Gmail auth status first to avoid 401 errors
        try {
            const authResp = await apiFetch(`${API_BASE}/email/auth-status`);
            if (authResp.status === 401) {
                const emailsList = document.getElementById('emailsList');
                if (emailsList) emailsList.innerHTML = `<div style="padding:20px;text-align:center;">Vui lòng đăng nhập Gmail để xem email.<br><br><button class="btn-primary" id="promptLoginBtn">Đăng nhập Gmail</button></div>`;
                const btnLogin = document.getElementById('promptLoginBtn');
                if (btnLogin) btnLogin.addEventListener('click', gmailLogin);
                return;
            }
            const authData = await authResp.json();
            if (!authData || !authData.authenticated) {
                const emailsList = document.getElementById('emailsList');
                if (emailsList) emailsList.innerHTML = `<div style="padding:20px;text-align:center;">Vui lòng đăng nhập Gmail để xem email.<br><br><button class="btn-primary" id="promptLoginBtn">Đăng nhập Gmail</button></div>`;
                const btnLogin = document.getElementById('promptLoginBtn');
                if (btnLogin) btnLogin.addEventListener('click', gmailLogin);
                return;
            }
        } catch (err) {
            console.error('Auth check failed:', err);
            // Fallback to attempting to load emails — loadEmails will handle errors
        }

        loadEmails().catch(err => console.error('Email load error:', err));
    } else if (page === 'schedule') {
        loadSchedules().catch(err => console.error('Schedule load error:', err));
        // also load Google Calendar events (merged into schedule tab)
        loadCalendarEvents().catch(err => console.error('Calendar load error:', err));
    } else if (page === 'history') {
        loadActivityHistory().catch(err => console.error('History load error:', err));
    }
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

// CHAT FUNCTIONS (CRITICAL FIX)
// sendMessage wrapper: detect scheduling intent and prompt confirmation before sending
function sendMessage() {
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

        // populate modal fields
        const draft = extractScheduleDraft(message);
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
        if (body) {
            body.innerHTML = `
                <div><strong>Nội dung phát hiện:</strong> ${escapeHtml(draft.content)}</div>
                <div style="margin-top:8px; font-size:13px; line-height:1.5;">
                    Ngày: ${escapeHtml(draft.date || 'Chưa xác định')}<br>
                    Thời gian: ${escapeHtml(draft.startTime ? (draft.endTime ? `${draft.startTime} - ${draft.endTime}` : draft.startTime) : 'Chưa xác định')}<br>
                    Hình thức: ${escapeHtml(draft.format || 'Trực tiếp')}<br>
                    Đối tượng: ${escapeHtml(draft.attendees || 'Chưa xác định')}
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
    console.log(`📨 Sending message: ${message.substring(0, 50)}...`);
    addMessage(message, 'user');
    userInput.value = '';

    // Show loading
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message assistant';
    loadingDiv.innerHTML = '<div class="message-content"><div class="loading"></div></div>';
    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        console.log(`🔗 POST ${API_BASE}/chat/message`);
        const response = await apiFetch(`${API_BASE}/chat/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, confirmed_schedule: confirmed })
        });

        console.log(`⚙️ Response status: ${response.status}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('✅ Response received:', data);

        loadingDiv.remove();

        if (data.success) {
            const providerBadge = data.provider ? 
                `<span class="provider-badge" style="font-size: 11px; padding: 2px 8px; background: ${data.demo_mode ? '#FF9800' : '#4CAF50'}; color: white; border-radius: 10px; margin-left: 8px;">
                    ${data.demo_mode ? '🎭 Demo' : '🤖 ' + data.provider.toUpperCase()}
                </span>` : '';

            addMessage(data.response, 'assistant', providerBadge);

            if (data.demo_mode) {
                showNotification('⚠️ Demo Mode - Tất cả AI providers đang cooldown', 'info');
            }

            // Handle schedule results from server
            if (data.schedule_created) {
                // Server already created the schedule (user confirmed or server-side)
                try { await loadSchedules(); } catch (e) { /* ignore */ }
                showNotification(`✅ Đã tạo lịch: ${data.schedule_created.title || 'Lịch hẹn'}`, 'success');
            } else if (data.schedule_suggestion && isScheduleIntent(message)) {
                const suggested = data.schedule_suggestion;
                // Show inline suggestion with create/dismiss buttons
                const suggestionDiv = document.createElement('div');
                suggestionDiv.className = 'message assistant';
                suggestionDiv.innerHTML = `
                    <div class="message-content">
                        <div style="font-weight:700; margin-bottom:6px;">AI gợi ý tạo lịch: ${escapeHtml(suggested.title || 'Lịch hẹn')}</div>
                        <div style="color:var(--text-secondary); font-size:13px; margin-bottom:8px;">${escapeHtml(suggested.description || '')}</div>
                        <div style="display:flex; gap:8px;">
                            <button class="btn-primary confirm-create-schedule">Tạo lịch</button>
                            <button class="btn-secondary dismiss-schedule">Bỏ qua</button>
                        </div>
                    </div>
                `;
                chatMessages.appendChild(suggestionDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;

                // wire buttons
                suggestionDiv.querySelector('.dismiss-schedule').addEventListener('click', () => {
                    suggestionDiv.remove();
                    showNotification('Đã bỏ qua gợi ý tạo lịch', 'info');
                });

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
                            showNotification(`✅ Đã tạo lịch: ${j.calendar_event_id ? 'đã đồng bộ Google Calendar' : suggested.title}`, 'success');
                            try { await loadSchedules(); } catch (e) { /* ignore */ }
                            suggestionDiv.remove();
                        } else {
                            showNotification('❌ Không thể tạo lịch: ' + (j.error || resp.statusText || 'lỗi'), 'error');
                            suggestionDiv.querySelectorAll('button').forEach(b => b.disabled = false);
                        }
                    } catch (err) {
                        console.error('Create schedule error', err);
                        showNotification('❌ Lỗi tạo lịch: ' + err.message, 'error');
                        suggestionDiv.querySelectorAll('button').forEach(b => b.disabled = false);
                    }
                });
            }
        } else {
            addMessage('❌ Lỗi: ' + (data.error || 'Unknown error'), 'assistant');
            console.error('AI error:', data.error);
        }
    } catch (error) {
        loadingDiv.remove();
        console.error('❌ Message send error:', error);
        addMessage('❌ Lỗi kết nối: ' + error.message, 'assistant');

        // Detailed error message
        const errorMsg = `
Lỗi: ${error.message}
Endpoint: ${API_BASE}/chat/message
Status: Not reached
        `.trim();
        console.error(errorMsg);
    }
}

function addMessage(text, role, badge = '') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.innerHTML = `<div class="message-content">${renderMarkdown(escapeHtml(text))}${badge}</div>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function loadUserProfile() {
    try {
        const [profileResponse, gmailResponse] = await Promise.all([
            apiFetch(`${API_BASE}/user/profile`),
            apiFetch(`${API_BASE}/user/gmail-info`).catch(() => null)
        ]);

        const data = await profileResponse.json();
        const gmailData = gmailResponse ? await gmailResponse.json() : null;
        
        if (data.success && data.user) {
            const user = data.user;
            const gmailConnected = !!(gmailData && gmailData.success && gmailData.gmail_connected);
            const currentSidebarName = document.getElementById('userName')?.textContent?.trim() || '';
            const currentSidebarAvatar = document.getElementById('userAvatar')?.getAttribute('src') || '';

            updateSidebarUserProfile({
                name: (gmailConnected && ((gmailData && gmailData.gmail_name) || user.gmail_name || currentSidebarName)) || user.name || 'Teacher',
                email: (gmailData && gmailData.gmail_email) || user.gmail_email || user.email || '',
                avatarUrl: (gmailConnected && ((gmailData && gmailData.gmail_picture) || user.avatar_url || user.gmail_picture || currentSidebarAvatar)) || user.avatar_url || user.gmail_picture || '',
                connected: gmailConnected || !!user.gmail_connected
            });

            const userAvatar = document.getElementById('userAvatar');
            if (userAvatar) {
                userAvatar.title = gmailConnected ? 'Đã kết nối Gmail' : 'Đăng nhập Gmail';
            }
        }
    } catch (error) {
        console.error('Error loading user profile:', error);
    }
}

async function loadChatHistory() {
    try {
        const response = await apiFetch(`${API_BASE}/chat/history?limit=20`);
        const data = await response.json();
        
        if (data.success && data.history.length > 0) {
            chatMessages.innerHTML = '';
            data.history.reverse().forEach(record => {
                addMessage(record.user_message, 'user');
                addMessage(record.assistant_response, 'assistant');
            });
        }
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

async function clearConversation() {
    if (!confirm('Bạn có chắc chắn muốn làm mới cuộc trò chuyện?')) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/chat/clear`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        if (data.success) {
            chatMessages.innerHTML = '';
            showNotification('✅ Lịch sử đã bị xóa', 'success');
        }
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
    }
}

// EMAIL FUNCTIONS
async function gmailLogin() {
    try {
        const response = await apiFetch(`${API_BASE}/email/auth_url`);
        const data = await response.json();

        if (!response.ok || !data.auth_url) {
            alert('Lỗi: ' + (data.error || 'OAuth chưa được cấu hình'));
            return;
        }

        window.location.href = data.auth_url;
    } catch (err) {
        alert('Lỗi: ' + err.message);
    }
}

// Client-side email cache for fallback pagination
let emailsCache = [];

async function toggleEmailReadStatus(emailId, isUnread) {
    try {
        const endpoint = isUnread ? 'mark-as-read' : 'mark-as-unread';
        const response = await apiFetch(`${API_BASE}/email/${endpoint}/${emailId}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            const action = isUnread ? 'đã đọc' : 'chưa đọc';
            showNotification(`✅ Đã đánh dấu email ${action}`, 'success');
            // Reload emails to reflect the change
            await loadEmails(currentEmailPage);
        } else {
            showNotification(`❌ Lỗi: ${data.error || 'Không thể đánh dấu email'}`, 'error');
        }
    } catch (error) {
        console.error('Error toggling email read status:', error);
        showNotification(`❌ Lỗi: ${error.message}`, 'error');
    }
}

async function checkRuntimeConfig() {
    try {
        const response = await apiFetch(`${API_BASE}/chat/providers`);
        const data = await response.json();
        
        if (data.success && data.providers) {
            const providers = data.providers;
            if (providers.demo_mode) {
                console.warn('⚠️ Demo Mode - Tất cả AI providers đang cooldown hoặc chưa cấu hình');
            } else {
                console.log('✅ AI providers configured and active');
            }
        }
    } catch (err) {
        console.error('Config check failed:', err);
    }
}

async function loadEmails(page = 1) {
    const emailsList = document.getElementById('emailsList');
    if (!emailsList) {
        console.error('❌ emailsList element not found');
        return;
    }
    
    emailsList.innerHTML = '<p style="padding: 20px; text-align: center; color: #666;">⏳ Đang tải email...</p>';
    const selectedFilter = emailFilterSelect ? emailFilterSelect.value : 'all';
    const includeReadCheckbox = document.getElementById('includeReadCheckbox');
    const includeRead = includeReadCheckbox ? includeReadCheckbox.checked : false;
    currentEmailPage = page;

    await refreshAuthButtons();
    
    try {
        const url = `${API_BASE}/email/get-unread?max_results=20&page=${page}&filter=${encodeURIComponent(selectedFilter)}&include_read=${includeRead}`;
        console.log(`📧 Loading emails: ${url}`);
        console.log(`🔍 Filter: ${selectedFilter}, Page: ${page}, Include read: ${includeRead}`);
        
        const response = await apiFetch(url);
        console.log(`📡 Response status: ${response.status}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('📦 Email data received:', data);
        
        if (data && data.error === 'not_authenticated') {
            emailsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #FFF3E0; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #E65100; margin-bottom: 15px;">⚠️ Chưa đăng nhập Gmail</p>
                    <button id="loginPromptBtn" class="btn-primary">Đăng nhập Gmail</button>
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
                    <button onclick="loadEmails(1)" class="btn-primary" style="margin-top: 10px;">🔄 Thử lại</button>
                </div>
            `;
            return;
        }
        
        if (!data.emails || data.emails.length === 0) {
            console.warn('⚠️ No emails found');
            emailsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #E8F5E9; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #2E7D32; margin-bottom: 10px;">📭 Không tìm thấy email</p>
                    <p style="color: #666; font-size: 14px; margin-bottom: 15px;">
                        Filter hiện tại: <strong>${selectedFilter}</strong><br>
                        ${data.debug ? `Tổng email quét: ${data.debug.raw_email_count || 0}` : ''}
                    </p>
                    <div style="display: flex; gap: 10px; justify-content: center;">
                        <button onclick="emailFilterSelect.value='all'; loadEmails(1);" class="btn-primary">🔍 Xem tất cả</button>
                        <button onclick="loadEmails(1)" class="btn-secondary">🔄 Làm mới</button>
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
                renderEmailItem(email, emailsList);
            });

            const { current_page, total_pages } = data.pagination;
            if (total_pages > 1) {
                const paginationDiv = document.createElement('div');
                paginationDiv.style.cssText = 'padding: 16px; display: flex; justify-content: center; gap: 8px; margin-top: 16px;';
                const prevBtn = document.createElement('button');
                prevBtn.textContent = '◀ Trang trước';
                prevBtn.disabled = current_page === 1;
                prevBtn.addEventListener('click', () => loadEmails(current_page - 1));
                paginationDiv.appendChild(prevBtn);

                const pageInfo = document.createElement('span');
                pageInfo.textContent = `Trang ${current_page} / ${total_pages}`;
                pageInfo.style.cssText = 'font-weight: bold; padding: 0 16px;';
                paginationDiv.appendChild(pageInfo);

                const nextBtn = document.createElement('button');
                nextBtn.textContent = 'Trang sau ▶';
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
                renderEmailItem(email, emailsList);
            });

            if (total_pages > 1) {
                const paginationDiv = document.createElement('div');
                paginationDiv.style.cssText = 'padding: 16px; display: flex; justify-content: center; gap: 8px; margin-top: 16px;';
                const prevBtn = document.createElement('button');
                prevBtn.textContent = '◀ Trang trước';
                prevBtn.disabled = current_page === 1;
                prevBtn.addEventListener('click', () => loadEmails(current_page - 1));
                paginationDiv.appendChild(prevBtn);

                const pageInfo = document.createElement('span');
                pageInfo.textContent = `Trang ${current_page} / ${total_pages}`;
                pageInfo.style.cssText = 'font-weight: bold; padding: 0 16px;';
                paginationDiv.appendChild(pageInfo);

                const nextBtn = document.createElement('button');
                nextBtn.textContent = 'Trang sau ▶';
                nextBtn.disabled = current_page === total_pages;
                nextBtn.addEventListener('click', () => loadEmails(current_page + 1));
                paginationDiv.appendChild(nextBtn);

                emailsList.appendChild(paginationDiv);
            }
        }
        
        return;
        
        
        function renderEmailItem(email, container) {
            const emailDiv = document.createElement('div');
            emailDiv.className = 'email-item';
            
            // Add visual indicator for unread emails
            const readStatus = email.is_unread ? 
                '<span style="display: inline-block; width: 8px; height: 8px; background: #4CAF50; border-radius: 50%; margin-right: 6px;" title="Chưa đọc"></span>' : 
                '<span style="display: inline-block; width: 8px; height: 8px; background: #ccc; border-radius: 50%; margin-right: 6px;" title="Đã đọc"></span>';
            
            const markButtonText = email.is_unread ? '✅ Đánh dấu đã đọc' : '📧 Đánh dấu chưa đọc';
            const markButtonClass = email.is_unread ? 'mark-read-btn' : 'mark-unread-btn';
            
            emailDiv.innerHTML = `
                <div class="email-item-header">
                    <span class="email-item-subject">${readStatus}${escapeHtml(email.subject)}</span>
                </div>
                <div class="email-item-sender">Từ: ${escapeHtml(email.sender)}</div>
                <div class="email-item-snippet">${escapeHtml(email.snippet)}</div>
                <div class="email-item-actions" style="margin-top: 8px; display: flex; gap: 6px;">
                    <button class="email-view-detail-btn" style="padding: 4px 12px; font-size: 12px; background: #666; color: white; border: none; border-radius: 4px; cursor: pointer;">👁️ Xem</button>
                    <button class="${markButtonClass}" data-email-id="${email.id}" data-is-unread="${email.is_unread}" style="padding: 4px 12px; font-size: 12px; background: ${email.is_unread ? '#4CAF50' : '#FF9800'}; color: white; border: none; border-radius: 4px; cursor: pointer;">${markButtonText}</button>
                </div>
            `;
            
            emailDiv.querySelector('.email-view-detail-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                showEmailDetail(email);
            });

            // Click on the item opens the full-email modal
            emailDiv.addEventListener('click', (e) => {
                if (e.target && e.target.closest('button')) return;
                showEmailDetail(email);
            });
            
            // Add mark as read/unread handler
            const markButton = emailDiv.querySelector(`.${markButtonClass}`);
            markButton.addEventListener('click', async (e) => {
                e.stopPropagation();
                await toggleEmailReadStatus(email.id, email.is_unread);
            });
            
            container.appendChild(emailDiv);
        }
        
        // Pagination
        if (data.pagination && data.pagination.total_pages > 1) {
            const { current_page, total_pages } = data.pagination;
            const paginationDiv = document.createElement('div');
            paginationDiv.style.cssText = 'padding: 16px; display: flex; justify-content: center; gap: 8px; margin-top: 16px;';
            
            const prevBtn = document.createElement('button');
            prevBtn.textContent = '◀ Trang trước';
            prevBtn.disabled = current_page === 1;
            prevBtn.addEventListener('click', () => loadEmails(current_page - 1));
            paginationDiv.appendChild(prevBtn);
            
            const pageInfo = document.createElement('span');
            pageInfo.textContent = `Trang ${current_page} / ${total_pages}`;
            pageInfo.style.cssText = 'font-weight: bold; padding: 0 16px;';
            paginationDiv.appendChild(pageInfo);
            
            const nextBtn = document.createElement('button');
            nextBtn.textContent = 'Trang sau ▶';
            nextBtn.disabled = current_page === total_pages;
            nextBtn.addEventListener('click', () => loadEmails(current_page + 1));
            paginationDiv.appendChild(nextBtn);
            
            emailsList.appendChild(paginationDiv);
        }
    } catch (error) {
        console.error('Email load error:', error);
        emailsList.innerHTML = `<p>❌ Lỗi: ${error.message}</p>`;
    }
}

async function showEmailDetail(email) {
    const emailDetail = document.getElementById('emailDetail');
    if (!emailDetail) return;
    
    emailDetail.innerHTML = `
        <div class="email-detail-subject">${escapeHtml(email.subject)}</div>
        <div class="email-detail-meta">
            <strong>Từ:</strong> ${escapeHtml(email.sender)}<br>
            <strong>Ngày:</strong> ${escapeHtml(email.date)}
        </div>
        <div class="email-detail-body" style="color: #666; font-style: italic;">Đang tải nội dung...</div>
    `;
    
    if (emailDetailModal) emailDetailModal.classList.add('show');
    
    // Lazy load body
    if (!email.body) {
        try {
            const response = await apiFetch(`${API_BASE}/email/get-email-body/${email.id}`);
            const data = await response.json();
            email.body = data.success ? data.body : 'Không thể tải nội dung';
        } catch (error) {
            email.body = 'Lỗi: ' + error.message;
        }
    }
    
    emailDetail.innerHTML = `
        <div class="email-detail-subject">${escapeHtml(email.subject)}</div>
        <div class="email-detail-meta">
            <strong>Từ:</strong> ${escapeHtml(email.sender)}<br>
            <strong>Ngày:</strong> ${escapeHtml(email.date)}
        </div>
        <div class="email-detail-body">${escapeHtml(email.body)}</div>
    `;
}

// Note: Preview pane removed — email items open the modal showing full content.

// SCHEDULE FUNCTIONS
async function loadSchedules() {
    const schedulesList = document.getElementById('schedulesList');
    if (!schedulesList) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/upcoming`);
        const data = await response.json();
        
        if (data.success && data.schedules.length > 0) {
            schedulesList.innerHTML = '';
            data.schedules.forEach(schedule => {
                const scheduleDiv = document.createElement('div');
                scheduleDiv.className = 'schedule-item';
                const startTime = new Date(schedule.start_time).toLocaleString('vi-VN');
                const endTime = schedule.end_time ? new Date(schedule.end_time).toLocaleString('vi-VN') : '';
                const durationMinutes = getDurationMinutes(schedule.start_time, schedule.end_time);
                const statusClass = schedule.status === 'completed' ? 'completed' : 'pending';
                const statusText = schedule.status === 'completed' ? 'Đã hoàn thành' : 'Chưa hoàn thành';
                const syncBadge = schedule.calendar_event_id
                    ? '<span class="schedule-item-status" style="background:#E8F5E9;color:#2E7D32;">Đã đồng bộ Google Calendar</span>'
                    : '<span class="schedule-item-status" style="background:#FFF3E0;color:#E65100;">Chưa đồng bộ Google Calendar</span>';
                
                scheduleDiv.innerHTML = `
                    <div class="schedule-item-info">
                        <div class="schedule-item-title">${escapeHtml(schedule.title)}</div>
                        <span class="schedule-item-status ${statusClass}">${statusText}</span>
                        ${syncBadge}
                        <div class="schedule-item-time">${startTime}</div>
                        ${endTime ? `<div class="schedule-item-time">Kết thúc: ${endTime}</div>` : ''}
                        ${durationMinutes ? `<div class="schedule-item-time">Thời lượng: ${durationMinutes} phút</div>` : ''}
                    </div>
                    <div class="schedule-item-actions">
                        ${schedule.status === 'completed' ? 
                            `<button class="btn-check" onclick="markScheduleIncomplete(${schedule.id})">↩️ Chưa xong</button>` :
                            `<button class="btn-check" onclick="markScheduleComplete(${schedule.id})">✓ Hoàn thành</button>`
                        }
                        <button class="btn-edit" onclick="openEditSchedule(${schedule.id})">✏️ Sửa</button>
                        <button class="btn-delete" onclick="deleteSchedule(${schedule.id})">🗑️ Xóa</button>
                    </div>
                `;
                schedulesList.appendChild(scheduleDiv);
            });
        } else {
            schedulesList.innerHTML = '<p>Không có lịch hẹn sắp tới</p>';
        }
    } catch (error) {
        schedulesList.innerHTML = `<p>❌ Lỗi: ${error.message}</p>`;
    }
}

async function markScheduleComplete(scheduleId) {
    if (!confirm('Đánh dấu lịch hẹn đã hoàn thành?')) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}/update-status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'completed' })
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification('✓ Đã đánh dấu hoàn thành', 'success');
            await loadSchedules();
        }
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
    }
}

async function markScheduleIncomplete(scheduleId) {
    if (!confirm('Đánh dấu lịch hẹn chưa hoàn thành?')) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}/update-status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'pending' })
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification('↩️ Đã cập nhật trạng thái', 'success');
            await loadSchedules();
        }
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
    }
}

async function openEditSchedule(scheduleId) {
    try {
        const response = await apiFetch(`${API_BASE}/schedule/list`);
        const data = await response.json();
        
        if (!data.success) throw new Error('Lỗi lấy dữ liệu');
        
        const schedule = data.schedules.find(s => s.id === scheduleId);
        if (!schedule) throw new Error('Lịch hẹn không tìm thấy');
        
        const editForm = document.getElementById('editScheduleForm');
        document.getElementById('editScheduleTitle').value = schedule.title;
        document.getElementById('editScheduleDesc').value = schedule.description || '';
        document.getElementById('editScheduleTime').value = toDatetimeLocal(schedule.start_time);
        const editDurationInput = document.getElementById('editScheduleDuration');
        if (editDurationInput) {
            editDurationInput.value = getDurationMinutes(schedule.start_time, schedule.end_time) || 60;
        }
        document.getElementById('editScheduleAttendees').value = schedule.attendees || '';
        editForm.dataset.scheduleId = scheduleId;
        
        document.getElementById('editScheduleModal').style.display = 'block';
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
    }
}

async function handleEditScheduleSubmit(e) {
    e.preventDefault();
    
    const scheduleId = document.getElementById('editScheduleForm').dataset.scheduleId;
    const title = document.getElementById('editScheduleTitle').value.trim();
    const description = document.getElementById('editScheduleDesc').value.trim();
    const start_time = document.getElementById('editScheduleTime').value;
    const duration_minutes = parseInt(document.getElementById('editScheduleDuration')?.value || '60', 10);
    const attendees_str = document.getElementById('editScheduleAttendees').value.trim();
    const attendees = attendees_str ? attendees_str.split(',').map(e => e.trim()) : [];
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, start_time, duration_minutes, attendees })
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification('✓ Đã cập nhật lịch hẹn', 'success');
            document.getElementById('editScheduleModal').style.display = 'none';
            await loadSchedules();
            await loadCalendarEvents();
        }
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
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
    if (!confirm('Xóa lịch hẹn này?')) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification('🗑️ Đã xóa', 'success');
            await loadSchedules();
            await loadCalendarEvents();
        }
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
    }
}

async function handleScheduleSubmit(e) {
    e.preventDefault();
    
    const title = document.getElementById('scheduleTitle').value.trim();
    const description = document.getElementById('scheduleDesc').value.trim();
    const start_time = document.getElementById('scheduleStartTime').value;
    const end_time = document.getElementById('scheduleEndTime') ? document.getElementById('scheduleEndTime').value : '';
    const duration_minutes = parseInt(document.getElementById('scheduleDuration')?.value || '60', 10);
    const location = document.getElementById('scheduleLocation') ? document.getElementById('scheduleLocation').value.trim() : '';
    const attendees_str = document.getElementById('scheduleAttendees').value.trim();
    const attendees = attendees_str ? attendees_str.split(',').map(e => e.trim()) : [];
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, start_time, end_time, duration_minutes, location, attendees })
        });
        
        const data = await response.json();
        if (data.success) {
            const sid = data.schedule_id;
            if (data.calendar_event_id) {
                showNotification('✅ Lịch hẹn đã được tạo và đồng bộ Google Calendar', 'success');
            } else {
                showNotification('✅ Đã tạo lịch hẹn. Đang đồng bộ với Google Calendar...', 'info');
            }
            scheduleForm.reset();
            await loadSchedules();
            // refresh calendar events too
            await loadCalendarEvents();

            // If calendar_event_id not present, poll for status in background
            if (!data.calendar_event_id && sid) {
                pollScheduleSync(sid, 30000).then(synced => {
                    if (synced) {
                        showNotification('✅ Lịch hẹn đã được đồng bộ với Google Calendar', 'success');
                    } else {
                        showNotification('⚠️ Đồng bộ lịch hẹn chưa hoàn tất - thử lại sau', 'info');
                    }
                    loadSchedules();
                    loadCalendarEvents();
                }).catch(err => {
                    console.warn('Poll schedule sync error', err);
                });
            }
        }
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
    }
}

// GOOGLE CALENDAR FUNCTIONS
async function loadCalendarEvents() {
    const eventsList = document.getElementById('calendarEventsList');
    if (!eventsList) return;
    
    eventsList.innerHTML = '<p style="padding: 20px; text-align: center; color: #666;">⏳ Đang tải sự kiện Google Calendar...</p>';
    
    try {
        const response = await apiFetch(`${API_BASE}/calendar/events?max_results=10`);
        const data = await response.json();
        
        const calendarStatus = document.getElementById('calendarStatus');
        
        if (data && data.error === 'not_authenticated') {
            eventsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #FFF3E0; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #E65100; margin-bottom: 15px;">⚠️ Chưa kết nối Google Calendar</p>
                    <p style="color: #666; font-size: 14px; margin-bottom: 15px;">Vui lòng đăng nhập Gmail để truy cập Google Calendar</p>
                    <button id="calendarLoginBtn" class="btn-primary">Đăng nhập Gmail</button>
                </div>
            `;
            if (calendarStatus) calendarStatus.textContent = 'Chưa kết nối Google Calendar';
            
            const calendarLoginBtn = document.getElementById('calendarLoginBtn');
            if (calendarLoginBtn) {
                calendarLoginBtn.addEventListener('click', gmailLogin);
            }
            return;
        }
        
        if (!data.success) {
            eventsList.innerHTML = `
                <div style="padding: 20px; background: #FFEBEE; border-radius: 8px; margin: 20px;">
                    <p style="color: #C62828; font-weight: bold;">❌ Lỗi: ${escapeHtml(data.error || 'Unknown error')}</p>
                    <button onclick="loadCalendarEvents()" class="btn-primary" style="margin-top: 10px;">🔄 Thử lại</button>
                </div>
            `;
            if (calendarStatus) calendarStatus.textContent = 'Lỗi tải sự kiện';
            return;
        }
        
        if (!data.events || data.events.length === 0) {
            eventsList.innerHTML = `
                <div style="padding: 30px; text-align: center; background: #E8F5E9; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #2E7D32; margin-bottom: 10px;">📭 Không có sự kiện sắp tới</p>
                    <p style="color: #666; font-size: 14px; margin-bottom: 15px;">Hãy tạo sự kiện mới hoặc kiểm tra Google Calendar</p>
                </div>
            `;
            if (calendarStatus) calendarStatus.textContent = 'Đã kết nối - Không có sự kiện';
            return;
        }
        
        console.log(`✅ Loaded ${data.events.length} calendar events`);
        
        eventsList.innerHTML = '';
        data.events.forEach(event => {
            const eventDiv = document.createElement('div');
            eventDiv.className = 'event-item';
            const startTime = new Date(event.start).toLocaleString('vi-VN');
            const endTime = new Date(event.end).toLocaleString('vi-VN');
            const attendeeList = event.attendees && event.attendees.length > 0 
                ? `<div style="margin-top: 8px; font-size: 12px; color: #666;"><strong>Người tham dự:</strong> ${event.attendees.join(', ')}</div>`
                : '';
            
            eventDiv.innerHTML = `
                <div style="padding: 16px; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; background: white;">
                    <div class="event-item-title" style="font-weight: 600; font-size: 16px; margin-bottom: 8px;">📆 ${escapeHtml(event.title)}</div>
                    <div style="font-size: 13px; color: #666; margin-bottom: 6px;">
                        <strong>Bắt đầu:</strong> ${startTime}
                    </div>
                    <div style="font-size: 13px; color: #666; margin-bottom: 6px;">
                        <strong>Kết thúc:</strong> ${endTime}
                    </div>
                    ${event.location ? `<div style="font-size: 13px; color: #666; margin-bottom: 6px;"><strong>Địa điểm:</strong> ${escapeHtml(event.location)}</div>` : ''}
                    ${event.description ? `<div style="font-size: 13px; color: #666; margin-bottom: 6px; margin-top: 8px;"><strong>Mô tả:</strong> ${escapeHtml(event.description)}</div>` : ''}
                    ${attendeeList}
                    <div style="margin-top: 12px; display: flex; gap: 6px;">
                        <button class="event-delete-btn" data-event-id="${event.id}" style="padding: 6px 12px; font-size: 12px; background: #F44336; color: white; border: none; border-radius: 4px; cursor: pointer;">🗑️ Xóa</button>
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
        
        if (calendarStatus) calendarStatus.textContent = `Đã kết nối - ${data.count} sự kiện sắp tới`;
    } catch (error) {
        console.error('Calendar load error:', error);
        eventsList.innerHTML = `<p>❌ Lỗi: ${error.message}</p>`;
        const calendarStatus = document.getElementById('calendarStatus');
        if (calendarStatus) calendarStatus.textContent = 'Lỗi kết nối';
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
        showNotification('❌ Vui lòng điền đầy đủ thông tin bắt buộc', 'error');
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
            showNotification(`✅ Sự kiện "${title}" đã được tạo`, 'success');
            document.getElementById('calendarEventForm').reset();
            await loadCalendarEvents();
        } else {
            showNotification(`❌ Lỗi: ${data.error || 'Không thể tạo sự kiện'}`, 'error');
        }
    } catch (error) {
        showNotification(`❌ Lỗi: ${error.message}`, 'error');
    }
}

async function deleteCalendarEvent(eventId) {
    if (!confirm('Xóa sự kiện này?')) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/calendar/delete/${eventId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        if (data.success) {
            showNotification('🗑️ Đã xóa sự kiện', 'success');
            await loadCalendarEvents();
        } else {
            showNotification(`❌ Lỗi: ${data.error || 'Không thể xóa sự kiện'}`, 'error');
        }
    } catch (error) {
        showNotification(`❌ Lỗi: ${error.message}`, 'error');
    }
}

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
                const date = new Date(record.created_at).toLocaleString('vi-VN');
                historyDiv.innerHTML = `
                    <div style="font-weight: 600;">${getActionLabel(record.action_type)}</div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">${date}</div>
                    <div style="font-size: 13px; margin-top: 8px; color: var(--text-secondary);">${escapeHtml(record.user_message.substring(0, 100))}...</div>
                `;
                historyList.appendChild(historyDiv);
            });
        } else {
            historyList.innerHTML = '<p>Không có lịch sử</p>';
        }
    } catch (error) {
        historyList.innerHTML = `<p>❌ Lỗi: ${error.message}</p>`;
    }
}

function getActionLabel(actionType) {
    const labels = {
        'chat': '💬 Chat',
        'email_summary': '📧 Tóm tắt',
        'schedule_created': '📅 Tạo lịch'
    };
    return labels[actionType] || actionType;
}

// MODAL
function closeModalWindow() {
    if (emailDetailModal) emailDetailModal.classList.remove('show');
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    let result = text;
    result = result.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
    result = result.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
    result = result.replace(/\[([^\]]+)\]\(([^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    result = result.replace(/\n/g, '<br>');
    return result;
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
            showNotification('✅ Email đã gửi', 'success');
            composeForm.reset();
        }
    } catch (error) {
        showNotification('❌ Lỗi: ' + error.message, 'error');
    }
}

// DAILY REPORT
async function generateDailyReport() {
    const dateInput = document.getElementById('reportDate');
    const container = document.getElementById('dailyReportContainer');
    const btn = document.getElementById('generateReportBtn');
    
    if (!dateInput || !container) return;

    if (!dateInput.value) {
        alert('Vui lòng chọn ngày');
        return;
    }

    const [yyyy, mm, dd] = dateInput.value.split('-');
    const dateForApi = `${dd}/${mm}/${yyyy}`;

    container.innerHTML = '<p style="padding: 20px; text-align: center; color: #666;">⏳ Đang tải email và tạo báo cáo...</p>';
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
                    <p style="font-size: 16px; color: #E65100; margin-bottom: 10px;">⚠️ Chưa đăng nhập Gmail</p>
                    <button onclick="gmailLogin()" class="btn-primary">Đăng nhập Gmail</button>
                </div>
            `;
            return;
        }

        if (!data.success) {
            container.innerHTML = `
                <div style="padding: 20px; background: #FFEBEE; border-radius: 8px; margin: 20px;">
                    <p style="color: #C62828; font-weight: bold;">❌ Lỗi: ${escapeHtml(data.error || 'Không thể tạo báo cáo')}</p>
                    <p style="color: #666; font-size: 14px; margin-top: 10px;">Hãy thử: Kiểm tra kết nối Gmail, chọn ngày khác, hoặc xem F12 console</p>
                </div>
            `;
            return;
        }

        if (!data.rows || data.rows.length === 0) {
            container.innerHTML = `
                <div style="padding: 20px; text-align: center; background: #E8F5E9; border-radius: 8px; margin: 20px;">
                    <p style="font-size: 16px; color: #2E7D32; margin-bottom: 10px;">📭 Không có email trong ngày ${escapeHtml(data.date)}</p>
                    <p style="color: #666; font-size: 14px;">Hãy thử chọn ngày khác có nhiều email hơn</p>
                </div>
            `;
            return;
        }

        const rowsHtml = data.rows.map((row, i) => {
            const isMeeting = !!row.is_meeting;
            const meetingNote = isMeeting && row.meeting_note ? row.meeting_note : '';
            const actionButtons = isMeeting
                ? `
                    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
                        <button class="report-schedule-yes" data-report-index="${i}" style="padding:6px 12px;border:none;border-radius:6px;background:#4CAF50;color:white;cursor:pointer;">Yes</button>
                        <button class="report-schedule-no" data-report-index="${i}" style="padding:6px 12px;border:none;border-radius:6px;background:#9E9E9E;color:white;cursor:pointer;">No</button>
                    </div>
                `
                : '';

            return `
                <tr>
                    <td style="padding: 12px 8px; border-bottom: 1px solid #e0e0e0; text-align: center; vertical-align: top;">${i + 1}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; vertical-align: top;">
                        <div style="font-weight:600;">${escapeHtml(row.sender || 'N/A')}</div>
                        <div style="font-size:12px;color:#666;margin-top:4px;">${escapeHtml(row.subject || '')}</div>
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; vertical-align: top;">
                        <div>${escapeHtml(row.summary || 'Không có tóm tắt')}</div>
                        ${meetingNote ? `<div style="margin-top:8px;padding:8px 10px;background:#FFF8E1;border-left:4px solid #FFB300;border-radius:6px;font-size:13px;color:#8D6E63;">${escapeHtml(meetingNote)}</div>` : ''}
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; vertical-align: top; min-width: 180px;">
                        <span style="display:inline-block;padding:4px 8px;border-radius:999px;background:${isMeeting ? '#FFF3E0' : '#F5F5F5'};color:${isMeeting ? '#E65100' : '#666'};font-size:12px;font-weight:600;">${isMeeting ? '📅 Gợi ý tạo lịch' : 'Không phải cuộc họp'}</span>
                        ${actionButtons}
                    </td>
                </tr>
            `;
        }).join('');

        container.innerHTML = `
            <div style="padding: 20px;">
                <div style="margin-bottom: 16px; padding: 12px; background: #E8F5E9; border-radius: 8px;">
                    <strong style="color: #2E7D32;">📧 Báo cáo email ngày ${escapeHtml(data.date)}</strong><br>
                    <span style="color: #666; font-size: 14px;">Tổng: ${data.total_emails} email</span>
                </div>
                <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <thead>
                        <tr style="background: #4F46E5; color: white;">
                            <th style="padding: 12px 8px; text-align: center; width: 60px;">STT</th>
                            <th style="padding: 12px; text-align: left; width: 30%;">Người gửi</th>
                            <th style="padding: 12px; text-align: left;">Nội dung tóm tắt</th>
                            <th style="padding: 12px; text-align: left; width: 210px;">Chú thích / Hành động</th>
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
                showNotification('Đã bỏ qua gợi ý tạo lịch hẹn', 'info');
                if (yesBtn) yesBtn.disabled = true;
                if (noBtn) noBtn.disabled = true;
            });
        });
        showNotification(`✅ Đã tạo báo cáo ${data.total_emails} email`, 'success');
    } catch (error) {
        console.error('❌ Report generation error:', error);
        container.innerHTML = `
            <div style="padding: 20px; background: #FFEBEE; border-radius: 8px; margin: 20px;">
                <p style="color: #C62828; font-weight: bold;">❌ Lỗi kết nối: ${escapeHtml(error.message)}</p>
                <p style="color: #666; font-size: 14px; margin-top: 10px;">Kiểm tra:</p>
                <ul style="color: #666; font-size: 14px; margin-left: 20px;">
                    <li>Server đang chạy (http://localhost:5000)</li>
                    <li>Đã đăng nhập Gmail</li>
                    <li>Console (F12) để xem chi tiết</li>
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
        showNotification('❌ Không xác định được thời gian để tạo lịch hẹn', 'error');
        return;
    }

    const payload = {
        title: row.schedule_title || row.subject || 'Lịch hẹn từ email',
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
                    ? '✅ Đã tạo lịch hẹn và đồng bộ Google Calendar'
                    : '✅ Đã tạo lịch hẹn từ email',
                'success'
            );
            await loadSchedules();
            await loadCalendarEvents();
        } else {
            showNotification(`❌ Lỗi: ${data.error || 'Không thể tạo lịch hẹn'}`, 'error');
            if (yesBtn) yesBtn.disabled = false;
            if (noBtn) noBtn.disabled = false;
        }
    } catch (error) {
        showNotification(`❌ Lỗi: ${error.message}`, 'error');
        if (yesBtn) yesBtn.disabled = false;
        if (noBtn) noBtn.disabled = false;
    }
}
