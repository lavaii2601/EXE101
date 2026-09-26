// ---------------------------------------------------------------------
// Multi-tenant Business workspace switcher (Worker Business Phase 1).
// See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md sections 4, 10, 13.
// Named "orgWorkspace*" to avoid colliding with the pre-existing
// workspaceSync*/#workspaceApp vocabulary above, which is unrelated: the
// personal single-tenant app shell's own background sync/polling cursor.
// ---------------------------------------------------------------------

function orgWorkspaceStorageKey() {
    const ownerId = (lastAuthStatus && lastAuthStatus.user_id) || 'anon';
    return `flowmate-org-workspace:${ownerId}`;
}

function orgRoleLabelVi(role) {
    if (role === 'owner') return 'Chủ sở hữu';
    if (role === 'admin') return 'Quản trị';
    return 'Thành viên';
}

function orgRoleLabelEn(role) {
    if (role === 'owner') return 'Owner';
    if (role === 'admin') return 'Admin';
    return 'Worker';
}

function orgAccessStateLabel(state) {
    if (state === 'active') return ui('Đang hoạt động', 'Active');
    if (state === 'grace') return ui('Sắp hết hạn (gia hạn ngay)', 'Expiring soon (renew now)');
    if (state === 'read_only') return ui('Chỉ đọc (đã hết hạn)', 'Read-only (expired)');
    return ui('Chưa có gói', 'No subscription yet');
}

function currentOrgWorkspace() {
    return orgWorkspaces.find((w) => w.id === currentOrgWorkspaceId) || null;
}

async function loadOrgWorkspaces() {
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces`);
        const data = await resp.json();
        if (!resp.ok || !data.success) return;
        orgWorkspaces = data.workspaces || [];
        const saved = localStorage.getItem(orgWorkspaceStorageKey());
        const savedStillValid = saved && orgWorkspaces.some((w) => w.id === saved);
        if (savedStillValid) {
            currentOrgWorkspaceId = saved;
        } else {
            const personal = orgWorkspaces.find((w) => w.type === 'personal');
            currentOrgWorkspaceId = personal ? personal.id : (orgWorkspaces[0] ? orgWorkspaces[0].id : null);
        }
        renderOrgWorkspaceSwitcher();
    } catch (err) {
        console.warn('loadOrgWorkspaces failed', err);
    }
}

// Business-workspace collaboration (Thành viên/Công việc/Báo cáo/Chia sẻ) is
// scoped to the "worker" and "business" user modes -- switching to another
// mode (student, freelancer, mentor, teacher, creator) hides these even if
// the account is still an active Business workspace member, since the
// whole Worker Business Subscription feature set is framed around the
// worker persona (design doc's approved Worker Free/Premium/Business
// tiering), not a general-purpose feature for every mode.
function canShowBusinessFeatures() {
    return currentUserMode === 'worker' || currentUserMode === 'business';
}

function renderOrgWorkspaceSwitcher() {
    const nameEl = document.getElementById('orgWorkspaceName');
    const typeEl = document.getElementById('orgWorkspaceType');
    const iconEl = document.getElementById('orgWorkspaceIcon');
    const listEl = document.getElementById('orgWorkspaceList');
    const membersNavBtn = document.getElementById('orgWorkspaceMembersNavBtn');
    const workHubNavBtn = document.getElementById('orgWorkHubNavBtn');
    const statusReportsNavBtn = document.getElementById('orgStatusReportsNavBtn');
    const sharingCenterNavBtn = document.getElementById('sharingCenterNavBtn');
    const workspaceKnowledgeNavBtn = document.getElementById('orgWorkspaceKnowledgeNavBtn');
    const active = currentOrgWorkspace();

    if (nameEl) nameEl.textContent = active ? active.name : ui('Cá nhân', 'Personal');
    if (typeEl) {
        typeEl.textContent = active && active.type === 'business'
            ? ui('Không gian doanh nghiệp', 'Business workspace')
            : ui('Không gian cá nhân', 'Personal workspace');
    }
    if (iconEl) iconEl.textContent = active && active.type === 'business' ? '🏢' : '👤';
    const showBusinessNav = active && active.type === 'business' && canShowBusinessFeatures();
    if (membersNavBtn) {
        membersNavBtn.style.display = showBusinessNav ? '' : 'none';
    }
    if (workHubNavBtn) {
        workHubNavBtn.style.display = showBusinessNav ? '' : 'none';
    }
    if (statusReportsNavBtn) {
        statusReportsNavBtn.style.display = showBusinessNav ? '' : 'none';
    }
    if (workspaceKnowledgeNavBtn) {
        workspaceKnowledgeNavBtn.style.display = showBusinessNav ? '' : 'none';
    }
    if (sharingCenterNavBtn) {
        // Not workspace-scoped (GET /api/user/sharing spans every workspace the
        // caller belongs to), so this stays visible as long as they're in ANY
        // Business workspace, not just whichever one is currently active.
        sharingCenterNavBtn.style.display = orgWorkspaces.some((w) => w.type === 'business') && canShowBusinessFeatures() ? '' : 'none';
    }

    if (listEl) {
        listEl.innerHTML = orgWorkspaces.map((w) => `
            <button type="button" class="org-workspace-item${w.id === currentOrgWorkspaceId ? ' active' : ''}" data-workspace-id="${escapeHtml(w.id)}">
                <span>${w.type === 'business' ? '🏢' : '👤'}</span>
                <span>
                    ${escapeHtml(w.name)}
                    <small>${w.member_role ? escapeHtml(ui(orgRoleLabelVi(w.member_role), orgRoleLabelEn(w.member_role))) : ''}</small>
                </span>
            </button>
        `).join('');
        listEl.querySelectorAll('[data-workspace-id]').forEach((btn) => {
            btn.addEventListener('click', () => switchOrgWorkspace(btn.getAttribute('data-workspace-id')));
        });
    }
}

function switchOrgWorkspace(workspaceId) {
    closeOrgWorkspacePopup();
    if (!workspaceId || workspaceId === currentOrgWorkspaceId) return;
    currentOrgWorkspaceId = workspaceId;
    localStorage.setItem(orgWorkspaceStorageKey(), workspaceId);
    renderOrgWorkspaceSwitcher();
    showNotification(ui('Đã chuyển không gian làm việc', 'Switched workspace'), 'success');
    if (currentPage === 'workspace-members') {
        loadOrgWorkspaceMembers();
    }
    // chat_sessions rows are workspace-scoped server-side (see
    // web/backend/models/history.py); activeChatSessionId is a single
    // global here, not per-workspace, so without this the chat page would
    // keep showing (and could keep appending to) the previous workspace's
    // conversation after the switch.
    activeChatSessionId = createChatSessionId();
    activeChatSessionTitle = '';
    persistChatSessionId();
    persistChatSessionTitle();
    if (chatMessages) chatMessages.innerHTML = '';
    updateChatSessionTitle();
    if (currentPage === 'chat') {
        loadChatHistory();
        loadChatSessions();
    }
}

function toggleOrgWorkspacePopup() {
    const popup = document.getElementById('orgWorkspacePopup');
    const btn = document.getElementById('orgWorkspaceSwitcherBtn');
    if (!popup || !btn) return;
    const isOpen = popup.classList.toggle('show');
    btn.setAttribute('aria-expanded', String(isOpen));
}

function closeOrgWorkspacePopup() {
    document.getElementById('orgWorkspacePopup')?.classList.remove('show');
    document.getElementById('orgWorkspaceSwitcherBtn')?.setAttribute('aria-expanded', 'false');
}

function openCreateOrgWorkspaceModal() {
    closeOrgWorkspacePopup();
    const modal = document.getElementById('createOrgWorkspaceModal');
    const status = document.getElementById('createOrgWorkspaceStatus');
    const input = document.getElementById('createOrgWorkspaceName');
    if (status) status.textContent = '';
    if (input) input.value = '';
    modal?.classList.add('show');
    input?.focus();
}

function closeCreateOrgWorkspaceModal() {
    document.getElementById('createOrgWorkspaceModal')?.classList.remove('show');
}

async function submitCreateOrgWorkspace(event) {
    event.preventDefault();
    const input = document.getElementById('createOrgWorkspaceName');
    const status = document.getElementById('createOrgWorkspaceStatus');
    const name = (input?.value || '').trim();
    if (!name) return;
    if (status) status.textContent = ui('Đang tạo...', 'Creating...');
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            throw new Error(data.error || ui('Không tạo được không gian làm việc', 'Could not create workspace'));
        }
        await loadOrgWorkspaces();
        currentOrgWorkspaceId = data.workspace.id;
        localStorage.setItem(orgWorkspaceStorageKey(), data.workspace.id);
        renderOrgWorkspaceSwitcher();
        closeCreateOrgWorkspaceModal();
        showNotification(ui('Đã tạo không gian doanh nghiệp', 'Business workspace created'), 'success');
    } catch (err) {
        if (status) status.textContent = err.message;
    }
}

async function loadOrgWorkspaceMembers() {
    const emptyEl = document.getElementById('orgWorkspaceMembersEmpty');
    const contentEl = document.getElementById('orgWorkspaceMembersContent');
    const inviteCard = document.getElementById('orgWorkspaceInviteCard');
    const active = currentOrgWorkspace();
    if (!active || active.type !== 'business') {
        if (emptyEl) emptyEl.hidden = false;
        if (contentEl) contentEl.hidden = true;
        return;
    }
    if (emptyEl) emptyEl.hidden = true;
    if (contentEl) contentEl.hidden = false;

    const canManage = active.member_role === 'owner' || active.member_role === 'admin';
    if (inviteCard) inviteCard.hidden = !canManage;

    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/members`);
        const data = await resp.json();
        if (resp.ok && data.success) {
            orgWorkspaceMembers = data.members || [];
        }
    } catch (err) {
        console.warn('loadOrgWorkspaceMembers failed', err);
    }
    renderOrgWorkspaceMembers();

    loadOrgWorkspaceSubscription();

    if (canManage) {
        try {
            const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/invitations`);
            const data = await resp.json();
            if (resp.ok && data.success) {
                orgWorkspacePendingInvitations = (data.invitations || []).filter((i) => i.status === 'pending');
            }
        } catch (err) {
            console.warn('load invitations failed', err);
        }
        renderOrgWorkspacePendingInvitations();
        loadOrgWorkspaceSeatRequests();
    }
}

async function loadOrgWorkspaceSubscription() {
    const active = currentOrgWorkspace();
    if (!active) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/subscription`);
        const data = await resp.json();
        if (resp.ok && data.success) {
            orgWorkspaceSubscription = data;
        }
    } catch (err) {
        console.warn('loadOrgWorkspaceSubscription failed', err);
    }
    renderOrgWorkspaceSubscription();
}

function renderOrgWorkspaceSubscription() {
    const bodyEl = document.getElementById('orgWorkspaceSubscriptionBody');
    if (!bodyEl || !orgWorkspaceSubscription) return;
    const { subscription, access_state: accessState, seat_capacity: seatCapacity, active_seats: activeSeats } = orgWorkspaceSubscription;
    const stateClass = `org-subscription-state-${accessState}`;
    bodyEl.innerHTML = `
        <div class="org-subscription-heading">
            <strong>${escapeHtml(subscription?.plan_name || ui('Chưa có gói doanh nghiệp', 'No Business plan yet'))}</strong>
            <span class="org-subscription-badge ${stateClass}">${escapeHtml(orgAccessStateLabel(accessState))}</span>
        </div>
        <div class="org-subscription-seats">
            ${ui('Chỗ đang dùng', 'Seats used')}: <strong>${activeSeats}</strong> / ${seatCapacity}
        </div>
        ${subscription?.current_period_end ? `
            <div class="org-subscription-period">
                ${ui('Hết hạn', 'Expires')}: ${new Date(subscription.current_period_end).toLocaleDateString(currentLanguage === 'en' ? 'en-US' : 'vi-VN')}
            </div>
        ` : ''}
        ${accessState === 'grace' ? `
            <p class="org-subscription-notice org-subscription-notice-warn">${ui('Gói đã hết hạn, đang trong 7 ngày gia hạn. Sau đó không gian sẽ chuyển sang chỉ đọc.', 'Your plan has expired and is in the 7-day grace period. After that, this workspace becomes read-only.')}</p>
        ` : ''}
        ${accessState === 'read_only' ? `
            <p class="org-subscription-notice org-subscription-notice-danger">${ui('Không gian đang ở chế độ chỉ đọc do gói đã hết hạn. Gia hạn để tiếp tục chỉnh sửa.', 'This workspace is read-only because its plan expired. Renew to resume editing.')}</p>
        ` : ''}
    `;
}

async function loadOrgWorkspaceSeatRequests() {
    const active = currentOrgWorkspace();
    if (!active) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/seat-requests`);
        const data = await resp.json();
        if (resp.ok && data.success) {
            orgWorkspaceSeatRequests = (data.seat_requests || []).filter((r) => r.status === 'pending_owner');
        }
    } catch (err) {
        console.warn('loadOrgWorkspaceSeatRequests failed', err);
    }
    renderOrgWorkspaceSeatRequests();
}

function renderOrgWorkspaceSeatRequests() {
    const cardEl = document.getElementById('orgWorkspaceSeatRequestsCard');
    const listEl = document.getElementById('orgWorkspaceSeatRequestsList');
    if (!cardEl || !listEl) return;
    if (!orgWorkspaceSeatRequests.length) {
        cardEl.hidden = true;
        listEl.innerHTML = '';
        return;
    }
    cardEl.hidden = false;
    listEl.innerHTML = orgWorkspaceSeatRequests.map((r) => `
        <div class="org-seat-request-row">
            <div class="org-seat-request-info">
                <strong>${ui('Cần thêm', 'Needs')} ${r.requested_seats} ${ui('chỗ', 'seat(s)')}</strong>
                <small>${escapeHtml(r.requested_by_user_id || '')}</small>
            </div>
            <div class="org-seat-request-actions">
                <button type="button" class="btn-primary org-approve-seat-btn" data-request-id="${escapeHtml(r.id)}">${ui('Duyệt', 'Approve')}</button>
                <button type="button" class="btn-secondary org-reject-seat-btn" data-request-id="${escapeHtml(r.id)}">${ui('Từ chối', 'Reject')}</button>
            </div>
        </div>
    `).join('');
    listEl.querySelectorAll('.org-approve-seat-btn').forEach((btn) => {
        btn.addEventListener('click', () => resolveOrgSeatRequest(btn.getAttribute('data-request-id'), 'approve'));
    });
    listEl.querySelectorAll('.org-reject-seat-btn').forEach((btn) => {
        btn.addEventListener('click', () => resolveOrgSeatRequest(btn.getAttribute('data-request-id'), 'reject'));
    });
}

async function resolveOrgSeatRequest(requestId, action) {
    const active = currentOrgWorkspace();
    if (!active) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/seat-requests/${encodeURIComponent(requestId)}/${action}`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'error');
        showNotification(
            action === 'approve' ? ui('Đã duyệt yêu cầu thêm chỗ', 'Seat request approved') : ui('Đã từ chối yêu cầu', 'Seat request rejected'),
            'success'
        );
        loadOrgWorkspaceSeatRequests();
        loadOrgWorkspaceSubscription();
    } catch (err) {
        showNotification(ui(`Không xử lý được yêu cầu: ${err.message}`, `Could not process request: ${err.message}`), 'error');
    }
}

function renderOrgWorkspaceMembers() {
    const listEl = document.getElementById('orgWorkspaceMembersList');
    if (!listEl) return;
    const active = currentOrgWorkspace();
    const canManage = active && (active.member_role === 'owner' || active.member_role === 'admin');
    listEl.innerHTML = orgWorkspaceMembers.map((m) => `
        <div class="org-workspace-member-row">
            <div class="org-workspace-member-info">
                <strong>${escapeHtml(m.name || m.email || m.user_id)}</strong>
                <small>${escapeHtml(m.email || '')}</small>
            </div>
            <span class="org-role-badge">${escapeHtml(ui(orgRoleLabelVi(m.role), orgRoleLabelEn(m.role)))}</span>
            ${canManage && m.role !== 'owner' ? `
                <select class="org-role-select" data-user-id="${escapeHtml(m.user_id)}">
                    <option value="worker" ${m.role === 'worker' ? 'selected' : ''}>Worker</option>
                    <option value="admin" ${m.role === 'admin' ? 'selected' : ''}>Admin</option>
                </select>
                <button type="button" class="btn-secondary org-disable-member-btn" data-user-id="${escapeHtml(m.user_id)}">${ui('Xóa', 'Remove')}</button>
            ` : ''}
        </div>
    `).join('') || `<p>${ui('Chưa có thành viên nào.', 'No members yet.')}</p>`;

    listEl.querySelectorAll('.org-role-select').forEach((select) => {
        select.addEventListener('change', () => changeOrgMemberRole(select.getAttribute('data-user-id'), select.value));
    });
    listEl.querySelectorAll('.org-disable-member-btn').forEach((btn) => {
        btn.addEventListener('click', () => disableOrgMember(btn.getAttribute('data-user-id')));
    });
}

function renderOrgWorkspacePendingInvitations() {
    const listEl = document.getElementById('orgWorkspacePendingInvitations');
    if (!listEl) return;
    if (!orgWorkspacePendingInvitations.length) {
        listEl.innerHTML = '';
        return;
    }
    listEl.innerHTML = `<p style="margin-top:10px;font-size:11px;font-weight:800;letter-spacing:.05em;color:var(--text-secondary);">${ui('LỜI MỜI ĐANG CHỜ', 'PENDING INVITATIONS')}</p>` +
        orgWorkspacePendingInvitations.map((inv) => `
            <div class="org-workspace-invitation-row">
                <div class="org-workspace-invitation-info">
                    <strong>${escapeHtml(inv.email_normalized)}</strong>
                    <span class="org-role-badge">${escapeHtml(ui(orgRoleLabelVi(inv.role), orgRoleLabelEn(inv.role)))}</span>
                </div>
                <button type="button" class="btn-secondary org-revoke-invitation-btn" data-invitation-id="${escapeHtml(inv.id)}">${ui('Thu hồi', 'Revoke')}</button>
            </div>
        `).join('');
    listEl.querySelectorAll('.org-revoke-invitation-btn').forEach((btn) => {
        btn.addEventListener('click', () => revokeOrgInvitation(btn.getAttribute('data-invitation-id')));
    });
}

async function changeOrgMemberRole(userId, role) {
    const active = currentOrgWorkspace();
    if (!active) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/members/${encodeURIComponent(userId)}/role`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'error');
        showNotification(ui('Đã đổi vai trò', 'Role updated'), 'success');
        loadOrgWorkspaceMembers();
    } catch (err) {
        showNotification(ui(`Không đổi được vai trò: ${err.message}`, `Could not change role: ${err.message}`), 'error');
    }
}

async function disableOrgMember(userId) {
    const active = currentOrgWorkspace();
    if (!active) return;
    if (!confirm(ui('Xóa thành viên này khỏi không gian làm việc?', 'Remove this member from the workspace?'))) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/members/${encodeURIComponent(userId)}/disable`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'error');
        showNotification(ui('Đã xóa thành viên', 'Member removed'), 'success');
        loadOrgWorkspaceMembers();
    } catch (err) {
        showNotification(ui(`Không xóa được thành viên: ${err.message}`, `Could not remove member: ${err.message}`), 'error');
    }
}

async function submitOrgWorkspaceInvite(event) {
    event.preventDefault();
    const active = currentOrgWorkspace();
    if (!active) return;
    const emailInput = document.getElementById('orgInviteEmail');
    const roleSelect = document.getElementById('orgInviteRole');
    const status = document.getElementById('orgInviteStatus');
    const email = (emailInput?.value || '').trim();
    const role = roleSelect?.value || 'worker';
    if (!email) return;
    if (status) status.textContent = ui('Đang gửi lời mời...', 'Sending invitation...');
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/invitations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, role }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            throw new Error(data.error || ui('Không gửi được lời mời', 'Could not send invitation'));
        }
        // No email delivery yet (see design doc section 1.1) -- the raw
        // token only ever appears in this response, so the admin/owner has
        // to relay this link out-of-band themselves for now.
        const inviteLink = `${window.location.origin}${window.location.pathname}?invite=${encodeURIComponent(data.invitation.token)}`;
        if (status) {
            status.innerHTML = ui(
                `Đã tạo lời mời. Gửi link này cho ${escapeHtml(email)}:<br><code>${escapeHtml(inviteLink)}</code>`,
                `Invitation created. Send this link to ${escapeHtml(email)}:<br><code>${escapeHtml(inviteLink)}</code>`
            );
        }
        if (emailInput) emailInput.value = '';
        loadOrgWorkspaceMembers();
    } catch (err) {
        if (status) status.textContent = err.message;
    }
}

async function revokeOrgInvitation(invitationId) {
    const active = currentOrgWorkspace();
    if (!active) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${active.id}/invitations/${encodeURIComponent(invitationId)}`, {
            method: 'DELETE',
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'error');
        showNotification(ui('Đã thu hồi lời mời', 'Invitation revoked'), 'success');
        loadOrgWorkspaceMembers();
    } catch (err) {
        showNotification(ui(`Lỗi: ${err.message}`, `Error: ${err.message}`), 'error');
    }
}

async function checkPendingOrgInvitationFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('invite');
    if (!token) return;
    // Strip the token from the URL immediately so a refresh/share doesn't
    // re-trigger acceptance or leak the token into browser history.
    params.delete('invite');
    const cleanUrl = window.location.pathname + (params.toString() ? `?${params}` : '') + window.location.hash;
    window.history.replaceState({}, '', cleanUrl);

    try {
        const resp = await apiFetch(`${API_BASE}/workspace-invitations/${encodeURIComponent(token)}/accept`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            if (data.error === 'capacity_blocked') {
                throw new Error(ui(
                    'Không gian doanh nghiệp đã đầy chỗ. Quản trị viên đã được thông báo để mua thêm chỗ, bạn sẽ nhận lại lời mời khi có chỗ trống.',
                    'This Business workspace is at full seat capacity. The owner/admin has been notified to add seats -- try this invite again once they do.'
                ));
            }
            throw new Error(data.error || ui('Không chấp nhận được lời mời', 'Could not accept invitation'));
        }
        showNotification(ui('Đã tham gia không gian doanh nghiệp!', 'Joined the business workspace!'), 'success');
        await loadOrgWorkspaces();
        currentOrgWorkspaceId = data.invitation.workspace_id;
        localStorage.setItem(orgWorkspaceStorageKey(), data.invitation.workspace_id);
        renderOrgWorkspaceSwitcher();
    } catch (err) {
        showNotification(ui(`Lỗi lời mời: ${err.message}`, `Invitation error: ${err.message}`), 'error');
    }
}

function setupOrgWorkspaceUI() {
    const switcherBtn = document.getElementById('orgWorkspaceSwitcherBtn');
    const createBtn = document.getElementById('createOrgWorkspaceBtn');
    const createForm = document.getElementById('createOrgWorkspaceForm');
    const inviteForm = document.getElementById('orgWorkspaceInviteForm');

    switcherBtn?.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleOrgWorkspacePopup();
    });
    document.addEventListener('click', () => closeOrgWorkspacePopup());
    document.getElementById('orgWorkspacePopup')?.addEventListener('click', (event) => event.stopPropagation());

    createBtn?.addEventListener('click', openCreateOrgWorkspaceModal);
    createForm?.addEventListener('submit', submitCreateOrgWorkspace);
    document.getElementById('createOrgWorkspaceModal')?.querySelectorAll('[data-modal="createOrgWorkspaceModal"]').forEach((el) => {
        el.addEventListener('click', closeCreateOrgWorkspaceModal);
    });

    inviteForm?.addEventListener('submit', submitOrgWorkspaceInvite);
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
        try { await loadEmails(currentEmailPage || 1, { cacheOnly: true, silent: true }); } catch (e) { /* ignore refresh errors */ }
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

function getWorkspaceSyncOwner() {
    return String(lastAuthStatus?.user_id || lastAuthStatus?.gmail_email || '').trim().toLowerCase();
}

function getWorkspaceSyncStorageKey(ownerId) {
    return `flowmate-sync-revision:${ownerId}`;
}

function parseWorkspaceSyncRevision(value) {
    const revision = Number.parseInt(value, 10);
    return Number.isSafeInteger(revision) && revision >= 0 ? revision : null;
}

function clampWorkspaceSyncPollDelay(value) {
    const delay = Number.parseInt(value, 10);
    if (!Number.isFinite(delay)) return 12000;
    return Math.min(Math.max(delay, WORKSPACE_SYNC_POLL_MIN_MS), WORKSPACE_SYNC_POLL_MAX_MS);
}

function configureWorkspaceSyncOwner() {
    const nextOwnerId = getWorkspaceSyncOwner();
    if (!nextOwnerId) return false;
    if (workspaceSyncOwnerId === nextOwnerId) return true;

    workspaceSyncGeneration += 1;
    workspaceSyncAbortController?.abort();
    workspaceSyncAbortController = null;
    workspaceSyncInFlight = false;
    workspaceSyncOwnerId = nextOwnerId;

    const storedRevision = parseWorkspaceSyncRevision(
        localStorage.getItem(getWorkspaceSyncStorageKey(nextOwnerId))
    );
    workspaceSyncRevision = storedRevision;
    workspaceSyncHasBaseline = storedRevision !== null;
    return true;
}

function pauseWorkspaceSyncWatcher() {
    if (workspaceSyncPollTimer) {
        window.clearTimeout(workspaceSyncPollTimer);
        workspaceSyncPollTimer = null;
    }
}

function stopWorkspaceSyncWatcher() {
    pauseWorkspaceSyncWatcher();
    workspaceSyncGeneration += 1;
    workspaceSyncAbortController?.abort();
    workspaceSyncAbortController = null;
    workspaceSyncInFlight = false;
    workspaceSyncRevision = null;
    workspaceSyncOwnerId = '';
    workspaceSyncHasBaseline = false;
    workspaceSyncPollAfterMs = 12000;
}

function workspaceSyncChangedDomains(data, sinceRevision) {
    if (Array.isArray(data?.changed)) {
        return Array.from(new Set(data.changed.map((item) => String(item || '').trim()).filter(Boolean)));
    }

    // Tolerate older/pre-release field names without weakening the canonical
    // server contract (`changed`). The domains fallback is also useful during
    // rolling deploys where a newer frontend can briefly hit an older worker.
    const aliases = data?.changed_targets || data?.targets || data?.refresh_targets;
    if (Array.isArray(aliases)) {
        return Array.from(new Set(aliases.map((item) => String(item || '').trim()).filter(Boolean)));
    }
    if (data?.domains && typeof data.domains === 'object') {
        return Object.entries(data.domains)
            .filter(([, revision]) => {
                const parsed = parseWorkspaceSyncRevision(revision);
                return parsed !== null && parsed > sinceRevision;
            })
            .map(([domain]) => domain);
    }
    return [];
}

async function refreshVisibleWorkspaceChanges(changedDomains = []) {
    const changed = new Set(changedDomains);
    if (!changed.size || !isAuthenticated) return;
    const affects = (...domains) => domains.some((domain) => changed.has(domain));
    const refreshes = [];

    // Profile is visible in the workspace shell on every page. Settings and
    // provider changes also affect global connection/status controls.
    if (affects('profile', 'settings')) {
        refreshes.push(loadUserProfile());
        refreshes.push(refreshAuthButtons());
    }
    if (affects('providers')) {
        refreshes.push(checkRuntimeConfig());
        refreshes.push(loadAgentProfile());
    }

    if (currentPage === 'chat' && affects('chat', 'history')) {
        refreshes.push(loadChatSessions());
        refreshes.push(loadChatHistory());
    } else if (
        currentPage === 'overview'
        && affects('overview', 'email', 'schedule', 'calendar')
    ) {
        refreshes.push(loadOverviewPage({ background: true }));
    } else if (currentPage === 'emails' && affects('email')) {
        refreshes.push(loadEmails(currentEmailPage || 1, { cacheOnly: true, silent: true }));
        refreshes.push(loadMeetingSuggestions());
    } else if (currentPage === 'schedule') {
        if (affects('schedule', 'calendar')) {
            // The remote mutation already updated FlowMate's shared local
            // schedule state. Read that state directly; a full Google sync
            // here would be expensive and can create a cross-device loop.
            invalidateScheduleCaches();
            refreshes.push(loadSchedules());
            refreshes.push(loadWeekSchedule());
            refreshes.push(refreshQuickScheduleSummary());
        }
        if (affects('email')) {
            refreshes.push(loadMeetingSuggestions());
        }
    } else if (currentPage === 'history' && affects('history')) {
        refreshes.push(loadActivityHistory());
    } else if (
        currentPage === 'settings'
        && affects('profile', 'settings', 'email', 'providers')
    ) {
        refreshes.push(loadSettingsPage());
    } else if (currentPage === 'work-hub' && affects('work_hub')) {
        refreshes.push(loadWorkHubPage());
    } else if (currentPage === 'status-reports' && affects('status_reports')) {
        refreshes.push(loadStatusReportsPage());
    } else if (currentPage === 'workspace-knowledge' && affects('workspace_knowledge')) {
        refreshes.push(loadWorkspaceKnowledgePage());
    } else if (currentPage === 'sharing-center' && affects('sharing')) {
        refreshes.push(loadSharingCenter());
    } else if (currentPage === 'workspace-members' && affects('workspace_members')) {
        refreshes.push(loadOrgWorkspaceMembers());
    }

    await Promise.allSettled(refreshes);
}

async function checkWorkspaceSyncState() {
    if (
        workspaceSyncInFlight
        || !isAuthenticated
        || document.visibilityState !== 'visible'
        || !configureWorkspaceSyncOwner()
    ) {
        return;
    }

    workspaceSyncInFlight = true;
    const generation = workspaceSyncGeneration;
    const ownerId = workspaceSyncOwnerId;
    const sinceRevision = workspaceSyncRevision ?? 0;
    const hadBaseline = workspaceSyncHasBaseline;
    const controller = new AbortController();
    workspaceSyncAbortController = controller;
    const abortTimer = window.setTimeout(() => controller.abort(), 8000);

    try {
        const response = await fetch(
            `${API_BASE}/sync/state?since=${encodeURIComponent(sinceRevision)}`,
            {
                credentials: 'include',
                headers: { Accept: 'application/json' },
                signal: controller.signal
            }
        );

        if (response.status === 401) {
            isAuthenticated = false;
            lastAuthStatus = null;
            stopWorkspaceSyncWatcher();
            showAuthGate(ui(
                'PhiÃªn Ä‘Äƒng nháº­p Ä‘Ã£ háº¿t háº¡n. Vui lÃ²ng Ä‘Äƒng nháº­p láº¡i.',
                'Your session has expired. Please sign in again.'
            ));
            return;
        }

        const data = await response.json().catch(() => ({}));
        if (
            !response.ok
            || !data.success
            || generation !== workspaceSyncGeneration
            || ownerId !== workspaceSyncOwnerId
        ) {
            return;
        }

        const nextRevision = parseWorkspaceSyncRevision(data.revision);
        if (nextRevision === null) return;
        const changedDomains = workspaceSyncChangedDomains(data, sinceRevision);

        workspaceSyncRevision = nextRevision;
        workspaceSyncHasBaseline = true;
        workspaceSyncPollAfterMs = clampWorkspaceSyncPollDelay(data.poll_after_ms);
        localStorage.setItem(getWorkspaceSyncStorageKey(ownerId), String(nextRevision));

        // A first-time browser has no meaningful cursor. Establish its
        // baseline without replaying every historical domain change.
        if (hadBaseline && changedDomains.length) {
            await refreshVisibleWorkspaceChanges(changedDomains);
        }
    } catch (error) {
        if (error?.name !== 'AbortError') {
            console.warn('Workspace sync check failed:', error);
        }
    } finally {
        window.clearTimeout(abortTimer);
        if (workspaceSyncAbortController === controller) {
            workspaceSyncAbortController = null;
        }
        if (generation === workspaceSyncGeneration) {
            workspaceSyncInFlight = false;
        }
    }
}

function scheduleWorkspaceSyncPoll() {
    pauseWorkspaceSyncWatcher();
    if (!isAuthenticated || document.visibilityState !== 'visible') return;
    workspaceSyncPollTimer = window.setTimeout(async () => {
        workspaceSyncPollTimer = null;
        await checkWorkspaceSyncState();
        scheduleWorkspaceSyncPoll();
    }, workspaceSyncPollAfterMs);
}

function startWorkspaceSyncWatcher({ immediate = true } = {}) {
    if (!isAuthenticated || !configureWorkspaceSyncOwner()) return;
    if (!workspaceSyncListenersBound) {
        workspaceSyncListenersBound = true;
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                startWorkspaceSyncWatcher({ immediate: true });
            } else {
                pauseWorkspaceSyncWatcher();
            }
        });
        window.addEventListener('focus', () => {
            if (document.visibilityState === 'visible') {
                startWorkspaceSyncWatcher({ immediate: true });
            }
        });
    }

    pauseWorkspaceSyncWatcher();
    if (document.visibilityState !== 'visible') return;
    const immediateCheck = immediate ? checkWorkspaceSyncState() : Promise.resolve();
    return immediateCheck.finally(scheduleWorkspaceSyncPoll);
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
    syncSidebarIndicator();
    
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
    } else if (page === 'workspace-members') {
        loadOrgWorkspaceMembers().catch(err => console.error('Workspace members load error:', err));
    } else if (page === 'work-hub') {
        loadWorkHubPage().catch(err => console.error('Work Hub load error:', err));
    } else if (page === 'status-reports') {
        loadStatusReportsPage().catch(err => console.error('Status reports load error:', err));
    } else if (page === 'workspace-knowledge') {
        loadWorkspaceKnowledgePage().catch(err => console.error('Workspace knowledge load error:', err));
    } else if (page === 'sharing-center') {
        loadSharingCenter().catch(err => console.error('Sharing center load error:', err));
    }
}

function syncSidebarIndicator({ instant = false } = {}) {
    const navigation = document.querySelector('.sidebar-nav');
    const activeButton = navigation?.querySelector('.nav-btn.active');
    if (!navigation || !activeButton) return;

    if (instant) navigation.classList.add('indicator-no-transition');
    navigation.style.setProperty('--nav-indicator-y', `${activeButton.offsetTop}px`);
    navigation.style.setProperty('--nav-indicator-height', `${activeButton.offsetHeight}px`);
    const mobileIndicatorSize = 58;
    const mobileIndicatorX = activeButton.offsetLeft + ((activeButton.offsetWidth - mobileIndicatorSize) / 2);
    navigation.style.setProperty('--mobile-indicator-x', `${Math.max(0, mobileIndicatorX)}px`);
    navigation.dataset.indicatorReady = 'true';

    if (instant) {
        requestAnimationFrame(() => navigation.classList.remove('indicator-no-transition'));
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

    const storageKey = 'flowmate-sidebar-collapsed';
    const isMobile = () => window.innerWidth <= 860;
    const updateToggle = () => {
        const mobileOpen = sidebar.classList.contains('open');
        const collapsed = container.classList.contains('sidebar-collapsed');
        const expanded = isMobile() ? mobileOpen : !collapsed;
        menuToggle.setAttribute('aria-expanded', String(expanded));
        menuToggle.setAttribute('aria-label', isMobile()
            ? ui(mobileOpen ? 'Đóng menu' : 'Mở menu', mobileOpen ? 'Close menu' : 'Open menu')
            : ui(collapsed ? 'Mở rộng thanh điều hướng' : 'Thu gọn thanh điều hướng', collapsed ? 'Expand navigation' : 'Collapse navigation'));
        menuToggle.classList.toggle('is-collapsed', collapsed);
    };

    const closeMobileSidebar = () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
        updateToggle();
    };

    const applyResponsiveState = ({ instant = false } = {}) => {
        if (isMobile()) {
            container.classList.remove('sidebar-collapsed');
            closeMobileSidebar();
        } else {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
            container.classList.toggle('sidebar-collapsed', localStorage.getItem(storageKey) === 'true');
            updateToggle();
        }
        requestAnimationFrame(() => syncSidebarIndicator({ instant }));
    };

    menuToggle.addEventListener('click', (event) => {
        event.stopPropagation();
        if (isMobile()) {
            const shouldOpen = !sidebar.classList.contains('open');
            sidebar.classList.toggle('open', shouldOpen);
            overlay.classList.toggle('show', shouldOpen);
        } else {
            const collapsed = !container.classList.contains('sidebar-collapsed');
            container.classList.toggle('sidebar-collapsed', collapsed);
            localStorage.setItem(storageKey, String(collapsed));
            requestAnimationFrame(() => syncSidebarIndicator());
        }
        updateToggle();
    });

    overlay.addEventListener('click', closeMobileSidebar);
    navBtns.forEach((button) => {
        button.addEventListener('click', () => {
            if (isMobile()) closeMobileSidebar();
        });
    });
    let resizeFrame = 0;
    window.addEventListener('resize', () => {
        cancelAnimationFrame(resizeFrame);
        resizeFrame = requestAnimationFrame(() => applyResponsiveState({ instant: true }));
    });
    container.addEventListener('transitionend', (event) => {
        if (event.propertyName === 'grid-template-columns') {
            syncSidebarIndicator({ instant: true });
        }
    });
    applyResponsiveState({ instant: true });
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

async function checkRuntimeConfig() {
    try {
        const response = await apiFetch(`${API_BASE}/chat/providers`);
        const data = await response.json();
        
        if (data.success && data.providers) {
            const providers = data.providers;
            console.log(
                providers.local_only
                    ? '✅ Bob local engine active'
                    : '✅ Bob runtime active'
            );
        }
    } catch (err) {
        console.error('Config check failed:', err);
    }
}
