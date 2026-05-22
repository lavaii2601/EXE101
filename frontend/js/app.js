// API Configuration
const API_BASE = '/api';

// DOM Elements - Cached for performance
const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const navBtns = document.querySelectorAll('[data-page]');
const tabBtns = document.querySelectorAll('[data-tab]');
const emailDetailModal = document.getElementById('emailDetailModal');
const closeModal = document.querySelector('.close');
const clearBtn = document.getElementById('clearBtn');
const composeForm = document.getElementById('composeForm');
const scheduleForm = document.getElementById('scheduleForm');
const gmailLoginBtn = document.getElementById('gmailLoginBtn');
const gmailLogoutBtn = document.getElementById('gmailLogoutBtn');
const gmailAccountBadge = document.getElementById('gmailAccountBadge');
const gmailProfileCard = document.getElementById('gmailProfileCard');
const gmailAvatar = document.getElementById('gmailAvatar');
const gmailName = document.getElementById('gmailName');
const gmailEmail = document.getElementById('gmailEmail');
const openGmailBtn = document.getElementById('openGmailBtn');
const emailFilterSelect = document.getElementById('emailFilterSelect');

// State
let currentPage = 'chat';
let currentEmailPage = 1;

// Initialize
document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
    console.log('🚀 Initializing app...');
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

async function apiFetch(url, options = {}) {
    return fetch(url, {
        credentials: 'include',
        ...options
    });
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
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function updateSidebarUserProfile(profile = {}) {
    const userName = document.getElementById('userName');
    const userAvatar = document.getElementById('userAvatar');
    const gmailStatus = document.getElementById('gmailStatus');

    const isConnected = !!profile.connected;
    const currentName = userName?.textContent?.trim() || '';
    const currentAvatar = userAvatar?.getAttribute('src') || '';
    const incomingName = (profile.name || '').trim();
    const displayName = isConnected && (!incomingName || incomingName === 'Teacher' || incomingName === 'Google User')
        ? (currentName && currentName !== 'Teacher' ? currentName : incomingName || 'Google User')
        : (incomingName || 'Teacher');
    const displayEmail = profile.email || '';
    const avatarUrl = profile.avatarUrl || '';
    const resolvedAvatar = isConnected && !avatarUrl ? currentAvatar : avatarUrl;

    if (userName) userName.textContent = displayName;

    if (userAvatar) {
        if (resolvedAvatar) {
            userAvatar.src = resolvedAvatar;
            userAvatar.textContent = '';
            userAvatar.style.backgroundColor = '';
            userAvatar.style.display = 'block';
        } else {
            const initials = (displayName || 'T').substring(0, 1).toUpperCase();
            userAvatar.removeAttribute('src');
            userAvatar.style.backgroundColor = '#4F46E5';
            userAvatar.style.display = 'flex';
            userAvatar.style.alignItems = 'center';
            userAvatar.style.justifyContent = 'center';
            userAvatar.style.fontSize = '20px';
            userAvatar.style.fontWeight = 'bold';
            userAvatar.style.color = 'white';
            userAvatar.textContent = initials;
        }
    }

    if (gmailStatus) {
        gmailStatus.textContent = isConnected
            ? `Đã kết nối Gmail${displayEmail ? ` • ${displayEmail}` : ''}`
            : 'Chưa kết nối Gmail';
    }
}

function setupEventListeners() {
    console.log('📋 Setting up event listeners');
    
    // Navigation buttons
    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            console.log(`📍 Nav click: ${btn.dataset.page}`);
            handlePageChange(btn);
        });
    });
    
    // Chat send
    if (sendBtn) {
        sendBtn.addEventListener('click', () => {
            console.log('📨 Send button clicked');
            sendMessage();
        });
    }
    
    // Enter to send
    if (userInput) {
        userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                console.log('⌨️ Enter pressed');
                sendMessage();
            }
        });
    }
    
    // Tab buttons
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            console.log(`📂 Tab click: ${btn.dataset.tab}`);
            handleTabChange(btn);
        });
    });
    
    // Modal close
    if (closeModal) {
        closeModal.addEventListener('click', closeModalWindow);
    }
    if (emailDetailModal) {
        emailDetailModal.addEventListener('click', (e) => {
            if (e.target === emailDetailModal) closeModalWindow();
        });
    }
    
    // Forms
    if (composeForm) composeForm.addEventListener('submit', handleComposeSubmit);
    if (scheduleForm) scheduleForm.addEventListener('submit', handleScheduleSubmit);
    
    const editForm = document.getElementById('editScheduleForm');
    if (editForm) editForm.addEventListener('submit', handleEditScheduleSubmit);
    
    const editModal = document.getElementById('editScheduleModal');
    if (editModal) {
        const closeBtn = editModal.querySelector('.close');
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
function handlePageChange(btn) {
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
async function sendMessage() {
    const message = userInput.value.trim();
    if (!message) {
        console.warn('⚠️ Empty message');
        return;
    }
    
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
            body: JSON.stringify({ message })
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
            
            if (data.schedule_created) {
                showNotification(
                    `✅ Lịch hẹn "${data.schedule_created.title}" đã được tạo`,
                    'success'
                );
                try {
                    await loadSchedules();
                } catch (e) {
                    console.log('Schedule refresh noted');
                }
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
        data.emails.forEach(email => {
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
            
            // Add mark as read/unread handler
            const markButton = emailDiv.querySelector(`.${markButtonClass}`);
            markButton.addEventListener('click', async (e) => {
                e.stopPropagation();
                await toggleEmailReadStatus(email.id, email.is_unread);
            });
            
            emailsList.appendChild(emailDiv);
        });
        
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
