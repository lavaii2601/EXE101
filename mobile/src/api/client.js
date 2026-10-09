import { Alert } from 'react-native';
import { API_BASE } from './config';
import { clearPersistedSession, getCurrentWorkspaceId, getMobileAccessToken } from './session';

let authAlertActive = false;
let lastAuthAlertAt = 0;
const AUTH_ALERT_COOLDOWN_MS = 60000;

// Set by App.js so this non-component module can drive isAuthenticated back
// to false (and reset the rest of the app shell's state) the same way a
// manual "Đăng xuất" tap does, without client.js importing App.js itself.
let sessionRevokedHandler = null;
export function setSessionRevokedHandler(handler) {
  sessionRevokedHandler = handler;
}

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
  if (!googleOnly) {
    // Unlike a Google-scope reconnect, this token can never work again
    // (expired past its 30-day signature, or explicitly revoked via "log
    // out all devices" from another device) -- clear it now instead of
    // leaving a dead token in SecureStore that keeps tripping this same 401
    // on every background poll (new-mail-check, workspace sync, ...) for
    // up to 30 more days with no way for the user to get back to a clean
    // login screen.
    clearPersistedSession().catch(() => {});
    if (sessionRevokedHandler) sessionRevokedHandler();
  }
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
  const workspaceId = getCurrentWorkspaceId();
  // A FormData body (email attachment uploads) must NOT get a hardcoded
  // 'application/json' Content-Type -- RN's fetch needs to set its own
  // multipart/form-data boundary header instead.
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      // No X-User-Id here: this app always authenticates with a real Bearer
      // token, so the header would be redundant identity at best and, if
      // MOBILE_USER_HEADER_ENABLED were ever accidentally left on in some
      // environment, an unauthenticated impersonation path at worst. It's
      // still meant to exist as a dev-only escape hatch (see utils/security.py),
      // just not one this production client should be the one sending.
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
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

// For multipart/form-data uploads (email attachments) -- formData is sent
// as-is, see request()'s isFormData branch for why no Content-Type is set.
export function apiPostForm(path, formData) {
  return request(path, {
    method: 'POST',
    body: formData
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
