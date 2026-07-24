const state = { timer: null };

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
  $('adminLogoutButton').classList.add('hidden');
  if (name === 'google') $('authError').textContent = message;
  if (name === 'totp') {
    $('totpError').textContent = message;
    setTimeout(() => $('totpInput').focus(), 0);
  }
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
    setConnection('online', 'Admin đã xác thực');
  } catch (error) {
    const code = error.data?.error;
    if (code === 'admin_totp_required') {
      showGate('totp');
      setConnection('waiting', 'Chờ mã TOTP');
    } else {
      showGate('google', error.message);
      setConnection('offline', code === 'admin_not_configured' ? 'Admin đang khóa' : 'Cần đăng nhập');
    }
  } finally {
    $('refreshButton').disabled = false;
  }
}

async function loginWithGoogle() {
  $('authError').textContent = '';
  try {
    const response = await fetch('/api/email/auth_url?next=/admin', { credentials: 'include' });
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

$('refreshButton').addEventListener('click', loadDashboard);
$('googleLoginButton').addEventListener('click', loginWithGoogle);
$('totpVerifyButton').addEventListener('click', verifyTotp);
$('adminLogoutButton').addEventListener('click', lockDashboard);
$('totpInput').addEventListener('input', (event) => {
  event.target.value = event.target.value.replace(/\D/g, '').slice(0, 6);
});
$('totpInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') verifyTotp();
});

loadDashboard();
state.timer = setInterval(loadDashboard, 30000);
