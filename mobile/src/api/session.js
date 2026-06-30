import * as SecureStore from 'expo-secure-store';

const USER_ID_KEY = 'flowmate.mobileUserId';
const ACCESS_TOKEN_KEY = 'flowmate.mobileAccessToken';

let mobileUserId = '';
let mobileAccessToken = '';

// api/client.js reads these synchronously on every request, so we keep an
// in-memory cache fed from SecureStore at startup (see loadPersistedSession)
// instead of making every request await disk/keychain access.
export function setMobileUserId(value) {
  mobileUserId = (value || '').trim();
  SecureStore.setItemAsync(USER_ID_KEY, mobileUserId).catch(() => {});
}

export function getMobileUserId() {
  return mobileUserId;
}

export function setMobileAccessToken(value) {
  mobileAccessToken = (value || '').trim();
  if (mobileAccessToken) {
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, mobileAccessToken).catch(() => {});
  } else {
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY).catch(() => {});
  }
}

export function getMobileAccessToken() {
  return mobileAccessToken;
}

export function setMobileSession({ userId, accessToken } = {}) {
  if (userId !== undefined) setMobileUserId(userId);
  if (accessToken !== undefined) setMobileAccessToken(accessToken);
}

// Call once at app startup, before the first API request, so a previously
// signed-in user doesn't get logged out just from closing the app.
export async function loadPersistedSession() {
  try {
    const [storedUserId, storedToken] = await Promise.all([
      SecureStore.getItemAsync(USER_ID_KEY),
      SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    ]);
    mobileUserId = storedUserId || '';
    mobileAccessToken = storedToken || '';
  } catch {
    // Corrupted keychain entry or unsupported platform: fall back to a
    // logged-out state instead of crashing app startup.
    mobileUserId = '';
    mobileAccessToken = '';
  }
  return { userId: mobileUserId, accessToken: mobileAccessToken };
}

export async function clearPersistedSession() {
  mobileUserId = '';
  mobileAccessToken = '';
  await Promise.all([
    SecureStore.deleteItemAsync(USER_ID_KEY).catch(() => {}),
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY).catch(() => {}),
  ]);
}
