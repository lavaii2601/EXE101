import { apiPost } from './client';
import { setMobileSession } from './session';

// Password-based account creation/sign-in, alongside the existing Google
// OAuth flow in googleAuth.js. Mirrors its shape (store the session, resolve
// once connected) so LoginScreen can treat both paths the same way.

export async function registerWithEmail({ name, email, password }) {
  const data = await apiPost('/auth/register', { name, email, password });
  setMobileSession({ userId: data.user_id, accessToken: data.access_token });
  return data;
}

export async function loginWithEmail({ email, password }) {
  const data = await apiPost('/auth/login', { email, password });
  setMobileSession({ userId: data.user_id, accessToken: data.access_token });
  return data;
}

// First-time password setup for an account recovered via Google (see
// googleAuth.js's connectGoogleAccount('recover')) that never had one.
// Requires the session connectGoogleAccount already established.
export async function setPassword(password) {
  return apiPost('/auth/set-password', { password });
}

// Revokes every mobile access token issued for this account (bumps
// token_version server-side) plus the browser session -- for a user who
// suspects a device was lost/stolen. Includes the very token used to call
// it, so the caller must also log this device out locally right after.
export async function logoutAllDevices() {
  return apiPost('/auth/logout-all-devices');
}
