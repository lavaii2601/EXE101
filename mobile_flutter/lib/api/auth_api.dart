import 'client.dart';

class AuthResult {
  final String userId;
  final String email;
  final String accessToken;
  AuthResult({required this.userId, required this.email, required this.accessToken});

  factory AuthResult.fromJson(Map<String, dynamic> json) => AuthResult(
        userId: json['user_id'] as String? ?? '',
        email: json['email'] as String? ?? '',
        accessToken: json['access_token'] as String? ?? '',
      );
}

Future<AuthResult> registerWithEmail({
  required String name,
  required String email,
  required String password,
}) async {
  final data = await apiPost('/auth/register', {'name': name, 'email': email, 'password': password});
  return AuthResult.fromJson(data as Map<String, dynamic>);
}

Future<AuthResult> loginWithEmail({required String email, required String password}) async {
  final data = await apiPost('/auth/login', {'email': email, 'password': password});
  return AuthResult.fromJson(data as Map<String, dynamic>);
}

/// First-time password setup for an account recovered via Google (see
/// google_auth.dart's connectGoogleAccount(intent: 'recover')) that never
/// had one. Requires the session connectGoogleAccount already established.
Future<void> setPassword(String password) async {
  await apiPost('/auth/set-password', {'password': password});
}

/// Revokes every mobile access token issued for this account (bumps
/// token_version server-side) plus the browser session -- for a user who
/// suspects a device was lost/stolen. Includes the very token used to call
/// it, so the caller must also log this device out locally right after.
Future<void> logoutAllDevices() async {
  await apiPost('/auth/logout-all-devices');
}
