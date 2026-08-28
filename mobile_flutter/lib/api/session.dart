import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();
const _userIdKey = 'flowmate.mobileUserId';
const _accessTokenKey = 'flowmate.mobileAccessToken';
const _workspaceIdKey = 'flowmate.currentWorkspaceId';

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

Future<void> setMobileSession({required String userId, required String accessToken}) async {
  await setMobileUserId(userId);
  await setMobileAccessToken(accessToken);
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
    _mobileUserId = await _storage.read(key: _userIdKey) ?? '';
    _mobileAccessToken = await _storage.read(key: _accessTokenKey) ?? '';
    _currentWorkspaceId = await _storage.read(key: _workspaceIdKey) ?? '';
  } catch (_) {
    _mobileUserId = '';
    _mobileAccessToken = '';
    _currentWorkspaceId = '';
  }
}

Future<void> clearPersistedSession() async {
  _mobileUserId = '';
  _mobileAccessToken = '';
  _currentWorkspaceId = '';
  await _storage.delete(key: _userIdKey);
  await _storage.delete(key: _accessTokenKey);
  await _storage.delete(key: _workspaceIdKey);
}
