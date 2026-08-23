import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();
const _userIdKey = 'flowmate.mobileUserId';
const _accessTokenKey = 'flowmate.mobileAccessToken';

// client.dart reads these synchronously on every request, so we keep an
// in-memory cache fed from secure storage at startup (see
// loadPersistedSession) instead of making every request await disk access --
// mirrors mobile/src/api/session.js exactly.
String _mobileUserId = '';
String _mobileAccessToken = '';

String getMobileUserId() => _mobileUserId;
String getMobileAccessToken() => _mobileAccessToken;

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

/// Call once at app startup, before the first API request, so a previously
/// signed-in user doesn't get logged out just from closing the app.
Future<void> loadPersistedSession() async {
  try {
    _mobileUserId = await _storage.read(key: _userIdKey) ?? '';
    _mobileAccessToken = await _storage.read(key: _accessTokenKey) ?? '';
  } catch (_) {
    _mobileUserId = '';
    _mobileAccessToken = '';
  }
}

Future<void> clearPersistedSession() async {
  _mobileUserId = '';
  _mobileAccessToken = '';
  await _storage.delete(key: _userIdKey);
  await _storage.delete(key: _accessTokenKey);
}
