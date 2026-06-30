import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import { apiGet } from './client';
import { setMobileSession } from './session';

// Runs Google's OAuth consent flow and stores the resulting mobile session.
// Shared by LoginScreen (initial sign-in) and EmailScreen (reconnect Gmail
// from Settings) so the deep-link handling only lives in one place.
//
// openAuthSessionAsync (NOT openBrowserAsync) is required: the app's own
// fetch() never shares cookies with the system browser tab that completes
// Google's consent screen, so the backend can't hand the session back via a
// cookie. Instead it 302-redirects to our `flowmateai://oauth-callback?
// access_token=...` deep link once the OAuth exchange finishes server-side,
// and openAuthSessionAsync is the API that actually captures that redirect.
export async function connectGoogleAccount() {
  const data = await apiGet('/email/auth_url?platform=mobile');
  if (data.access_token || data.user_id) {
    setMobileSession({ userId: data.user_id || data.email, accessToken: data.access_token || '' });
    return { connected: true };
  }
  if (!data.auth_url) {
    throw new Error('Server không trả về đường dẫn đăng nhập Google.');
  }

  const redirectUrl = Linking.createURL('oauth-callback');
  const result = await WebBrowser.openAuthSessionAsync(data.auth_url, redirectUrl);
  if (result.type !== 'success' || !result.url) {
    return { connected: false, cancelled: true };
  }
  const { queryParams } = Linking.parse(result.url);
  if (!queryParams?.access_token) {
    throw new Error('Không nhận được access token từ máy chủ.');
  }
  setMobileSession({ userId: queryParams.user_id, accessToken: queryParams.access_token });
  return { connected: true };
}
