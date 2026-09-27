import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:app_links/app_links.dart';
import 'package:crypto/crypto.dart';
import 'package:url_launcher/url_launcher.dart';
import 'client.dart';
import 'session.dart';

class GoogleAuthResult {
  final bool connected;
  final bool cancelled;
  const GoogleAuthResult({required this.connected, this.cancelled = false});
}

bool isGoogleAuthCallback(Uri uri) =>
    uri.scheme == 'flowmateai' && uri.host == 'oauth-callback';

String _bytesToHex(List<int> bytes) =>
    bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

String _base64ToBase64Url(String value) =>
    value.replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');

/// RFC 7636 PKCE, generated app-side and applied to the backend->app
/// deep-link handoff (distinct from, and in addition to, the PKCE
/// google-auth-oauthlib already does server-side for its own exchange with
/// Google). A custom URL scheme like flowmateai:// isn't domain-verified, so
/// another app registering the same scheme could in principle intercept the
/// oauth2callback redirect; this verifier never leaves the device except as
/// a POST body over HTTPS when redeeming the exchange_code, so an
/// interceptor holding only the deep link's URL can't complete the exchange.
({String codeVerifier, String codeChallenge}) _generatePkcePair() {
  final randomBytes = List<int>.generate(32, (_) => Random.secure().nextInt(256));
  final codeVerifier = _bytesToHex(randomBytes);
  final digest = sha256.convert(utf8.encode(codeVerifier));
  final codeChallenge = _base64ToBase64Url(base64.encode(digest.bytes));
  return (codeVerifier: codeVerifier, codeChallenge: codeChallenge);
}

/// Persist a Google OAuth callback whether it arrived in the running app or
/// cold-started Android after the OS reclaimed the process in the browser
/// (see the pending-verifier comment in session.dart for why that matters
/// here specifically).
Future<bool> consumeGoogleAuthCallback(Uri uri) async {
  if (!isGoogleAuthCallback(uri)) return false;

  final exchangeCode = uri.queryParameters['exchange_code'];
  if (exchangeCode != null && exchangeCode.isNotEmpty) {
    final codeVerifier = await getPendingOauthCodeVerifier();
    await clearPendingOauthCodeVerifier();
    if (codeVerifier == null || codeVerifier.isEmpty) return false;
    try {
      final data = await apiPost('/email/oauth-token-exchange', {
        'exchange_code': exchangeCode,
        'code_verifier': codeVerifier,
      });
      final accessToken = (data is Map ? data['access_token'] as String? : null) ?? '';
      if (accessToken.isEmpty) return false;
      await setMobileSession(
        userId: (data['user_id'] ?? data['email'] ?? '').toString(),
        accessToken: accessToken,
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  // Legacy fallback, kept for a backend deploy that predates the
  // exchange-code flow: the token arrives directly in the deep link.
  final accessToken = uri.queryParameters['access_token'];
  if (accessToken == null || accessToken.isEmpty) return false;
  await clearPendingOauthCodeVerifier();
  await setMobileSession(
    userId: uri.queryParameters['user_id'] ?? '',
    accessToken: accessToken,
  );
  return true;
}

/// Mirrors mobile/src/api/googleAuth.js: the app's own http client never
/// shares cookies with the system browser tab that completes Google's
/// consent screen, so the backend hands the result back via a
/// `flowmateai://oauth-callback?...` deep link instead (see
/// routes/email/oauth.py's oauth2callback). We open that URL in an external
/// browser and wait for the redirect on the same app_links stream
/// registered in main.dart.
Future<GoogleAuthResult> connectGoogleAccount(AppLinks appLinks) async {
  final pkce = _generatePkcePair();
  // Written before launching the browser, not after getting a result back --
  // an external browser (unlike RN's in-app auth session) can get this
  // process killed by the OS while the user is still in it.
  await setPendingOauthCodeVerifier(pkce.codeVerifier);

  final data = await apiGet(
    '/email/auth_url?platform=mobile&code_challenge=${Uri.encodeComponent(pkce.codeChallenge)}',
  );
  if (data is Map &&
      ((data['access_token'] as String?)?.isNotEmpty == true ||
          data['user_id'] != null)) {
    await clearPendingOauthCodeVerifier();
    await setMobileSession(
        userId: (data['user_id'] ?? data['email'] ?? '').toString(),
        accessToken: (data['access_token'] ?? '').toString());
    return const GoogleAuthResult(connected: true);
  }
  final authUrl = data is Map ? data['auth_url'] as String? : null;
  if (authUrl == null || authUrl.isEmpty) {
    throw Exception('Server không trả về đường dẫn đăng nhập Google.');
  }

  final completer = Completer<Uri?>();
  late final StreamSubscription<Uri> sub;
  sub = appLinks.uriLinkStream.listen((uri) {
    if (isGoogleAuthCallback(uri)) {
      if (!completer.isCompleted) completer.complete(uri);
    }
  });

  final launched =
      await launchUrl(Uri.parse(authUrl), mode: LaunchMode.externalApplication);
  if (!launched) {
    await sub.cancel();
    throw Exception('Không thể mở trình duyệt để đăng nhập Google.');
  }

  final resultUri = await completer.future.timeout(
    const Duration(minutes: 5),
    onTimeout: () => null,
  );
  await sub.cancel();

  if (resultUri == null) {
    return const GoogleAuthResult(connected: false, cancelled: true);
  }
  if (!await consumeGoogleAuthCallback(resultUri)) {
    throw Exception('Không nhận được access token từ máy chủ.');
  }
  return const GoogleAuthResult(connected: true);
}
