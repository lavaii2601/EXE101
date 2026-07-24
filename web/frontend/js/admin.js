const state = {
  timer: null,
  activeTab: 'overview',
  finance: null,
  financeLoaded: false,
  financeLoading: false,
  financeGeneratedAt: null,
};

const $ = (id) => document.getElementById(id);
const number = (value) => new Intl.NumberFormat('vi-VN').format(Number(value || 0));
const dateTime = (value) => value
  ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value))
  : '—';
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
const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

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
  $('authPanel').classList.toggle('hidden', name !== 'google');
  $('totpPanel').classList.toggle('hidden', name !== 'totp');
  $('accessDeniedPanel').classList.toggle('hidden', name !== 'denied');
  $('adminLogoutButton').classList.add('hidden');
  if (name === 'google') $('authError').textContent = message;
  if (name === 'totp') {
    $('totpError').textContent = message;
    setTimeout(() => $('totpInput').focus(), 0);
  }
}

function activateTab(name, { focus = false, load = true } = {}) {
  const next = name === 'finance' ? 'finance' : 'overview';
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
    showGate('google', error.message);
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
  $('syncJobsBody').innerHTML = items.length ? items.map((job) => (
    `<tr>
      <td>${escapeHtml(dateTime(job.created_at))}</td>
      <td>${escapeHtml(job.user_id)}</td>
      <td>${escapeHtml(job.job_type)}</td>
      <td><span class="badge ${escapeHtml(job.status)}">${escapeHtml(job.status)}</span></td>
      <td>${escapeHtml(job.error_message || (job.finished_at ? `Hoàn tất ${dateTime(job.finished_at)}` : 'Đang xử lý'))}</td>
    </tr>`
  )).join('') : '<tr><td colspan="5" class="muted">Chưa có tác vụ đồng bộ.</td></tr>';
}

function renderUsers(items) {
  $('usersBody').innerHTML = items.length ? items.map((user) => (
    `<tr>
      <td><strong>${escapeHtml(user.name || user.user_id)}</strong><br><span class="muted">${escapeHtml(user.gmail_email || user.email || user.user_id)}</span></td>
      <td><span class="badge ${user.gmail_connected ? 'success' : 'failed'}">${user.gmail_connected ? 'Đã kết nối' : 'Chưa kết nối'}</span></td>
      <td>${escapeHtml(user.user_mode || 'Chưa chọn')}</td>
      <td>${escapeHtml(dateTime(user.updated_at))}</td>
    </tr>`
  )).join('') : '<tr><td colspan="4" class="muted">Chưa có người dùng.</td></tr>';
}

function renderAlerts(summary) {
  const alerts = [];
  if (Number(summary.oauth_access_expired)) alerts.push(['warning', `${number(summary.oauth_access_expired)} access token Google đã hết hạn; refresh token sẽ được thử khi người dùng đồng bộ.`]);
  if (Number(summary.oauth_missing_scopes)) alerts.push(['danger', `${number(summary.oauth_missing_scopes)} tài khoản thiếu scope Gmail hoặc Calendar và cần kết nối lại.`]);
  if (Number(summary.sync_failures_24h)) alerts.push(['danger', `${number(summary.sync_failures_24h)} tác vụ đồng bộ thất bại trong 24 giờ qua.`]);
  $('alerts').innerHTML = alerts.map(([tone, text]) => `<div class="alert ${tone === 'danger' ? 'danger' : ''}">${escapeHtml(text)}</div>`).join('');
}

function render(data) {
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

  renderAlerts(summary);
  renderMetricList(summary);
  renderActivity(data.activity_14d || []);
  renderBars('modeBars', data.users_by_mode || []);
  renderBars('tableSizes', data.table_sizes || [], bytes);
  renderSyncJobs(data.recent_sync_jobs || []);
  renderUsers(data.recent_users || []);
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

function renderFinanceMetrics(summary, currency) {
  const metrics = [
    ['Phí cổng thanh toán', money(summary.fees_month, currency), Number(summary.fees_month) ? 'warn' : ''],
    ['Hoàn tiền trong tháng', money(summary.refunds_month, currency), Number(summary.refunds_month) ? 'warn' : ''],
    ['Đang dùng thử', number(summary.trialing_subscriptions), ''],
    ['Quá hạn thanh toán', number(summary.past_due_subscriptions), Number(summary.past_due_subscriptions) ? 'bad' : ''],
    ['Subscription mới', number(summary.new_subscriptions_month), ''],
    ['Subscription hủy', number(summary.canceled_subscriptions_month), Number(summary.canceled_subscriptions_month) ? 'warn' : ''],
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
  $('recentSubscriptionsBody').innerHTML = items.length ? items.map((subscription) => (
    `<tr>
      <td><strong>${escapeHtml(subscription.customer)}</strong><br><span class="muted">${escapeHtml(subscription.provider)}</span></td>
      <td>${escapeHtml(subscription.plan_name || subscription.plan_code)}</td>
      <td>${subscription.billing_interval === 'yearly' ? 'Hằng năm' : 'Hằng tháng'}</td>
      <td>${escapeHtml(money(subscription.unit_amount, currency))}</td>
      <td>${escapeHtml(dateTime(subscription.current_period_end))}${subscription.cancel_at_period_end ? '<br><span class="muted">Sẽ hủy cuối kỳ</span>' : ''}</td>
      <td><span class="badge ${escapeHtml(subscription.status)}">${escapeHtml(statusLabel(subscription.status))}</span></td>
    </tr>`
  )).join('') : '<tr><td colspan="6" class="muted">Chưa có subscription cho đơn vị tiền này.</td></tr>';
}

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
  renderFinanceMetrics(summary, currency);
  renderSubscriptionPlans(finance, currency);
  renderRecentPayments(finance, currency);
  renderRecentSubscriptions(finance, currency);
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
      showGate('google', error.message);
      setConnection('offline', 'Không tải được dashboard');
    }
  } finally {
    $('refreshButton').disabled = false;
  }
}

async function loginWithGoogle() {
  $('authError').textContent = '';
  try {
    const response = await fetch('/api/email/auth_url?next=/admin/login', { credentials: 'include' });
    const data = await response.json();
    if (!response.ok || !data.auth_url) throw new Error(data.error || 'Không tạo được liên kết Google OAuth.');
    window.location.assign(data.auth_url);
  } catch (error) {
    $('authError').textContent = error.message;
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

function refreshActiveTab() {
  return state.activeTab === 'finance' ? loadFinance() : loadDashboard();
}

$('refreshButton').addEventListener('click', refreshActiveTab);
$('googleLoginButton').addEventListener('click', loginWithGoogle);
$('totpVerifyButton').addEventListener('click', verifyTotp);
$('adminLogoutButton').addEventListener('click', lockDashboard);
$('financeCurrency').addEventListener('change', rerenderFinanceCurrency);
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
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = tabs.length - 1;
    else return;
    event.preventDefault();
    activateTab(tabs[nextIndex].dataset.dashboardTab, { focus: true });
  });
});

loadDashboard();
state.timer = setInterval(() => {
  if (!document.hidden) refreshActiveTab();
}, 30000);
