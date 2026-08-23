import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();
const _userIdKey = 'flowmate.mobileUserId';
const _accessTokenKey = 'flowmate.mobileAccessToken';

Future<void> setMobileSession({required String userId, required String accessToken}) async {
  await _storage.write(key: _userIdKey, value: userId);
  await _storage.write(key: _accessTokenKey, value: accessToken);
}

Future<String?> getMobileUserId() => _storage.read(key: _userIdKey);
Future<String?> getMobileAccessToken() => _storage.read(key: _accessTokenKey);

Future<void> clearMobileSession() async {
  await _storage.delete(key: _userIdKey);
  await _storage.delete(key: _accessTokenKey);
}
