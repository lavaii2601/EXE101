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

// Set by main.dart so this file can drive AppState back to a logged-out
// state (and reset the rest of the app shell) the same way a manual
// "Đăng xuất" tap does, without client.dart importing app_state.dart --
// app_state.dart already imports client.dart, so the reverse would be a
// circular import.
VoidCallback? _onSessionRevoked;
void setSessionRevokedHandler(VoidCallback? handler) {
  _onSessionRevoked = handler;
}

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
  if (!googleOnly) {
    // Unlike a Google-scope reconnect, this token can never work again
    // (expired past its 30-day signature, or explicitly revoked via "log
    // out all devices" from another device) -- clear it now instead of
    // leaving a dead token in secure storage that keeps tripping this same
    // 401 on every background poll (workspace sync, ...) for up to 30 more
    // days with no way for the user to get back to a clean login screen.
    _onSessionRevoked?.call();
  }
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
  final workspaceId = getCurrentWorkspaceId();
  final headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    // No X-User-Id here: this app always authenticates with a real Bearer
    // token, so the header would be redundant identity at best and, if
    // MOBILE_USER_HEADER_ENABLED were ever accidentally left on in some
    // environment, an unauthenticated impersonation path at worst. It's
    // still meant to exist as a dev-only escape hatch (see utils/security.py),
    // just not one this production client should be the one sending.
    if (accessToken.isNotEmpty) 'Authorization': 'Bearer $accessToken',
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

  return _decodeResponse(response);
}

dynamic _decodeResponse(http.Response response) {
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

/// One file to upload via apiPostMultipart -- `path` for a real on-disk file
/// (file_picker's PlatformFile.path on mobile) or `bytes` when only in-memory
/// data is available (e.g. web, or a picker result with withData: true).
class ComposeAttachment {
  final String filename;
  final String? path;
  final List<int>? bytes;
  ComposeAttachment({required this.filename, this.path, this.bytes});
}

// multipart/form-data upload (email attachments) -- the plain-JSON apiPost
// above can't carry file bytes, and a FormData-equivalent here needs an
// http.MultipartRequest instead of the shared _request()'s json-only body.
Future<dynamic> apiPostMultipart(
  String path, {
  required Map<String, String> fields,
  List<ComposeAttachment> attachments = const [],
}) async {
  final accessToken = getMobileAccessToken();
  final workspaceId = getCurrentWorkspaceId();
  final uri = Uri.parse('$kApiBase$path');
  final request = http.MultipartRequest('POST', uri)
    ..headers.addAll({
      'Accept': 'application/json',
      if (accessToken.isNotEmpty) 'Authorization': 'Bearer $accessToken',
      if (workspaceId.isNotEmpty) 'X-Workspace-Id': workspaceId,
    })
    ..fields.addAll(fields);

  for (final attachment in attachments) {
    if (attachment.bytes != null) {
      request.files.add(http.MultipartFile.fromBytes(
        'attachments', attachment.bytes!,
        filename: attachment.filename,
      ));
    } else if (attachment.path != null) {
      request.files.add(await http.MultipartFile.fromPath(
        'attachments', attachment.path!,
        filename: attachment.filename,
      ));
    }
  }

  final streamed = await _httpClient.send(request).timeout(_kRequestTimeout);
  final response = await http.Response.fromStream(streamed);
  return _decodeResponse(response);
}
