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
