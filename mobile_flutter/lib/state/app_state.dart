import 'package:flutter/material.dart';
import '../api/client.dart';
import '../api/session.dart';

/// Mirrors App.js's AppShell top-level state: who's signed in, their
/// profile/status, and the "something changed, go refetch" signal every
/// screen listens to instead of each polling independently.
class AppState extends ChangeNotifier {
  bool? isAuthenticated; // null = not checked yet
  Map<String, dynamic>? profile;
  Map<String, dynamic>? status;
  String? userMode;
  int syncRevision = 0;
  List<String> lastSyncTargets = [];

  Future<void> bootstrap() async {
    await loadPersistedSession();
    await refreshShell();
  }

  Future<void> refreshShell() async {
    try {
      final result = await apiGet('/user/profile');
      if (result is Map<String, dynamic> && result['success'] == true) {
        isAuthenticated = true;
        profile = result['user'] as Map<String, dynamic>?;
        userMode = (profile?['user_mode'] as String?) ?? '';
      }
    } on ApiException catch (e) {
      if (e.status == 401) {
        isAuthenticated = false;
      }
    } catch (_) {
      // Network hiccup: leave isAuthenticated as-is rather than bouncing
      // the user to the login screen for a transient error.
    }
    try {
      final s = await apiGet('/status');
      if (s is Map<String, dynamic>) status = s;
    } catch (_) {}
    notifyListeners();
  }

  void onAgentSync(List<String> targets) {
    final unique = targets.toSet().toList();
    if (unique.isEmpty) return;
    syncRevision += 1;
    lastSyncTargets = unique;
    if (unique.any((t) => ['settings', 'profile', 'providers'].contains(t))) {
      refreshShell();
    }
    notifyListeners();
  }

  Future<void> saveUserMode(String mode) async {
    try {
      final data = await apiPost('/user/profile', {'user_mode': mode});
      if (data is Map<String, dynamic> && data['user'] != null) {
        profile = data['user'] as Map<String, dynamic>;
      }
      userMode = mode;
    } on ApiException catch (e) {
      if (e.status == 401 || e.status == 403) {
        userMode = mode;
      } else {
        rethrow;
      }
    }
    notifyListeners();
  }

  Future<void> onLoggedIn() async {
    isAuthenticated = null;
    notifyListeners();
    await refreshShell();
  }

  Future<void> logout() async {
    await clearPersistedSession();
    profile = null;
    status = null;
    userMode = null;
    isAuthenticated = false;
    notifyListeners();
  }
}
