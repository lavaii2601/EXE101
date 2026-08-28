import 'package:flutter/material.dart';
import '../api/client.dart';
import '../api/session.dart';

/// Multi-tenant Business workspace state (Worker Business Phase 1).
/// See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md sections 4, 10, 13, and
/// web/frontend/js/app.js's orgWorkspace* functions for the client this
/// mirrors. Kept as its own ChangeNotifier (like ThemeController/
/// LanguageController) rather than folded into AppState, since it has its
/// own independent load/switch lifecycle.
class WorkspaceController extends ChangeNotifier {
  List<Map<String, dynamic>> workspaces = [];
  String? currentWorkspaceId;
  bool loading = false;

  Map<String, dynamic>? _findById(String? id) {
    if (id == null) return null;
    for (final workspace in workspaces) {
      if (workspace['id'] == id) return workspace;
    }
    return null;
  }

  Map<String, dynamic>? get current => _findById(currentWorkspaceId);
  bool get isBusiness => current?['type'] == 'business';
  String get currentRole => (current?['member_role'] as String?) ?? 'worker';
  bool get canManage => currentRole == 'owner' || currentRole == 'admin';

  Future<void> loadWorkspaces() async {
    loading = true;
    notifyListeners();
    try {
      final data = await apiGet('/workspaces');
      if (data is Map && data['success'] == true) {
        final list = (data['workspaces'] as List?) ?? [];
        workspaces = list.map((w) => Map<String, dynamic>.from(w as Map)).toList();

        final saved = getCurrentWorkspaceId();
        final savedIsValid = saved.isNotEmpty && _findById(saved) != null;
        if (savedIsValid) {
          currentWorkspaceId = saved;
        } else {
          final personal = _findFirstByType('personal');
          final fallbackId = personal?['id'] as String? ??
              (workspaces.isNotEmpty ? workspaces.first['id'] as String? : null);
          currentWorkspaceId = fallbackId;
          if (fallbackId != null) await setCurrentWorkspaceId(fallbackId);
        }
      }
    } catch (_) {
      // Leave whatever state was already loaded; the switcher UI just won't
      // update. Matches web's apiFetch failure handling for this same call.
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Map<String, dynamic>? _findFirstByType(String type) {
    for (final workspace in workspaces) {
      if (workspace['type'] == type) return workspace;
    }
    return null;
  }

  Future<void> switchWorkspace(String workspaceId) async {
    if (workspaceId == currentWorkspaceId) return;
    currentWorkspaceId = workspaceId;
    await setCurrentWorkspaceId(workspaceId);
    notifyListeners();
  }

  Future<Map<String, dynamic>> createBusinessWorkspace(String name) async {
    final data = await apiPost('/workspaces', {'name': name});
    if (data is Map && data['success'] == true) {
      final workspace = Map<String, dynamic>.from(data['workspace'] as Map);
      await loadWorkspaces();
      await switchWorkspace(workspace['id'] as String);
      return workspace;
    }
    throw Exception((data is Map ? data['error'] as String? : null) ?? 'create_workspace_failed');
  }

  Future<void> acceptInvitation(String token) async {
    final data = await apiPost('/workspace-invitations/$token/accept', {});
    if (data is Map && data['success'] == true) {
      final invitation = Map<String, dynamic>.from(data['invitation'] as Map);
      await loadWorkspaces();
      final workspaceId = invitation['workspace_id'] as String?;
      if (workspaceId != null) await switchWorkspace(workspaceId);
      return;
    }
    throw Exception((data is Map ? data['error'] as String? : null) ?? 'accept_invitation_failed');
  }

  /// Called on logout so a fresh sign-in never inherits a stale workspace.
  void reset() {
    workspaces = [];
    currentWorkspaceId = null;
    notifyListeners();
  }
}
