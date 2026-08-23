import 'dart:convert';
import 'package:http/http.dart' as http;
import 'config.dart';

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  @override
  String toString() => message;
}

class AuthResult {
  final String userId;
  final String email;
  final String accessToken;
  AuthResult({required this.userId, required this.email, required this.accessToken});
}

Future<AuthResult> registerWithEmail({
  required String name,
  required String email,
  required String password,
}) {
  return _postAuth('/auth/register', {
    'name': name,
    'email': email,
    'password': password,
  });
}

Future<AuthResult> loginWithEmail({
  required String email,
  required String password,
}) {
  return _postAuth('/auth/login', {
    'email': email,
    'password': password,
  });
}

Future<AuthResult> _postAuth(String path, Map<String, dynamic> body) async {
  final response = await http.post(
    Uri.parse('$kApiBase$path'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(body),
  );

  Map<String, dynamic> data;
  try {
    data = jsonDecode(response.body) as Map<String, dynamic>;
  } catch (_) {
    data = {};
  }

  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw ApiException(
      (data['message'] as String?) ?? (data['error'] as String?) ?? 'HTTP ${response.statusCode}',
    );
  }

  return AuthResult(
    userId: data['user_id'] as String? ?? '',
    email: data['email'] as String? ?? '',
    accessToken: data['access_token'] as String? ?? '',
  );
}
