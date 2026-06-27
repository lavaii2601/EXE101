let mobileUserId = '';
let mobileAccessToken = '';

export function setMobileUserId(value) {
  mobileUserId = (value || '').trim();
}

export function getMobileUserId() {
  return mobileUserId;
}

export function setMobileAccessToken(value) {
  mobileAccessToken = (value || '').trim();
}

export function getMobileAccessToken() {
  return mobileAccessToken;
}

export function setMobileSession({ userId, accessToken } = {}) {
  if (userId !== undefined) setMobileUserId(userId);
  if (accessToken !== undefined) setMobileAccessToken(accessToken);
}
