import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import * as Crypto from 'expo-crypto';
import { apiGet, apiPost } from './client';
import { setMobileSession } from './session';

function bytesToHex(bytes) {
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
}

function base64ToBase64Url(base64) {
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// RFC 7636 PKCE, generated app-side and applied to the backend->app deep-link
// handoff below -- distinct from (and in addition to) the PKCE
// google-auth-oauthlib already does server-side for its own exchange with
// Google. A custom URL scheme like flowmateai:// isn't domain-verified, so
// another app registering the same scheme could in principle intercept the
// oauth2callback redirect; this verifier never leaves this function except
// as a POST body over HTTPS when redeeming the exchange_code, so an
// interceptor holding only the deep link's URL can't complete the exchange.
async function generatePkcePair() {
  const randomBytes = await Crypto.getRandomBytesAsync(32);
  const codeVerifier = bytesToHex(randomBytes);
  const digest = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    codeVerifier,
    { encoding: Crypto.CryptoEncoding.BASE64 }
  );
  return { codeVerifier, codeChallenge: base64ToBase64Url(digest) };
}

// Runs Google's OAuth consent flow and stores the resulting mobile session.
// Shared by every "Connect Gmail" entry point (Settings, Overview, Schedule,
// Email) plus the Login screen's recovery link, so the deep-link handling
// only lives in one place.
//
// intent: 'link' (default) attaches a Gmail account to the CURRENTLY
// logged-in user -- Google can no longer sign anyone in on its own. 'recover'
// is the one exception: an existing account that only ever used Google (no
// password set yet) regains access, then must set one -- see needsPassword
// on the returned object. There is no more implicit "login" behavior.
//
// openAuthSessionAsync (NOT openBrowserAsync) is required: the app's own
// fetch() never shares cookies with the system browser tab that completes
// Google's consent screen, so the backend can't hand the session back via a
// cookie. Instead it 302-redirects to our `flowmateai://oauth-callback?...`
// deep link once the OAuth exchange finishes server-side, and
// openAuthSessionAsync is the API that actually captures that redirect.
export async function connectGoogleAccount(intent = 'link') {
  const { codeVerifier, codeChallenge } = await generatePkcePair();
  const data = await apiGet(
    `/email/auth_url?intent=${intent}&platform=mobile&code_challenge=${encodeURIComponent(codeChallenge)}`
  );
  if (data.access_token || data.user_id) {
    setMobileSession({ userId: data.user_id || data.email, accessToken: data.access_token || '' });
    return { connected: true, needsPassword: !!data.needs_password };
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

  if (queryParams?.exchange_code) {
    // The deep link carried only a one-time code, not the real token --
    // redeem it by proving we hold the matching verifier.
    const exchanged = await apiPost('/email/oauth-token-exchange', {
      exchange_code: queryParams.exchange_code,
      code_verifier: codeVerifier,
    });
    if (!exchanged?.access_token) {
      throw new Error('Không đổi được mã xác thực lấy access token.');
    }
    setMobileSession({ userId: exchanged.user_id, accessToken: exchanged.access_token });
    return { connected: true, needsPassword: !!exchanged.needs_password };
  }

  // Legacy fallback, kept for a backend deploy that predates the
  // exchange-code flow: the token arrives directly in the deep link.
  if (!queryParams?.access_token) {
    throw new Error('Không nhận được access token từ máy chủ.');
  }
  setMobileSession({ userId: queryParams.user_id, accessToken: queryParams.access_token });
  return { connected: true, needsPassword: queryParams.needs_password === '1' };
}
