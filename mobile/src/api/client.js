import { API_BASE } from './config';
import { getMobileUserId } from './session';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(getMobileUserId() ? { 'X-User-Id': getMobileUserId() } : {}),
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
