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
    'Chế độ làm việc': 'Work mode',
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
    'Đăng xuất FlowMate': 'Sign out of FlowMate',
    'Kết thúc phiên đăng nhập trên trình duyệt này.': 'End the sign-in session on this browser.',
    'Đăng xuất': 'Sign out',
    'Họ và tên': 'Full Name',
    'Mật khẩu': 'Password',
    'Hiện': 'Show',
    'Mật khẩu phải có ít nhất 8 ký tự.': 'Password must be at least 8 characters.',
    'HOẶC TIẾP TỤC VỚI': 'OR CONTINUE WITH',
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
    'Mô tả / Nội dung cuộc hẹn': 'Description / Appointment details',
    'Nhập họ và tên': 'Enter your full name'
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
    if (document.getElementById('authLoginStage') && !document.getElementById('authLoginStage').hidden) {
        setAuthFormMode(authFormMode);
    }
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
    renderSubscriptionUI(currentSubscription);
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
