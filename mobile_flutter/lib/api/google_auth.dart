import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:app_links/app_links.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/app_button.dart';
import 'client.dart';
import 'session.dart';

class GoogleAuthResult {
  final bool connected;
  final bool cancelled;
  final bool needsPassword;
  const GoogleAuthResult({
    required this.connected,
    this.cancelled = false,
    this.needsPassword = false,
  });
}

/// Thrown when oauth2callback redirects back with an error code (see
/// _oauth_error_redirect) instead of a token. `code` lets callers offer a
/// "Thử tài khoản khác" retry specifically for
/// google_account_already_linked_elsewhere -- see showGoogleAuthErrorDialog.
class GoogleAuthError implements Exception {
  final String code;
  final String message;
  const GoogleAuthError(this.code, this.message);
  @override
  String toString() => message;
}

bool isGoogleAuthCallback(Uri uri) =>
    uri.scheme == 'flowmateai' && uri.host == 'oauth-callback';

String _bytesToHex(List<int> bytes) =>
    bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

String _base64ToBase64Url(String value) =>
    value.replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');

// Keep in sync with web/frontend/js/auth.js's GMAIL_AUTH_ERROR_MESSAGES and
// routes/email/oauth.py's _oauth_error_redirect error codes.
const Map<String, String> _kGmailAuthErrorMessages = {
  'google_account_already_linked_elsewhere':
      'Tài khoản Google này đã được liên kết với một tài khoản FlowMate khác. Hãy đăng xuất khỏi tài khoản đó trên Google hoặc dùng một tài khoản Google khác.',
  'no_flowmate_account_for_google_identity':
      'Không tìm thấy tài khoản FlowMate nào từng liên kết với tài khoản Google này.',
  'token_fetch_failed': 'Không thể hoàn tất xác thực với Google. Vui lòng thử lại.',
  'invalid_oauth_state': 'Phiên liên kết Google đã hết hạn hoặc đã được dùng. Vui lòng thử lại.',
  'flow_not_initialized': 'Không tìm thấy phiên liên kết Google. Vui lòng thử lại.',
  'oauth_flow_unavailable': 'Google OAuth hiện chưa khả dụng. Vui lòng thử lại sau.',
  'callback_error': 'Có lỗi xảy ra khi liên kết tài khoản Google. Vui lòng thử lại.',
};

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
Future<({bool success, bool needsPassword})> consumeGoogleAuthCallback(Uri uri) async {
  const failure = (success: false, needsPassword: false);
  if (!isGoogleAuthCallback(uri)) return failure;

  final exchangeCode = uri.queryParameters['exchange_code'];
  if (exchangeCode != null && exchangeCode.isNotEmpty) {
    final codeVerifier = await getPendingOauthCodeVerifier();
    await clearPendingOauthCodeVerifier();
    if (codeVerifier == null || codeVerifier.isEmpty) return failure;
    try {
      final data = await apiPost('/email/oauth-token-exchange', {
        'exchange_code': exchangeCode,
        'code_verifier': codeVerifier,
      });
      final accessToken = (data is Map ? data['access_token'] as String? : null) ?? '';
      if (accessToken.isEmpty) return failure;
      await setMobileSession(
        userId: (data['user_id'] ?? data['email'] ?? '').toString(),
        accessToken: accessToken,
      );
      return (success: true, needsPassword: data['needs_password'] == true);
    } catch (_) {
      return failure;
    }
  }

  // Legacy fallback, kept for a backend deploy that predates the
  // exchange-code flow: the token arrives directly in the deep link.
  final accessToken = uri.queryParameters['access_token'];
  if (accessToken == null || accessToken.isEmpty) return failure;
  await clearPendingOauthCodeVerifier();
  await setMobileSession(
    userId: uri.queryParameters['user_id'] ?? '',
    accessToken: accessToken,
  );
  return (success: true, needsPassword: uri.queryParameters['needs_password'] == '1');
}

/// Mirrors mobile/src/api/googleAuth.js: the app's own http client never
/// shares cookies with the system browser tab that completes Google's
/// consent screen, so the backend hands the result back via a
/// `flowmateai://oauth-callback?...` deep link instead (see
/// routes/email/oauth.py's oauth2callback). We open that URL in an external
/// browser and wait for the redirect on the same app_links stream
/// registered in main.dart.
///
/// intent: 'link' (default) attaches a Gmail account to the CURRENTLY
/// logged-in user -- Google can no longer sign anyone in on its own. 'recover'
/// is the one exception: an existing account that only ever used Google (no
/// password set yet) regains access, then must set one -- see
/// GoogleAuthResult.needsPassword. There is no more implicit "login".
Future<GoogleAuthResult> connectGoogleAccount(AppLinks appLinks, {String intent = 'link'}) async {
  final pkce = _generatePkcePair();
  // Written before launching the browser, not after getting a result back --
  // an external browser (unlike RN's in-app auth session) can get this
  // process killed by the OS while the user is still in it.
  await setPendingOauthCodeVerifier(pkce.codeVerifier);

  final data = await apiGet(
    '/email/auth_url?intent=$intent&platform=mobile&code_challenge=${Uri.encodeComponent(pkce.codeChallenge)}',
  );
  if (data is Map &&
      ((data['access_token'] as String?)?.isNotEmpty == true ||
          data['user_id'] != null)) {
    await clearPendingOauthCodeVerifier();
    await setMobileSession(
        userId: (data['user_id'] ?? data['email'] ?? '').toString(),
        accessToken: (data['access_token'] ?? '').toString());
    return GoogleAuthResult(connected: true, needsPassword: data['needs_password'] == true);
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
  final errorCode = resultUri.queryParameters['error'];
  if (errorCode != null && errorCode.isNotEmpty) {
    // oauth2callback failed server-side and redirected back to this deep
    // link with an error code instead of exchange_code/access_token (see
    // _oauth_error_redirect) -- surface a specific message instead of
    // falling through to consumeGoogleAuthCallback's generic failure path.
    final conflictEmail = resultUri.queryParameters['email'] ?? '';
    final message = errorCode == 'google_account_already_linked_elsewhere' && conflictEmail.isNotEmpty
        ? 'Tài khoản Google $conflictEmail đã được liên kết với một tài khoản FlowMate khác. Hãy đăng xuất khỏi tài khoản đó trên Google hoặc dùng một tài khoản Google khác.'
        : (_kGmailAuthErrorMessages[errorCode] ?? 'Không thể liên kết tài khoản Google. Vui lòng thử lại.');
    throw GoogleAuthError(errorCode, message);
  }
  final result = await consumeGoogleAuthCallback(resultUri);
  if (!result.success) {
    throw Exception('Không nhận được access token từ máy chủ.');
  }
  return GoogleAuthResult(connected: true, needsPassword: result.needsPassword);
}

/// One linked Google account, as returned by GET /api/email/accounts (see
/// routes/email/accounts.py). Backs the linked-accounts switcher in
/// SettingsScreen -- multiple Gmail accounts can be linked to one
/// FlowMate account (see utils/user_context.py's "active slot" design).
class GoogleAccount {
  final String accountEmail;
  final String accountName;
  final String accountPicture;
  final bool isActive;
  const GoogleAccount({
    required this.accountEmail,
    required this.accountName,
    required this.accountPicture,
    required this.isActive,
  });

  factory GoogleAccount.fromJson(Map<String, dynamic> json) => GoogleAccount(
        accountEmail: (json['account_email'] as String?) ?? '',
        accountName: (json['account_name'] as String?) ?? '',
        accountPicture: (json['account_picture'] as String?) ?? '',
        isActive: json['is_active'] == true,
      );
}

List<GoogleAccount> _parseGoogleAccounts(dynamic data) {
  final raw = (data is Map ? data['accounts'] : null) as List?;
  if (raw == null) return const [];
  return raw
      .whereType<Map>()
      .map((item) => GoogleAccount.fromJson(Map<String, dynamic>.from(item)))
      .toList();
}

Future<List<GoogleAccount>> listGoogleAccounts() async {
  return _parseGoogleAccounts(await apiGet('/email/accounts'));
}

Future<List<GoogleAccount>> activateGoogleAccount(String accountEmail) async {
  return _parseGoogleAccounts(
    await apiPost('/email/accounts/activate', {'account_email': accountEmail}),
  );
}

Future<List<GoogleAccount>> removeGoogleAccount(String accountEmail) async {
  return _parseGoogleAccounts(
    await apiDelete('/email/accounts/${Uri.encodeComponent(accountEmail)}'),
  );
}

/// Shared error presenter for every connectGoogleAccount() caller. Any
/// other Google-auth error keeps the plain system AlertDialog -- only
/// already-linked-elsewhere gets the styled, animated card (below), since
/// it's the one case with a meaningful "Thử tài khoản khác" retry action:
/// Google always re-prompts account selection (prompt=select_account
/// server-side), so simply restarting the flow lets the user pick a
/// different account. Mirrors mobile/src/api/googleAuth.js's
/// alertGoogleAuthError and web/frontend's gmailLinkConflictModal (same
/// copy, same two actions).
Future<void> showGoogleAuthErrorDialog(
  BuildContext context,
  Object error, {
  String title = 'Không kết nối được Google',
  Future<void> Function()? onRetry,
}) {
  final message = error is GoogleAuthError ? error.message : error.toString();
  final canRetry = error is GoogleAuthError &&
      error.code == 'google_account_already_linked_elsewhere' &&
      onRetry != null;

  if (!canRetry) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Đóng'),
          ),
        ],
      ),
    );
  }

  // showGeneralDialog (not showDialog/AlertDialog) so transitionBuilder can
  // drive a real fade+scale entrance/exit instead of Material's default
  // dialog transition -- matches the fade+scale timing web/frontend's
  // gmailLinkConflictModal and the RN GoogleAuthConflictModal both use.
  return showGeneralDialog<void>(
    context: context,
    barrierDismissible: true,
    barrierLabel: 'Dismiss',
    barrierColor: Colors.black54,
    transitionDuration: const Duration(milliseconds: 200),
    pageBuilder: (dialogContext, animation, secondaryAnimation) {
      return _GoogleAuthConflictCard(message: message, onRetry: onRetry);
    },
    transitionBuilder: (dialogContext, animation, secondaryAnimation, child) {
      final curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);
      return FadeTransition(
        opacity: curved,
        child: ScaleTransition(
          scale: Tween<double>(begin: 0.96, end: 1.0).animate(curved),
          child: child,
        ),
      );
    },
  );
}

class _GoogleAuthConflictCard extends StatelessWidget {
  final String message;
  final Future<void> Function() onRetry;
  const _GoogleAuthConflictCard({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Dialog(
      backgroundColor: colors.panel,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.card)),
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              alignment: Alignment.center,
              decoration: const BoxDecoration(color: Color(0xFFFFF3E0), shape: BoxShape.circle),
              child: const Icon(Icons.warning_amber_rounded, color: Color(0xFFE65100), size: 26),
            ),
            const SizedBox(height: 14),
            Text(
              'Tài khoản Google đã được liên kết',
              textAlign: TextAlign.center,
              style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17),
            ),
            const SizedBox(height: 10),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: colors.textMuted, fontSize: 13.5, height: 1.5),
            ),
            const SizedBox(height: 22),
            Row(
              children: [
                Expanded(
                  child: AppButton(
                    title: 'Đóng',
                    variant: AppButtonVariant.secondary,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: AppButton(
                    title: 'Thử tài khoản khác',
                    onPressed: () {
                      Navigator.of(context).pop();
                      onRetry();
                    },
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
