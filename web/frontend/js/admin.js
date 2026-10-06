const state = {
  timer: null,
  activeTab: 'overview',
  overview: null,
  finance: null,
  financeLoaded: false,
  financeLoading: false,
  financeGeneratedAt: null,
  workspaces: null,
  workspacesLoaded: false,
  workspacesLoading: false,
  workspacesGeneratedAt: null,
  autoRefresh: true,
  refreshIntervalSeconds: 30,
  nextRefreshAt: null,
  auditWorkspaceId: null,
  auditEvents: [],
  auditNextBefore: null,
  auditLoading: false,
  users: [],
  aiUsage: null,
  controls: null,
  integrations: null,
  health: null,
  security: null,
  loadedTabs: new Set(),
  loadingTab: null,
};

const $ = (id) => document.getElementById(id);
const number = (value) => new Intl.NumberFormat('vi-VN').format(Number(value || 0));
const dateTime = (value) => value
  ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value))
  : '—';
const remainingTime = (seconds, periodEnd) => {
  if (!periodEnd) return 'Không giới hạn';
  let value = Math.max(0, Number(seconds || 0));
  const days = Math.floor(value / 86400);
  value -= days * 86400;
  const hours = Math.floor(value / 3600);
  value -= hours * 3600;
  const minutes = Math.floor(value / 60);
  if (days) return `${number(days)} ngày${hours ? ` ${hours} giờ` : ''}`;
  if (hours) return `${hours} giờ${minutes ? ` ${minutes} phút` : ''}`;
  return `${Math.max(0, minutes)} phút`;
};
const bytes = (value) => {
  let size = Number(value || 0);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index ? 1 : 0)} ${units[index]}`;
};
const currencyScale = (currency) => {
  try {
    const options = new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency,
    }).resolvedOptions();
    return 10 ** Number(options.maximumFractionDigits || 0);
  } catch {
    return 1;
  }
};
const money = (minorValue, currency = 'VND', compact = false) => {
  const value = Number(minorValue || 0) / currencyScale(currency);
  try {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency,
      notation: compact ? 'compact' : 'standard',
      maximumFractionDigits: compact ? 1 : undefined,
    }).format(value);
  } catch {
    return `${number(value)} ${currency}`;
  }
};
const usd = (value) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4,
}).format(Number(value || 0));
const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');
const normalizedText = (value) => String(value ?? '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase();

function renderMiniChart(targetId, items, valueKey = 'value', formatter = number) {
  const target = $(targetId);
  if (!target) return;
  const values = items.map((item) => Number(item[valueKey] || 0));
  const max = Math.max(...values, 1);
  target.innerHTML = items.length ? items.map((item) => {
    const value = Number(item[valueKey] || 0);
    const height = Math.max(3, Math.round(value / max * 120));
    const label = String(item.day || item.month || '').slice(-5);
    return `<div class="chart-column" title="${escapeHtml(item.day || item.month || '')}: ${escapeHtml(formatter(value))}">
      <span class="chart-value">${escapeHtml(formatter(value))}</span>
      <div class="chart-bar" style="height:${height}px"></div><span class="chart-day">${escapeHtml(label)}</span>
    </div>`;
  }).join('') : '<p class="muted">Chưa có dữ liệu.</p>';
}

function showToast(message, tone = 'success') {
  const node = $('adminToast');
  node.textContent = message;
  node.className = `admin-toast show ${tone}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    node.className = 'admin-toast';
  }, 3200);
}

function markRefreshed(data) {
  const identity = data?.admin?.identity;
  if (identity) $('adminIdentity').textContent = identity;
  const generatedAt = data?.generated_at || new Date().toISOString();
  $('lastRefreshText').textContent = `Làm mới ${dateTime(generatedAt)}`;
  state.nextRefreshAt = Date.now() + state.refreshIntervalSeconds * 1000;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.message || data.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function setConnection(kind, text) {
  const node = $('liveStatus');
  node.className = `status ${kind}`;
  node.innerHTML = `<i></i> ${escapeHtml(text)}`;
}

function showGate(name, message = '') {
  $('dashboard').classList.add('hidden');
  $('authPanel').classList.toggle('hidden', name !== 'login');
  $('totpPanel').classList.toggle('hidden', name !== 'totp');
  $('accessDeniedPanel').classList.toggle('hidden', name !== 'denied');
  $('adminLogoutButton').classList.add('hidden');
  if (name === 'login') $('authError').textContent = message;
  if (name === 'totp') {
    $('totpError').textContent = message;
    setTimeout(() => $('totpInput').focus(), 0);
  }
}

function activateTab(name, { focus = false, load = true } = {}) {
  const validTabs = ['overview', 'users', 'finance', 'ai', 'controls', 'integrations', 'health', 'security', 'workspaces'];
  const next = validTabs.includes(name) ? name : 'overview';
  state.activeTab = next;
  document.querySelectorAll('[data-dashboard-tab]').forEach((tab) => {
    const active = tab.dataset.dashboardTab === next;
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.tabIndex = active ? 0 : -1;
    if (active && focus) tab.focus();
  });
  document.querySelectorAll('[data-dashboard-panel]').forEach((panel) => {
    panel.hidden = panel.dataset.dashboardPanel !== next;
  });
  if (next === 'finance' && load && !state.financeLoaded) loadFinance();
  if (next === 'workspaces' && load && !state.workspacesLoaded) loadWorkspaces();
  if (load && !state.loadedTabs.has(next)) {
    const loaders = {
      users: loadAdminUsers,
      ai: loadAiUsage,
      controls: loadAiControls,
      integrations: loadIntegrations,
      health: loadSystemHealth,
      security: loadSecurity,
    };
    loaders[next]?.();
  }
  closeMobileSidebar();
}

function openMobileSidebar() {
  document.body.classList.add('sidebar-open');
  $('sidebar').classList.add('open');
  $('sidebarScrim').hidden = false;
  $('sidebarOpenButton').setAttribute('aria-expanded', 'true');
}

function closeMobileSidebar() {
  document.body.classList.remove('sidebar-open');
  $('sidebar').classList.remove('open');
  $('sidebarScrim').hidden = true;
  $('sidebarOpenButton').setAttribute('aria-expanded', 'false');
}

function setSidebarCollapsed(collapsed) {
  $('dashboard').classList.toggle('sidebar-collapsed', collapsed);
  $('sidebarCollapseButton').setAttribute('aria-pressed', collapsed ? 'true' : 'false');
  try {
    localStorage.setItem('admin_sidebar_collapsed', collapsed ? '1' : '0');
  } catch (_) {}
}

function handleAdminGate(error) {
  const code = error.data?.error;
  if (code === 'admin_totp_required') {
    showGate('totp');
    setConnection('waiting', 'Chờ mã TOTP');
    return true;
  }
  if (code === 'admin_not_allowed') {
    showGate('denied');
    setConnection('offline', 'Tài khoản không có quyền admin');
    return true;
  }
  if (code === 'admin_google_login_required' || code === 'admin_not_configured' || error.status === 401) {
    showGate('login', error.message);
    setConnection('offline', code === 'admin_not_configured' ? 'Admin đang khóa' : 'Cần đăng nhập');
    return true;
  }
  return false;
}

function renderMetricList(summary) {
  const metrics = [
    ['Token đang hoạt động', summary.oauth_active, ''],
    ['Access token đã hết hạn', summary.oauth_access_expired, summary.oauth_access_expired ? 'warn' : ''],
    ['Token thiếu scope Gmail/Calendar', summary.oauth_missing_scopes, summary.oauth_missing_scopes ? 'bad' : ''],
    ['Token đã thu hồi', summary.oauth_revoked, ''],
    ['Lịch lỗi đồng bộ', summary.schedules_sync_failed, summary.schedules_sync_failed ? 'bad' : ''],
    ['Gợi ý lịch đang chờ', summary.meeting_suggestions_pending, ''],
  ];
  $('oauthMetrics').innerHTML = metrics.map(([label, value, tone]) => (
    `<div class="metric-row"><span>${escapeHtml(label)}</span><strong class="${tone}">${number(value)}</strong></div>`
  )).join('');
}

function renderActivity(items) {
  const values = items.map((item) => Number(item.value || 0));
  const max = Math.max(...values, 1);
  $('activityChart').innerHTML = items.map((item) => {
    const height = Math.max(3, Math.round((Number(item.value || 0) / max) * 150));
    const day = new Date(`${item.day}T00:00:00`);
    return `<div class="chart-column" title="${escapeHtml(item.day)}: ${number(item.value)}">
      <span class="chart-value">${number(item.value)}</span>
      <div class="chart-bar" style="height:${height}px"></div>
      <span class="chart-day">${day.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })}</span>
    </div>`;
  }).join('');
}

function renderBars(target, items, formatValue = number) {
  const values = items.map((item) => Number(item.value ?? item.bytes ?? 0));
  const max = Math.max(...values, 1);
  $(target).innerHTML = items.length ? items.map((item) => {
    const value = Number(item.value ?? item.bytes ?? 0);
    const label = item.label ?? item.table_name ?? 'unknown';
    return `<div class="bar-row">
      <span class="bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, value / max * 100)}%"></div></div>
      <span class="bar-value">${escapeHtml(formatValue(value))}</span>
    </div>`;
  }).join('') : '<p class="muted">Chưa có dữ liệu.</p>';
}

function renderSyncJobs(items) {
  const query = normalizedText($('syncJobSearch').value);
  const status = $('syncJobStatusFilter').value;
  const filtered = items.filter((job) => {
    const haystack = normalizedText([
      job.user_id,
      job.job_type,
      job.status,
      job.error_message,
    ].join(' '));
    return (!query || haystack.includes(query)) && (status === 'all' || job.status === status);
  });
  $('syncJobResultCount').textContent = `${number(filtered.length)} / ${number(items.length)} tác vụ`;
  $('syncJobsBody').innerHTML = filtered.length ? filtered.map((job) => (
    `<tr>
      <td>${escapeHtml(dateTime(job.created_at))}</td>
      <td>${escapeHtml(job.user_id)}</td>
      <td>${escapeHtml(job.job_type)}</td>
      <td><span class="badge ${escapeHtml(job.status)}">${escapeHtml(job.status)}</span></td>
      <td>${escapeHtml(job.error_message || (job.finished_at ? `Hoàn tất ${dateTime(job.finished_at)}` : 'Đang xử lý'))}</td>
    </tr>`
  )).join('') : '<tr><td colspan="5" class="muted">Không có tác vụ phù hợp bộ lọc.</td></tr>';
}

function renderUsers(items) {
  const query = normalizedText($('userSearch').value);
  const plan = $('userPlanFilter').value;
  const connection = $('userConnectionFilter').value;
  const filtered = items.filter((user) => {
    const isPremium = Boolean(user.subscription_plan_name);
    const haystack = normalizedText([user.name, user.gmail_email, user.email, user.user_id].join(' '));
    const planMatches = plan === 'all' || (plan === 'premium' ? isPremium : !isPremium);
    const connectionMatches = connection === 'all'
      || (connection === 'connected' ? user.gmail_connected : !user.gmail_connected);
    return (!query || haystack.includes(query)) && planMatches && connectionMatches;
  });
  $('userResultCount').textContent = `${number(filtered.length)} / ${number(items.length)} người dùng`;
  $('usersBody').innerHTML = filtered.length ? filtered.map((user) => {
    const isPremium = Boolean(user.subscription_plan_name);
    const remaining = remainingTime(
      user.subscription_remaining_seconds,
      user.subscription_current_period_end
    );
    return `<tr>
      <td><strong>${escapeHtml(user.name || user.user_id)}</strong><br><span class="muted">${escapeHtml(user.gmail_email || user.email || user.user_id)}</span></td>
      <td><span class="badge ${user.gmail_connected ? 'success' : 'failed'}">${user.gmail_connected ? 'Đã kết nối' : 'Chưa kết nối'}</span></td>
      <td>${escapeHtml(user.user_mode || 'Chưa chọn')}</td>
      <td>${escapeHtml(dateTime(user.updated_at))}</td>
      <td>
        <span class="badge ${isPremium ? 'success' : ''}">${isPremium ? 'Premium' : 'Free'}</span>
        ${isPremium ? `<br><strong class="premium-remaining">Còn ${escapeHtml(remaining)}</strong>
          <br><span class="muted">Hết hạn ${escapeHtml(dateTime(user.subscription_current_period_end))}</span>` : ''}
      </td>
      <td class="subscription-actions">
        ${isPremium
          ? `<button type="button" class="btn-link" data-renew-premium="${escapeHtml(user.user_id)}">Gia hạn 30 ngày</button>
             <button type="button" class="btn-link danger" data-revoke-premium="${escapeHtml(user.user_id)}">Thu hồi</button>`
          : `<button type="button" class="btn-link" data-grant-premium="${escapeHtml(user.user_id)}">Cấp Premium</button>`}
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="6" class="muted">Không có người dùng phù hợp bộ lọc.</td></tr>';
}

async function grantPremium(userId, action = 'purchase') {
  const renewing = action === 'renew';
  const verb = renewing ? 'Gia hạn Premium thêm 30 ngày' : 'Cấp Premium 30 ngày';
  if (!window.confirm(`${verb} cho ${userId}?`)) return;
  try {
    const result = await api(`/api/admin/users/${encodeURIComponent(userId)}/subscription`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        plan_code: 'premium_monthly',
        plan_name: 'Premium',
        billing_interval: 'monthly',
        unit_amount: 49000,
        days: 30,
      }),
    });
    const remaining = remainingTime(
      result.subscription?.remaining_seconds,
      result.subscription?.current_period_end
    );
    showToast(`${renewing ? 'Đã gia hạn' : 'Đã cấp'} Premium. Còn lại ${remaining}.`);
    state.financeLoaded = false;
    await loadDashboard();
  } catch (error) {
    if (!handleAdminGate(error)) {
      if (error.data?.allowed_action === 'renew') {
        window.alert('Tài khoản đã có Premium và chỉ có thể gia hạn.');
        await loadDashboard();
      } else {
        window.alert(error.message || 'Không cập nhật được Premium.');
      }
    }
  }
}

async function revokePremium(userId) {
  if (!window.confirm(`Thu hồi Premium của ${userId}?`)) return;
  try {
    await api(`/api/admin/users/${encodeURIComponent(userId)}/subscription/revoke`, { method: 'POST', body: '{}' });
    state.financeLoaded = false;
    showToast(`Đã thu hồi Premium của ${userId}.`, 'warning');
    await loadDashboard();
  } catch (error) {
    if (!handleAdminGate(error)) window.alert(error.message || 'Không thu hồi được Premium.');
  }
}

$('usersBody')?.addEventListener('click', (event) => {
  const grantId = event.target.closest('[data-grant-premium]')?.dataset.grantPremium;
  const renewId = event.target.closest('[data-renew-premium]')?.dataset.renewPremium;
  const revokeId = event.target.closest('[data-revoke-premium]')?.dataset.revokePremium;
  if (grantId) grantPremium(grantId, 'purchase');
  if (renewId) grantPremium(renewId, 'renew');
  if (revokeId) revokePremium(revokeId);
});

function renderAlerts(summary) {
  const alerts = [];
  if (Number(summary.oauth_access_expired)) alerts.push(['warning', `${number(summary.oauth_access_expired)} access token Google đã hết hạn; refresh token sẽ được thử khi người dùng đồng bộ.`]);
  if (Number(summary.oauth_missing_scopes)) alerts.push(['danger', `${number(summary.oauth_missing_scopes)} tài khoản thiếu scope Gmail hoặc Calendar và cần kết nối lại.`]);
  if (Number(summary.sync_failures_24h)) alerts.push(['danger', `${number(summary.sync_failures_24h)} tác vụ đồng bộ thất bại trong 24 giờ qua.`]);
  // Phase 6 ("Billing automation and production hardening"): operational
  // alerts for the subscription lifecycle -- live-queried, not a separate
  // alert-delivery system (see services/subscription_lifecycle_scheduler.py).
  if (Number(summary.workspaces_in_grace)) alerts.push(['warning', `${number(summary.workspaces_in_grace)} workspace doanh nghiệp đang trong 7 ngày gia hạn.`]);
  if (Number(summary.workspaces_read_only)) alerts.push(['danger', `${number(summary.workspaces_read_only)} workspace doanh nghiệp đã chuyển sang chỉ đọc do hết hạn.`]);
  if (Number(summary.failed_payments_24h)) alerts.push(['warning', `${number(summary.failed_payments_24h)} giao dịch thanh toán thất bại trong 24 giờ qua.`]);
  $('alerts').innerHTML = alerts.length
    ? alerts.map(([tone, text]) => `<div class="alert ${tone === 'danger' ? 'danger' : ''}">${escapeHtml(text)}</div>`).join('')
    : '<div class="alert success">Hệ thống đang ổn định — không có cảnh báo vận hành trong 24 giờ qua.</div>';
}

function render(data) {
  state.overview = data;
  const summary = data.summary || {};
  $('usersTotal').textContent = number(summary.users_total);
  $('usersConnected').textContent = `${number(summary.google_connected_users)} đã kết nối Google`;
  $('calendarTotal').textContent = number(summary.calendar_events_total);
  $('calendarFresh').textContent = `${number(summary.calendar_events_fetched_24h)} lấy trong 24 giờ`;
  $('schedulesUpcoming').textContent = number(summary.schedules_upcoming);
  $('schedulesSynced').textContent = `${number(summary.schedules_synced)} đã đồng bộ Google`;
  $('actions24h').textContent = number(summary.actions_24h);
  $('syncFailures').textContent = `${number(summary.sync_failures_24h)} lỗi sync`;
  $('historyTotal').textContent = `${number(summary.history_total)} hoạt động`;
  $('databaseSize').textContent = bytes(data.database?.bytes);
  $('generatedAt').textContent = `Cập nhật ${dateTime(data.generated_at)}`;
  $('runtimeInfo').textContent = `${data.backend} · uptime ${Math.floor(Number(data.process_uptime_seconds || 0) / 60)} phút`;
  $('activeUsersToday').textContent = number(summary.users_active_today);
  $('activeUsersMonth').textContent = `${number(summary.users_active_month)} active trong tháng`;
  $('planMix').textContent = `${number(summary.users_free)} / ${number(summary.users_plus)}`;
  $('newUsersMonth').textContent = `${number(summary.users_new_month)} mới tháng này · ${number(summary.users_new_today)} hôm nay`;
  $('overviewRevenueMonth').textContent = money(summary.revenue_month, 'VND', true);
  $('overviewAiCost').textContent = usd(summary.ai_cost_month_usd);
  $('overviewAiRequests').textContent = `${number(summary.ai_requests_month)} requests`;
  const overviewErrorRate = Number(summary.ai_requests_month)
    ? Number(summary.ai_errors_month || 0) / Number(summary.ai_requests_month) * 100 : 0;
  $('overviewErrorRate').textContent = `${overviewErrorRate.toFixed(1)}% lỗi`;

  renderAlerts(summary);
  renderMetricList(summary);
  renderActivity(data.activity_14d || []);
  renderBars('modeBars', data.users_by_mode || []);
  renderBars('tableSizes', data.table_sizes || [], bytes);
  renderSyncJobs(data.recent_sync_jobs || []);
  renderUsers(data.recent_users || []);
  renderMiniChart('userGrowthChart', data.user_growth_30d || [], 'value');
  renderMiniChart('overviewRevenueChart', data.revenue_30d || [], 'value');
  renderMiniChart('aiCostChart', data.ai_cost_30d || [], 'value', (value) => usd(value));
  markRefreshed(data);
}

function workspaceAccessLabel(accessState) {
  return {
    active: 'Hoạt động',
    grace: 'Grace period',
    read_only: 'Chỉ đọc',
    none: 'Chưa có gói',
  }[accessState] || accessState || '—';
}

function renderWorkspaces(data = state.workspaces) {
  if (!data) return;
  const summary = data.summary || {};
  const items = data.workspaces || [];
  const query = normalizedText($('workspaceSearch').value);
  const accessState = $('workspaceStateFilter').value;
  const filtered = items.filter((workspace) => {
    const haystack = normalizedText([
      workspace.name,
      workspace.slug,
      workspace.owner,
      workspace.owner_user_id,
      workspace.workspace_id,
    ].join(' '));
    return (!query || haystack.includes(query))
      && (accessState === 'all' || workspace.access_state === accessState);
  });

  $('businessWorkspaces').textContent = number(summary.business_workspaces);
  $('activeBusinessWorkspaces').textContent = `${number(summary.active_workspaces)} đang hoạt động`;
  $('workspaceSeats').textContent = `${number(summary.active_seats)} / ${number(summary.seat_capacity)}`;
  $('attentionWorkspaces').textContent = number(summary.attention_workspaces);
  $('pendingSeatRequests').textContent = number(summary.pending_seat_requests);
  $('workspacesGeneratedAt').textContent = `Cập nhật ${dateTime(data.generated_at)}`;
  $('workspaceResultCount').textContent = `${number(filtered.length)} / ${number(items.length)} tổ chức`;
  $('workspacesBody').innerHTML = filtered.length ? filtered.map((workspace) => {
    const hasSubscription = Boolean(workspace.subscription_id);
    const renew = hasSubscription ? 'renew' : 'purchase';
    const primaryLabel = hasSubscription ? 'Gia hạn 30 ngày' : 'Kích hoạt Business';
    const plan = workspace.plan_name || workspace.plan_code || 'Chưa kích hoạt';
    const seatDetail = [
      Number(workspace.pending_invitations || 0) ? `${number(workspace.pending_invitations)} lời mời chờ` : '',
      Number(workspace.pending_seat_requests || 0) ? `${number(workspace.pending_seat_requests)} yêu cầu ghế` : '',
    ].filter(Boolean).join(' · ');
    return `<tr>
      <td><strong>${escapeHtml(workspace.name || workspace.workspace_id)}</strong><br><span class="muted">${escapeHtml(workspace.slug || workspace.workspace_id)}</span></td>
      <td>${escapeHtml(workspace.owner || workspace.owner_user_id || '—')}</td>
      <td><span class="badge ${escapeHtml(workspace.access_state)}">${escapeHtml(workspaceAccessLabel(workspace.access_state))}</span></td>
      <td><strong>${number(workspace.active_seats)} / ${number(workspace.seat_capacity)}</strong>${seatDetail ? `<br><span class="muted">${escapeHtml(seatDetail)}</span>` : ''}</td>
      <td>${escapeHtml(plan)}<br><span class="muted">${escapeHtml(workspace.billing_interval === 'yearly' ? 'Hằng năm' : (hasSubscription ? 'Hằng tháng' : '10 ghế mặc định'))}</span></td>
      <td>${escapeHtml(dateTime(workspace.current_period_end || workspace.updated_at))}</td>
      <td class="subscription-actions">
        <button type="button" class="btn-link" data-${renew === 'renew' ? 'renew' : 'grant'}-business="${escapeHtml(workspace.workspace_id)}">${escapeHtml(primaryLabel)}</button>
        ${hasSubscription ? `<button type="button" class="btn-link danger" data-revoke-business="${escapeHtml(workspace.workspace_id)}">Thu hồi</button>` : ''}
        <button type="button" class="btn-link" data-view-audit="${escapeHtml(workspace.workspace_id)}" data-view-audit-name="${escapeHtml(workspace.name || workspace.workspace_id)}">Nhật ký</button>
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="7" class="muted">Không có tổ chức phù hợp bộ lọc.</td></tr>';
}

async function grantBusinessSubscription(workspaceId, action = 'purchase') {
  const renewing = action === 'renew';
  if (!window.confirm(`${renewing ? 'Gia hạn' : 'Kích hoạt'} Business 30 ngày cho workspace ${workspaceId}?`)) return;
  try {
    await api(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/subscription`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        plan_code: 'business_monthly',
        plan_name: 'Business',
        billing_interval: 'monthly',
        currency: 'VND',
        unit_amount: 0,
        included_seats: 10,
        days: 30,
      }),
    });
    state.financeLoaded = false;
    state.workspacesLoaded = false;
    showToast(`${renewing ? 'Đã gia hạn' : 'Đã kích hoạt'} Business cho workspace.`);
    await loadWorkspaces();
  } catch (error) {
    if (!handleAdminGate(error)) {
      if (error.data?.allowed_action === 'renew') {
        showToast('Workspace đã có gói; hãy dùng thao tác gia hạn.', 'warning');
        await loadWorkspaces();
      } else {
        showToast(error.message || 'Không cập nhật được gói Business.', 'error');
      }
    }
  }
}

async function revokeBusinessSubscription(workspaceId) {
  if (!window.confirm(`Thu hồi quyền Business của workspace ${workspaceId}?`)) return;
  try {
    await api(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/subscription/revoke`, {
      method: 'POST',
      body: '{}',
    });
    state.financeLoaded = false;
    state.workspacesLoaded = false;
    showToast('Đã thu hồi quyền Business của workspace.', 'warning');
    await loadWorkspaces();
  } catch (error) {
    if (!handleAdminGate(error)) showToast(error.message || 'Không thu hồi được gói Business.', 'error');
  }
}

// Phase 5 ("Advanced workspace and AI"): surface workspace_audit_events,
// written on every business-data mutation (see routes/work_hub.py,
// sharing.py, workspace_subscription.py) but never displayed before this.
function openWorkspaceAudit(workspaceId, workspaceName) {
  state.auditWorkspaceId = workspaceId;
  state.auditEvents = [];
  state.auditNextBefore = null;
  $('workspaceAuditTitle').textContent = `Nhật ký · ${workspaceName || workspaceId}`;
  $('auditEventTypeFilter').value = '';
  $('workspaceAuditPanel').hidden = false;
  $('workspaceAuditPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  loadWorkspaceAudit({ reset: true });
}

function closeWorkspaceAudit() {
  state.auditWorkspaceId = null;
  $('workspaceAuditPanel').hidden = true;
}

async function loadWorkspaceAudit({ reset = false } = {}) {
  if (!state.auditWorkspaceId || state.auditLoading) return;
  state.auditLoading = true;
  const params = new URLSearchParams({ limit: '50' });
  const eventType = $('auditEventTypeFilter').value;
  if (eventType) params.set('event_type', eventType);
  if (!reset && state.auditNextBefore) params.set('before', state.auditNextBefore);
  try {
    const data = await api(`/api/admin/workspaces/${encodeURIComponent(state.auditWorkspaceId)}/audit?${params}`);
    state.auditEvents = reset ? (data.events || []) : [...state.auditEvents, ...(data.events || [])];
    state.auditNextBefore = data.has_more ? data.next_before : null;
    renderWorkspaceAudit();
  } catch (error) {
    if (!handleAdminGate(error)) showToast(error.message || 'Không tải được nhật ký hoạt động.', 'error');
  } finally {
    state.auditLoading = false;
  }
}

function renderWorkspaceAudit() {
  const filterSelect = $('auditEventTypeFilter');
  const knownTypes = new Set(Array.from(filterSelect.options).map((option) => option.value).filter(Boolean));
  state.auditEvents.forEach((event) => {
    if (event.event_type && !knownTypes.has(event.event_type)) {
      knownTypes.add(event.event_type);
      filterSelect.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(event.event_type)}">${escapeHtml(event.event_type)}</option>`);
    }
  });
  $('workspaceAuditBody').innerHTML = state.auditEvents.length
    ? state.auditEvents.map((event) => `<tr>
        <td>${escapeHtml(dateTime(event.created_at))}</td>
        <td><span class="badge">${escapeHtml(event.event_type || '—')}</span></td>
        <td>${escapeHtml(event.actor_user_id || '—')}</td>
        <td>${escapeHtml([event.target_type, event.target_id].filter(Boolean).join(' · ') || '—')}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" class="muted">Chưa có sự kiện nào.</td></tr>';
  $('loadMoreAuditButton').hidden = !state.auditNextBefore;
}

function setMoneyValue(id, value, currency) {
  const node = $(id);
  node.textContent = money(value, currency);
  node.classList.toggle('negative-money', Number(value || 0) < 0);
}

function financeSummaryFor(finance, currency) {
  return (finance.currencies || []).find((item) => item.currency === currency) || {
    currency,
    gross_revenue_month: 0,
    fees_month: 0,
    refunds_month: 0,
    net_revenue_month: 0,
    payments_month: 0,
    active_subscriptions: 0,
    trialing_subscriptions: 0,
    past_due_subscriptions: 0,
    new_subscriptions_month: 0,
    canceled_subscriptions_month: 0,
    mrr: 0,
  };
}

function populateFinanceCurrencies(finance) {
  const picker = $('financeCurrency');
  const current = picker.value || 'VND';
  const currencies = Array.from(new Set(
    (finance.currencies || []).map((item) => item.currency).filter(Boolean)
  ));
  if (!currencies.length) currencies.push('VND');
  picker.innerHTML = currencies.map((currency) => (
    `<option value="${escapeHtml(currency)}">${escapeHtml(currency)}</option>`
  )).join('');
  picker.value = currencies.includes(current) ? current : currencies[0];
  return picker.value;
}

function renderRevenueChart(finance, currency) {
  const items = (finance.revenue_12m || []).filter((item) => item.currency === currency);
  const max = Math.max(
    ...items.flatMap((item) => [Math.abs(Number(item.gross || 0)), Math.abs(Number(item.net || 0))]),
    1
  );
  const netTotal = items.reduce((sum, item) => sum + Number(item.net || 0), 0);
  $('revenueChartSummary').textContent = `12T: ${money(netTotal, currency, true)}`;
  $('revenueChart').setAttribute(
    'aria-label',
    `Biểu đồ 12 tháng, tổng thực thu ${money(netTotal, currency)}`
  );
  $('revenueChart').innerHTML = items.map((item) => {
    const grossHeight = Math.max(3, Math.round(Math.abs(Number(item.gross || 0)) / max * 150));
    const netHeight = Math.max(3, Math.round(Math.abs(Number(item.net || 0)) / max * 150));
    const [year, month] = String(item.month || '').split('-');
    return `<div class="chart-column" title="${escapeHtml(item.month)} · Gộp ${escapeHtml(money(item.gross, currency))} · Thực thu ${escapeHtml(money(item.net, currency))}">
      <span class="chart-value ${Number(item.net || 0) < 0 ? 'negative-money' : ''}">${escapeHtml(money(item.net, currency, true))}</span>
      <div class="revenue-bars">
        <div class="revenue-bar gross" style="height:${grossHeight}px"></div>
        <div class="revenue-bar net" style="height:${netHeight}px"></div>
      </div>
      <span class="chart-day">${escapeHtml(month || '—')}/${escapeHtml(String(year || '').slice(-2))}</span>
    </div>`;
  }).join('');
}

function renderFinanceMetrics(summary, currency, audience = {}) {
  const metrics = [
    ['Revenue hôm nay', money(summary.revenue_today, currency), ''],
    ['Phí cổng thanh toán', money(summary.fees_month, currency), Number(summary.fees_month) ? 'warn' : ''],
    ['Hoàn tiền trong tháng', money(summary.refunds_month, currency), Number(summary.refunds_month) ? 'warn' : ''],
    ['Đang dùng thử', number(summary.trialing_subscriptions), ''],
    ['Quá hạn thanh toán', number(summary.past_due_subscriptions), Number(summary.past_due_subscriptions) ? 'bad' : ''],
    ['Subscription mới', number(summary.new_subscriptions_month), ''],
    ['Subscription hủy', number(summary.canceled_subscriptions_month), Number(summary.canceled_subscriptions_month) ? 'warn' : ''],
    ['Failed payments', number(summary.failed_payments), Number(summary.failed_payments) ? 'bad' : ''],
    ['Free / Plus users', `${number(audience.free_users)} / ${number(audience.plus_users)}`, ''],
    ['Monthly / Annual', `${number(audience.monthly_subscriptions)} / ${number(audience.annual_subscriptions)}`, ''],
    ['Conversion Free → Plus', `${Number(audience.conversion_rate || 0).toFixed(2)}%`, ''],
    ['Churn rate', `${Number(audience.churn_rate || 0).toFixed(2)}%`, Number(audience.churn_rate) ? 'warn' : ''],
  ];
  $('financeMetrics').innerHTML = metrics.map(([label, value, tone]) => (
    `<div class="metric-row"><span>${escapeHtml(label)}</span><strong class="${tone}">${escapeHtml(value)}</strong></div>`
  )).join('');
}

function renderSubscriptionPlans(finance, currency) {
  const items = (finance.subscriptions_by_plan || []).filter((item) => item.currency === currency);
  const max = Math.max(...items.map((item) => Number(item.active || 0)), 1);
  $('plansTotal').textContent = `${number(items.length)} gói`;
  $('subscriptionPlans').innerHTML = items.length ? items.map((item) => {
    const active = Number(item.active || 0);
    const details = [
      `${number(active)} active`,
      Number(item.trialing || 0) ? `${number(item.trialing)} trial` : '',
      money(item.mrr, currency, true),
    ].filter(Boolean).join(' · ');
    return `<div class="bar-row">
      <span class="bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, active / max * 100)}%"></div></div>
      <span class="bar-value" title="${escapeHtml(details)}">${escapeHtml(details)}</span>
    </div>`;
  }).join('') : '<p class="muted">Chưa có subscription cho đơn vị tiền này.</p>';
}

function statusLabel(status) {
  return {
    pending: 'Chờ xử lý',
    paid: 'Đã thanh toán',
    failed: 'Thất bại',
    partially_refunded: 'Hoàn một phần',
    refunded: 'Đã hoàn tiền',
    trialing: 'Dùng thử',
    active: 'Hoạt động',
    past_due: 'Quá hạn',
    paused: 'Tạm dừng',
    canceled: 'Đã hủy',
    incomplete: 'Chưa hoàn tất',
    expired: 'Hết hạn',
  }[status] || status || '—';
}

function renderRecentPayments(finance, currency) {
  const items = (finance.recent_payments || []).filter((item) => item.currency === currency);
  $('recentPaymentsBody').innerHTML = items.length ? items.map((payment) => (
    `<tr>
      <td>${escapeHtml(dateTime(payment.paid_at || payment.created_at))}</td>
      <td><strong>${escapeHtml(payment.customer)}</strong><br><span class="muted">${escapeHtml(payment.description || `#${payment.id}`)}</span></td>
      <td>${escapeHtml(payment.plan_name || '—')}<br><span class="muted">${escapeHtml(payment.provider)}</span></td>
      <td>${escapeHtml(money(payment.gross_amount, currency))}</td>
      <td>${escapeHtml(money(payment.fee_amount, currency))}</td>
      <td>${escapeHtml(money(payment.refund_amount, currency))}</td>
      <td class="${Number(payment.net_amount || 0) < 0 ? 'negative-money' : ''}"><strong>${escapeHtml(money(payment.net_amount, currency))}</strong></td>
      <td><span class="badge ${escapeHtml(payment.status)}">${escapeHtml(statusLabel(payment.status))}</span></td>
    </tr>`
  )).join('') : '<tr><td colspan="8" class="muted">Chưa có giao dịch cho đơn vị tiền này.</td></tr>';
}

function renderRecentSubscriptions(finance, currency) {
  const items = (finance.recent_subscriptions || []).filter((item) => item.currency === currency);
  $('recentSubscriptionsBody').innerHTML = items.length ? items.map((subscription) => {
    const active = ['active', 'trialing'].includes(subscription.status)
      && (!subscription.current_period_end || Number(subscription.remaining_seconds || 0) > 0);
    const remaining = remainingTime(
      subscription.remaining_seconds,
      subscription.current_period_end
    );
    const workspaceId = subscription.workspace_id;
    const actions = workspaceId
      ? `<button type="button" class="btn-link" data-renew-business="${escapeHtml(workspaceId)}">Gia hạn 30 ngày</button>
         <button type="button" class="btn-link danger" data-revoke-business="${escapeHtml(workspaceId)}">Thu hồi</button>`
      : (active && subscription.user_id
        ? `<button type="button" class="btn-link" data-renew-premium="${escapeHtml(subscription.user_id)}">Gia hạn 30 ngày</button>
           <button type="button" class="btn-link danger" data-revoke-premium="${escapeHtml(subscription.user_id)}">Thu hồi</button>`
        : '<span class="muted">—</span>');
    return `<tr>
      <td><strong>${escapeHtml(subscription.customer)}</strong><br><span class="muted">${escapeHtml(subscription.provider)}</span></td>
      <td>${escapeHtml(subscription.plan_name || subscription.plan_code)}</td>
      <td>${subscription.billing_interval === 'yearly' ? 'Hằng năm' : 'Hằng tháng'}</td>
      <td>${escapeHtml(money(subscription.unit_amount, currency))}</td>
      <td>${escapeHtml(dateTime(subscription.current_period_end))}
        ${active ? `<br><strong class="premium-remaining">Còn ${escapeHtml(remaining)}</strong>` : ''}
        ${subscription.cancel_at_period_end ? '<br><span class="muted">Sẽ hủy cuối kỳ</span>' : ''}
      </td>
      <td><span class="badge ${escapeHtml(subscription.status)}">${escapeHtml(statusLabel(subscription.status))}</span></td>
      <td class="subscription-actions">
        ${actions}
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="7" class="muted">Chưa có subscription cho đơn vị tiền này.</td></tr>';
}

$('recentSubscriptionsBody')?.addEventListener('click', (event) => {
  const renewId = event.target.closest('[data-renew-premium]')?.dataset.renewPremium;
  const revokeId = event.target.closest('[data-revoke-premium]')?.dataset.revokePremium;
  const renewWorkspaceId = event.target.closest('[data-renew-business]')?.dataset.renewBusiness;
  const revokeWorkspaceId = event.target.closest('[data-revoke-business]')?.dataset.revokeBusiness;
  if (renewId) grantPremium(renewId, 'renew');
  if (revokeId) revokePremium(revokeId);
  if (renewWorkspaceId) grantBusinessSubscription(renewWorkspaceId, 'renew');
  if (revokeWorkspaceId) revokeBusinessSubscription(revokeWorkspaceId);
});

function renderFinance(data) {
  const finance = data.finance || {};
  state.finance = finance;
  state.financeGeneratedAt = data.generated_at;
  const currency = populateFinanceCurrencies(finance);
  const summary = financeSummaryFor(finance, currency);
  const reportDate = data.generated_at ? new Date(data.generated_at) : new Date();

  $('financePeriodLabel').textContent = `${new Intl.DateTimeFormat('vi-VN', {
    month: 'long',
    year: 'numeric',
  }).format(reportDate)} · ${finance.reporting_timezone || 'Asia/Ho_Chi_Minh'}`;
  $('financeEmptyState').classList.toggle('hidden', Boolean(finance.has_data));
  setMoneyValue('grossRevenueMonth', summary.gross_revenue_month, currency);
  setMoneyValue('netRevenueMonth', summary.net_revenue_month, currency);
  setMoneyValue('monthlyRecurringRevenue', summary.mrr, currency);
  $('paymentsMonth').textContent = `${number(summary.payments_month)} giao dịch thành công`;
  $('activeSubscriptions').textContent = number(summary.active_subscriptions);
  $('subscriptionMovement').textContent = `+${number(summary.new_subscriptions_month)} mới · ${number(summary.canceled_subscriptions_month)} hủy trong tháng`;
  $('financeGeneratedAt').textContent = `Cập nhật ${dateTime(data.generated_at)}`;

  renderRevenueChart(finance, currency);
  renderFinanceMetrics(summary, currency, finance.audience || {});
  renderSubscriptionPlans(finance, currency);
  renderRecentPayments(finance, currency);
  renderRecentSubscriptions(finance, currency);
  markRefreshed(data);
}

function rerenderFinanceCurrency() {
  if (!state.finance) return;
  renderFinance({
    finance: state.finance,
    generated_at: state.financeGeneratedAt,
  });
}

async function loadFinance() {
  if (state.financeLoading) return;
  state.financeLoading = true;
  $('refreshButton').disabled = true;
  $('financeError').classList.add('hidden');
  setConnection('waiting', 'Đang tải tài chính');
  try {
    const data = await api('/api/admin/finance');
    state.financeLoaded = true;
    renderFinance(data);
    setConnection('online', 'Admin đã xác thực');
  } catch (error) {
    state.financeLoaded = false;
    if (!handleAdminGate(error)) {
      $('financeError').textContent = `Không tải được số liệu tài chính: ${error.message}`;
      $('financeError').classList.remove('hidden');
      setConnection('offline', 'Lỗi dữ liệu tài chính');
    }
  } finally {
    state.financeLoading = false;
    $('refreshButton').disabled = false;
  }
}

async function loadWorkspaces() {
  if (state.workspacesLoading) return;
  state.workspacesLoading = true;
  $('refreshButton').disabled = true;
  $('workspacesError').classList.add('hidden');
  setConnection('waiting', 'Đang tải tổ chức');
  try {
    const data = await api('/api/admin/workspaces');
    state.workspaces = data;
    state.workspacesLoaded = true;
    state.workspacesGeneratedAt = data.generated_at;
    renderWorkspaces(data);
    markRefreshed(data);
    setConnection('online', 'Admin đã xác thực');
  } catch (error) {
    state.workspacesLoaded = false;
    if (!handleAdminGate(error)) {
      $('workspacesError').textContent = `Không tải được danh sách tổ chức: ${error.message}`;
      $('workspacesError').classList.remove('hidden');
      setConnection('offline', 'Lỗi dữ liệu tổ chức');
    }
  } finally {
    state.workspacesLoading = false;
    $('refreshButton').disabled = false;
  }
}

function renderAdminUsers() {
  const query = normalizedText($('adminUserSearch').value);
  const plan = $('adminUserPlanFilter').value;
  const status = $('adminUserStatusFilter').value;
  const filtered = state.users.filter((user) => {
    const isPlus = Boolean(user.plan_code || user.plan_name);
    const matchesPlan = plan === 'all' || (plan === 'plus' ? isPlus : !isPlus);
    const matchesStatus = status === 'all' || (user.account_status || 'active') === status;
    const haystack = normalizedText([user.user_id, user.name, user.email, user.gmail_email].join(' '));
    return matchesPlan && matchesStatus && (!query || haystack.includes(query));
  });
  $('adminUserCount').textContent = `${number(filtered.length)} / ${number(state.users.length)} users`;
  $('adminUsersBody').innerHTML = filtered.length ? filtered.map((user) => {
    const isPlus = Boolean(user.plan_code || user.plan_name);
    const accountStatus = user.account_status || 'active';
    return `<tr>
      <td><strong>${escapeHtml(user.name || user.user_id)}</strong><br><span class="muted">${escapeHtml(user.email || user.gmail_email || '—')}</span><br><code>${escapeHtml(user.user_id)}</code></td>
      <td><span class="badge ${isPlus ? 'success' : ''}">${isPlus ? 'Plus' : 'Free'}</span><br><span class="badge ${escapeHtml(accountStatus)}">${escapeHtml(accountStatus)}</span></td>
      <td>${escapeHtml(dateTime(user.last_login_at))}<br><span class="muted">Active ${escapeHtml(dateTime(user.last_active_at))}</span></td>
      <td>Gmail: ${user.gmail_connected ? '✓' : '—'}<br><span class="muted">Calendar: ${user.calendar_connected ? '✓' : '—'}</span></td>
      <td>${number(user.ai_usage_month)} requests<br><strong>${escapeHtml(usd(user.ai_cost_month_usd))}</strong></td>
      <td class="subscription-actions">
        <button class="btn-link" type="button" data-user-detail="${escapeHtml(user.user_id)}">Chi tiết</button>
        ${accountStatus === 'active' ? `<button class="btn-link" type="button" data-user-status="suspended" data-user-id="${escapeHtml(user.user_id)}">Suspend</button>` : `<button class="btn-link" type="button" data-user-status="active" data-user-id="${escapeHtml(user.user_id)}">Activate</button>`}
        ${accountStatus !== 'disabled' ? `<button class="btn-link danger" type="button" data-user-status="disabled" data-user-id="${escapeHtml(user.user_id)}">Disable</button>` : ''}
        ${isPlus ? `<button class="btn-link danger" type="button" data-admin-revoke-plan="${escapeHtml(user.user_id)}">Downgrade</button>` : `<button class="btn-link" type="button" data-admin-upgrade-plan="${escapeHtml(user.user_id)}">Upgrade</button>`}
        <button class="btn-link" type="button" data-reset-quota="${escapeHtml(user.user_id)}">Reset quota</button>
        <button class="btn-link danger" type="button" data-reset-usage="${escapeHtml(user.user_id)}">Reset AI limits</button>
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="6" class="muted">Không có người dùng phù hợp.</td></tr>';
}

async function loadAdminUsers() {
  if (state.loadingTab === 'users') return;
  state.loadingTab = 'users';
  try {
    const data = await api('/api/admin/users');
    state.users = data.users || [];
    state.loadedTabs.add('users');
    renderAdminUsers();
    markRefreshed(data);
  } catch (error) {
    if (!handleAdminGate(error)) showToast(error.message, 'error');
  } finally { state.loadingTab = null; }
}

async function updateUserStatus(userId, status) {
  if (!window.confirm(`${status} tài khoản ${userId}?`)) return;
  try {
    await api(`/api/admin/users/${encodeURIComponent(userId)}/status`, {
      method: 'POST', body: JSON.stringify({ status }),
    });
    state.loadedTabs.delete('users');
    await loadAdminUsers();
    showToast(`Đã chuyển tài khoản sang ${status}.`, status === 'active' ? 'success' : 'warning');
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
}

async function resetUserUsage(userId, scope = 'today') {
  const label = scope === 'all' ? 'toàn bộ bộ đếm AI usage' : 'quota AI hôm nay';
  if (!window.confirm(`Reset ${label} của ${userId}?`)) return;
  try {
    await api(`/api/admin/users/${encodeURIComponent(userId)}/usage/reset`, {
      method: 'POST', body: JSON.stringify({ scope }),
    });
    showToast(`Đã reset ${label}.`);
    state.loadedTabs.delete('users');
    await loadAdminUsers();
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
}

function showUserDetail(userId) {
  const user = state.users.find((item) => item.user_id === userId);
  if (!user) return;
  const rows = [
    ['User ID', user.user_id], ['Name', user.name], ['Email', user.email || user.gmail_email],
    ['Plan', user.plan_name || 'Free'], ['Account status', user.account_status || 'active'],
    ['Created', dateTime(user.created_at)], ['Last login', dateTime(user.last_login_at)],
    ['Last active', dateTime(user.last_active_at)], ['Gmail', user.gmail_connected ? 'Connected' : 'Not connected'],
    ['Calendar', user.calendar_connected ? 'Connected' : 'Not connected'],
    ['AI usage tháng', number(user.ai_usage_month)], ['AI cost tháng', usd(user.ai_cost_month_usd)],
    ['Input / Output tokens', `${number(user.ai_input_tokens_month)} / ${number(user.ai_output_tokens_month)}`],
  ];
  $('userDetailContent').innerHTML = `<p class="eyebrow">USER DETAIL</p><h2>${escapeHtml(user.name || user.user_id)}</h2><div class="detail-list">${rows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || '—')}</strong></div>`).join('')}</div>`;
  $('userDetailDialog').showModal();
}

function renderAiUsage(data) {
  const usage = data.usage || {};
  const summary = usage.summary || {};
  const requests = Number(summary.requests || 0);
  const successes = Number(summary.successes || 0);
  const errors = Number(summary.errors || 0);
  const totalTokens = Number(summary.input_tokens || 0) + Number(summary.output_tokens || 0);
  $('aiTotalRequests').textContent = number(requests);
  $('aiSuccessRate').textContent = `${requests ? (successes / requests * 100).toFixed(1) : '0.0'}% success`;
  $('aiTotalTokens').textContent = number(totalTokens);
  $('aiAvgTokens').textContent = `${number(summary.input_tokens)} in · ${number(summary.output_tokens)} out · ${number(summary.avg_tokens_request)} / request`;
  $('aiTotalCost').textContent = usd(summary.cost_usd);
  $('aiAvgCost').textContent = `${usd(summary.avg_cost_user_usd)} / user · ${usd(summary.avg_cost_request_usd)} / request`;
  $('aiCacheRate').textContent = `${requests ? (Number(summary.cache_hits || 0) / requests * 100).toFixed(1) : '0.0'}%`;
  $('aiErrorRate').textContent = `${requests ? (errors / requests * 100).toFixed(1) : '0.0'}% error rate`;
  renderMiniChart('aiDailyChart', usage.daily || [], 'cost_usd', usd);
  const renderGroups = (target, rows) => {
    $(target).innerHTML = rows.length ? rows.map((item) => `<div class="metric-row"><span>${escapeHtml(item.label)}</span><strong>${number(item.requests)} · ${escapeHtml(usd(item.cost_usd))}</strong></div>`).join('') : '<p class="muted">Chưa có dữ liệu.</p>';
  };
  renderGroups('aiProviders', usage.providers || []);
  renderGroups('aiTiers', usage.tiers || []);
  renderBars('aiModels', (usage.models || []).map((item) => ({ label: item.label, value: item.requests })));
  renderBars('aiFeatures', (usage.features || []).map((item) => ({ label: item.label, value: item.requests })));
  $('aiErrorsBody').innerHTML = (usage.recent_errors || []).length ? usage.recent_errors.map((item) => `<tr><td>${escapeHtml(dateTime(item.created_at))}</td><td>${escapeHtml(item.user_id || '—')}</td><td>${escapeHtml(item.feature || '—')}</td><td>${escapeHtml([item.provider, item.model].filter(Boolean).join(' · ') || '—')}</td><td>${escapeHtml(item.error_type || 'error')}</td><td>${number(item.latency_ms)} ms</td></tr>`).join('') : '<tr><td colspan="6" class="muted">Không có lỗi trong kỳ.</td></tr>';
}

async function loadAiUsage() {
  const days = Number($('aiUsageDays').value || 30);
  if (state.loadingTab === 'ai') return;
  state.loadingTab = 'ai';
  try {
    const data = await api(`/api/admin/ai-usage?days=${days}`);
    state.aiUsage = data;
    state.loadedTabs.add('ai');
    renderAiUsage(data);
    markRefreshed(data);
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
  finally { state.loadingTab = null; }
}

const quotaLabels = {
  bob_chat: 'Bob requests/day', email_summary: 'Email summaries/day',
  daily_overview: 'Daily Overview/day', claude: 'Claude requests/day',
  study_summary: 'Study summaries/day',
};
const budgetLabels = {
  monthly_usd: 'Monthly AI Budget', openai_usd: 'OpenAI Budget', claude_usd: 'Claude Budget',
  warning_usd: 'Warning level 1', warning_high_usd: 'Warning level 2',
  critical_usd: 'Critical level', hard_limit_usd: 'Hard limit',
};

function renderAiControls(data) {
  state.controls = data.controls;
  ['free', 'plus'].forEach((plan) => {
    $(`${plan}QuotaFields`).innerHTML = Object.entries(state.controls.quotas[plan]).map(([key, value]) => `<label><span>${escapeHtml(quotaLabels[key] || key)}</span><input type="number" min="0" max="1000000" step="1" data-quota-plan="${plan}" data-quota-key="${escapeHtml(key)}" value="${Number(value)}"></label>`).join('');
  });
  $('budgetFields').innerHTML = Object.entries(budgetLabels).map(([key, label]) => `<label><span>${escapeHtml(label)} (USD)</span><input type="number" min="0" step="0.01" data-budget-key="${escapeHtml(key)}" value="${Number(state.controls.budgets[key] || 0)}"></label>`).join('');
  $('hardStopEnabled').checked = Boolean(state.controls.budgets.hard_stop_enabled);
  $('budgetSpent').textContent = `${usd(data.budget_state?.month_cost_usd)} đã dùng`;
}

async function loadAiControls() {
  try {
    const data = await api('/api/admin/ai-controls');
    renderAiControls(data);
    state.loadedTabs.add('controls');
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
}

async function saveAiControls(event) {
  event.preventDefault();
  const controls = { quotas: { free: {}, plus: {} }, budgets: {} };
  document.querySelectorAll('[data-quota-plan]').forEach((input) => { controls.quotas[input.dataset.quotaPlan][input.dataset.quotaKey] = Number(input.value); });
  document.querySelectorAll('[data-budget-key]').forEach((input) => { controls.budgets[input.dataset.budgetKey] = Number(input.value); });
  controls.budgets.hard_stop_enabled = $('hardStopEnabled').checked;
  try {
    const data = await api('/api/admin/ai-controls', { method: 'PUT', body: JSON.stringify(controls) });
    renderAiControls(data);
    showToast('Đã lưu quota và budget.');
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
}

async function loadIntegrations() {
  try {
    const data = await api('/api/admin/integrations');
    const item = data.integrations || {};
    state.integrations = item;
    const google = item.google || {};
    const providerHealth = item.ai_providers?.provider_health || {};
    const providerMetrics = Object.fromEntries((item.provider_metrics || []).map((metric) => [metric.provider, metric]));
    const cards = [
      ['Gmail', google.gmail_active, `${number(google.expired_tokens)} expired · ${number(google.revoked_access)} revoked`, true],
      ['Google Calendar', google.calendar_active, `${number(google.connected_users)} connected users`, true],
      ...['openai', 'claude'].map((provider) => {
        const metric = providerMetrics[provider] || {};
        return [provider === 'openai' ? 'OpenAI' : 'Claude', providerHealth[provider]?.healthy ? 'Online' : 'Unavailable', `${number(metric.avg_latency_ms)} ms avg · ${number(metric.rate_limit_errors)} rate-limit errors`, Boolean(providerHealth[provider]?.healthy)];
      }),
    ];
    $('integrationCards').innerHTML = cards.map(([label, value, detail, ok]) => `<article class="panel integration-card"><p class="eyebrow">${escapeHtml(label)}</p><h2 class="${ok ? 'good' : 'warn'}">${escapeHtml(value)}</h2><p class="muted">${escapeHtml(detail)}</p></article>`).join('');
    $('integrationErrors').innerHTML = (item.api_errors || []).length ? item.api_errors.map((error) => `<div class="metric-row"><span>${escapeHtml(error.feature)}</span><strong class="bad">${number(error.errors)}</strong></div>`).join('') : '<p class="muted">Không có lỗi tích hợp được ghi nhận.</p>';
    state.loadedTabs.add('integrations');
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
}

async function loadSystemHealth() {
  try {
    const data = await api('/api/admin/system-health');
    const health = data.health || {};
    state.health = health;
    const metrics = health.metrics || {};
    const google = health.integration_status?.google || {};
    const providers = health.ai_providers?.provider_health || {};
    const errorRate = Number(metrics.requests) ? Number(metrics.errors || 0) / Number(metrics.requests) * 100 : 0;
    const cards = [['Frontend', health.frontend_status], ['Backend', health.backend_status], ['Database', health.database_status], ['Gmail API', Number(google.gmail_active) ? 'operational' : 'not connected'], ['Calendar API', Number(google.calendar_active) ? 'operational' : 'not connected'], ['OpenAI', providers.openai?.healthy ? 'operational' : 'unavailable'], ['Claude', providers.claude?.healthy ? 'operational' : 'unavailable'], ['Average API', `${number(metrics.avg_latency_ms)} ms`], ['Uptime', `${Math.floor(Number(health.uptime_seconds || 0) / 60)} min`], ['Error rate', `${errorRate.toFixed(2)}%`]];
    $('healthCards').innerHTML = cards.map(([label, value]) => `<article class="hero-card"><p class="metric-label">${escapeHtml(label)}</p><strong>${escapeHtml(value)}</strong></article>`).join('');
    $('systemLogsBody').innerHTML = (health.events || []).length ? health.events.map((event) => `<tr><td>${escapeHtml(dateTime(event.created_at))}</td><td><code>${escapeHtml(event.request_id || '—')}</code></td><td>${escapeHtml(event.user_id || '—')}</td><td>${escapeHtml(event.feature || event.event_type)}</td><td>${escapeHtml(event.provider || '—')}</td><td>${escapeHtml(event.model || '—')}</td><td><span class="badge ${Number(event.status) >= 500 || event.status === 'error' ? 'failed' : ''}">${escapeHtml(event.status)}</span></td><td>${number(event.latency_ms)} ms</td><td>${escapeHtml(event.error_message || '—')}</td></tr>`).join('') : '<tr><td colspan="9" class="muted">Chưa có log lỗi vận hành.</td></tr>';
    state.loadedTabs.add('health');
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
}

async function loadSecurity() {
  try {
    const data = await api('/api/admin/security');
    const security = data.security || {};
    state.security = security;
    $('securityCounters').innerHTML = (security.event_counts || []).map((item) => `<article class="hero-card"><p class="metric-label">${escapeHtml(item.event_type.replaceAll('_', ' '))}</p><strong>${number(item.value)}</strong><span>30 ngày gần nhất</span></article>`).join('') || '<article class="hero-card"><p class="metric-label">Security events</p><strong>0</strong><span>30 ngày gần nhất</span></article>';
    $('adminAuditBody').innerHTML = (security.admin_audit || []).length ? security.admin_audit.map((event) => `<tr><td>${escapeHtml(dateTime(event.created_at))}</td><td>${escapeHtml(event.admin_user_id || 'system')}</td><td>${escapeHtml(event.action)}</td><td>${escapeHtml([event.target_type, event.target_id].filter(Boolean).join(' · '))}</td><td><code>${escapeHtml(JSON.stringify(event.before_state || {}))}</code><br><code>${escapeHtml(JSON.stringify(event.after_state || {}))}</code></td><td><code>${escapeHtml(event.request_id || '—')}</code></td></tr>`).join('') : '<tr><td colspan="6" class="muted">Chưa có admin activity.</td></tr>';
    $('suspiciousLoginList').innerHTML = (security.suspicious_logins || []).length ? security.suspicious_logins.map((item) => `<div class="metric-row"><span>Client ${escapeHtml(item.client_fingerprint)}<br><small>${escapeHtml(dateTime(item.last_attempt_at))}</small></span><strong class="bad">${number(item.failed_attempts)} failures</strong></div>`).join('') : '<p class="muted">Không phát hiện đăng nhập đáng ngờ.</p>';
    $('suspiciousAiList').innerHTML = (security.suspicious_ai_usage || []).length ? security.suspicious_ai_usage.map((item) => `<div class="metric-row"><span>${escapeHtml(item.user_id || 'anonymous')} · ${number(item.requests)} requests · ${number(item.tokens)} tokens</span><strong class="warn">${escapeHtml(usd(item.cost_usd))}</strong></div>`).join('') : '<p class="muted">Không phát hiện usage bất thường.</p>';
    state.loadedTabs.add('security');
  } catch (error) { if (!handleAdminGate(error)) showToast(error.message, 'error'); }
}

async function loadDashboard() {
  $('refreshButton').disabled = true;
  setConnection('waiting', 'Đang tải');
  try {
    const data = await api('/api/admin/overview');
    $('authPanel').classList.add('hidden');
    $('totpPanel').classList.add('hidden');
    $('dashboard').classList.remove('hidden');
    $('adminLogoutButton').classList.remove('hidden');
    render(data);
    activateTab(state.activeTab, { load: true });
    setConnection('online', 'Admin đã xác thực');
  } catch (error) {
    if (!handleAdminGate(error)) {
      showGate('login', error.message);
      setConnection('offline', 'Không tải được dashboard');
    }
  } finally {
    $('refreshButton').disabled = false;
  }
}

async function loginWithPassword() {
  $('authError').textContent = '';
  const email = $('adminEmailInput').value.trim();
  const password = $('adminPasswordInput').value;
  if (!email || !password) {
    $('authError').textContent = 'Nhập email và mật khẩu.';
    return;
  }
  $('adminLoginButton').disabled = true;
  try {
    await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    $('adminPasswordInput').value = '';
    await loadDashboard();
  } catch (error) {
    $('authError').textContent = error.message;
  } finally {
    $('adminLoginButton').disabled = false;
  }
}

async function verifyTotp() {
  const code = $('totpInput').value.replace(/\D/g, '').slice(0, 6);
  $('totpError').textContent = '';
  if (code.length !== 6) {
    $('totpError').textContent = 'Nhập đủ 6 chữ số.';
    return;
  }
  $('totpVerifyButton').disabled = true;
  try {
    await api('/api/admin/verify-totp', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
    $('totpInput').value = '';
    await loadDashboard();
  } catch (error) {
    $('totpError').textContent = error.message;
    $('totpInput').select();
  } finally {
    $('totpVerifyButton').disabled = false;
  }
}

async function lockDashboard() {
  try {
    await api('/api/admin/logout', { method: 'POST', body: '{}' });
  } finally {
    showGate('totp');
    setConnection('waiting', 'Dashboard đã khóa');
  }
}

function csvCell(value) {
  let text = String(value ?? '');
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function downloadCsv(filename, rows) {
  if (!rows.length) {
    showToast('Chưa có dữ liệu để xuất.', 'warning');
    return;
  }
  const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`;
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast(`Đã xuất ${filename}.`);
}

function exportCurrentData() {
  const stamp = new Date().toISOString().slice(0, 10);
  if (state.activeTab === 'workspaces') {
    const rows = (state.workspaces?.workspaces || []).map((workspace) => [
      workspace.workspace_id,
      workspace.name,
      workspace.owner,
      workspace.access_state,
      workspace.active_seats,
      workspace.seat_capacity,
      workspace.pending_invitations,
      workspace.pending_seat_requests,
      workspace.plan_name || workspace.plan_code,
      workspace.current_period_end,
    ]);
    downloadCsv(`flowmate-workspaces-${stamp}.csv`, [[
      'workspace_id', 'name', 'owner', 'access_state', 'active_seats', 'seat_capacity',
      'pending_invitations', 'pending_seat_requests', 'plan', 'period_end',
    ], ...rows]);
    return;
  }
  if (state.activeTab === 'finance') {
    const currency = $('financeCurrency').value;
    const rows = (state.finance?.recent_payments || [])
      .filter((payment) => payment.currency === currency)
      .map((payment) => [
        payment.id,
        payment.paid_at || payment.created_at,
        payment.customer,
        payment.plan_name,
        payment.status,
        payment.currency,
        payment.gross_amount,
        payment.fee_amount,
        payment.refund_amount,
        payment.net_amount,
      ]);
    downloadCsv(`flowmate-finance-${currency}-${stamp}.csv`, [[
      'payment_id', 'time', 'customer', 'plan', 'status', 'currency',
      'gross_minor', 'fee_minor', 'refund_minor', 'net_minor',
    ], ...rows]);
    return;
  }
  if (state.activeTab === 'users') {
    const rows = state.users.map((user) => [
      user.user_id, user.name, user.email || user.gmail_email, user.plan_name || 'Free',
      user.account_status || 'active', user.created_at, user.last_login_at, user.last_active_at,
      user.gmail_connected, user.calendar_connected, user.ai_usage_month, user.ai_cost_month_usd,
    ]);
    downloadCsv(`flowmate-user-management-${stamp}.csv`, [[
      'user_id', 'name', 'email', 'plan', 'status', 'created_at', 'last_login', 'last_active',
      'gmail_connected', 'calendar_connected', 'ai_usage_month', 'ai_cost_month_usd',
    ], ...rows]);
    return;
  }
  const rows = (state.overview?.recent_users || []).map((user) => [
    user.user_id,
    user.name,
    user.gmail_email || user.email,
    user.gmail_connected ? 'connected' : 'disconnected',
    user.user_mode,
    user.subscription_plan_name || 'Free',
    user.subscription_current_period_end,
    user.updated_at,
  ]);
  downloadCsv(`flowmate-users-${stamp}.csv`, [[
    'user_id', 'name', 'email', 'google_status', 'mode', 'plan', 'period_end', 'updated_at',
  ], ...rows]);
}

function refreshActiveTab() {
  if (state.activeTab === 'finance') return loadFinance();
  if (state.activeTab === 'workspaces') return loadWorkspaces();
  const loaders = {
    users: loadAdminUsers, ai: loadAiUsage, controls: loadAiControls,
    integrations: loadIntegrations, health: loadSystemHealth, security: loadSecurity,
  };
  if (loaders[state.activeTab]) {
    state.loadedTabs.delete(state.activeTab);
    return loaders[state.activeTab]();
  }
  return loadDashboard();
}

function updateRefreshCountdown() {
  if (!state.autoRefresh) {
    $('refreshCountdown').textContent = 'Đã tắt';
    return;
  }
  if (!state.nextRefreshAt) {
    $('refreshCountdown').textContent = `${state.refreshIntervalSeconds} giây`;
    return;
  }
  const seconds = Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000));
  $('refreshCountdown').textContent = `${seconds} giây`;
  if (seconds === 0 && !document.hidden) {
    state.nextRefreshAt = Date.now() + state.refreshIntervalSeconds * 1000;
    refreshActiveTab();
  }
}

$('refreshButton').addEventListener('click', refreshActiveTab);
$('adminLoginButton').addEventListener('click', loginWithPassword);
$('adminPasswordInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') loginWithPassword();
});
$('totpVerifyButton').addEventListener('click', verifyTotp);
$('adminLogoutButton').addEventListener('click', lockDashboard);
$('financeCurrency').addEventListener('change', rerenderFinanceCurrency);
$('exportCurrentButton').addEventListener('click', exportCurrentData);
$('autoRefreshToggle').addEventListener('change', (event) => {
  state.autoRefresh = event.target.checked;
  state.nextRefreshAt = state.autoRefresh
    ? Date.now() + state.refreshIntervalSeconds * 1000
    : null;
  updateRefreshCountdown();
});
['syncJobSearch', 'syncJobStatusFilter'].forEach((id) => {
  $(id).addEventListener(id === 'syncJobSearch' ? 'input' : 'change', () => {
    renderSyncJobs(state.overview?.recent_sync_jobs || []);
  });
});
['userSearch', 'userPlanFilter', 'userConnectionFilter'].forEach((id) => {
  $(id).addEventListener(id === 'userSearch' ? 'input' : 'change', () => {
    renderUsers(state.overview?.recent_users || []);
  });
});
['workspaceSearch', 'workspaceStateFilter'].forEach((id) => {
  $(id).addEventListener(id === 'workspaceSearch' ? 'input' : 'change', () => renderWorkspaces());
});
['adminUserSearch', 'adminUserPlanFilter', 'adminUserStatusFilter'].forEach((id) => {
  $(id).addEventListener(id === 'adminUserSearch' ? 'input' : 'change', renderAdminUsers);
});
$('adminUsersBody').addEventListener('click', (event) => {
  const detail = event.target.closest('[data-user-detail]')?.dataset.userDetail;
  const statusButton = event.target.closest('[data-user-status]');
  const resetQuota = event.target.closest('[data-reset-quota]')?.dataset.resetQuota;
  const reset = event.target.closest('[data-reset-usage]')?.dataset.resetUsage;
  const upgrade = event.target.closest('[data-admin-upgrade-plan]')?.dataset.adminUpgradePlan;
  const downgrade = event.target.closest('[data-admin-revoke-plan]')?.dataset.adminRevokePlan;
  if (detail) showUserDetail(detail);
  if (statusButton) updateUserStatus(statusButton.dataset.userId, statusButton.dataset.userStatus);
  if (resetQuota) resetUserUsage(resetQuota, 'today');
  if (reset) resetUserUsage(reset, 'all');
  if (upgrade) grantPremium(upgrade, 'purchase').then(() => { state.loadedTabs.delete('users'); loadAdminUsers(); });
  if (downgrade) revokePremium(downgrade).then(() => { state.loadedTabs.delete('users'); loadAdminUsers(); });
});
$('closeUserDetail').addEventListener('click', () => $('userDetailDialog').close());
$('userDetailDialog').addEventListener('click', (event) => {
  if (event.target === $('userDetailDialog')) $('userDetailDialog').close();
});
$('aiUsageDays').addEventListener('change', () => {
  state.loadedTabs.delete('ai');
  loadAiUsage();
});
$('aiControlsForm').addEventListener('submit', saveAiControls);
$('workspacesBody').addEventListener('click', (event) => {
  const grantId = event.target.closest('[data-grant-business]')?.dataset.grantBusiness;
  const renewId = event.target.closest('[data-renew-business]')?.dataset.renewBusiness;
  const revokeId = event.target.closest('[data-revoke-business]')?.dataset.revokeBusiness;
  const auditButton = event.target.closest('[data-view-audit]');
  if (grantId) grantBusinessSubscription(grantId, 'purchase');
  if (renewId) grantBusinessSubscription(renewId, 'renew');
  if (revokeId) revokeBusinessSubscription(revokeId);
  if (auditButton) openWorkspaceAudit(auditButton.dataset.viewAudit, auditButton.dataset.viewAuditName);
});
$('closeWorkspaceAuditButton').addEventListener('click', closeWorkspaceAudit);
$('auditEventTypeFilter').addEventListener('change', () => loadWorkspaceAudit({ reset: true }));
$('loadMoreAuditButton').addEventListener('click', () => loadWorkspaceAudit({ reset: false }));
$('totpInput').addEventListener('input', (event) => {
  event.target.value = event.target.value.replace(/\D/g, '').slice(0, 6);
});
$('totpInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') verifyTotp();
});
document.querySelectorAll('[data-dashboard-tab]').forEach((tab) => {
  tab.addEventListener('click', () => activateTab(tab.dataset.dashboardTab));
  tab.addEventListener('keydown', (event) => {
    const tabs = Array.from(document.querySelectorAll('[data-dashboard-tab]'));
    const index = tabs.indexOf(tab);
    let nextIndex = index;
    if (event.key === 'ArrowDown') nextIndex = (index + 1) % tabs.length;
    else if (event.key === 'ArrowUp') nextIndex = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = tabs.length - 1;
    else return;
    event.preventDefault();
    activateTab(tabs[nextIndex].dataset.dashboardTab, { focus: true });
  });
});

$('sidebarCollapseButton').addEventListener('click', () => {
  setSidebarCollapsed(!$('dashboard').classList.contains('sidebar-collapsed'));
});
$('sidebarOpenButton').addEventListener('click', openMobileSidebar);
$('sidebarScrim').addEventListener('click', closeMobileSidebar);
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && $('sidebar').classList.contains('open')) closeMobileSidebar();
});

let sidebarCollapsedPref = '0';
try {
  sidebarCollapsedPref = localStorage.getItem('admin_sidebar_collapsed') || '0';
} catch (_) {}
setSidebarCollapsed(sidebarCollapsedPref === '1');

loadDashboard();
state.timer = setInterval(updateRefreshCountdown, 1000);
