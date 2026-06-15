let mobileUserId = '';

export function setMobileUserId(value) {
  mobileUserId = (value || '').trim();
}

export function getMobileUserId() {
  return mobileUserId;
}
