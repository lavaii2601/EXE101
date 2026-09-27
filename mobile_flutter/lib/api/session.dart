import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();
const _userIdKey = 'flowmate.mobileUserId';
const _accessTokenKey = 'flowmate.mobileAccessToken';
const _workspaceIdKey = 'flowmate.currentWorkspaceId';
// Unlike RN's WebBrowser.openAuthSessionAsync (an in-app overlay that keeps
// the app alive), google_auth.dart launches a real external browser -- the
// OS can kill the Flutter process while the user is still in it, and
// main.dart's cold-start link handler needs this PKCE verifier to still be
// around to redeem the deep link's exchange_code. A plain random string
// isn't itself a credential (it's useless without the matching one-time
// exchange_code, which is short-lived and single-use), so this doesn't need
// the same protection as the access token above -- but it's already in
// secure storage, so no reason not to keep it there too.
const _pendingOauthVerifierKey = 'flowmate.pendingOauthCodeVerifier';

// client.dart reads these synchronously on every request, so we keep an
// in-memory cache fed from secure storage at startup (see
// loadPersistedSession) instead of making every request await disk access --
// mirrors mobile/src/api/session.js exactly.
String _mobileUserId = '';
String _mobileAccessToken = '';
// The active Business workspace (Worker Business Phase 1). Lives alongside
// user/token here, not in WorkspaceController, so client.dart can read it
// synchronously the same way it reads the user id/token -- see
// web/frontend/js/app.js's analogous X-Workspace-Id header injection in
// apiFetch for the client this mirrors.
String _currentWorkspaceId = '';

String getMobileUserId() => _mobileUserId;
String getMobileAccessToken() => _mobileAccessToken;
String getCurrentWorkspaceId() => _currentWorkspaceId;

Future<void> setMobileUserId(String value) async {
  _mobileUserId = value.trim();
  await _storage.write(key: _userIdKey, value: _mobileUserId);
}

Future<void> setMobileAccessToken(String value) async {
  _mobileAccessToken = value.trim();
  if (_mobileAccessToken.isNotEmpty) {
    await _storage.write(key: _accessTokenKey, value: _mobileAccessToken);
  } else {
    await _storage.delete(key: _accessTokenKey);
  }
}

Future<void> setMobileSession(
    {required String userId, required String accessToken}) async {
  await Future.wait([
    setMobileUserId(userId),
    setMobileAccessToken(accessToken),
  ]);
}

Future<void> setCurrentWorkspaceId(String value) async {
  _currentWorkspaceId = value.trim();
  if (_currentWorkspaceId.isNotEmpty) {
    await _storage.write(key: _workspaceIdKey, value: _currentWorkspaceId);
  } else {
    await _storage.delete(key: _workspaceIdKey);
  }
}

/// Call once at app startup, before the first API request, so a previously
/// signed-in user doesn't get logged out just from closing the app.
Future<void> loadPersistedSession() async {
  try {
    final values = await Future.wait([
      _storage.read(key: _userIdKey),
      _storage.read(key: _accessTokenKey),
      _storage.read(key: _workspaceIdKey),
    ]);
    _mobileUserId = values[0] ?? '';
    _mobileAccessToken = values[1] ?? '';
    _currentWorkspaceId = values[2] ?? '';
  } catch (_) {
    _mobileUserId = '';
    _mobileAccessToken = '';
    _currentWorkspaceId = '';
  }
}

Future<void> setPendingOauthCodeVerifier(String value) async {
  await _storage.write(key: _pendingOauthVerifierKey, value: value);
}

Future<String?> getPendingOauthCodeVerifier() async {
  return _storage.read(key: _pendingOauthVerifierKey);
}

Future<void> clearPendingOauthCodeVerifier() async {
  await _storage.delete(key: _pendingOauthVerifierKey);
}

Future<void> clearPersistedSession() async {
  _mobileUserId = '';
  _mobileAccessToken = '';
  _currentWorkspaceId = '';
  await Future.wait([
    _storage.delete(key: _userIdKey),
    _storage.delete(key: _accessTokenKey),
    _storage.delete(key: _workspaceIdKey),
  ]);
}
