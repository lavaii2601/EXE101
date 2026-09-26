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

function subscriptionRemainingLabel(subscription) {
    if (!subscription?.current_period_end) {
        return ui('không giới hạn', 'unlimited');
    }
    let seconds = Number(subscription.remaining_seconds);
    if (!Number.isFinite(seconds)) {
        seconds = Math.max(0, Math.floor(
            (new Date(subscription.current_period_end).getTime() - Date.now()) / 1000
        ));
    }
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (days) {
        return ui(
            `${days} ngày${hours ? ` ${hours} giờ` : ''}`,
            `${days} day${days === 1 ? '' : 's'}${hours ? ` ${hours}h` : ''}`
        );
    }
    if (hours) return ui(`${hours} giờ ${minutes} phút`, `${hours}h ${minutes}m`);
    return ui(`${Math.max(0, minutes)} phút`, `${Math.max(0, minutes)}m`);
}

function renderSubscriptionUI(subscription = null) {
    currentSubscription = subscription || {
        tier: 'free',
        is_premium: false,
        allowed_action: 'purchase',
        remaining_seconds: 0
    };
    const isPremium = !!(
        currentSubscription.is_premium
        || currentSubscription.tier === 'premium'
    );
    const remaining = subscriptionRemainingLabel(currentSubscription);
    const periodEnd = currentSubscription.current_period_end
        ? new Date(currentSubscription.current_period_end).toLocaleDateString(
            currentLanguage === 'en' ? 'en-US' : 'vi-VN'
        )
        : '';

    const headerButton = document.getElementById('subscriptionHeaderBtn');
    const headerLabel = document.getElementById('subscriptionHeaderLabel');
    if (headerButton) headerButton.classList.toggle('is-premium', isPremium);
    if (headerLabel) {
        headerLabel.textContent = isPremium
            ? ui(`Premium · còn ${remaining}`, `Premium · ${remaining} left`)
            : ui('Nâng cấp Premium', 'Upgrade to Premium');
    }

    const tier = document.getElementById('settingsSubscriptionTier');
    const status = document.getElementById('settingsSubscriptionStatus');
    const badge = document.getElementById('settingsSubscriptionBadge');
    const details = document.getElementById('settingsSubscriptionDetails');
    const button = document.getElementById('settingsSubscriptionBtn');
    if (tier) tier.textContent = isPremium ? 'Premium' : 'Free';
    if (status) {
        status.textContent = isPremium
            ? ui(
                `Còn ${remaining}${periodEnd ? ` · Hết hạn ${periodEnd}` : ''}`,
                `${remaining} left${periodEnd ? ` · Expires ${periodEnd}` : ''}`
            )
            : ui(
                'Nâng cấp để mở khóa toàn bộ tính năng nâng cao.',
                'Upgrade to unlock all advanced features.'
            );
    }
    if (badge) {
        badge.textContent = isPremium ? 'PREMIUM' : 'FREE';
        badge.classList.toggle('is-premium', isPremium);
    }
    if (details) {
        details.innerHTML = isPremium
            ? `<span>${ui('Tóm tắt email AI không giới hạn', 'Unlimited AI email summaries')}</span>
               <span>${ui('Xử lý nhiều bước và phản hồi AI nâng cao', 'Multi-step processing and advanced AI responses')}</span>`
            : `<span>${ui('Chat và soạn trả lời AI không giới hạn', 'Unlimited chat and AI reply drafting')}</span>
               <span>${ui('Tóm tắt email AI: 10 lượt/ngày', 'AI email summaries: 10 per day')}</span>`;
    }
    if (button) {
        button.textContent = isPremium
            ? ui('Gia hạn Premium', 'Renew Premium')
            : ui('Nâng cấp Premium', 'Upgrade to Premium');
    }

    applySubscriptionFeatureCopy(currentSubscription.features);
}

// The compare-grid <li> copy (retention days, quota, analytics lock) is
// hardcoded in index.html as a static fallback, but the real numbers come
// from backend models/entitlements.py via /api/user's 'features' field --
// this keeps the two from drifting apart again the way "365 days" vs
// "unlimited" vs a 93-day backend clamp did.
function applySubscriptionFeatureCopy(features) {
    if (!Array.isArray(features)) return;
    const byKey = new Map(features.map((item) => [item.key, item]));
    document.querySelectorAll('[data-feature][data-tier]').forEach((el) => {
        const feature = byKey.get(el.dataset.feature);
        if (!feature) return;
        const value = el.dataset.tier === 'premium' ? feature.premium : feature.free;
        if (typeof value === 'string') el.textContent = value;
    });
}

function selectSubscriptionPlan(plan) {
    selectedSubscriptionPlan = ['monthly', 'yearly'].includes(plan)
        ? plan
        : 'monthly';
    document.querySelectorAll('[data-subscription-plan]').forEach((button) => {
        const active = button.dataset.subscriptionPlan === selectedSubscriptionPlan;
        button.classList.toggle('active', active);
        button.setAttribute('aria-checked', String(active));
    });
    updateSubscriptionPlanAction();
}

function selectSubscriptionPaymentMethod(method) {
    selectedSubscriptionPaymentMethod = method === 'CARD' ? 'CARD' : 'BANK_TRANSFER';
    document.querySelectorAll('[data-payment-method]').forEach((button) => {
        button.classList.toggle(
            'active',
            button.dataset.paymentMethod === selectedSubscriptionPaymentMethod
        );
    });
}

function subscriptionPlanDetails(plan = selectedSubscriptionPlan) {
    if (plan === 'yearly') {
        return {
            name: ui('Premium năm', 'Annual Premium'),
            description: ui('520.000đ / năm (~$19.99) · tiết kiệm 12%', '520,000 VND / year (~$19.99) · save 12%'),
            contact: 'Hàng năm (520.000đ/năm ~ $19.99, tiết kiệm 12%)'
        };
    }
    return {
        name: ui('Premium tháng', 'Monthly Premium'),
        description: ui('49.000đ / tháng (~$1.99)', '49,000 VND / month (~$1.99)'),
        contact: 'Hàng tháng (49.000đ/tháng ~ $1.99)'
    };
}

function updateSubscriptionPlanAction() {
    const button = document.getElementById('subscriptionContinueBtn');
    if (!button) return;
    const isPremium = !!(
        currentSubscription?.is_premium
        || currentSubscription?.tier === 'premium'
    );
    button.disabled = false;
    const plan = subscriptionPlanDetails();
    button.textContent = `${isPremium ? ui('Tiếp tục gia hạn', 'Continue renewal') : ui('Tiếp tục với', 'Continue with')} ${plan.name}`;
}

function showSubscriptionPlanStep() {
    const planStep = document.getElementById('subscriptionPlanStep');
    const paymentStep = document.getElementById('subscriptionPaymentStep');
    if (planStep) planStep.hidden = false;
    if (paymentStep) paymentStep.hidden = true;
    document.getElementById('subscriptionStepPlan')?.classList.add('active');
    document.getElementById('subscriptionStepPayment')?.classList.remove('active');
    updateSubscriptionPlanAction();
}

function showSubscriptionPaymentStep() {
    const plan = subscriptionPlanDetails();
    const name = document.getElementById('subscriptionSelectedPlanName');
    const description = document.getElementById('subscriptionSelectedPlanDescription');
    if (name) name.textContent = plan.name;
    if (description) description.textContent = plan.description;
    const planStep = document.getElementById('subscriptionPlanStep');
    const paymentStep = document.getElementById('subscriptionPaymentStep');
    if (planStep) planStep.hidden = true;
    if (paymentStep) paymentStep.hidden = false;
    document.getElementById('subscriptionStepPlan')?.classList.remove('active');
    document.getElementById('subscriptionStepPayment')?.classList.add('active');

    const isPremium = !!(
        currentSubscription?.is_premium
        || currentSubscription?.tier === 'premium'
    );
    const submit = document.getElementById('subscriptionSubmitBtn');
    if (submit) {
        submit.textContent = isPremium
            ? ui('Thanh toán gia hạn qua SEPay', 'Renew with SEPay')
            : ui('Thanh toán qua SEPay', 'Pay with SEPay');
    }
}

function openSubscriptionModal() {
    const modal = document.getElementById('subscriptionModal');
    if (!modal) return;
    const isPremium = !!(
        currentSubscription?.is_premium
        || currentSubscription?.tier === 'premium'
    );
    const title = document.getElementById('subscriptionModalTitle');
    const subtitle = document.getElementById('subscriptionModalSubtitle');
    const notice = document.getElementById('subscriptionCurrentNotice');
    const remaining = document.getElementById('subscriptionCurrentRemaining');
    if (title) {
        title.textContent = isPremium
            ? ui('Gia hạn Premium', 'Renew Premium')
            : ui('Nâng cấp Premium', 'Upgrade to Premium');
    }
    if (subtitle) {
        subtitle.textContent = isPremium
            ? ui(
                'So sánh các chu kỳ và chọn gói bạn muốn gia hạn.',
                'Compare billing cycles and choose the plan you want to renew.'
            )
            : ui(
                'Gói hiện tại của bạn là Freemium. So sánh với hai gói Premium để chọn lựa phù hợp.',
                'Your current plan is Freemium. Compare it with two Premium options.'
            );
    }
    if (notice) notice.hidden = !isPremium;
    if (remaining && isPremium) {
        remaining.textContent = ui(
            `Còn ${subscriptionRemainingLabel(currentSubscription)}`,
            `${subscriptionRemainingLabel(currentSubscription)} left`
        );
    }
    const freeBadge = document.getElementById('freePlanCurrentBadge');
    const freeLabel = document.getElementById('freePlanCurrentLabel');
    const freeCard = document.getElementById('freePlanCard');
    if (freeBadge) freeBadge.hidden = isPremium;
    if (freeLabel) freeLabel.hidden = isPremium;
    if (freeCard) {
        freeCard.classList.toggle('current', !isPremium);
        freeCard.setAttribute(
            'aria-label',
            isPremium ? ui('So sánh với Freemium', 'Compare with Freemium') : ui('Gói hiện tại Freemium', 'Current Freemium plan')
        );
    }
    selectSubscriptionPlan(
        isPremium && currentSubscription?.billing_interval === 'yearly'
            ? 'yearly'
            : 'monthly'
    );
    showSubscriptionPlanStep();
    modal.classList.add('show');
    document.body.classList.add('modal-open');
}

function closeSubscriptionModal() {
    document.getElementById('subscriptionModal')?.classList.remove('show');
    document.body.classList.remove('modal-open');
}

async function submitSubscriptionIntent() {
    const button = document.getElementById('subscriptionSubmitBtn');
    const isPremium = !!(
        currentSubscription?.is_premium
        || currentSubscription?.tier === 'premium'
    );
    const action = isPremium ? 'renew' : 'purchase';
    if (button) {
        button.disabled = true;
        button.textContent = ui('Đang tạo đơn SEPay...', 'Creating SEPay checkout...');
    }

    try {
        const response = await apiFetch(`${API_BASE}/payments/sepay/checkout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action,
                plan_code: selectedSubscriptionPlan === 'yearly'
                    ? 'premium_yearly'
                    : 'premium_monthly',
                payment_method: selectedSubscriptionPaymentMethod,
            })
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            if (data.subscription) renderSubscriptionUI(data.subscription);
            if (data.allowed_action === 'renew') {
                throw new Error(ui(
                    'Tài khoản đã có Premium và chỉ có thể gia hạn.',
                    'This account already has Premium and can only renew.'
                ));
            }
            if (data.allowed_action === 'purchase') {
                throw new Error(ui(
                    'Premium đã hết hiệu lực. Hãy mua một gói mới.',
                    'Premium has expired. Please purchase a new plan.'
                ));
            }
            throw new Error(data.message || data.error || ui('Không thể kiểm tra gói', 'Unable to check plan'));
        }

        if (!data.checkout_url) {
            throw new Error(ui('SEPay không trả về trang thanh toán.', 'SEPay checkout URL was not returned.'));
        }
        window.location.assign(data.checkout_url);
    } catch (error) {
        showNotification(error.message || ui('Không thể xử lý yêu cầu Premium', 'Unable to process Premium request'), 'error');
        renderSubscriptionUI(currentSubscription);
        openSubscriptionModal();
    } finally {
        if (button) button.disabled = false;
        if (document.getElementById('subscriptionPaymentStep')?.hidden === false) {
            const isPremiumNow = !!(
                currentSubscription?.is_premium
                || currentSubscription?.tier === 'premium'
            );
            if (button) {
                button.textContent = isPremiumNow
                    ? ui('Thanh toán gia hạn qua SEPay', 'Renew with SEPay')
                    : ui('Thanh toán qua SEPay', 'Pay with SEPay');
            }
        }
    }
}

function showSepayReturnNotice() {
    const params = new URLSearchParams(window.location.search);
    const outcome = params.get('payment');
    if (!['success', 'error', 'cancel'].includes(outcome)) return;
    const message = outcome === 'success'
        ? ui(
            'SEPay đã nhận giao dịch. Trạng thái Premium sẽ cập nhật ngay khi IPN được xác nhận.',
            'SEPay received the payment. Premium will update as soon as the IPN is confirmed.'
        )
        : outcome === 'cancel'
            ? ui('Bạn đã hủy thanh toán SEPay.', 'SEPay payment was cancelled.')
            : ui('Thanh toán SEPay chưa hoàn tất.', 'SEPay payment was not completed.');
    showNotification(message, outcome === 'success' ? 'success' : 'error');
    params.delete('payment');
    params.delete('invoice');
    const query = params.toString();
    window.history.replaceState({}, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
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
        renderSubscriptionUI(user.subscription);
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
        // Business-workspace nav items (Thành viên/Công việc/Báo cáo/Chia sẻ)
        // are gated on mode too now (canShowBusinessFeatures) -- re-render so
        // switching mode hides/reveals them without needing a page reload.
        renderOrgWorkspaceSwitcher();
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
