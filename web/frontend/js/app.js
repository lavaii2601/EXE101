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
let userModeSelect;
let userModeModal;
let emailSearchInput;
let emailSearchTimer;

// State
let currentPage = 'chat';
let currentEmailPage = 1;
let currentWeekStart = getMonday(new Date());
let currentDetailEmail = null;
let currentUserMode = 'worker';
let pendingUserMode = '';
let userModeRequired = false;
let pendingPageAfterMode = '';
let isAuthenticated = false;
let currentLanguage = localStorage.getItem('flowmate-language') === 'en' ? 'en' : 'vi';

const I18N = {
    vi: {
        'nav.chat': 'Chat',
        'nav.email': 'Email',
        'nav.calendar': 'Lịch',
        'nav.history': 'Lịch sử',
        'nav.settings': 'Cài đặt',
        'common.clear': 'Xóa',
        'common.refresh': 'Làm mới',
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
        'nav.email': 'Email',
        'nav.calendar': 'Calendar',
        'nav.history': 'Activity',
        'nav.settings': 'Settings',
        'common.clear': 'Clear',
        'common.refresh': 'Refresh',
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

function applyStaticLanguage() {
    const reverseText = Object.fromEntries(Object.entries(STATIC_ENGLISH_TEXT).map(([vi, en]) => [en, vi]));
    const reversePlaceholders = Object.fromEntries(Object.entries(STATIC_ENGLISH_PLACEHOLDERS).map(([vi, en]) => [en, vi]));
    const userContentSelector = '#chatMessages, #emailsList, #emailDetail, #dailyReportContainer, #historyList, #schedulesList';
    document.querySelectorAll('body *').forEach((element) => {
        if (element.closest(userContentSelector)) return;
        if (element.children.length === 0) {
            const text = element.textContent.trim();
            const replacement = currentLanguage === 'en' ? STATIC_ENGLISH_TEXT[text] : reverseText[text];
            if (replacement) element.textContent = replacement;
        }
        if ('placeholder' in element && element.placeholder) {
            const replacement = currentLanguage === 'en'
                ? STATIC_ENGLISH_PLACEHOLDERS[element.placeholder]
                : reversePlaceholders[element.placeholder];
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
        description: 'Ưu tiên bài tập, deadline, email lớp và lịch học.',
        descriptionEn: 'Prioritize assignments, deadlines, class email, and study schedules.'
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

const ONBOARDING_MODE_KEYS = ['student', 'worker', 'mentor', 'teacher', 'freelancer'];

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
    userModeSelect = document.getElementById('userModeSelect');
    userModeModal = document.getElementById('userModeModal');
    emailSearchInput = document.getElementById('emailSearchInput');
    setupAuthGate();
    setupWorkspaceShell();
    applyLanguage();
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

        // New schedule form submit
        if (scheduleForm) {
            scheduleForm.addEventListener('submit', handleScheduleSubmit);
        }

        // Edit schedule form submit
        const editScheduleForm = document.getElementById('editScheduleForm');
        if (editScheduleForm) {
            editScheduleForm.addEventListener('submit', handleEditScheduleSubmit);
        }

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
                loadEmails();
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
                    loadEmails(1);
                }, 300);
            });
        }
        const clearEmailSearchBtn = document.getElementById('clearEmailSearchBtn');
        if (clearEmailSearchBtn) {
            clearEmailSearchBtn.addEventListener('click', () => {
                if (!emailSearchInput) return;
                emailSearchInput.value = '';
                currentEmailPage = 1;
                loadEmails(1);
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
                loadEmails();
            });
        }

        // Refresh emails
        const refreshEmailsBtn = document.getElementById('refreshEmailsBtn');
        if (refreshEmailsBtn) {
            refreshEmailsBtn.addEventListener('click', () => {
                console.log('🔄 Refreshing emails');
                apiFetch(`${API_BASE}/email/cache/clear`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                }).then(() => {
                    loadEmails();
                }).catch(err => console.error('Cache clear error:', err));
            });
        }

        // Generate daily report
        const generateReportBtn = document.getElementById('generateReportBtn');
        if (generateReportBtn) {
            generateReportBtn.addEventListener('click', generateDailyReport);
        }

        // Calendar buttons
        const refreshCalendarBtn = document.getElementById('refreshCalendarBtn');
        if (refreshCalendarBtn) {
            refreshCalendarBtn.addEventListener('click', () => {
                console.log('🔄 Refreshing calendar events');
                loadCalendarEvents();
            });
        }

        const openCalendarBtn = document.getElementById('openCalendarBtn');
        if (openCalendarBtn) {
            openCalendarBtn.addEventListener('click', () => openExternalUrl('https://calendar.google.com'));
        }

        // Weekly schedule table navigation
        const prevWeekBtn = document.getElementById('prevWeekBtn');
        if (prevWeekBtn) {
            prevWeekBtn.addEventListener('click', () => {
                currentWeekStart.setDate(currentWeekStart.getDate() - 7);
                loadWeekSchedule();
            });
        }

        const nextWeekBtn = document.getElementById('nextWeekBtn');
        if (nextWeekBtn) {
            nextWeekBtn.addEventListener('click', () => {
                currentWeekStart.setDate(currentWeekStart.getDate() + 7);
                loadWeekSchedule();
            });
        }

        const todayWeekBtn = document.getElementById('todayWeekBtn');
        if (todayWeekBtn) {
            todayWeekBtn.addEventListener('click', () => {
                currentWeekStart = getMonday(new Date());
                loadWeekSchedule();
            });
        }

        // Listen for postMessage from OAuth popup to update UI without redirect
        window.addEventListener('message', (ev) => {
            try {
                if (ev.origin === window.location.origin && ev.data && ev.data.type === 'gmail_auth' && ev.data.status === 'success') {
                    console.log('📥 Received gmail_auth success message');
                    refreshAuthButtons();
                    loadUserProfile().then(() => {
                        if (userModeRequired) {
                            pendingPageAfterMode = 'chat';
                        } else {
                            showWorkspace();
                            if (currentPage === 'emails') {
                                setTimeout(() => loadEmails(), 300);
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

    await loadUserProfile();
    if (!userModeRequired) {
        showWorkspace();
        await loadChatHistory();
        const activeNavButton = document.querySelector('.sidebar-nav .nav-btn.active');
        if (activeNavButton) {
            await handlePageChange(activeNavButton);
        }
    }
    await refreshAuthButtons();
    scanMeetingSuggestions().catch(error => {
        console.warn('Background meeting suggestion scan failed:', error);
    });
    checkRuntimeConfig();
    
    // Auto-load emails if user is on emails page and authenticated
    if (currentPage === 'emails') {
        console.log('📧 Auto-loading emails on init...');
        setTimeout(() => loadEmails(), 500);
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
        isAuthenticated = !!(response.ok && data.authenticated);
    } catch (error) {
        console.error('Initial auth check failed:', error);
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

function setupWorkspaceShell() {
    renderQuickActions(currentPage);
}

const QUICK_ACTIONS = {
    chat: {
        icon: 'AI',
        title: 'Chat',
        description: 'Trò chuyện với FlowMate cho yêu cầu cần phân tích hoặc xử lý nhiều bước.',
        tip: 'Các thao tác ngắn đã được tách sang panel này để Chat tập trung vào hội thoại.',
        actions: [
            { icon: '✉', label: 'Mở hộp thư', detail: 'Xem và xử lý email', action: 'open-email' },
            { icon: '▣', label: 'Mở lịch tuần', detail: 'Kiểm tra lịch và cuộc họp', action: 'open-calendar' }
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
}

async function runQuickAction(action) {
    const pageButton = (page) => document.querySelector(`.sidebar-nav [data-page="${page}"]`);
    if (action === 'open-email') return handlePageChange(pageButton('emails'));
    if (action === 'open-calendar') return handlePageChange(pageButton('schedule'));
    if (action === 'refresh-email') return document.getElementById('refreshEmailsBtn')?.click();
    if (action === 'daily-report') return document.querySelector('#emails-page [data-tab="daily-report"]')?.click();
    if (action === 'compose-email') return document.querySelector('#emails-page [data-tab="compose"]')?.click();
    if (action === 'create-event') return openNewScheduleModal();
    if (action === 'this-week') return document.getElementById('todayWeekBtn')?.click();
    if (action === 'refresh-history') return loadActivityHistory();
    if (action === 'change-mode') return openUserModeModal(false);
    if (action === 'refresh-settings') return loadSettingsPage();
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
            if (userModeRequired) {
                pendingPageAfterMode = 'chat';
                return;
            }

            showWorkspace();
            const chatNavBtn = document.querySelector('[data-page="chat"]');
            if (chatNavBtn) {
                await handlePageChange(chatNavBtn);
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
                body: JSON.stringify({
                    message,
                    mode: currentUserMode,
                    confirmed_schedule: confirmed,
                    schedule_override: override
                })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            const data = await response.json();

            loadingDiv.remove();

            if (!data.success) {
                addMessage(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || 'Unknown error'), 'assistant');
                console.error('AI error:', data.error);
                return;
            }

            const providerBadge = data.provider ? `<span class="provider-badge" style="font-size:11px;padding:2px 8px;background:${data.demo_mode?'#FF9800':'#4CAF50'};color:white;border-radius:10px;margin-left:8px;">${data.demo_mode? '🎭 Demo' : ('🤖 '+data.provider.toUpperCase())}</span>` : '';
            addMessage(data.response, 'assistant', providerBadge);

            if (data.demo_mode) showNotification(ui('⚠️ Chế độ demo - Tất cả nhà cung cấp AI đang tạm nghỉ', '⚠️ Demo mode - All AI providers are cooling down'), 'info');

            // If server already created the schedule, just notify and refresh
            if (data.schedule_created) {
                try { await loadSchedules(); } catch (e) { /* ignore */ }
                try { await loadWeekSchedule(); } catch (e) { /* ignore */ }
                showNotification(`${ui('✅ Đã tạo lịch', '✅ Event created')}: ${data.schedule_created.title || ui('Lịch hẹn', 'Appointment')}`, 'success');
                return;
            }

        } catch (error) {
            loadingDiv.remove();
            console.error('❌ Message send error:', error);
            addMessage(ui('❌ Lỗi kết nối: ', '❌ Connection error: ') + error.message, 'assistant');
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
    if (openGmailBtn) openGmailBtn.addEventListener('click', () => openExternalUrl('https://mail.google.com'));
    
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
        openCalendarBtn.addEventListener('click', () => openExternalUrl('https://calendar.google.com'));
    }

    // Weekly schedule table navigation
    const prevWeekBtn = document.getElementById('prevWeekBtn');
    if (prevWeekBtn) {
        prevWeekBtn.addEventListener('click', () => {
            currentWeekStart.setDate(currentWeekStart.getDate() - 7);
            loadWeekSchedule();
        });
    }

    const nextWeekBtn = document.getElementById('nextWeekBtn');
    if (nextWeekBtn) {
        nextWeekBtn.addEventListener('click', () => {
            currentWeekStart.setDate(currentWeekStart.getDate() + 7);
            loadWeekSchedule();
        });
    }

    const todayWeekBtn = document.getElementById('todayWeekBtn');
    if (todayWeekBtn) {
        todayWeekBtn.addEventListener('click', () => {
            currentWeekStart = getMonday(new Date());
            loadWeekSchedule();
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
            showAuthGate(ui(
                'Bạn đã đăng xuất. Đăng nhập để tiếp tục.',
                'You are signed out. Sign in to continue.'
            ));
            const emailsList = document.getElementById('emailsList');
            if (emailsList) emailsList.innerHTML = `<p>${ui('Đã đăng xuất Gmail. Vui lòng đăng nhập lại.', 'You have signed out of Gmail. Please sign in again.')}</p>`;
        }
    } catch (err) {
        alert(ui('Lỗi: ', 'Error: ') + err.message);
    }
}

// PAGE MANAGEMENT (CRITICAL FIX)
async function handlePageChange(btn) {
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
    renderQuickActions(page);
    
    // Load page data
    if (page === 'emails') {
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

        loadEmails().catch(err => console.error('Email load error:', err));
    } else if (page === 'schedule') {
        loadWeekSchedule().catch(err => console.error('Week schedule load error:', err));
        loadSchedules().catch(err => console.error('Schedule load error:', err));
        // also load Google Calendar events (merged into schedule tab)
        loadCalendarEvents().catch(err => console.error('Calendar load error:', err));
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
                <div><strong>${ui('Nội dung phát hiện', 'Detected content')}:</strong> ${escapeHtml(draft.content)}</div>
                <div style="margin-top:8px; font-size:13px; line-height:1.5;">
                    ${ui('Ngày', 'Date')}: ${escapeHtml(draft.date || ui('Chưa xác định', 'Not specified'))}<br>
                    ${ui('Thời gian', 'Time')}: ${escapeHtml(draft.startTime ? (draft.endTime ? `${draft.startTime} - ${draft.endTime}` : draft.startTime) : ui('Chưa xác định', 'Not specified'))}<br>
                    ${ui('Hình thức', 'Format')}: ${escapeHtml(draft.format || ui('Trực tiếp', 'In person'))}<br>
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
            body: JSON.stringify({ message, mode: currentUserMode, confirmed_schedule: confirmed })
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
            const sourceLabels = {
                email: ui('Email', 'Email'),
                calendar: ui('Lịch', 'Calendar'),
                history: ui('Lịch sử', 'History'),
                profile: ui('Hồ sơ', 'Profile')
            };
            const workspaceSources = Array.isArray(data.workspace_sources)
                ? data.workspace_sources.filter(source => sourceLabels[source])
                : [];
            const sourceBadge = workspaceSources.length
                ? `<span class="provider-badge workspace-source-badge">${workspaceSources.map(source => sourceLabels[source]).join(' + ')}</span>`
                : '';

            addMessage(data.response, 'assistant', providerBadge + sourceBadge);

            if (data.demo_mode) {
                showNotification(ui('⚠️ Chế độ demo - Tất cả nhà cung cấp AI đang tạm nghỉ', '⚠️ Demo mode - All AI providers are cooling down'), 'info');
            }

            // Handle schedule results from server
            if (data.schedule_created) {
                // Server already created the schedule (user confirmed or server-side)
                try { await loadSchedules(); } catch (e) { /* ignore */ }
                try { await loadWeekSchedule(); } catch (e) { /* ignore */ }
                showNotification(`${ui('✅ Đã tạo lịch', '✅ Event created')}: ${data.schedule_created.title || ui('Lịch hẹn', 'Appointment')}`, 'success');
            } else if (data.schedule_suggestion && isScheduleIntent(message)) {
                const suggested = data.schedule_suggestion;
                // Show inline suggestion with create/dismiss buttons
                const suggestionDiv = document.createElement('div');
                suggestionDiv.className = 'message assistant';
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
                chatMessages.appendChild(suggestionDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;

                // wire buttons
                suggestionDiv.querySelector('.dismiss-schedule').addEventListener('click', () => {
                    suggestionDiv.remove();
                    showNotification(ui('Đã bỏ qua gợi ý tạo lịch', 'Event suggestion dismissed'), 'info');
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
                            showNotification(`${ui('✅ Đã tạo lịch', '✅ Event created')}: ${j.calendar_event_id ? ui('đã đồng bộ Google Calendar', 'synced with Google Calendar') : suggested.title}`, 'success');
                            try { await loadSchedules(); } catch (e) { /* ignore */ }
                            try { await loadWeekSchedule(); } catch (e) { /* ignore */ }
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

function addMessage(text, role, badge = '') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.innerHTML = `<div class="message-content">${renderMarkdown(escapeHtml(text))}${badge}</div>`;
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
            googleBtn.textContent = connected ? ui('Mở Gmail', 'Open Gmail') : ui('Kết nối', 'Connect');
            googleBtn.dataset.connected = connected ? 'true' : 'false';
        }
        updateUserModeUI(user.user_mode || currentUserMode);
        setSettingsState(ui('Đã đồng bộ', 'Synced'));
    } catch (error) {
        setSettingsState(`${ui('Lỗi', 'Error')}: ${error.message}`, true);
    }
}

function handleSettingsGoogleAction() {
    const button = document.getElementById('settingsGoogleBtn');
    if (button?.dataset.connected === 'true') {
        openExternalUrl('https://mail.google.com');
    } else {
        gmailLogin();
    }
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
    if (!confirm(ui('Bạn có chắc chắn muốn làm mới cuộc trò chuyện?', 'Are you sure you want to clear this conversation?'))) return;
    
    try {
        const response = await apiFetch(`${API_BASE}/chat/clear`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
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
let lastMeetingSuggestionScanAt = 0;

async function toggleEmailReadStatus(emailId, isUnread) {
    try {
        const endpoint = isUnread ? 'mark-as-read' : 'mark-as-unread';
        const response = await apiFetch(`${API_BASE}/email/${endpoint}/${emailId}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            const action = isUnread ? ui('đã đọc', 'read') : ui('chưa đọc', 'unread');
            showNotification(ui(`✅ Đã đánh dấu email ${action}`, `✅ Email marked as ${action}`), 'success');
            // Reload emails to reflect the change
            await loadEmails(currentEmailPage);
        } else {
            showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${data.error || ui('Không thể đánh dấu email', 'Unable to update email')}`, 'error');
        }
    } catch (error) {
        console.error('Error toggling email read status:', error);
        showNotification(`${ui('❌ Lỗi', '❌ Error')}: ${error.message}`, 'error');
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
    
    emailsList.innerHTML = `<p style="padding: 20px; text-align: center; color: #666;">${ui('⏳ Đang tải email...', '⏳ Loading email...')}</p>`;
    const selectedFilter = emailFilterSelect ? emailFilterSelect.value : 'all';
    const includeReadCheckbox = document.getElementById('includeReadCheckbox');
    const includeRead = includeReadCheckbox ? includeReadCheckbox.checked : true;
    currentEmailPage = page;

    await refreshAuthButtons();
    
    try {
        const search = emailSearchInput ? emailSearchInput.value.trim() : '';
        const url = `${API_BASE}/email/get-unread?max_results=20&page=${page}&filter=${encodeURIComponent(selectedFilter)}&include_read=${includeRead}&search=${encodeURIComponent(search)}`;
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
                        <button onclick="loadEmails(1)" class="btn-primary" style="margin-top: 10px;">${ui('🔄 Thử lại', '🔄 Try again')}</button>
                </div>
            `;
            return;
        }

        notifyMeetingSuggestions(data.meeting_suggestions || []);
        
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
                        <button onclick="emailFilterSelect.value='all'; updateEmailFilterUI(); loadEmails(1);" class="btn-primary">${ui('🔍 Xem tất cả', '🔍 View all')}</button>
                        <button onclick="loadEmails(1)" class="btn-secondary">${ui('🔄 Làm mới', '🔄 Refresh')}</button>
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
        
        return;
        
        
        function renderEmailItem(email, container) {
            const emailDiv = document.createElement('div');
            emailDiv.className = 'email-item';
            
            // Add visual indicator for unread emails
            const readStatus = email.is_unread ? 
                `<span style="display: inline-block; width: 8px; height: 8px; background: #4CAF50; border-radius: 50%; margin-right: 6px;" title="${ui('Chưa đọc', 'Unread')}"></span>` :
                `<span style="display: inline-block; width: 8px; height: 8px; background: #ccc; border-radius: 50%; margin-right: 6px;" title="${ui('Đã đọc', 'Read')}"></span>`;
            
            const markButtonText = email.is_unread ? ui('✅ Đánh dấu đã đọc', '✅ Mark as read') : ui('📧 Đánh dấu chưa đọc', '📧 Mark as unread');
            const markButtonClass = email.is_unread ? 'mark-read-btn' : 'mark-unread-btn';
            
            // Tag styling
            const tagColors = {
                'education': '#4CAF50',
                'business': '#2196F3',
                'ads': '#FF9800',
                'notification': '#9C27B0',
                'personal': '#F44336',
                'social': '#00BCD4',
                'other': '#757575'
            };
            const tagColor = tagColors[email.tag] || tagColors['other'];
            const tagHTML = email.tag ? 
                `<span style="display: inline-block; background: ${tagColor}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-right: 6px; font-weight: bold;">${email.tag}</span>` : '';
            
            // Summary display
            const summaryHTML = email.summary ? 
                `<div class="email-item-summary" style="font-size: 13px; color: #666; margin-top: 6px; font-style: italic;">${escapeHtml(email.summary)}</div>` : '';
            
            emailDiv.innerHTML = `
                <div class="email-item-header">
                    <span class="email-item-subject">${readStatus}${tagHTML}${escapeHtml(email.subject)}</span>
                </div>
                <div class="email-item-sender">${ui('Từ', 'From')}: ${escapeHtml(email.sender)}</div>
                ${summaryHTML}
                <div class="email-item-snippet" style="color: #888; font-size: 12px; margin-top: 4px;">${escapeHtml(email.snippet)}</div>
                <div class="email-item-actions" style="margin-top: 8px; display: flex; gap: 6px;">
                    <button class="email-view-detail-btn" style="padding: 4px 12px; font-size: 12px; background: #666; color: white; border: none; border-radius: 4px; cursor: pointer;">👁️ Xem</button>
                    <button class="${markButtonClass}" data-email-id="${email.id}" data-is-unread="${email.is_unread}" style="padding: 4px 12px; font-size: 12px; background: ${email.is_unread ? '#4CAF50' : '#FF9800'}; color: white; border: none; border-radius: 4px; cursor: pointer;">${markButtonText}</button>
                </div>
            `;
            
            emailDiv.querySelector('.email-view-detail-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                showFormattedEmailDetail(email);
            });

            // Click on the item opens the full-email modal
            emailDiv.addEventListener('click', (e) => {
                if (e.target && e.target.closest('button')) return;
                showFormattedEmailDetail(email);
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
            prevBtn.textContent = ui('◀ Trang trước', '◀ Previous');
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

    emailDiv.innerHTML = `
        <div class="email-item-header">
            <span class="email-item-subject">
                <span class="email-read-state">${email.is_unread ? ui('Chưa đọc', 'Unread') : ui('Đã đọc', 'Read')}</span>
                ${tagHTML}${escapeHtml(email.subject || ui('(Không có tiêu đề)', '(No subject)'))}
            </span>
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

async function showEmailDetail(email) {
    const emailDetail = document.getElementById('emailDetail');
    if (!emailDetail) return;
    currentDetailEmail = email;

    // Tag styling
    const tagColors = {
        'education': '#4CAF50',
        'business': '#2196F3',
        'ads': '#FF9800',
        'notification': '#9C27B0',
        'personal': '#F44336',
        'social': '#00BCD4',
        'other': '#757575'
    };
    const tagColor = tagColors[email.tag] || tagColors['other'];
    const tagHTML = email.tag ? 
        `<div style="margin: 12px 0;"><span style="display: inline-block; background: ${tagColor}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold;">📁 ${email.tag.toUpperCase()}</span></div>` : '';
    
    const summaryHTML = email.summary ? 
        `<div style="margin: 12px 0; padding: 12px; background: #F5F5F5; border-left: 3px solid ${tagColor}; border-radius: 4px;">
            <strong style="color: #333;">📋 ${ui('Tóm tắt', 'Summary')}:</strong>
            <p style="margin: 6px 0 0 0; color: #666;">${escapeHtml(email.summary)}</p>
        </div>` : '';
    
    emailDetail.innerHTML = `
        <div class="email-detail-subject">${escapeHtml(email.subject)}</div>
        ${tagHTML}
        ${summaryHTML}
        <div class="email-detail-meta">
            <strong>${ui('Từ', 'From')}:</strong> ${escapeHtml(email.sender)}<br>
            <strong>${ui('Ngày', 'Date')}:</strong> ${escapeHtml(email.date)}
        </div>
        <div class="email-detail-body" style="color: #666; font-style: italic;">${ui('Đang tải nội dung...', 'Loading content...')}</div>
    `;
    
    if (emailDetailModal) emailDetailModal.classList.add('show');
    
    // Lazy load body
    if (!email.body || !Array.isArray(email.attachments)) {
        try {
            const response = await apiFetch(`${API_BASE}/email/get-email-body/${email.id}`);
            const data = await response.json();
            email.body = data.success ? data.body : ui('Không thể tải nội dung', 'Unable to load content');
            email.attachments = data.success && Array.isArray(data.email?.attachments)
                ? data.email.attachments
                : [];
        } catch (error) {
            email.body = ui('Lỗi: ', 'Error: ') + error.message;
            email.attachments = [];
        }
    }
    
    emailDetail.innerHTML = `
        <div class="email-detail-subject">${escapeHtml(email.subject)}</div>
        ${tagHTML}
        ${summaryHTML}
        <div class="email-detail-meta">
            <strong>${ui('Từ', 'From')}:</strong> ${escapeHtml(email.sender)}<br>
            <strong>${ui('Ngày', 'Date')}:</strong> ${escapeHtml(email.date)}
        </div>
        <div class="email-detail-body">${formatEmailText(email.body)}</div>
    `;
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

function formatWeekDate(date) {
    const dd = String(date.getDate()).padStart(2, '0');
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    return `${dd}/${mm}`;
}

function isSameDate(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

async function loadWeekSchedule() {
    const headerRow = document.getElementById('weekTableHeader');
    const tableBody = document.getElementById('weekTableBody');
    const rangeLabel = document.getElementById('weekRangeLabel');
    if (!headerRow || !tableBody) return;

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

    tableBody.innerHTML = `<tr><td colspan="6" class="week-loading">${ui('Đang tải...', 'Loading...')}</td></tr>`;

    try {
        const response = await apiFetch(`${API_BASE}/schedule/week?start=${weekStartStr}`);
        const data = await response.json();

        if (!data.success) {
            tableBody.innerHTML = `<tr><td colspan="6" class="week-loading">${ui('Không thể tải lịch tuần', 'Unable to load weekly calendar')}</td></tr>`;
            return;
        }

        tableBody.innerHTML = '';
        for (let hour = 8; hour <= 18; hour++) {
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

                const dayEvents = (data.days && data.days[i]) || [];
                dayEvents
                    .filter((schedule) => new Date(schedule.start_time).getHours() === hour)
                    .forEach((schedule) => {
                    const eventDiv = document.createElement('div');
                    eventDiv.className = 'week-event';
                    const startTime = new Date(schedule.start_time).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
                    const endTime = schedule.end_time ? new Date(schedule.end_time).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }) : '';

                    eventDiv.innerHTML = `
                        <div class="week-event-title">${escapeHtml(schedule.title)}</div>
                        <div class="week-event-time">${startTime}${endTime ? ' - ' + endTime : ''}</div>
                    `;
                    eventDiv.addEventListener('click', () => openEditSchedule(schedule.id));
                    td.appendChild(eventDiv);
                });
                row.appendChild(td);
            }
            tableBody.appendChild(row);
        }
    } catch (error) {
        tableBody.innerHTML = `<tr><td colspan="6" class="week-loading">${ui('Không thể tải lịch tuần', 'Unable to load weekly calendar')}</td></tr>`;
    }
}

function openNewScheduleModal(preserveSuggestion = false) {
    const modal = document.getElementById('newScheduleModal');
    const form = document.getElementById('scheduleForm');
    if (!preserveSuggestion && form) delete form.dataset.meetingSuggestionId;
    if (modal) modal.classList.add('show');
}

function closeNewScheduleModal() {
    const modal = document.getElementById('newScheduleModal');
    const form = document.getElementById('scheduleForm');
    if (form) delete form.dataset.meetingSuggestionId;
    if (modal) modal.classList.remove('show');
}

// SCHEDULE FUNCTIONS
async function loadSchedules() {
    const schedulesList = document.getElementById('schedulesList');
    if (!schedulesList) return;

    schedulesList.innerHTML = `<p class="schedule-empty-state">${ui('Đang tải lịch tổng hợp...', 'Loading calendar...')}</p>`;
    scanMeetingSuggestions()
        .catch(error => console.warn('Meeting suggestion scan error:', error))
        .finally(() => loadMeetingSuggestions().catch(error => {
            console.error('Meeting suggestion load error:', error);
        }));

    try {
        const response = await apiFetch(`${API_BASE}/schedule/unified?max_results=100`);
        const data = await response.json();

        const calendarStatus = document.getElementById('calendarStatus');
        if (calendarStatus) {
            calendarStatus.textContent = data.calendar_connected
                ? ui(`Đã kết nối - ${data.count || 0} sự kiện`, `Connected - ${data.count || 0} events`)
                : ui('Lịch FlowMate', 'FlowMate Calendar');
        }

        const schedules = Array.isArray(data.items) ? data.items : [];
        if (data.success && schedules.length > 0) {
            schedulesList.innerHTML = '';
            schedules.forEach(schedule => {
                const scheduleDiv = document.createElement('div');
                scheduleDiv.className = `schedule-item unified-schedule-item source-${schedule.source || 'local'}`;
                const startTime = new Date(schedule.start_time).toLocaleString('vi-VN');
                const endTime = schedule.end_time ? new Date(schedule.end_time).toLocaleString('vi-VN') : '';
                const durationMinutes = getDurationMinutes(schedule.start_time, schedule.end_time);
                const statusClass = schedule.status === 'completed' ? 'completed' : 'pending';
                const statusText = schedule.status === 'completed'
                    ? ui('Đã hoàn thành', 'Completed')
                    : ui('Chưa hoàn thành', 'Pending');
                const isLocal = schedule.local_id !== null && schedule.local_id !== undefined;
                const sourceText = schedule.source === 'synced'
                    ? 'FlowMate + Google'
                    : schedule.source === 'google' ? 'Google Calendar' : 'FlowMate';
                const sourceClass = schedule.source === 'synced'
                    ? 'synced'
                    : schedule.source === 'google' ? 'google' : 'local';
                const attendees = Array.isArray(schedule.attendees)
                    ? schedule.attendees.join(', ')
                    : String(schedule.attendees || '');
                const description = plainTextFromHtml(schedule.description || '');
                const localActions = isLocal
                    ? `
                        ${schedule.status === 'completed'
                            ? `<button class="btn-check" onclick="markScheduleIncomplete(${schedule.local_id})">${ui('↩ Chưa xong', '↩ Mark pending')}</button>`
                            : `<button class="btn-check" onclick="markScheduleComplete(${schedule.local_id})">${ui('✓ Hoàn thành', '✓ Complete')}</button>`}
                        <button class="btn-edit" onclick="openEditSchedule(${schedule.local_id})">${ui('Sửa', 'Edit')}</button>
                        <button class="btn-delete" onclick="deleteSchedule(${schedule.local_id})">${ui('Xóa', 'Delete')}</button>
                    `
                    : `<button class="btn-delete" data-google-event-id="${escapeHtml(schedule.google_event_id || '')}">${ui('Xóa khỏi Google', 'Delete from Google')}</button>`;

                scheduleDiv.innerHTML = `
                    <div class="schedule-item-main">
                        <div class="schedule-item-heading">
                            <div>
                                <div class="schedule-item-title">${escapeHtml(schedule.title || ui('Sự kiện', 'Event'))}</div>
                                <div class="schedule-item-time">${startTime}${endTime ? ` - ${endTime}` : ''}</div>
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
                schedulesList.appendChild(scheduleDiv);
            });
        } else {
            schedulesList.innerHTML = `<p class="schedule-empty-state">${ui('Không có sự kiện sắp tới', 'No upcoming events')}</p>`;
        }
    } catch (error) {
        schedulesList.innerHTML = `<p class="schedule-empty-state">${ui('Lỗi', 'Error')}: ${escapeHtml(error.message)}</p>`;
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
    section.hidden = suggestions.length === 0;
    count.textContent = String(suggestions.length);
    list.innerHTML = '';
    notifyMeetingSuggestions(suggestions);

    suggestions.forEach(suggestion => {
        const card = document.createElement('article');
        card.className = 'meeting-suggestion-card';
        const start = suggestion.start_time
            ? new Date(suggestion.start_time).toLocaleString(currentLanguage === 'en' ? 'en-US' : 'vi-VN')
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
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể cập nhật trạng thái', 'Unable to update status')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
    }
}

async function openEditSchedule(scheduleId) {
    try {
        const response = await apiFetch(`${API_BASE}/schedule/list`);
        const data = await response.json();
        
        if (!data.success) throw new Error(ui('Lỗi lấy dữ liệu', 'Unable to load data'));
        
        const schedule = data.schedules.find(s => s.id === scheduleId);
        if (!schedule) throw new Error(ui('Lịch hẹn không tìm thấy', 'Appointment not found'));
        
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
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
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
            showNotification(ui('✓ Đã cập nhật lịch hẹn', '✓ Appointment updated'), 'success');
            document.getElementById('editScheduleModal').style.display = 'none';
            await loadSchedules();
            await loadCalendarEvents();
            await loadWeekSchedule();
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể cập nhật lịch hẹn', 'Unable to update appointment')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
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
            await loadSchedules();
            await loadCalendarEvents();
            await loadWeekSchedule();
        } else {
            showNotification(ui('❌ Lỗi: ', '❌ Error: ') + (data.error || ui('Không thể xóa lịch hẹn', 'Unable to delete appointment')), 'error');
        }
    } catch (error) {
        showNotification(ui('❌ Lỗi: ', '❌ Error: ') + error.message, 'error');
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
            } else {
                showNotification(ui('✅ Đã tạo lịch hẹn. Đang đồng bộ với Google Calendar...', '✅ Appointment created. Syncing with Google Calendar...'), 'info');
            }
            scheduleForm.reset();
            closeNewScheduleModal();
            await loadSchedules();
            // refresh calendar events too
            await loadCalendarEvents();
            await loadWeekSchedule();

            // If calendar_event_id not present, poll for status in background
            if (!data.calendar_event_id && sid) {
                pollScheduleSync(sid, 30000).then(synced => {
                    if (synced) {
                        showNotification(ui('✅ Lịch hẹn đã được đồng bộ với Google Calendar', '✅ Appointment synced with Google Calendar'), 'success');
                    } else {
                        showNotification(ui('⚠️ Đồng bộ lịch hẹn chưa hoàn tất - thử lại sau', '⚠️ Appointment sync is not complete - try again later'), 'info');
                    }
                    loadSchedules();
                    loadCalendarEvents();
                    loadWeekSchedule();
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
            await loadSchedules();
            await loadWeekSchedule();
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
            await loadSchedules();
            await loadWeekSchedule();
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
                        <div>${escapeHtml(row.summary || ui('Không có tóm tắt', 'No summary available'))}</div>
                        ${meetingNote ? `<div style="margin-top:8px;padding:8px 10px;background:#FFF8E1;border-left:4px solid #FFB300;border-radius:6px;font-size:13px;color:#8D6E63;">${escapeHtml(meetingNote)}</div>` : ''}
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; vertical-align: top; min-width: 180px;">
                        <span style="display:inline-block;padding:4px 8px;border-radius:999px;background:${isMeeting ? '#FFF3E0' : '#F5F5F5'};color:${isMeeting ? '#E65100' : '#666'};font-size:12px;font-weight:600;">${isMeeting ? ui('📅 Gợi ý tạo lịch', '📅 Event suggested') : ui('Không phải cuộc họp', 'Not a meeting')}</span>
                        ${actionButtons}
                    </td>
                </tr>
            `;
        }).join('');

        container.innerHTML = `
            <div style="padding: 20px;">
                <div style="margin-bottom: 16px; padding: 12px; background: #E8F5E9; border-radius: 8px;">
                    <strong style="color: #2E7D32;">${ui('📧 Báo cáo email ngày', '📧 Email report for')} ${escapeHtml(data.date)}</strong><br>
                    <span style="color: #666; font-size: 14px;">${ui('Tổng', 'Total')}: ${data.total_emails} email</span>
                </div>
                <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <thead>
                        <tr style="background: #4F46E5; color: white;">
                            <th style="padding: 12px 8px; text-align: center; width: 60px;">#</th>
                            <th style="padding: 12px; text-align: left; width: 30%;">${ui('Người gửi', 'Sender')}</th>
                            <th style="padding: 12px; text-align: left;">${ui('Nội dung tóm tắt', 'Summary')}</th>
                            <th style="padding: 12px; text-align: left; width: 210px;">${ui('Chú thích / Hành động', 'Notes / Actions')}</th>
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
            await loadSchedules();
            await loadCalendarEvents();
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
