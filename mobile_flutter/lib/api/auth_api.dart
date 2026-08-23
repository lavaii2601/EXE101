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
