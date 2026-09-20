import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'config.dart';
import 'nav_key.dart';
import 'session.dart';

// The http package applies no timeout on its own -- a silently-dropped
// connection (e.g. DNS/network trouble reaching kApiBase) would otherwise
// hang a request forever instead of throwing something callers can react to.
const _kRequestTimeout = Duration(seconds: 15);

// Keep one client for the app lifetime so HTTPS/TLS connections can be reused
// across overview, email, calendar, and workspace requests. The top-level
// http helpers create and close a new client for every call.
final http.Client _httpClient = http.Client();

class ApiException implements Exception {
  final String message;
  final int status;
  final Map<String, dynamic> data;
  ApiException(this.message, this.status, this.data);
  @override
  String toString() => message;
}

bool _authAlertActive = false;
DateTime? _lastAuthAlertAt;
const _kAuthAlertCooldown = Duration(seconds: 60);

// Mirrors mobile/src/api/client.js's handleUnauthorized. A 401 with no
// token stored just means "never signed in on this device" -- normal for a
// fresh install, not worth interrupting the user. A 401 while a token IS
// present means it expired or access was revoked -- that's the case worth a
// popup, since login/reconnect only lives in the Settings tab now (no
// per-screen login UI to surface this inline). The cooldown avoids re-
// popping the same alert every few seconds from background polls (e.g.
// workspace-sync polling) while the user hasn't reconnected yet.
void _handleUnauthorized(Map<String, dynamic> data) {
  if (getMobileAccessToken().isEmpty) return;
  final now = DateTime.now();
  if (_authAlertActive ||
      (_lastAuthAlertAt != null &&
          now.difference(_lastAuthAlertAt!) < _kAuthAlertCooldown)) {
    return;
  }
  final context = navigatorKey.currentContext;
  if (context == null) return;
  _authAlertActive = true;
  _lastAuthAlertAt = now;
  final googleOnly = data['auth_scope'] == 'google';
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => AlertDialog(
      title: Text(googleOnly ? 'Cần kết nối lại Google' : 'Cần đăng nhập lại'),
      content: Text(
        googleOnly
            ? 'FlowMate vẫn đang đăng nhập, nhưng quyền Gmail/Calendar cần được cấp lại trong tab Cài đặt.'
            : 'Phiên FlowMate trên thiết bị đã hết hạn. Vui lòng đăng nhập lại để tiếp tục đồng bộ.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(),
          child: const Text('Đã hiểu'),
        ),
      ],
    ),
  ).then((_) => _authAlertActive = false);
}

Future<dynamic> _request(String path,
    {required String method, Map<String, dynamic>? body}) async {
  final accessToken = getMobileAccessToken();
  final userId = getMobileUserId();
  final workspaceId = getCurrentWorkspaceId();
  final headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    if (accessToken.isNotEmpty) 'Authorization': 'Bearer $accessToken',
    if (userId.isNotEmpty) 'X-User-Id': userId,
    // Tells the backend which tenant (Personal vs. a Business workspace)
    // this request belongs to -- routes/chat.py's get_current_workspace_id
    // resolves it, scoping chat history/sessions and the AI response cache.
    if (workspaceId.isNotEmpty) 'X-Workspace-Id': workspaceId,
  };
  final uri = Uri.parse('$kApiBase$path');

  http.Response response;
  switch (method) {
    case 'GET':
      response = await _httpClient
          .get(uri, headers: headers)
          .timeout(_kRequestTimeout);
      break;
    case 'POST':
      response = await _httpClient
          .post(uri,
              headers: headers, body: body != null ? jsonEncode(body) : null)
          .timeout(_kRequestTimeout);
      break;
    case 'PUT':
      response = await _httpClient
          .put(uri,
              headers: headers, body: body != null ? jsonEncode(body) : null)
          .timeout(_kRequestTimeout);
      break;
    case 'PATCH':
      response = await _httpClient
          .patch(uri,
              headers: headers, body: body != null ? jsonEncode(body) : null)
          .timeout(_kRequestTimeout);
      break;
    case 'DELETE':
      response = await _httpClient
          .delete(uri, headers: headers)
          .timeout(_kRequestTimeout);
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
    if (response.statusCode == 401) _handleUnauthorized(map);
    // Login/register endpoints return stable machine codes in `error` and a
    // user-facing localized explanation in `message`. Match the web and React
    // Native clients by presenting the explanation when one is available.
    final message = (map['message'] as String?) ??
        (map['error'] as String?) ??
        'HTTP ${response.statusCode}';
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
