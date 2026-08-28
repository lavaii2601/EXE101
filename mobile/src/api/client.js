import { Alert } from 'react-native';
import { API_BASE } from './config';
import { getCurrentWorkspaceId, getMobileAccessToken, getMobileUserId } from './session';

let authAlertActive = false;
let lastAuthAlertAt = 0;
const AUTH_ALERT_COOLDOWN_MS = 60000;

// A 401 with no token at all just means "never signed in yet" -- normal for
// a fresh install, not worth interrupting the user. A 401 while a token IS
// present means it expired or access was revoked -- that's the case worth a
// popup, since login/reconnect now lives only in Settings (no per-screen
// login UI to surface this inline anymore). Cooldown avoids re-popping the
// same alert every few seconds from background polls (e.g. new-mail-check)
// while the user hasn't gotten around to reconnecting yet.
function handleUnauthorized(data = {}) {
    if (!getMobileAccessToken()) return;
  const now = Date.now();
  if (authAlertActive || now - lastAuthAlertAt < AUTH_ALERT_COOLDOWN_MS) return;
  authAlertActive = true;
  lastAuthAlertAt = now;
  const googleOnly = data?.auth_scope === 'google';
  Alert.alert(
    googleOnly ? 'Cần kết nối lại Google' : 'Cần đăng nhập lại',
    googleOnly
      ? 'FlowMate vẫn đang đăng nhập, nhưng quyền Gmail/Calendar cần được cấp lại trong tab Cài đặt.'
      : 'Phiên FlowMate trên thiết bị đã hết hạn. Vui lòng đăng nhập lại để tiếp tục đồng bộ.',
    [{ text: 'Đã hiểu', onPress: () => { authAlertActive = false; } }]
  );
}

async function request(path, options = {}) {
  const accessToken = getMobileAccessToken();
  const mobileUserId = getMobileUserId();
  const workspaceId = getCurrentWorkspaceId();
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(mobileUserId ? { 'X-User-Id': mobileUserId } : {}),
      ...(workspaceId ? { 'X-Workspace-Id': workspaceId } : {}),
      ...(options.headers || {})
    }
  });

  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }

  if (!response.ok) {
    if (response.status === 401) handleUnauthorized(data);
    const message = data.error || data.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export function apiGet(path) {
  return request(path);
}

export function apiPost(path, body = {}) {
  return request(path, {
    method: 'POST',
    body: JSON.stringify(body)
  });
}

export function apiPut(path, body = {}) {
  return request(path, {
    method: 'PUT',
    body: JSON.stringify(body)
  });
}

export function apiPatch(path, body = {}) {
  return request(path, {
    method: 'PATCH',
    body: JSON.stringify(body)
  });
}

export function apiDelete(path) {
  return request(path, {
    method: 'DELETE'
  });
}
