function setupAuthGate() {
    document.getElementById('appAuthForm')?.addEventListener('submit', submitPasswordAuth);
    document.getElementById('authModeToggle')?.addEventListener('click', () => {
        setAuthFormMode(authFormMode === 'login' ? 'signup' : 'login');
    });
    document.getElementById('authPasswordToggle')?.addEventListener('click', toggleAuthPasswordVisibility);
    document.getElementById('authRecoverGoogleBtn')?.addEventListener('click', recoverViaGoogle);
    document.getElementById('setPasswordForm')?.addEventListener('submit', submitSetPassword);
    document.getElementById('authForgotPasswordBtn')?.addEventListener('click', () => {
        const status = document.getElementById('authGateStatus');
        if (status) status.textContent = ui('Tính năng khôi phục mật khẩu sẽ sớm ra mắt.', 'Password recovery is coming soon.');
    });
    document.getElementById('adminOpenAppBtn')?.addEventListener('click', () => {
        const key = adminDestinationStorageKey();
        if (key) sessionStorage.setItem(key, 'app');
        window.location.replace('/app');
    });
    document.getElementById('adminOpenDashboardBtn')?.addEventListener('click', () => {
        window.location.assign('/admin');
    });
    setupGmailLinkConflictModal();
    setAuthFormMode('login');
    showAuthGate(ui('Đang kiểm tra phiên đăng nhập...', 'Checking your sign-in session...'), true);
}

function setAuthFormMode(mode) {
    authFormMode = mode === 'signup' ? 'signup' : 'login';
    const isSignup = authFormMode === 'signup';
    const nameField = document.getElementById('authNameField');
    const nameInput = document.getElementById('authNameInput');
    const passwordInput = document.getElementById('authPasswordInput');
    const passwordHint = document.getElementById('authPasswordHint');
    const title = document.getElementById('authFormTitle');
    const subtitle = document.getElementById('authFormSubtitle');
    const submitLabel = document.querySelector('#authSubmitBtn .auth-submit-label');
    const prompt = document.getElementById('authModePrompt');
    const toggle = document.getElementById('authModeToggle');

    if (nameField) nameField.hidden = !isSignup;
    if (nameInput) nameInput.required = isSignup;
    if (passwordInput) passwordInput.autocomplete = isSignup ? 'new-password' : 'current-password';
    if (passwordHint) passwordHint.hidden = !isSignup;
    if (title) title.textContent = isSignup
        ? ui('Tạo tài khoản', 'Create Account')
        : ui('Chào mừng trở lại', 'Welcome Back');
    if (subtitle) subtitle.textContent = isSignup
        ? ui('Tham gia FlowMate ngay hôm nay.', 'Join FlowMate today.')
        : ui('Đăng nhập để tiếp tục không gian làm việc của bạn.', 'Sign in to continue to your workspace.');
    if (submitLabel) submitLabel.textContent = isSignup
        ? ui('Tạo tài khoản →', 'Create Account →')
        : ui('Vào không gian làm việc →', 'Enter Workspace →');
    if (prompt) prompt.textContent = isSignup
        ? ui('Đã có tài khoản?', 'Already have an account?')
        : ui('Chưa có tài khoản?', "Don't have an account?");
    if (toggle) toggle.textContent = isSignup
        ? ui('Đăng nhập ngay', 'Sign in now')
        : ui('Đăng ký ngay', 'Sign up now');

    const status = document.getElementById('authGateStatus');
    if (status) status.textContent = '';
}

function toggleAuthPasswordVisibility() {
    const input = document.getElementById('authPasswordInput');
    const button = document.getElementById('authPasswordToggle');
    const icon = button?.querySelector('.auth-eye-icon');
    if (!input || !button) return;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    icon?.classList.toggle('is-visible', show);
    button.setAttribute('aria-label', show ? ui('Ẩn mật khẩu', 'Hide password') : ui('Hiện mật khẩu', 'Show password'));
    button.setAttribute('aria-pressed', String(show));
}

function setPasswordAuthLoading(loading) {
    const form = document.getElementById('appAuthForm');
    const submit = document.getElementById('authSubmitBtn');
    form?.querySelectorAll('input, button').forEach((control) => {
        control.disabled = loading;
    });
    submit?.classList.toggle('is-loading', loading);
    document.getElementById('authModeToggle')?.toggleAttribute('disabled', loading);
}

async function submitPasswordAuth(event) {
    event.preventDefault();
    const name = document.getElementById('authNameInput')?.value.trim() || '';
    const email = document.getElementById('authEmailInput')?.value.trim() || '';
    const password = document.getElementById('authPasswordInput')?.value || '';
    const status = document.getElementById('authGateStatus');
    const isSignup = authFormMode === 'signup';

    if (isSignup && !name) {
        if (status) status.textContent = ui('Vui lòng nhập họ và tên.', 'Please enter your full name.');
        document.getElementById('authNameInput')?.focus();
        return;
    }
    if (!email || !password) {
        if (status) status.textContent = ui('Vui lòng nhập email và mật khẩu.', 'Please enter your email and password.');
        return;
    }
    if (isSignup && password.length < 8) {
        if (status) status.textContent = ui('Mật khẩu phải có ít nhất 8 ký tự.', 'Password must be at least 8 characters.');
        document.getElementById('authPasswordInput')?.focus();
        return;
    }

    setPasswordAuthLoading(true);
    if (status) status.textContent = isSignup
        ? ui('Đang tạo tài khoản...', 'Creating your account...')
        : ui('Đang đăng nhập...', 'Signing in...');

    try {
        const response = await fetch(`${API_BASE}/auth/${isSignup ? 'register' : 'login'}`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify(isSignup ? { name, email, password } : { email, password })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(data.message || data.error || ui('Không thể đăng nhập.', 'Unable to sign in.'));
        }

        if (status) status.textContent = ui('Đăng nhập thành công. Đang mở ứng dụng...', 'Signed in. Opening your workspace...');
        window.location.replace('/app');
    } catch (error) {
        if (status) status.textContent = error.message || ui('Không thể đăng nhập. Vui lòng thử lại.', 'Unable to sign in. Please try again.');
        setPasswordAuthLoading(false);
    }
}

function showAuthGate(message = '', loading = false) {
    const gate = document.getElementById('authGate');
    const status = document.getElementById('authGateStatus');
    document.body.classList.remove('workspace-ready');
    gate?.classList.remove('is-hidden');
    gate?.classList.remove('is-mode-stage');
    gate?.classList.remove('is-admin-choice');
    gate?.classList.toggle('is-loading', loading);
    const loginStage = document.getElementById('authLoginStage');
    const adminChoice = document.getElementById('adminAccessChoice');
    if (loginStage) loginStage.hidden = false;
    if (adminChoice) adminChoice.hidden = true;
    if (status) status.textContent = message;
    document.getElementById('appAuthForm')?.querySelectorAll('input, button').forEach((control) => {
        control.disabled = loading;
    });
    const modeToggle = document.getElementById('authModeToggle');
    if (modeToggle) modeToggle.disabled = loading;
    document.getElementById('authRecoverGoogleBtn')?.toggleAttribute('disabled', loading);
    document.getElementById('workspaceApp')?.setAttribute('aria-hidden', 'true');
}

function showWorkspace() {
    const gate = document.getElementById('authGate');
    gate?.classList.add('is-hidden');
    gate?.classList.remove('is-loading', 'is-mode-stage', 'is-admin-choice');
    document.body.classList.add('workspace-ready');
    document.getElementById('workspaceApp')?.setAttribute('aria-hidden', 'false');
}

function adminDestinationStorageKey() {
    const identity = lastAuthStatus?.user_id || lastAuthStatus?.gmail_email;
    return identity ? `flowmate-admin-destination:${identity}` : '';
}

function shouldShowAdminAccessChoice() {
    if (!lastAuthStatus?.authenticated || !lastAuthStatus?.is_admin) return false;

    const key = adminDestinationStorageKey();
    const params = new URLSearchParams(window.location.search);
    if (params.get('admin_destination') === 'app' && key) {
        sessionStorage.setItem(key, 'app');
        params.delete('admin_destination');
        const query = params.toString();
        window.history.replaceState(
            {},
            document.title,
            `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`
        );
    }
    return !key || sessionStorage.getItem(key) !== 'app';
}

function showAdminAccessChoice() {
    const gate = document.getElementById('authGate');
    const status = document.getElementById('authGateStatus');
    const loginStage = document.getElementById('authLoginStage');
    const adminChoice = document.getElementById('adminAccessChoice');
    document.body.classList.remove('workspace-ready');
    gate?.classList.remove('is-hidden', 'is-loading', 'is-mode-stage');
    gate?.classList.add('is-admin-choice');
    if (loginStage) loginStage.hidden = true;
    if (adminChoice) adminChoice.hidden = false;
    if (status) status.textContent = '';
    document.getElementById('workspaceApp')?.setAttribute('aria-hidden', 'true');
}

function showModeSelectionStage() {
    const gate = document.getElementById('authGate');
    gate?.classList.remove('is-hidden', 'is-loading');
    gate?.classList.add('is-mode-stage');
    document.body.classList.remove('workspace-ready');
    document.getElementById('workspaceApp')?.setAttribute('aria-hidden', 'true');
}

async function resolveInitialAuthState() {
    let profileData = null;
    try {
        const profileResponse = await fetch(`${API_BASE}/user/profile`, {
            credentials: 'include',
            headers: { Accept: 'application/json' }
        });
        profileData = await profileResponse.json().catch(() => null);
        isAuthenticated = !!(profileResponse.ok && profileData?.success && profileData?.user);
    } catch (error) {
        console.error('Initial auth check failed:', error);
        isAuthenticated = false;
    }

    try {
        const response = await fetch(`${API_BASE}/email/auth-status`, {
            credentials: 'include',
            headers: { Accept: 'application/json' }
        });
        const googleStatus = await response.json();
        lastAuthStatus = {
            ...googleStatus,
            app_authenticated: isAuthenticated,
            user_id: profileData?.user?.user_id || googleStatus.user_id,
        };
    } catch (error) {
        console.warn('Google auth status check failed:', error);
        lastAuthStatus = {
            authenticated: false,
            app_authenticated: isAuthenticated,
            user_id: profileData?.user?.user_id || '',
        };
    }

    if (!isAuthenticated) {
        stopWorkspaceSyncWatcher();
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

// Update sidebar user profile display
function updateSidebarUserProfile(profile) {
    if (!profile) return;
    const { name, email, avatarUrl, connected } = profile;
    
    // Update username
    const userNameEl = document.getElementById('userName');
    if (userNameEl) {
        userNameEl.textContent = name || 'Teacher';
    }
    if (typeof updateOverviewGreeting === 'function') {
        updateOverviewGreeting(name || '');
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

// Keep in sync with routes/email/oauth.py's _oauth_error_redirect error codes.
const GMAIL_AUTH_ERROR_MESSAGES = {
    google_account_already_linked_elsewhere: ui(
        'Tài khoản Google này đã được liên kết với một tài khoản FlowMate khác. Hãy đăng xuất khỏi tài khoản đó trên Google hoặc dùng một tài khoản Google khác.',
        'This Google account is already linked to a different FlowMate account. Sign out of it on Google or use a different Google account.'
    ),
    no_flowmate_account_for_google_identity: ui(
        'Không tìm thấy tài khoản FlowMate nào từng liên kết với tài khoản Google này.',
        'No FlowMate account has ever linked this Google account.'
    ),
    token_fetch_failed: ui(
        'Không thể hoàn tất xác thực với Google. Vui lòng thử lại.',
        'Could not complete authentication with Google. Please try again.'
    ),
    invalid_oauth_state: ui(
        'Phiên liên kết Google đã hết hạn hoặc đã được dùng. Vui lòng thử lại.',
        'The Google linking session expired or was already used. Please try again.'
    ),
    flow_not_initialized: ui(
        'Không tìm thấy phiên liên kết Google. Vui lòng thử lại.',
        'No Google linking session was found. Please try again.'
    ),
    oauth_flow_unavailable: ui(
        'Google OAuth hiện chưa khả dụng. Vui lòng thử lại sau.',
        'Google OAuth is currently unavailable. Please try again later.'
    ),
    callback_error: ui(
        'Có lỗi xảy ra khi liên kết tài khoản Google. Vui lòng thử lại.',
        'Something went wrong linking your Google account. Please try again.'
    ),
};

async function checkOAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const needsPassword = urlParams.get('needs_password') === '1';
    if (urlParams.get('gmail_auth') === 'error') {
        console.log('❌ OAuth callback error detected');
        const errorCode = urlParams.get('error') || '';
        const conflictEmail = urlParams.get('email') || '';
        window.history.replaceState({}, document.title, window.location.pathname);
        // The already-linked-elsewhere case gets its own modal with a
        // concrete next step (try a different account) instead of a toast
        // that disappears before the user can act on it -- see
        // showGmailLinkConflictModal.
        if (errorCode === 'google_account_already_linked_elsewhere') {
            showGmailLinkConflictModal(conflictEmail);
            return;
        }
        showNotification(
            `❌ ${GMAIL_AUTH_ERROR_MESSAGES[errorCode] || ui('Không thể liên kết tài khoản Google. Vui lòng thử lại.', 'Could not link the Google account. Please try again.')}`,
            'error'
        );
        return;
    }
    if (urlParams.get('gmail_auth') === 'success') {
        console.log('✅ OAuth callback detected');
        Object.keys(sessionStorage)
            .filter((key) => key.startsWith('flowmate-admin-destination:'))
            .forEach((key) => sessionStorage.removeItem(key));
        window.history.replaceState({}, document.title, window.location.pathname);

        try {
            await apiFetch(`${API_BASE}/user/gmail-connected`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            await refreshAuthButtons();
            await loadUserProfile();

            if (needsPassword) {
                showSetPasswordModal();
                return;
            }

            showNotification(ui('✅ Gmail đã kết nối thành công!', '✅ Gmail connected successfully!'), 'success');
            // Give user immediate feedback that email is being loaded.
            setTimeout(() => showNotification(
                ui('⏳ Đang quét Gmail của bạn, chuyển sang tab Email để xem...', '⏳ Scanning your Gmail, switch to the Email tab to see results...'),
                'info'
            ), 800);
        } catch (error) {
            console.error('OAuth completion refresh failed:', error);
        }
    }
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
            : ui('Kết nối Gmail', 'Connect Gmail');
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
    if (!confirm(ui('Bạn có chắc muốn ngắt kết nối Gmail?', 'Are you sure you want to disconnect Gmail?'))) return;

    try {
        const response = await apiFetch(`${API_BASE}/email/logout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            showNotification(ui('✅ Đã ngắt kết nối Gmail', '✅ Gmail disconnected'), 'success');
            if (lastAuthStatus) lastAuthStatus.authenticated = false;
            await refreshAuthButtons();
        }
    } catch (err) {
        alert(ui('Lỗi: ', 'Error: ') + err.message);
    }
}

async function appLogout() {
    if (!confirm(ui('Bạn có chắc muốn đăng xuất FlowMate?', 'Are you sure you want to sign out of FlowMate?'))) return;

    try {
        const response = await apiFetch(`${API_BASE}/auth/logout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || data.error || ui('Không thể đăng xuất', 'Unable to sign out'));
        }

        isAuthenticated = false;
        lastAuthStatus = null;
        Object.keys(sessionStorage)
            .filter((key) => key.startsWith('flowmate-admin-destination:'))
            .forEach((key) => sessionStorage.removeItem(key));
        stopWorkspaceSyncWatcher();
        userModeRequired = false;
        pendingPageAfterMode = '';
        userModeModal?.classList.remove('show', 'is-required');
        window.location.replace('/');
    } catch (err) {
        alert(ui('Lỗi: ', 'Error: ') + err.message);
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
            isAuthenticated = true;
            renderSubscriptionUI(user.subscription);
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
            if (user.mode_required || !storedMode) {
                showModeSelectionStage();
                openUserModeModal(true);
            } else {
                userModeRequired = false;
            }
            return user;
        }
    } catch (error) {
        console.error('Error loading user profile:', error);
    }
    return null;
}

async function gmailLogin() {
    // Always called from an already-logged-in context (Email toolbar,
    // Settings) -- Google can no longer establish a FlowMate session on
    // its own, so this only ever links a Gmail account to the current one.
    try {
        const response = await fetch(`${API_BASE}/email/auth_url?intent=link`, {
            credentials: 'include',
            headers: { Accept: 'application/json' }
        });
        const data = await response.json();

        if (!response.ok || !data.auth_url) {
            alert(ui('Lỗi: ', 'Error: ') + (data.error || ui('OAuth chưa được cấu hình', 'OAuth is not configured')));
            return;
        }

        window.location.href = data.auth_url;
    } catch (err) {
        alert(ui('Lỗi: ', 'Error: ') + err.message);
    }
}

async function recoverViaGoogle() {
    // The ONLY remaining path where Google establishes a session on its
    // own: an existing account that previously linked this Gmail (no
    // password set yet) regains access, then must set one -- see
    // checkOAuthCallback's needs_password handling. Never creates a new
    // account (see oauth2callback's intent=recover branch).
    showAuthGate(ui('Đang chuyển đến Google...', 'Redirecting to Google...'), true);
    try {
        const response = await fetch(`${API_BASE}/email/auth_url?intent=recover`, {
            credentials: 'include',
            headers: { Accept: 'application/json' }
        });
        const data = await response.json();

        if (!response.ok || !data.auth_url) {
            showAuthGate(ui(
                'Không thể bắt đầu khôi phục tài khoản. Vui lòng thử lại.',
                'Unable to start account recovery. Please try again.'
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

function showSetPasswordModal() {
    // Deliberately no close/dismiss control -- this is a forced, one-time
    // step after recovering a Google-only account (no permanent "skip"),
    // matching the explicit choice to require it before continuing.
    document.getElementById('authGate')?.classList.add('is-hidden');
    document.getElementById('setPasswordModal')?.classList.add('show');
    document.getElementById('setPasswordInput')?.focus();

    // Shows which email this password will log in with -- the backend
    // already uses this account's own Gmail address as its login email with
    // no extra step from the user (see POST /auth/set-password); this just
    // makes that visible instead of leaving it implicit. Sourced from
    // #gmailEmail, already populated by refreshAuthButtons() (awaited right
    // before this is called) -- no extra network call needed here.
    const emailNode = document.getElementById('setPasswordAccountEmail');
    const knownEmail = document.getElementById('gmailEmail')?.textContent?.trim();
    if (emailNode) {
        if (knownEmail) {
            emailNode.textContent = ui(`Tài khoản đăng nhập: ${knownEmail}`, `Login account: ${knownEmail}`);
            emailNode.hidden = false;
        } else {
            emailNode.hidden = true;
        }
    }
}

// Shown when oauth2callback rejects linking a Google account because it's
// already attached to a different FlowMate account (see
// GMAIL_AUTH_ERROR_MESSAGES/_oauth_error_redirect). A plain toast here used
// to disappear before the user could read or act on it; this modal stays
// open and offers a concrete next step.
function showGmailLinkConflictModal(email) {
    const messageNode = document.getElementById('gmailLinkConflictMessage');
    if (messageNode) {
        messageNode.textContent = email
            ? ui(
                `Tài khoản Google ${email} đã được liên kết với một tài khoản FlowMate khác.`,
                `The Google account ${email} is already linked to a different FlowMate account.`
            )
            : ui(
                'Tài khoản Google này đã được liên kết với một tài khoản FlowMate khác.',
                'This Google account is already linked to a different FlowMate account.'
            );
    }
    document.getElementById('gmailLinkConflictModal')?.classList.add('show');
}

function closeGmailLinkConflictModal() {
    document.getElementById('gmailLinkConflictModal')?.classList.remove('show');
}

function setupGmailLinkConflictModal() {
    document.getElementById('gmailLinkConflictModal')?.querySelectorAll('[data-modal="gmailLinkConflictModal"]').forEach((el) => {
        el.addEventListener('click', closeGmailLinkConflictModal);
    });
    document.getElementById('gmailLinkConflictRetryBtn')?.addEventListener('click', () => {
        closeGmailLinkConflictModal();
        // Google always re-prompts account selection (prompt=select_account
        // in gmail_auth_url), so simply restarting the link flow is enough
        // to let the user pick a different account.
        gmailLogin();
    });
}

async function submitSetPassword(event) {
    event.preventDefault();
    const input = document.getElementById('setPasswordInput');
    const status = document.getElementById('setPasswordStatus');
    const password = input?.value || '';
    if (password.length < 8) {
        if (status) status.textContent = ui('Mật khẩu phải có ít nhất 8 ký tự.', 'Password must be at least 8 characters.');
        input?.focus();
        return;
    }

    const submitBtn = document.getElementById('setPasswordSubmitBtn');
    submitBtn?.classList.add('is-loading');
    if (input) input.disabled = true;
    if (status) status.textContent = ui('Đang lưu mật khẩu...', 'Saving password...');

    try {
        const response = await apiFetch(`${API_BASE}/auth/set-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(data.message || ui('Không thể lưu mật khẩu.', 'Could not save the password.'));
        }

        document.getElementById('setPasswordModal')?.classList.remove('show');
        document.getElementById('authGate')?.classList.remove('is-hidden');
        showNotification(ui('✅ Đã đặt mật khẩu thành công!', '✅ Password set successfully!'), 'success');
        await refreshAuthButtons();
        await loadUserProfile();
    } catch (error) {
        if (status) status.textContent = error.message || ui('Không thể lưu mật khẩu. Vui lòng thử lại.', 'Could not save the password. Please try again.');
    } finally {
        submitBtn?.classList.remove('is-loading');
        if (input) input.disabled = false;
    }
}
