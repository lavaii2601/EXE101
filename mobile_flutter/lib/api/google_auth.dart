import 'dart:async';
import 'package:app_links/app_links.dart';
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

/// Persist a Google OAuth callback whether it arrived in the running app or
/// cold-started Android after the OS reclaimed the process in the browser.
Future<bool> consumeGoogleAuthCallback(Uri uri) async {
  if (!isGoogleAuthCallback(uri)) return false;
  final accessToken = uri.queryParameters['access_token'];
  if (accessToken == null || accessToken.isEmpty) return false;
  await setMobileSession(
    userId: uri.queryParameters['user_id'] ?? '',
    accessToken: accessToken,
  );
  return true;
}

/// Mirrors mobile/src/api/googleAuth.js: the app's own http client never
/// shares cookies with the system browser tab that completes Google's
/// consent screen, so the backend hands the result back via a
/// `flowmateai://oauth-callback?access_token=...` deep link instead (see
/// web/backend/routes/email.py oauth2callback). We open that URL in an
/// external browser and wait for the redirect on the same app_links stream
/// registered in main.dart.
Future<GoogleAuthResult> connectGoogleAccount(AppLinks appLinks) async {
  final data = await apiGet('/email/auth_url?platform=mobile');
  if (data is Map &&
      ((data['access_token'] as String?)?.isNotEmpty == true ||
          data['user_id'] != null)) {
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
