// API Configuration
const API_BASE = '/api';

// DOM Elements - will be selected during initApp after DOM is ready
let chatMessages;
let chatJumpLatest;
let userInput;
let sendBtn;
let newChatBtn;
let newChatSidebarBtn;
let newChatPanelBtn;
let chatSessionsList;
let chatRetentionSelect;
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
let userModeSelect;
let userModeModal;
let emailSearchInput;
let emailSearchTimer;

// State
let currentPage = 'overview';
let currentEmailPage = 1;
let currentWeekStart = getMonday(new Date());
let currentDetailEmail = null;
let currentUserMode = 'worker';
let pendingUserMode = '';
let userModeRequired = false;
let pendingPageAfterMode = '';
let isAuthenticated = false;
let lastAuthStatus = null;
let currentLanguage = localStorage.getItem('flowmate-language') === 'en' ? 'en' : 'vi';
let activeChatSessionId = localStorage.getItem('flowmate-active-chat-session') || createChatSessionId();
let activeChatSessionTitle = localStorage.getItem('flowmate-active-chat-title') || '';
let agentProfile = null;
let newMailPollTimer = null;
let lastSeenMailId = localStorage.getItem('flowmate-last-mail-id') || null;
// Gmail push should be configured in production for true server-side push.
// This short watcher is the resilient foreground fallback and feels instant
// even when Pub/Sub is unavailable or the browser just resumed.
const NEW_MAIL_POLL_INTERVAL_MS = 5000;

function createChatSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
        const value = Math.random() * 16 | 0;
        const next = char === 'x' ? value : (value & 0x3 | 0x8);
        return next.toString(16);
    });
}

function persistChatSessionId() {
    localStorage.setItem('flowmate-active-chat-session', activeChatSessionId);
}

function persistChatSessionTitle() {
    if (activeChatSessionTitle) {
        localStorage.setItem('flowmate-active-chat-title', activeChatSessionTitle);
    } else {
        localStorage.removeItem('flowmate-active-chat-title');
    }
}

const I18N = {
    vi: {
        'nav.chat': 'Chat',
        'nav.overview': 'Tổng hợp',
        'nav.email': 'Email',
        'nav.calendar': 'Lịch',
        'nav.history': 'Lịch sử',
        'nav.settings': 'Cài đặt',
        'chat.new': 'Chat mới',
        'chat.newHint': 'Bắt đầu hội thoại sạch',
        'chat.sessions': 'Đoạn chat',
        'chat.retentionHint': 'Lưu 1-3 tháng',
        'chat.saveCurrent': 'Lưu chat hiện tại',
        'chat.oneMonth': '1 tháng',
        'chat.twoMonths': '2 tháng',
        'chat.threeMonths': '3 tháng',
        'chat.noSaved': 'Chưa có đoạn chat cũ.',
        'chat.jumpLatest': '↓ Tin nhắn mới nhất',
        'common.clear': 'Xóa',
        'common.refresh': 'Làm mới',
        'overview.title': 'Tổng hợp thông tin',
        'overview.subtitle': 'AI tự động gom deadline, email và task trong ngày được chọn.',
        'overview.refresh': 'Tổng hợp ngày này',
        'email.title': 'Quản lý Email',
        'email.search': 'Tìm theo người gửi, tiêu đề hoặc nội dung...',
        'email.includeRead': 'Giữ email đã đọc',
        'email.openGmail': 'Mở Gmail',
        'email.login': 'Đăng nhập / Đổi tài khoản',
        'email.logout': 'Đăng xuất Gmail',
        'email.inbox': 'Hộp thư đến',
        'email.report': 'Báo cáo theo ngày',
        'email.compose': 'Soạn thảo',
        'settings.title': 'Cài đặt',
        'settings.subtitle': 'Quản lý tài khoản, giao diện, dữ liệu và kết nối dịch vụ.',
        'settings.languageSection': 'NGÔN NGỮ',
        'settings.language': 'Ngôn ngữ hiển thị',
        'settings.languageHint': 'Áp dụng ngay và được ghi nhớ trên thiết bị này.',
        'settings.savedLanguage': 'Đã lưu ngôn ngữ',
        'filter.all': 'Tất cả',
        'filter.education': 'Giáo dục',
        'filter.work': 'Công việc',
        'filter.meeting': 'Họp',
        'filter.promotion': 'Khuyến mãi',
        'filter.finance': 'Tài chính',
        'filter.personal': 'Cá nhân',
        'filter.other': 'Khác'
    },
    en: {
        'nav.chat': 'Chat',
        'nav.overview': 'Overview',
        'nav.email': 'Email',
        'nav.calendar': 'Calendar',
        'nav.history': 'Activity',
        'nav.settings': 'Settings',
        'chat.new': 'New chat',
        'chat.newHint': 'Start a clean conversation',
        'chat.sessions': 'Chats',
        'chat.retentionHint': 'Saved for 1-3 months',
        'chat.saveCurrent': 'Save current chat',
        'chat.oneMonth': '1 month',
        'chat.twoMonths': '2 months',
        'chat.threeMonths': '3 months',
        'chat.noSaved': 'No saved chats yet.',
        'chat.jumpLatest': '↓ Latest message',
        'common.clear': 'Clear',
        'common.refresh': 'Refresh',
        'overview.title': 'Daily overview',
        'overview.subtitle': 'AI automatically summarizes deadlines, email, and tasks for the selected day.',
        'overview.refresh': 'Summarize day',
        'email.title': 'Email Management',
        'email.search': 'Search sender, subject, or content...',
        'email.includeRead': 'Include read email',
        'email.openGmail': 'Open Gmail',
        'email.login': 'Sign in / Switch account',
        'email.logout': 'Sign out of Gmail',
        'email.inbox': 'Inbox',
        'email.report': 'Daily report',
        'email.compose': 'Compose',
        'settings.title': 'Settings',
        'settings.subtitle': 'Manage your account, appearance, data, and connected services.',
        'settings.languageSection': 'LANGUAGE',
        'settings.language': 'Display language',
        'settings.languageHint': 'Applied immediately and remembered on this device.',
        'settings.savedLanguage': 'Language saved',
        'filter.all': 'All',
        'filter.education': 'Education',
        'filter.work': 'Work',
        'filter.meeting': 'Meetings',
        'filter.promotion': 'Promotions',
        'filter.finance': 'Finance',
        'filter.personal': 'Personal',
        'filter.other': 'Other'
    }
};

function t(key) {
    return I18N[currentLanguage]?.[key] || I18N.vi[key] || key;
}

function ui(vietnamese, english) {
    return currentLanguage === 'en' ? english : vietnamese;
}

const STATIC_ENGLISH_TEXT = {
    'Không gian làm việc': 'Workspace',
    'Xóa lịch sử': 'Clear history',
    'Gửi': 'Send',
    'Người nhận': 'Recipient',
    'Tiêu đề': 'Subject',
    'Nội dung': 'Content',
    'Gửi email': 'Send email',
    'Chọn ngày': 'Select date',
    'Tạo báo cáo': 'Generate report',
    'Lịch': 'Calendar',
    'Mở Google Calendar': 'Open Google Calendar',
    'Tạo sự kiện': 'Create event',
    '‹ Tuần trước': '‹ Previous week',
    'Tuần sau ›': 'Next week ›',
    'Tuần này': 'This week',
    'Lịch sử hoạt động': 'Activity history',
    'TÀI KHOẢN': 'ACCOUNT',
    'Người dùng': 'User',
    'Làm mới trạng thái': 'Refresh status',
    'CÁ NHÂN HÓA': 'PERSONALIZATION',
    'Chế độ người dùng': 'User mode',
    'Thay đổi': 'Change',
    'Giao diện tối': 'Dark mode',
    'Giảm độ sáng và tăng độ tương phản.': 'Reduce brightness and increase contrast.',
    'KẾT NỐI': 'CONNECTION',
    'Đang kiểm tra...': 'Checking...',
    'Kết nối': 'Connect',
    'DỮ LIỆU': 'DATA',
    'Xóa toàn bộ lịch sử': 'Clear all history',
    'Xóa chat, hoạt động email và lịch đã lưu.': 'Delete saved chat, email activity, and calendar history.',
    'Xóa dữ liệu': 'Delete data',
    'Đăng xuất Gmail': 'Sign out of Gmail',
    'Ngắt quyền truy cập Gmail và Calendar.': 'Revoke access to Gmail and Calendar.',
    'Đăng xuất': 'Sign out',
    'CÁ NHÂN HÓA FLOWMATE': 'PERSONALIZE FLOWMATE',
    'Bạn đang làm việc theo cách nào?': 'How do you work?',
    'Mỗi mode thay đổi ưu tiên email, gợi ý lịch và cách AI phản hồi.': 'Each mode adjusts email priorities, calendar suggestions, and AI responses.',
    'Tóm tắt': 'Summarize',
    'Trả lời tự động': 'Draft reply',
    'Tạo lịch hẹn mới': 'Create appointment',
    'Mô tả': 'Description',
    'Ngày giờ bắt đầu': 'Start date and time',
    'Ngày giờ kết thúc': 'End date and time',
    'Ngày giờ kết thúc (tự tính)': 'End date and time (auto)',
    'Thời lượng (phút)': 'Duration (minutes)',
    'Địa điểm': 'Location',
    'Người tham dự (email, cách nhau bằng dấu phẩy)': 'Attendees (comma-separated emails)',
    'Tạo lịch hẹn': 'Create appointment',
    'Hủy': 'Cancel',
    'Chỉnh sửa lịch hẹn': 'Edit appointment',
    'Ngày giờ': 'Date and time',
    'Lưu thay đổi': 'Save changes',
    'Xác nhận tạo lịch hẹn': 'Confirm appointment',
    'Ngày': 'Date',
    'Bắt đầu': 'Start',
    'Kết thúc': 'End',
    'Hình thức': 'Format',
    'Trực tiếp': 'In person',
    'Điện thoại': 'Phone',
    'Đối tượng': 'Participants',
    'Nội dung cuộc hẹn': 'Appointment details',
    'Xác nhận tạo lịch': 'Confirm appointment'
};

const STATIC_ENGLISH_PLACEHOLDERS = {
    'Nhập tin nhắn của bạn...': 'Type your message...',
    'Tiêu đề email': 'Email subject',
    'Nội dung email': 'Email content',
    'Tiêu đề lịch hẹn': 'Appointment title',
    'Mô tả chi tiết': 'Detailed description',
    'Ví dụ: 60': 'Example: 60',
    'Địa điểm': 'Location',
    'Tiêu đề (ví dụ: Họp phụ huynh)': 'Title (for example: Parent meeting)',
    'Ví dụ: phụ huynh, học sinh, email@example.com': 'Example: parents, students, email@example.com',
    'Mô tả / Nội dung cuộc hẹn': 'Description / Appointment details'
};

// STATIC_ENGLISH_TEXT/PLACEHOLDERS never change at runtime, so their reverse
// (EN -> VI) lookups are computed once here instead of on every language toggle.
const STATIC_VIETNAMESE_TEXT = Object.fromEntries(Object.entries(STATIC_ENGLISH_TEXT).map(([vi, en]) => [en, vi]));
const STATIC_VIETNAMESE_PLACEHOLDERS = Object.fromEntries(Object.entries(STATIC_ENGLISH_PLACEHOLDERS).map(([vi, en]) => [en, vi]));

function applyStaticLanguage() {
    const userContentSelector = '#chatMessages, #emailsList, #emailDetail, #dailyReportContainer, #historyList, #schedulesList';
    document.querySelectorAll('body *').forEach((element) => {
        if (element.closest(userContentSelector)) return;
        if (element.children.length === 0) {
            const text = element.textContent.trim();
            const replacement = currentLanguage === 'en' ? STATIC_ENGLISH_TEXT[text] : STATIC_VIETNAMESE_TEXT[text];
            if (replacement) element.textContent = replacement;
        }
        if ('placeholder' in element && element.placeholder) {
            const replacement = currentLanguage === 'en'
                ? STATIC_ENGLISH_PLACEHOLDERS[element.placeholder]
                : STATIC_VIETNAMESE_PLACEHOLDERS[element.placeholder];
            if (replacement) element.placeholder = replacement;
        }
    });
    document.title = ui('FlowMate - Không gian làm việc thông minh', 'FlowMate - Intelligent Workspace');
    const filterButton = document.getElementById('emailFilterBtn');
    if (filterButton) filterButton.title = ui('Lọc email', 'Filter email');
}

function applyLanguage() {
    document.documentElement.lang = currentLanguage;
    document.querySelectorAll('[data-i18n]').forEach((element) => {
        element.textContent = t(element.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((element) => {
        element.placeholder = t(element.dataset.i18nPlaceholder);
    });
    document.querySelectorAll('[data-language]').forEach((button) => {
        button.classList.toggle('active', button.dataset.language === currentLanguage);
    });
    applyStaticLanguage();
    updateUserModeUI(currentUserMode);
    updateEmailFilterUI();
    updateSidebarTooltips();
}

function updateSidebarTooltips() {
    document.querySelectorAll('.sidebar-nav .nav-btn').forEach((button) => {
        const label = button.querySelector('.nav-label')?.textContent?.trim() || '';
        button.dataset.tooltip = label;
        button.setAttribute('aria-label', label);
    });
    const clearButton = document.getElementById('clearBtn');
    if (clearButton) {
        const label = clearButton.querySelector('.sidebar-footer-label')?.textContent?.trim() || t('common.clear');
        clearButton.dataset.tooltip = label;
        clearButton.setAttribute('aria-label', label);
    }
}

function setLanguage(language) {
    currentLanguage = language === 'en' ? 'en' : 'vi';
    localStorage.setItem('flowmate-language', currentLanguage);
    applyLanguage();
    setSettingsState(t('settings.savedLanguage'));
}

function updateEmailFilterUI() {
    if (!emailFilterSelect) return;
    const value = emailFilterSelect.value || 'all';
    const label = document.getElementById('emailFilterLabel');
    if (label) label.textContent = t(`filter.${value}`);
    document.querySelectorAll('#emailFilterPopup [data-filter]').forEach((button) => {
        const filter = button.dataset.filter;
        button.textContent = t(`filter.${filter}`);
        button.classList.toggle('active', filter === value);
    });
}

const USER_MODES = {
    student: {
        initial: 'ST',
        label: 'Sinh viên',
        labelEn: 'Student',
        description: 'Ưu tiên môn học, bài tập, deadline, email lớp, lịch thi và kế hoạch ôn tập.',
        descriptionEn: 'Prioritize courses, assignments, deadlines, class email, exams, and study plans.'
    },
    worker: {
        initial: 'VP',
        label: 'Nhân viên văn phòng',
        labelEn: 'Office worker',
        description: 'Ưu tiên email công việc, cuộc họp, báo cáo và việc cần theo dõi.',
        descriptionEn: 'Prioritize work email, meetings, reports, and follow-up tasks.'
    },
    freelancer: {
        initial: 'FR',
        label: 'Freelancer',
        labelEn: 'Freelancer',
        description: 'Ưu tiên khách hàng, dự án, hóa đơn và lịch bàn giao.',
        descriptionEn: 'Prioritize clients, projects, invoices, and delivery dates.'
    },
    mentor: {
        initial: 'MT',
        label: 'Mentor',
        labelEn: 'Mentor',
        description: 'Ưu tiên học viên, lịch hướng dẫn và hạn phản hồi.',
        descriptionEn: 'Prioritize students, mentoring sessions, and feedback deadlines.'
    },
    teacher: {
        initial: 'GV',
        label: 'Giáo viên',
        labelEn: 'Teacher',
        description: 'Quản lý lớp học, chương trình và tương tác với học sinh.',
        descriptionEn: 'Manage classes, curriculum, and student engagement.'
    },
    business: {
        initial: 'KD',
        label: 'Kinh doanh',
        labelEn: 'Business',
        description: 'Ưu tiên vận hành, quyết định, đội nhóm và rủi ro.',
        descriptionEn: 'Prioritize operations, decisions, teams, and risks.'
    },
    creator: {
        initial: 'CR',
        label: 'Nhà sáng tạo',
        labelEn: 'Creator',
        description: 'Ưu tiên thương hiệu, chiến dịch và lịch nội dung.',
        descriptionEn: 'Prioritize brands, campaigns, and content schedules.'
    }
};

const ONBOARDING_MODE_KEYS = ['student', 'worker', 'freelancer', 'mentor', 'teacher', 'business', 'creator'];

function modeLabel(mode) {
    return currentLanguage === 'en' ? (mode.labelEn || mode.label) : mode.label;
}

function modeDescription(mode) {
    return currentLanguage === 'en' ? (mode.descriptionEn || mode.description) : mode.description;
}

// Initialize
document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
    console.log('🚀 Initializing app...');
    // Select DOM elements now that DOMContentLoaded fired
    chatMessages = document.getElementById('chatMessages');
    chatJumpLatest = document.getElementById('chatJumpLatest');
    userInput = document.getElementById('userInput');
    sendBtn = document.getElementById('sendBtn');
    newChatBtn = document.getElementById('newChatBtn');
    newChatSidebarBtn = document.getElementById('newChatSidebarBtn');
    newChatPanelBtn = document.getElementById('newChatPanelBtn');
    chatSessionsList = document.getElementById('chatSessionsList');
    chatRetentionSelect = document.getElementById('chatRetentionSelect');
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
    userModeSelect = document.getElementById('userModeSelect');
    userModeModal = document.getElementById('userModeModal');
    emailSearchInput = document.getElementById('emailSearchInput');
    setupAuthGate();
    setupWorkspaceShell();
    applyLanguage();
    setupDateTimePreviews();
    const savedTheme = localStorage.getItem('flowmate-theme');
    document.body.classList.toggle('dark-theme', savedTheme === 'dark');
    // Normalize page visibility on startup to avoid stale CSS/inline styles
    normalizePages();
    
    // Manually attach event listeners (setupEventListeners has scope issues)
    try {
        // Send message button
        if (sendBtn) {
            sendBtn.addEventListener('click', () => sendMessage());
        }
        if (newChatBtn) {
            newChatBtn.addEventListener('click', startNewChat);
        }
        if (newChatSidebarBtn) {
            newChatSidebarBtn.addEventListener('click', startNewChat);
        }
        if (newChatPanelBtn) {
            newChatPanelBtn.addEventListener('click', startNewChat);
        }
        if (chatRetentionSelect) {
            chatRetentionSelect.addEventListener('change', updateChatRetention);
        }
        if (chatMessages) {
            chatMessages.addEventListener('scroll', () => {
                if (!chatJumpLatest) return;
                const distFromBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight;
                chatJumpLatest.classList.toggle('visible', distFromBottom > 200);
            });
        }
        if (chatJumpLatest) {
            chatJumpLatest.addEventListener('click', () => {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            });
        }
        
        // Enter key in input
        if (userInput) {
            userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }
        
        // Page navigation
        navBtns.forEach(btn => {
            btn.addEventListener('click', () => handlePageChange(btn));
        });
        
        // Tab switching
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => handleTabChange(btn));
        });

        const refreshOverviewBtn = document.getElementById('refreshOverviewBtn');
        const overviewDate = document.getElementById('overviewDate');
        if (overviewDate && !overviewDate.value) {
            overviewDate.value = formatDateForApi(new Date());
        }
        if (refreshOverviewBtn) {
            refreshOverviewBtn.addEventListener('click', () => loadOverviewPage({ force: true }));
        }
        if (overviewDate) {
            overviewDate.addEventListener('change', () => loadOverviewPage({ force: true }));
        }

        // New schedule form submit
        if (scheduleForm) {
            scheduleForm.addEventListener('submit', handleScheduleSubmit);
            bindScheduleTimeLogic();
        }

        // Edit schedule form submit
        const editScheduleForm = document.getElementById('editScheduleForm');
        if (editScheduleForm) {
            editScheduleForm.addEventListener('submit', handleEditScheduleSubmit);
        }
        bindEditScheduleModal();

        // Create event button (opens the new-schedule popup)
        const createEventBtn = document.getElementById('createEventBtn');
        if (createEventBtn) {
            createEventBtn.addEventListener('click', () => openNewScheduleModal());
        }

        // New Schedule modal close handlers (X button and Hủy button)
        const newScheduleModal = document.getElementById('newScheduleModal');
        if (newScheduleModal) {
            newScheduleModal.querySelectorAll('[data-modal="newScheduleModal"]').forEach(el => {
                el.addEventListener('click', () => closeNewScheduleModal());
            });
        }

        // Compose email form submit
        if (composeForm) {
            composeForm.addEventListener('submit', handleComposeSubmit);
        }

        // Email detail modal action buttons
        const summarizeBtn = document.getElementById('summarizeBtn');
        if (summarizeBtn) {
            summarizeBtn.addEventListener('click', handleSummarizeEmail);
        }
        const replyBtn = document.getElementById('replyBtn');
        if (replyBtn) {
            replyBtn.addEventListener('click', handleAutoReply);
        }
        const emailDetailCloseBtn = emailDetailModal
            ? emailDetailModal.querySelector('.email-detail-close')
            : null;
        if (emailDetailCloseBtn) {
            emailDetailCloseBtn.addEventListener('click', closeModalWindow);
        }
        if (emailDetailModal) {
            emailDetailModal.addEventListener('click', (event) => {
                if (event.target === emailDetailModal) closeModalWindow();
            });
        }
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && emailDetailModal?.classList.contains('show')) {
                closeModalWindow();
            }
            if (event.key === 'Escape' && userModeModal?.classList.contains('show')) {
                closeUserModeModal();
            }
        });

        // Clear history
        if (clearBtn) {
            clearBtn.addEventListener('click', clearConversation);
        }

        // Gmail buttons
        const userAvatar = document.getElementById('userAvatar');
        if (userAvatar) userAvatar.addEventListener('click', gmailLogin);
        if (gmailLoginBtn) gmailLoginBtn.addEventListener('click', gmailLogin);
        if (gmailLogoutBtn) gmailLogoutBtn.addEventListener('click', gmailLogout);
        if (openGmailBtn) openGmailBtn.addEventListener('click', () => openExternalUrl('https://mail.google.com'));
        if (userModeSelect) {
            userModeSelect.addEventListener('change', () => saveUserMode(userModeSelect.value));
            updateUserModeUI(currentUserMode);
        }
        const openUserModeBtn = document.getElementById('openUserModeBtn');
        if (openUserModeBtn) openUserModeBtn.addEventListener('click', () => openUserModeModal(false));
        const userModeClose = userModeModal?.querySelector('.user-mode-close');
        if (userModeClose) userModeClose.addEventListener('click', closeUserModeModal);
        const userModeCancelBtn = document.getElementById('userModeCancelBtn');
        if (userModeCancelBtn) userModeCancelBtn.addEventListener('click', closeUserModeModal);
        const userModeConfirmBtn = document.getElementById('userModeConfirmBtn');
        if (userModeConfirmBtn) {
            userModeConfirmBtn.addEventListener('click', () => {
                if (pendingUserMode) saveUserMode(pendingUserMode, true);
            });
        }
        if (userModeModal) {
            userModeModal.addEventListener('click', (event) => {
                if (event.target === userModeModal) closeUserModeModal();
            });
        }

        // Email filter
        if (emailFilterSelect) {
            emailFilterSelect.addEventListener('change', () => {
                console.log(`🔍 Filter changed: ${emailFilterSelect.value}`);
                updateEmailFilterUI();
                currentEmailPage = 1;
                loadEmails(1, { cacheOnly: true });
            });
        }

        const emailFilterBtn = document.getElementById('emailFilterBtn');
        const emailFilterPopup = document.getElementById('emailFilterPopup');
        if (emailFilterBtn && emailFilterPopup) {
            emailFilterBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                const isOpen = emailFilterPopup.classList.toggle('show');
                emailFilterBtn.setAttribute('aria-expanded', String(isOpen));
            });
            emailFilterPopup.querySelectorAll('[data-filter]').forEach((button) => {
                button.addEventListener('click', () => {
                    emailFilterSelect.value = button.dataset.filter;
                    emailFilterSelect.dispatchEvent(new Event('change'));
                    emailFilterPopup.classList.remove('show');
                    emailFilterBtn.setAttribute('aria-expanded', 'false');
                });
            });
            document.addEventListener('click', (event) => {
                if (!event.target.closest('.email-filter-control')) {
                    emailFilterPopup.classList.remove('show');
                    emailFilterBtn.setAttribute('aria-expanded', 'false');
                }
            });
        }
        if (emailSearchInput) {
            emailSearchInput.addEventListener('input', () => {
                clearTimeout(emailSearchTimer);
                emailSearchTimer = setTimeout(() => {
                    currentEmailPage = 1;
                    loadEmails(1, { cacheOnly: true });
                }, 300);
            });
        }
        const clearEmailSearchBtn = document.getElementById('clearEmailSearchBtn');
        if (clearEmailSearchBtn) {
            clearEmailSearchBtn.addEventListener('click', () => {
                if (!emailSearchInput) return;
                emailSearchInput.value = '';
                currentEmailPage = 1;
                loadEmails(1, { cacheOnly: true });
                emailSearchInput.focus();
            });
        }
        const settingsModeBtn = document.getElementById('settingsModeBtn');
        if (settingsModeBtn) settingsModeBtn.addEventListener('click', () => openUserModeModal(false));
        const settingsRefreshBtn = document.getElementById('settingsRefreshBtn');
        if (settingsRefreshBtn) settingsRefreshBtn.addEventListener('click', loadSettingsPage);
        const settingsDarkMode = document.getElementById('settingsDarkMode');
        if (settingsDarkMode) {
            settingsDarkMode.checked = document.body.classList.contains('dark-theme');
            settingsDarkMode.addEventListener('change', () => {
                document.body.classList.toggle('dark-theme', settingsDarkMode.checked);
                localStorage.setItem('flowmate-theme', settingsDarkMode.checked ? 'dark' : 'light');
                setSettingsState('Đã lưu giao diện');
            });
        }
        const settingsGoogleBtn = document.getElementById('settingsGoogleBtn');
        if (settingsGoogleBtn) settingsGoogleBtn.addEventListener('click', handleSettingsGoogleAction);
        const settingsLogoutBtn = document.getElementById('settingsLogoutBtn');
        if (settingsLogoutBtn) settingsLogoutBtn.addEventListener('click', gmailLogout);
        const settingsClearDataBtn = document.getElementById('settingsClearDataBtn');
        if (settingsClearDataBtn) settingsClearDataBtn.addEventListener('click', clearAllUserHistory);
        document.querySelectorAll('[data-language]').forEach((button) => {
            button.addEventListener('click', () => setLanguage(button.dataset.language));
        });

        // Include read checkbox
        const includeReadCheckbox = document.getElementById('includeReadCheckbox');
        if (includeReadCheckbox) {
            includeReadCheckbox.addEventListener('change', () => {
                console.log(`📬 Include read: ${includeReadCheckbox.checked}`);
                currentEmailPage = 1;
                loadEmails(1, { cacheOnly: true });
            });
        }

        // Refresh emails
        const refreshEmailsBtn = document.getElementById('refreshEmailsBtn');
        if (refreshEmailsBtn && refreshEmailsBtn.dataset.refreshBound !== 'true') {
            refreshEmailsBtn.dataset.refreshBound = 'true';
            refreshEmailsBtn.addEventListener('click', () => {
                console.log('🔄 Refreshing emails');
                refreshEmailsFromGmail()
                    .catch(err => console.error('Cache clear error:', err));
            });
        }

        // Generate daily report
        const generateReportBtn = document.getElementById('generateReportBtn');
        if (generateReportBtn) {
            generateReportBtn.addEventListener('click', generateDailyReport);
        }

        // Calendar buttons
    const refreshCalendarBtn = document.getElementById('refreshCalendarBtn');
    if (refreshCalendarBtn && refreshCalendarBtn.dataset.refreshBound !== 'true') {
        refreshCalendarBtn.dataset.refreshBound = 'true';
        refreshCalendarBtn.addEventListener('click', () => {
            console.log('🔄 Refreshing calendar events');
            scheduleMeetingSuggestionRefresh({ scan: false, delay: 0 });
            refreshCalendarScheduleData({ notify: true, continueOnError: true })
                .catch(err => console.warn('Schedule refresh error:', err));
        });
    }

        const openCalendarBtn = document.getElementById('openCalendarBtn');
        if (openCalendarBtn) {
            openCalendarBtn.addEventListener('click', () => openExternalUrl('https://calendar.google.com'));
        }

        // Weekly schedule table navigation
        bindWeekNavigation();

        // Listen for postMessage from OAuth popup to update UI without redirect
        window.addEventListener('message', (ev) => {
            try {
                if (ev.origin === window.location.origin && ev.data && ev.data.type === 'gmail_auth' && ev.data.status === 'success') {
                    console.log('📥 Received gmail_auth success message');
                    refreshAuthButtons();
                    loadUserProfile().then(() => {
                        if (userModeRequired) {
                            pendingPageAfterMode = 'overview';
                        } else {
                            showWorkspace();
                            if (currentPage === 'emails') {
                                setTimeout(() => loadEmails(1, { cacheOnly: true }), 300);
                            }
                        }
                    });
                }
            } catch (e) {
                console.warn('PostMessage handling error', e);
            }
        });

        setupSidebarMenu();

        console.log('✅ Event listeners attached');
    } catch (err) {
        console.error('❌ Error attaching event listeners:', err);
    }
    
    await checkOAuthCallback();
    const authenticated = await resolveInitialAuthState();
    if (!authenticated) {
        checkRuntimeConfig();
        console.log('✅ App initialized in signed-out state');
        return;
    }

    if (await ensureGoogleCalendarPermission()) {
        return;
    }

    await loadUserProfile();
    if (!userModeRequired) {
        showWorkspace();
        updateChatSessionTitle();
        await loadChatSessions();
        await loadChatHistory();
        const activeNavButton = document.querySelector('.sidebar-nav .nav-btn.active');
        if (activeNavButton) {
            await handlePageChange(activeNavButton);
        }
    }
    await refreshAuthButtons();
    startNewMailWatcher();
    checkRuntimeConfig();
    loadAgentProfile();
    
    // Auto-load emails if user is on emails page and authenticated
    if (currentPage === 'emails') {
        console.log('📧 Auto-loading emails on init...');
        setTimeout(() => loadEmails(1, { cacheOnly: true }), 500);
    }
    
    console.log('✅ App initialized');
}

function setupAuthGate() {
    const loginButton = document.getElementById('authGateLoginBtn');
    if (loginButton) loginButton.addEventListener('click', gmailLogin);
    showAuthGate(ui('Đang kiểm tra phiên đăng nhập...', 'Checking your sign-in session...'), true);
}

function showAuthGate(message = '', loading = false) {
    const gate = document.getElementById('authGate');
    const status = document.getElementById('authGateStatus');
    const button = document.getElementById('authGateLoginBtn');
    const label = button?.querySelector('.auth-button-label');
    document.body.classList.remove('workspace-ready');
    gate?.classList.remove('is-hidden');
    gate?.classList.remove('is-mode-stage');
    gate?.classList.toggle('is-loading', loading);
    if (status) status.textContent = message;
    if (button) button.disabled = loading;
    if (label) {
        label.textContent = loading
            ? ui('Đang xác thực...', 'Authenticating...')
            : ui('Đăng nhập với Google', 'Sign in with Google');
    }
    document.getElementById('workspaceApp')?.setAttribute('aria-hidden', 'true');
}

function showWorkspace() {
    const gate = document.getElementById('authGate');
    gate?.classList.add('is-hidden');
    gate?.classList.remove('is-loading', 'is-mode-stage');
    document.body.classList.add('workspace-ready');
    document.getElementById('workspaceApp')?.setAttribute('aria-hidden', 'false');
}

function showModeSelectionStage() {
    const gate = document.getElementById('authGate');
    gate?.classList.remove('is-hidden', 'is-loading');
    gate?.classList.add('is-mode-stage');
    document.body.classList.remove('workspace-ready');
    document.getElementById('workspaceApp')?.setAttribute('aria-hidden', 'true');
}

async function resolveInitialAuthState() {
    try {
        const response = await fetch(`${API_BASE}/email/auth-status`, {
            credentials: 'include',
            headers: { Accept: 'application/json' }
        });
        const data = await response.json();
        lastAuthStatus = data;
        isAuthenticated = !!(response.ok && data.authenticated);
    } catch (error) {
        console.error('Initial auth check failed:', error);
        lastAuthStatus = null;
        isAuthenticated = false;
    }

    if (!isAuthenticated) {
        showAuthGate(ui(
            'Đăng nhập để truy cập không gian làm việc thông minh của bạn.',
            'Sign in to access your intelligent workspace.'
        ));
    }
    return isAuthenticated;
}

function calendarPermissionAttemptKey(authStatus) {
    const userId = authStatus?.user_id || authStatus?.gmail_email || 'default';
    return `flowmate-calendar-permission-attempt:${userId}`;
}

async function ensureGoogleCalendarPermission(options = {}) {
    const authStatus = options.authStatus || lastAuthStatus;
    if (!authStatus?.authenticated || authStatus.calendar_write_connected) return false;

    const attemptKey = calendarPermissionAttemptKey(authStatus);
    if (sessionStorage.getItem(attemptKey) === '1') return false;
    sessionStorage.setItem(attemptKey, '1');

    showAuthGate(ui(
        'Đang hoàn tất quyền Google Calendar...',
        'Finishing Google Calendar permission...'
    ), true);

    try {
        const response = await fetch(`${API_BASE}/email/auth_url?reason=calendar_scope`, {
            credentials: 'include',
            headers: { Accept: 'application/json' }
        });
        const data = await response.json();
        if (!response.ok || !data.auth_url) {
            console.warn('Unable to start Calendar permission OAuth:', data);
            showAuthGate(ui(
                'Không thể tự cấp quyền Calendar. Bạn vẫn có thể vào app và cấp lại quyền trong Cài đặt.',
                'Unable to auto-grant Calendar permission. You can still open the app and reconnect in Settings.'
            ));
            return false;
        }
        window.location.href = data.auth_url;
        return true;
    } catch (error) {
        console.warn('Calendar permission OAuth failed:', error);
        showAuthGate(ui(
            'Không thể kết nối Google để hoàn tất quyền Calendar.',
            'Unable to reach Google to finish Calendar permission.'
        ));
        return false;
    }
}

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
        try { await loadEmails(currentEmailPage || 1, { cacheOnly: true }); } catch (e) { /* ignore refresh errors */ }
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

function formatDateForApi(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function formatQuickScheduleDate(date) {
    return currentLanguage === 'en'
        ? date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
        : date.toLocaleDateString('vi-VN', { weekday: 'short', day: '2-digit', month: '2-digit' });
}

function formatQuickScheduleTime(schedule) {
    const start = new Date(schedule.start_time);
    if (Number.isNaN(start.getTime())) return ui('Chưa rõ giờ', 'Time unknown');
    const startText = start.toLocaleTimeString(currentLanguage === 'en' ? 'en-US' : 'vi-VN', {
        hour: '2-digit',
        minute: '2-digit'
    });
    if (!schedule.end_time) return startText;
    const end = new Date(schedule.end_time);
    if (Number.isNaN(end.getTime())) return startText;
    const endText = end.toLocaleTimeString(currentLanguage === 'en' ? 'en-US' : 'vi-VN', {
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
                <button class="overview-sort-btn" type="button" data-checklist-sort>${ui('Sắp xếp', 'AI sort')}</button>
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
            custom_items: sortOverviewCustomItems(nextState.custom_items || [])
        });
        await apiFetch(`${API_BASE}/schedule/checklist`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: selectedDate, ...state })
        });
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

    container.innerHTML = `<div class="overview-loading">${ui('Đang để AI tổng hợp dữ liệu trong ngày...', 'AI is summarizing your day...')}</div>`;
    // #overviewContent scrolls independently of the static header/date-picker
    // above it, so replacing its content without resetting scroll leaves a
    // leftover scroll offset from before the refresh -- the new hero card
    // then renders starting mid-way (kicker/heading scrolled out of view)
    // instead of from the top, looking like its content got cut off.
    container.scrollTop = 0;
    if (refreshBtn) refreshBtn.disabled = true;

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
            ? `<p class="overview-refresh-note">${ui('AI đang cập nhật email trong nền. Lịch/task đã sẵn sàng để xem ngay.', 'AI is updating email in the background. Schedule/task data is ready now.')}</p>`
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
    } catch (error) {
        container.innerHTML = `
            <div class="overview-error">
                <strong>${ui('Không thể tổng hợp dữ liệu', 'Unable to build overview')}</strong>
                <p>${escapeHtml(error.message || ui('Vui lòng thử lại sau.', 'Please try again later.'))}</p>
            </div>
        `;
    } finally {
        if (refreshBtn) refreshBtn.disabled = false;
    }
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

// Update sidebar user profile display
function updateSidebarUserProfile(profile) {
    if (!profile) return;
    const { name, email, avatarUrl, connected } = profile;
    
    // Update username
    const userNameEl = document.getElementById('userName');
    if (userNameEl) {
        userNameEl.textContent = name || 'Teacher';
    }
    
    // Update Gmail status
    const gmailStatusEl = document.getElementById('gmailStatus');
    if (gmailStatusEl) {
        gmailStatusEl.textContent = connected ? 'Gmail connected' : 'Not connected';
    }
    
    // Update avatar if provided
    const userAvatarEl = document.getElementById('userAvatar');
    if (userAvatarEl && avatarUrl) {
        userAvatarEl.src = avatarUrl;
    }
}

async function apiFetch(url, options = {}) {
    try {
        const method = String(options.method || 'GET').toUpperCase();
        const resp = await fetch(url, {
            credentials: 'include',
            ...options
        });

        if (resp.status === 401) {
            isAuthenticated = false;
            showAuthGate(ui(
                'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
                'Your session has expired. Please sign in again.'
            ));
        }

        if (method !== 'GET' && String(url).includes(`${API_BASE}/schedule`)) {
            invalidateScheduleCaches();
        }

        return resp;
    } catch (err) {
        throw err;
    }
}

async function checkOAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('gmail_auth') === 'success') {
        console.log('✅ OAuth callback detected');
        window.history.replaceState({}, document.title, window.location.pathname);

        try {
            await apiFetch(`${API_BASE}/user/gmail-connected`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            await refreshAuthButtons();
            await loadUserProfile();

            showNotification(ui('✅ Gmail đã kết nối thành công!', '✅ Gmail connected successfully!'), 'success');
            // Give user immediate feedback that email is being loaded.
            setTimeout(() => showNotification(
                ui('⏳ Đang quét Gmail của bạn, chuyển sang tab Email để xem...', '⏳ Scanning your Gmail, switch to the Email tab to see results...'),
                'info'
            ), 800);
            if (userModeRequired) {
                pendingPageAfterMode = 'overview';
                return;
            }

            showWorkspace();
            const overviewNavBtn = document.querySelector('[data-page="overview"]');
            if (overviewNavBtn) {
                await handlePageChange(overviewNavBtn);
            }
        } catch (error) {
            console.error('OAuth completion refresh failed:', error);
        }
    }
}

function openExternalUrl(url) {
    const popup = window.open(url, '_blank', 'noopener,noreferrer');
    if (popup) popup.opener = null;
}

const TOAST_COLORS = {
    success: '#4CAF50',
    error: '#e53935',
    warning: '#f39c12',
    info: '#2196F3',
    mail: '#7C4DFF'
};

let toastStackEl = null;
function getToastStack() {
    if (!toastStackEl || !document.body.contains(toastStackEl)) {
        toastStackEl = document.createElement('div');
        toastStackEl.id = 'toastStack';
        toastStackEl.setAttribute('aria-live', 'polite');
        toastStackEl.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: min(360px, calc(100vw - 32px));
            pointer-events: none;
        `;
        document.body.appendChild(toastStackEl);
    }
    return toastStackEl;
}

function showNotification(message, type = 'info', options = {}) {
    const stack = getToastStack();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
        pointer-events: auto;
        background: ${TOAST_COLORS[type] || TOAST_COLORS.info};
        color: white;
        padding: 14px 16px;
        border-radius: 10px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.2);
        font-size: 14px;
        line-height: 1.4;
        display: flex;
        align-items: flex-start;
        gap: 10px;
        animation: toastSlideIn 0.25s ease-out;
    `;

    const textEl = document.createElement('div');
    textEl.style.cssText = 'flex: 1; word-break: break-word;';
    textEl.textContent = message;
    toast.appendChild(textEl);

    const dismiss = () => {
        toast.style.animation = 'toastSlideOut 0.2s ease-in forwards';
        setTimeout(() => toast.remove(), 200);
    };

    if (options.actionLabel && typeof options.onAction === 'function') {
        const actionBtn = document.createElement('button');
        actionBtn.type = 'button';
        actionBtn.textContent = options.actionLabel;
        actionBtn.style.cssText = `
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 13px;
            cursor: pointer;
            white-space: nowrap;
        `;
        actionBtn.addEventListener('click', () => {
            options.onAction();
            dismiss();
        });
        toast.appendChild(actionBtn);
    }

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Dismiss');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = `
        background: none;
        border: none;
        color: white;
        opacity: 0.8;
        font-size: 18px;
        line-height: 1;
        cursor: pointer;
        padding: 0 2px;
    `;
    closeBtn.addEventListener('click', dismiss);
    toast.appendChild(closeBtn);

    stack.appendChild(toast);
    setTimeout(dismiss, options.autoDismissMs || 4500);
    return toast;
}

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
        
        gmailLoginBtn.style.display = 'inline-block';
        gmailLoginBtn.textContent = isAuth
            ? ui('Cấp lại quyền Google', 'Reconnect Google')
            : ui('Đăng nhập / Đổi tài khoản', 'Sign in / Switch account');
        gmailLogoutBtn.style.display = isAuth ? 'inline-block' : 'none';
        if (openGmailBtn) openGmailBtn.style.display = isAuth ? 'inline-block' : 'none';

        if (gmailAccountBadge) {
            gmailAccountBadge.textContent = isAuth
                ? ui('Đã kết nối Gmail', 'Gmail connected')
                : ui('Chưa đăng nhập Gmail', 'Gmail not connected');
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
    if (!confirm(ui('Bạn có chắc muốn đăng xuất Gmail?', 'Are you sure you want to sign out of Gmail?'))) return;

    try {
        const response = await apiFetch(`${API_BASE}/email/logout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            showNotification(ui('✅ Đã đăng xuất Gmail', '✅ Signed out of Gmail'), 'success');
            isAuthenticated = false;
            userModeRequired = false;
            pendingPageAfterMode = '';
            userModeModal?.classList.remove('show', 'is-required');
            window.location.replace('/');
        }
    } catch (err) {
        alert(ui('Lỗi: ', 'Error: ') + err.message);
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
        // Check Gmail auth status first to avoid 401 errors
        try {
            const authResp = await apiFetch(`${API_BASE}/email/auth-status`);
            if (authResp.status === 401) {
                const emailsList = document.getElementById('emailsList');
                if (emailsList) emailsList.innerHTML = `<div style="padding:20px;text-align:center;">${ui('Vui lòng đăng nhập Gmail để xem email.', 'Please sign in to Gmail to view email.')}<br><br><button class="btn-primary" id="promptLoginBtn">${ui('Đăng nhập Gmail', 'Sign in to Gmail')}</button></div>`;
                const btnLogin = document.getElementById('promptLoginBtn');
                if (btnLogin) btnLogin.addEventListener('click', gmailLogin);
                return;
            }
            const authData = await authResp.json();
            if (!authData || !authData.authenticated) {
                const emailsList = document.getElementById('emailsList');
                if (emailsList) emailsList.innerHTML = `<div style="padding:20px;text-align:center;">${ui('Vui lòng đăng nhập Gmail để xem email.', 'Please sign in to Gmail to view email.')}<br><br><button class="btn-primary" id="promptLoginBtn">${ui('Đăng nhập Gmail', 'Sign in to Gmail')}</button></div>`;
                const btnLogin = document.getElementById('promptLoginBtn');
                if (btnLogin) btnLogin.addEventListener('click', gmailLogin);
                return;
            }
        } catch (err) {
            console.error('Auth check failed:', err);
            // Fallback to attempting to load emails — loadEmails will handle errors
        }

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

    const isMobile = () => window.innerWidth <= 860;
    const updateToggle = () => {
        const mobileOpen = sidebar.classList.contains('open');
        const expanded = isMobile() ? mobileOpen : true;
        menuToggle.setAttribute('aria-expanded', String(expanded));
        menuToggle.setAttribute('aria-label', isMobile()
            ? ui(mobileOpen ? 'Đóng menu' : 'Mở menu', mobileOpen ? 'Close menu' : 'Open menu')
            : ui('Thanh điều hướng', 'Navigation'));
        const icon = menuToggle.querySelector('.menu-toggle-icon');
        if (icon) icon.textContent = isMobile() ? (mobileOpen ? '×' : '☰') : '‹';
    };

    const closeMobileSidebar = () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
        updateToggle();
    };

    const applyDesktopPreference = () => {
        container.classList.remove('sidebar-collapsed');
        localStorage.removeItem('flowmate-sidebar-collapsed');
        if (isMobile()) {
            closeMobileSidebar();
        } else {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
            updateToggle();
        }
    };

    menuToggle.addEventListener('click', (event) => {
        event.stopPropagation();
        if (isMobile()) {
            const shouldOpen = !sidebar.classList.contains('open');
            sidebar.classList.toggle('open', shouldOpen);
            overlay.classList.toggle('show', shouldOpen);
        }
        updateToggle();
    });

    overlay.addEventListener('click', closeMobileSidebar);
    navBtns.forEach((button) => {
        button.addEventListener('click', () => {
            if (isMobile()) closeMobileSidebar();
        });
    });
    window.addEventListener('resize', applyDesktopPreference);
    applyDesktopPreference();
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

            if (data.demo_mode) {
                showNotification(ui('⚠️ Chế độ demo - Tất cả nhà cung cấp AI đang tạm nghỉ', '⚠️ Demo mode - All AI providers are cooling down'), 'info');
            }

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

function updateUserModeUI(mode) {
    currentUserMode = USER_MODES[mode] ? mode : 'worker';
    if (userModeSelect) userModeSelect.value = currentUserMode;
    const description = document.getElementById('userModeDescription');
    if (description) description.textContent = modeDescription(USER_MODES[currentUserMode]);
    const label = document.getElementById('userModeLabel');
    if (label) label.textContent = modeLabel(USER_MODES[currentUserMode]);
    const initial = document.getElementById('userModeInitial');
    if (initial) initial.textContent = USER_MODES[currentUserMode].initial;
    const settingsModeText = document.getElementById('settingsModeText');
    if (settingsModeText) settingsModeText.textContent = modeLabel(USER_MODES[currentUserMode]);
    const settingsModeDescription = document.getElementById('settingsModeDescription');
    if (settingsModeDescription) settingsModeDescription.textContent = modeDescription(USER_MODES[currentUserMode]);
    const settingsModeIcon = document.getElementById('settingsModeIcon');
    if (settingsModeIcon) settingsModeIcon.textContent = USER_MODES[currentUserMode].initial;
    const workspaceModeInitial = document.getElementById('workspaceModeInitial');
    if (workspaceModeInitial) workspaceModeInitial.textContent = USER_MODES[currentUserMode].initial;
    const workspaceModeLabel = document.getElementById('workspaceModeLabel');
    if (workspaceModeLabel) workspaceModeLabel.textContent = modeLabel(USER_MODES[currentUserMode]);
    document.querySelectorAll('.user-mode-card').forEach((card) => {
        card.classList.toggle('active', card.dataset.mode === currentUserMode);
    });
}

function setSettingsState(message, isError = false) {
    const state = document.getElementById('settingsSaveState');
    if (!state) return;
    state.textContent = message;
    state.style.color = isError ? '#b91c1c' : '#0f766e';
}

async function loadSettingsPage() {
    setSettingsState(ui('Đang đồng bộ...', 'Syncing...'));
    try {
        const [profileResponse, authResponse] = await Promise.all([
            apiFetch(`${API_BASE}/user/profile`),
            apiFetch(`${API_BASE}/email/auth-status`)
        ]);
        const profileData = await profileResponse.json();
        const authData = await authResponse.json();
        const user = profileData.user || {};
        const connected = !!authData.authenticated;

        const name = document.getElementById('settingsName');
        const email = document.getElementById('settingsEmail');
        const avatar = document.getElementById('settingsAvatar');
        const googleStatus = document.getElementById('settingsGoogleStatus');
        const googleBtn = document.getElementById('settingsGoogleBtn');
        if (name) name.textContent = user.gmail_name || user.name || ui('Người dùng', 'User');
        if (email) email.textContent = user.gmail_email || user.email || ui('Chưa kết nối Gmail', 'Gmail not connected');
        if (avatar) avatar.src = user.gmail_picture || user.avatar_url || 'https://www.gravatar.com/avatar/?d=mp&s=96';
        if (googleStatus) googleStatus.textContent = connected
            ? ui('Đã kết nối và sẵn sàng đồng bộ.', 'Connected and ready to sync.')
            : ui('Chưa kết nối tài khoản Google.', 'Google account not connected.');
        if (googleBtn) {
            googleBtn.textContent = connected ? ui('Cấp lại quyền', 'Reconnect') : ui('Kết nối', 'Connect');
            googleBtn.dataset.connected = connected ? 'true' : 'false';
        }
        updateUserModeUI(user.user_mode || currentUserMode);
        setSettingsState(ui('Đã đồng bộ', 'Synced'));
    } catch (error) {
        setSettingsState(`${ui('Lỗi', 'Error')}: ${error.message}`, true);
    }
}

function handleSettingsGoogleAction() {
    gmailLogin();
}

async function clearAllUserHistory() {
    if (!confirm(ui(
        'Xóa toàn bộ lịch sử chat, email và lịch đã ghi nhận?',
        'Delete all saved chat, email, and calendar history?'
    ))) return;
    setSettingsState(ui('Đang xóa dữ liệu...', 'Deleting data...'));
    try {
        const response = await apiFetch(`${API_BASE}/chat/clear-all`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || ui('Không thể xóa dữ liệu', 'Unable to delete data'));
        if (chatMessages) chatMessages.innerHTML = '';
        const historyList = document.getElementById('historyList');
        if (historyList) historyList.innerHTML = '';
        setSettingsState(ui(`Đã xóa ${data.deleted_count || 0} mục`, `Deleted ${data.deleted_count || 0} items`));
        showNotification(ui('Đã xóa toàn bộ lịch sử', 'All history deleted'), 'success');
    } catch (error) {
        setSettingsState(`${ui('Lỗi', 'Error')}: ${error.message}`, true);
    }
}

function renderUserModeGrid() {
    const grid = document.getElementById('userModeGrid');
    if (!grid) return;
    grid.innerHTML = ONBOARDING_MODE_KEYS.map((value) => {
        const mode = USER_MODES[value];
        return `
        <button type="button" class="user-mode-card${value === pendingUserMode ? ' active' : ''}" data-mode="${value}">
            <span class="user-mode-card-icon">${mode.initial}</span>
            <strong>${modeLabel(mode)}</strong>
            <p>${modeDescription(mode)}</p>
            <span class="user-mode-card-check">${value === pendingUserMode ? '✓' : ''}</span>
        </button>
    `;
    }).join('');
    grid.querySelectorAll('.user-mode-card').forEach((card) => {
        card.addEventListener('click', () => {
            pendingUserMode = card.dataset.mode;
            renderUserModeGrid();
            const confirmButton = document.getElementById('userModeConfirmBtn');
            if (confirmButton) confirmButton.disabled = false;
        });
    });
}

function openUserModeModal(required = false) {
    if (!userModeModal) return;
    userModeRequired = required;
    pendingUserMode = !required && ONBOARDING_MODE_KEYS.includes(currentUserMode)
        ? currentUserMode
        : '';
    userModeModal.classList.toggle('is-required', required);
    const closeButton = userModeModal.querySelector('.user-mode-close');
    const cancelButton = document.getElementById('userModeCancelBtn');
    const confirmButton = document.getElementById('userModeConfirmBtn');
    if (closeButton) closeButton.hidden = required;
    if (cancelButton) cancelButton.hidden = required;
    if (confirmButton) confirmButton.disabled = !pendingUserMode;
    const title = document.getElementById('userModeModalTitle');
    if (title) title.textContent = ui('Chọn chế độ làm việc', 'Select Your Workspace Mode');
    const status = document.getElementById('userModeSaveStatus');
    if (status) {
        status.textContent = required
            ? ui('Hãy chọn một chế độ để tiếp tục sử dụng FlowMate.', 'Choose a mode to continue using FlowMate.')
            : pendingUserMode
                ? ''
                : ui('Hãy chọn chế độ mới rồi xác nhận.', 'Choose a new mode, then confirm.');
    }
    renderUserModeGrid();
    userModeModal.classList.add('show');
    (required ? gridFirstModeCard() : closeButton)?.focus();
}

function closeUserModeModal() {
    if (userModeRequired) return;
    userModeModal?.classList.remove('show');
}

function gridFirstModeCard() {
    return document.querySelector('#userModeGrid .user-mode-card');
}

async function saveUserMode(mode, closeAfterSave = false) {
    const previousMode = currentUserMode;
    updateUserModeUI(mode);
    const status = document.getElementById('userModeSaveStatus');
    if (status) status.textContent = ui('Đang áp dụng chế độ...', 'Applying mode...');
    document.querySelectorAll('.user-mode-card').forEach((card) => {
        card.disabled = true;
    });
    try {
        const response = await apiFetch(`${API_BASE}/user/profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_mode: currentUserMode })
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Không thể lưu chế độ người dùng');
        }
        renderUserModeGrid();
        updateUserModeUI(currentUserMode);
        if (status) status.textContent = ui(
            `Đã áp dụng ${modeLabel(USER_MODES[currentUserMode])}.`,
            `Applied ${modeLabel(USER_MODES[currentUserMode])}.`
        );
        showNotification(ui(
            `Đã chuyển sang ${modeLabel(USER_MODES[currentUserMode])}`,
            `Switched to ${modeLabel(USER_MODES[currentUserMode])}`
        ), 'success');
        userModeRequired = false;
        userModeModal?.classList.remove('is-required');
        if (closeAfterSave) {
            setTimeout(() => userModeModal?.classList.remove('show'), 200);
        }
        showWorkspace();
        await resumeWorkspaceAfterModeSelection();
    } catch (error) {
        updateUserModeUI(previousMode);
        renderUserModeGrid();
        if (status) status.textContent = ui(`Không thể lưu: ${error.message}`, `Could not save: ${error.message}`);
        showNotification(ui(`Lỗi lưu chế độ: ${error.message}`, `Mode save error: ${error.message}`), 'error');
    } finally {
        document.querySelectorAll('.user-mode-card').forEach((card) => {
            card.disabled = false;
        });
    }
}

async function resumeWorkspaceAfterModeSelection() {
    const targetPage = pendingPageAfterMode || currentPage;
    pendingPageAfterMode = '';

    if (targetPage === 'chat') {
        await loadChatHistory();
        return;
    }

    const targetButton = document.querySelector(`[data-page="${targetPage}"]`);
    if (targetButton) {
        await handlePageChange(targetButton);
    }
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
            const storedMode = user.user_mode && USER_MODES[user.user_mode] ? user.user_mode : '';
            updateUserModeUI(storedMode || 'worker');
            const gmailConnected = !!(
                (gmailData && gmailData.success && gmailData.gmail_connected)
                || user.gmail_connected
            );
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
                userAvatar.title = gmailConnected ? ui('Đã kết nối Gmail', 'Gmail connected') : ui('Đăng nhập Gmail', 'Sign in to Gmail');
            }
            if (gmailConnected && (user.mode_required || !storedMode)) {
                isAuthenticated = true;
                showModeSelectionStage();
                openUserModeModal(true);
            } else {
                userModeRequired = false;
                isAuthenticated = gmailConnected;
            }
            return user;
        }
    } catch (error) {
        console.error('Error loading user profile:', error);
    }
    return null;
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
    const menuIcon = menuToggle?.querySelector('.menu-toggle-icon');
    if (menuIcon && window.innerWidth <= 860) menuIcon.textContent = '☰';
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

// EMAIL FUNCTIONS
async function gmailLogin() {
    showAuthGate(ui('Đang chuyển đến Google...', 'Redirecting to Google...'), true);
    try {
        const response = await fetch(`${API_BASE}/email/auth_url`, {
            credentials: 'include',
            headers: { Accept: 'application/json' }
        });
        const data = await response.json();

        if (!response.ok || !data.auth_url) {
            showAuthGate(ui(
                'Không thể bắt đầu đăng nhập. Vui lòng thử lại.',
                'Unable to start sign-in. Please try again.'
            ));
            alert(ui('Lỗi: ', 'Error: ') + (data.error || ui('OAuth chưa được cấu hình', 'OAuth is not configured')));
            return;
        }

        window.location.href = data.auth_url;
    } catch (err) {
        showAuthGate(ui(
            'Không thể kết nối đến máy chủ. Vui lòng thử lại.',
            'Unable to reach the server. Please try again.'
        ));
        alert(ui('Lỗi: ', 'Error: ') + err.message);
    }
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
    
    emailsList.innerHTML = `<p style="padding: 20px; text-align: center; color: #666;">${ui('⏳ Đang tải email...', '⏳ Loading email...')}</p>`;
    const selectedFilter = emailFilterSelect ? emailFilterSelect.value : 'all';
    const includeReadCheckbox = document.getElementById('includeReadCheckbox');
    const includeRead = includeReadCheckbox ? includeReadCheckbox.checked : true;
    currentEmailPage = page;

    await refreshAuthButtons();
    
    try {
        const search = emailSearchInput ? emailSearchInput.value.trim() : '';
        const params = new URLSearchParams({
            max_results: '20',
            page: String(page),
            filter: selectedFilter,
            include_read: String(includeRead),
            search
        });
        if (options.fresh) params.set('fresh', 'true');
        if (options.cacheOnly) params.set('cache_only', 'true');
        const url = `${API_BASE}/email/get-unread?${params.toString()}`;
        console.log(`📧 Loading emails: ${url}`);
        console.log(`🔍 Filter: ${selectedFilter}, Page: ${page}, Include read: ${includeRead}`);
        
        const response = await apiFetch(url);
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
        console.error('Email load error:', error);
        emailsList.innerHTML = `<p>${ui('❌ Lỗi', '❌ Error')}: ${escapeHtml(error.message)}</p>`;
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
                ${tagHTML}${escapeHtml(email.subject || ui('(Không có tiêu đề)', '(No subject)'))}
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

// WEEKLY SCHEDULE TABLE (Mon-Sun, synced with Google Calendar)
function weekDayNames() {
    return currentLanguage === 'en'
        ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        : ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'];
}

function getMonday(date) {
    const d = new Date(date);
    const day = d.getDay(); // 0 = Sunday, 1 = Monday, ...
    const diff = (day === 0 ? -6 : 1) - day;
    d.setDate(d.getDate() + diff);
    d.setHours(0, 0, 0, 0);
    return d;
}

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
                const localActions = isLocal
                    ? `
                        ${schedule.status === 'completed'
                            ? `<button class="btn-check" onclick="markScheduleIncomplete(${schedule.local_id})">${ui('↩ Chưa xong', '↩ Mark pending')}</button>`
                            : `<button class="btn-check" onclick="markScheduleComplete(${schedule.local_id})">${ui('✓ Hoàn thành', '✓ Complete')}</button>`}
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

function plainTextFromHtml(value) {
    let decoded = String(value || '').trim();
    for (let index = 0; index < 2; index += 1) {
        const container = document.createElement('div');
        container.innerHTML = decoded
            .replace(/<br\s*\/?>/gi, '\n')
            .replace(/<\/(?:p|div|li|h[1-6])>/gi, '\n');
        const next = container.textContent || container.innerText || '';
        if (next === decoded) break;
        decoded = next;
    }
    return decoded
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n[ \t]+/g, '\n')
        .replace(/[ \t]{2,}/g, ' ')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

async function markScheduleComplete(scheduleId) {
    if (!confirm(ui('Đánh dấu lịch hẹn đã hoàn thành?', 'Mark this appointment as completed?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}/update-status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'completed' })
        });
        
        const data = await response.json();
        if (data.success) {
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

async function markScheduleIncomplete(scheduleId) {
    if (!confirm(ui('Đánh dấu lịch hẹn chưa hoàn thành?', 'Mark this appointment as pending?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/schedule/${scheduleId}/update-status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'pending' })
        });
        
        const data = await response.json();
        if (data.success) {
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
        
        openEditScheduleModal();
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}

async function handleEditScheduleSubmit(e) {
    e.preventDefault();
    
    const editForm = document.getElementById('editScheduleForm');
    const scheduleId = editForm?.dataset.scheduleId;
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
                attendees
            })
        });
        
        const data = await response.json();
        if (response.ok && data.success) {
            showNotification(ui('✓ Đã cập nhật lịch hẹn', '✓ Appointment updated'), 'success');
            closeEditScheduleModal();
            refreshLocalScheduleViews().catch(err => console.warn('Schedule refresh after edit failed:', err));
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
                ? `<div style="margin-top: 8px; font-size: 12px; color: #666;"><strong>${ui('Người tham dự', 'Attendees')}:</strong> ${event.attendees.join(', ')}</div>`
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
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function formatEmailText(text) {
    const tagTokens = {
        '\u0001EMAIL_BOLD_OPEN\u0001': '<strong>',
        '\u0001EMAIL_BOLD_CLOSE\u0001': '</strong>'
    };
    const normalized = String(text == null ? '' : text)
        .replace(/\r\n?/g, '\n')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<(?:b|strong)\s*>/gi, '\u0001EMAIL_BOLD_OPEN\u0001')
        .replace(/<\/(?:b|strong)\s*>/gi, '\u0001EMAIL_BOLD_CLOSE\u0001')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    let escaped = escapeHtml(normalized);
    Object.entries(tagTokens).forEach(([token, html]) => {
        escaped = escaped.split(token).join(html);
    });
    const linked = escaped.replace(
        /(https?:\/\/[^\s<]+)/gi,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    return linked
        .split(/\n{2,}/)
        .map(block => `<p>${block.replace(/\n/g, '<br>')}</p>`)
        .join('');
}

function renderMarkdown(text) {
    let result = text;
    result = result.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
    result = result.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
    result = result.replace(/\[([^\]]+)\]\(([^\)]+)\)/g, (match, label, url) => {
        const safeUrl = sanitizeExternalUrl(url);
        return safeUrl
            ? `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>`
            : label;
    });
    result = result.replace(/\n/g, '<br>');
    return result;
}

function sanitizeExternalUrl(value) {
    try {
        const parsed = new URL(String(value || '').trim(), window.location.origin);
        if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol)) return '';
        return escapeHtml(parsed.href);
    } catch (error) {
        return '';
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
