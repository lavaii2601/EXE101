import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../api/client.dart';
import '../api/session.dart';

// Mirrors mobile/App.js's WORKSPACE_SYNC_POLL_* constants exactly.
const _kWorkspaceSyncPollIntervalMs = 12000;
const _kWorkspaceSyncPollMinMs = 10000;
const _kWorkspaceSyncPollMaxMs = 15000;
// Mirrors mobile/src/state/workspaceSync.js's storage key/shape so a device
// that's been signed into both the RN and Flutter builds (unlikely, but
// cheap to keep consistent) doesn't need two separate cursors.
const _kWorkspaceSyncRevisionKey = 'flowmate.workspaceSyncRevision';
const _syncStorage = FlutterSecureStorage();

/// Maps changed sync domains (from GET /sync/state's `changed` list) to the
/// screen-refresh targets those changes actually affect. Ported 1:1 from
/// mobile/App.js's workspaceTargetsForDomains.
List<String> workspaceTargetsForDomains(Iterable<dynamic> domains) {
  final targets = <String>{};
  for (final raw in domains) {
    final key = raw.toString().trim().toLowerCase();
    if (key.isEmpty) continue;
    // A remote Calendar revision already represents server-side shared
    // state. Refresh the local schedule view without launching another
    // /schedule/sync mutation, which would advance the revision again and
    // create a poll loop.
    if (key == 'calendar') {
      targets.addAll(['schedule', 'overview']);
      continue;
    }
    targets.add(key);
    if (key == 'email') targets.add('overview');
    if (key == 'schedule') targets.addAll(['schedule', 'overview']);
    if (key == 'chat') targets.add('history');
    if (key == 'profile' || key == 'settings') targets.addAll(['profile', 'settings']);
    if (key == 'providers') targets.add('settings');
  }
  return targets.toList();
}

int _workspacePollDelay(dynamic value) {
  final requested = value is num ? value.toDouble() : double.tryParse('$value');
  if (requested == null || !requested.isFinite) return _kWorkspaceSyncPollIntervalMs;
  return requested.clamp(_kWorkspaceSyncPollMinMs, _kWorkspaceSyncPollMaxMs).round();
}

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

  // Cross-device sync polling (GET /sync/state) -- mirrors mobile/App.js's
  // dedicated useEffect. Unlike React's effect-cleanup model, this is
  // driven imperatively by _RootFlow's lifecycle: start/stop on
  // isAuthenticated transitions, pause/resume on app foreground/background
  // (see setSyncForeground).
  Timer? _syncTimer;
  bool _syncPollingActive = false;
  bool _syncForeground = true;
  bool _syncChecking = false;
  bool _syncCheckAgain = false;
  bool _syncRevisionLoaded = false;
  int? _syncRevisionCursor;
  int _syncPollDelayMs = _kWorkspaceSyncPollIntervalMs;
  String _syncOwner = '';

  String get _currentSyncOwner {
    final id = getMobileUserId();
    return id.isEmpty ? 'anonymous' : id;
  }

  Future<int?> _loadWorkspaceSyncRevision(String owner) async {
    try {
      final stored = await _syncStorage.read(key: _kWorkspaceSyncRevisionKey);
      if (stored == null) return null;
      final parsed = jsonDecode(stored);
      final revisions = (parsed is Map && parsed['revisions'] is Map) ? parsed['revisions'] as Map : const {};
      final value = revisions[owner];
      return (value is num && value >= 0) ? value.toInt() : null;
    } catch (_) {
      return null;
    }
  }

  Future<void> _persistWorkspaceSyncRevision(int revision, String owner) async {
    try {
      final stored = await _syncStorage.read(key: _kWorkspaceSyncRevisionKey);
      var revisions = <String, dynamic>{};
      if (stored != null) {
        final parsed = jsonDecode(stored);
        if (parsed is Map && parsed['revisions'] is Map) {
          revisions = Map<String, dynamic>.from(parsed['revisions'] as Map);
        }
      }
      revisions[owner] = revision;
      await _syncStorage.write(
        key: _kWorkspaceSyncRevisionKey,
        value: jsonEncode({'version': 1, 'revisions': revisions}),
      );
    } catch (_) {
      // Best-effort persistence -- a failed write just means the next
      // launch re-baselines from revision null (harmless: it never
      // notifies on that first poll since hasBaseline starts false).
    }
  }

  /// Start (or, if already running, no-op) the cross-device sync poll for
  /// the currently signed-in user. Call once auth is confirmed; safe to
  /// call repeatedly (e.g. from a widget's build method).
  void startWorkspaceSyncPolling() {
    if (_syncPollingActive) return;
    _syncPollingActive = true;
    _syncOwner = _currentSyncOwner;
    _syncRevisionLoaded = false;
    _syncCheckAgain = false;
    _loadWorkspaceSyncRevision(_syncOwner).then((revision) {
      if (!_syncPollingActive || _syncOwner != _currentSyncOwner) return;
      _syncRevisionCursor = revision;
      _syncRevisionLoaded = true;
      _checkWorkspaceSyncState();
    });
  }

  void stopWorkspaceSyncPolling() {
    _syncPollingActive = false;
    _syncTimer?.cancel();
    _syncTimer = null;
    _syncRevisionLoaded = false;
    _syncRevisionCursor = null;
    _syncPollDelayMs = _kWorkspaceSyncPollIntervalMs;
  }

  /// Call from a WidgetsBindingObserver.didChangeAppLifecycleState so
  /// polling pauses while backgrounded and immediately re-checks on
  /// foreground, instead of waking up to a stale delayed timer.
  void setSyncForeground(bool foreground) {
    if (_syncForeground == foreground) return;
    _syncForeground = foreground;
    if (!_syncPollingActive) return;
    _syncTimer?.cancel();
    _syncTimer = null;
    if (foreground) _checkWorkspaceSyncState();
  }

  void _scheduleNextSyncCheck() {
    _syncTimer?.cancel();
    if (!_syncPollingActive || !_syncForeground) return;
    _syncTimer = Timer(Duration(milliseconds: _syncPollDelayMs), _checkWorkspaceSyncState);
  }

  Future<void> _checkWorkspaceSyncState() async {
    if (!_syncPollingActive || !_syncForeground) return;
    if (!_syncRevisionLoaded || _syncChecking) {
      _syncCheckAgain = true;
      return;
    }

    _syncChecking = true;
    _syncCheckAgain = false;
    final owner = _syncOwner;
    try {
      final suffix = _syncRevisionCursor == null ? '' : '?since=$_syncRevisionCursor';
      final data = await apiGet('/sync/state$suffix');
      if (!_syncPollingActive ||
          !_syncForeground ||
          owner != _currentSyncOwner ||
          data is! Map ||
          data['success'] != true) {
        return;
      }

      final nextRevisionRaw = data['revision'];
      if (nextRevisionRaw is! num || nextRevisionRaw < 0) return;
      final nextRevision = nextRevisionRaw.toInt();

      final changedDomains = data['changed'] is List ? List<dynamic>.from(data['changed'] as List) : const [];
      final hasBaseline = _syncRevisionCursor != null;
      final shouldNotify = hasBaseline && nextRevision != _syncRevisionCursor && changedDomains.isNotEmpty;

      _syncRevisionCursor = nextRevision;
      _syncPollDelayMs = _workspacePollDelay(data['poll_after_ms']);
      unawaited(_persistWorkspaceSyncRevision(nextRevision, owner));

      if (shouldNotify) {
        onAgentSync(workspaceTargetsForDomains(changedDomains));
      }
    } catch (_) {
      // Network hiccup (or a 401 mid-transition) -- quietly retry on the
      // next scheduled tick, mirroring the RN client's swallow-and-continue.
    } finally {
      _syncChecking = false;
      if (!_syncPollingActive) return;
      if (_syncCheckAgain && _syncForeground) {
        _checkWorkspaceSyncState();
      } else {
        _scheduleNextSyncCheck();
      }
    }
  }

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
      } else {
        // Same "don't hang forever on first launch" reasoning as the
        // catch-all below -- a non-401 API error (e.g. a 500) shouldn't
        // leave isAuthenticated stuck at null either.
        isAuthenticated ??= false;
      }
    } catch (_) {
      // Network hiccup: leave isAuthenticated as-is rather than bouncing an
      // already-signed-in user to the login screen for a transient error.
      // But on the very first check (still null -- nothing to protect yet),
      // that would leave _RootFlow's `isAuthenticated == null` blank screen
      // showing forever with no way out. Fail open to the login flow instead.
      isAuthenticated ??= false;
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
