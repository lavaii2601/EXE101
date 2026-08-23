import 'dart:convert';
import 'package:http/http.dart' as http;
import 'config.dart';
import 'session.dart';

class ApiException implements Exception {
  final String message;
  final int status;
  final Map<String, dynamic> data;
  ApiException(this.message, this.status, this.data);
  @override
  String toString() => message;
}

Future<dynamic> _request(String path, {required String method, Map<String, dynamic>? body}) async {
  final accessToken = getMobileAccessToken();
  final userId = getMobileUserId();
  final headers = {
    'Content-Type': 'application/json',
    if (accessToken.isNotEmpty) 'Authorization': 'Bearer $accessToken',
    if (userId.isNotEmpty) 'X-User-Id': userId,
  };
  final uri = Uri.parse('$kApiBase$path');

  http.Response response;
  switch (method) {
    case 'GET':
      response = await http.get(uri, headers: headers);
      break;
    case 'POST':
      response = await http.post(uri, headers: headers, body: body != null ? jsonEncode(body) : null);
      break;
    case 'PUT':
      response = await http.put(uri, headers: headers, body: body != null ? jsonEncode(body) : null);
      break;
    case 'PATCH':
      response = await http.patch(uri, headers: headers, body: body != null ? jsonEncode(body) : null);
      break;
    case 'DELETE':
      response = await http.delete(uri, headers: headers);
      break;
    default:
      throw ArgumentError('Unsupported method $method');
  }

  dynamic data = {};
  if (response.body.isNotEmpty) {
    try {
      data = jsonDecode(response.body);
    } catch (_) {
      data = {'raw': response.body};
    }
  }

  if (response.statusCode < 200 || response.statusCode >= 300) {
    final map = data is Map<String, dynamic> ? data : <String, dynamic>{};
    final message = (map['error'] as String?) ?? (map['message'] as String?) ?? 'HTTP ${response.statusCode}';
    throw ApiException(message, response.statusCode, map);
  }
  return data;
}

Future<dynamic> apiGet(String path) => _request(path, method: 'GET');
Future<dynamic> apiPost(String path, [Map<String, dynamic> body = const {}]) =>
    _request(path, method: 'POST', body: body);
Future<dynamic> apiPut(String path, [Map<String, dynamic> body = const {}]) =>
    _request(path, method: 'PUT', body: body);
Future<dynamic> apiPatch(String path, [Map<String, dynamic> body = const {}]) =>
    _request(path, method: 'PATCH', body: body);
Future<dynamic> apiDelete(String path) => _request(path, method: 'DELETE');
