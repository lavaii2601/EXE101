import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';

const Map<String, IconData> _actionIcons = {
  'chat': Icons.auto_awesome_outlined,
  'email_summary': Icons.description_outlined,
  'email_reply': Icons.edit_outlined,
  'email_sent': Icons.send_outlined,
  'email_daily_summary': Icons.analytics_outlined,
  'schedule_created': Icons.event_outlined,
  'schedule_updated': Icons.event_repeat_outlined,
  'schedule_deleted': Icons.event_busy_outlined,
  'calendar_event_created': Icons.event_outlined,
  'calendar_event_updated': Icons.event_repeat_outlined,
  'calendar_event_deleted': Icons.event_busy_outlined,
  'settings_updated': Icons.tune_outlined,
  'system': Icons.memory_outlined,
};

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>> history = [];
  bool loading = false;
  String filter = 'all';
  int? expandedId;

  AppState? _appState;
  int _lastHandledSyncRevision = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Cross-device sync: another device/the web app logged a new activity
    // while this screen was open -- AppState's poller (see
    // state/app_state.dart) notifies here so the log doesn't sit stale
    // until manually reopened. Set up once per AppState instance
    // (didChangeDependencies can fire more than once).
    final appState = context.read<AppState>();
    if (_appState != appState) {
      _appState?.removeListener(_handleWorkspaceSync);
      _appState = appState;
      _lastHandledSyncRevision = appState.syncRevision;
      appState.addListener(_handleWorkspaceSync);
    }
  }

  void _handleWorkspaceSync() {
    final appState = _appState;
    if (appState == null || appState.syncRevision == _lastHandledSyncRevision) {
      return;
    }
    _lastHandledSyncRevision = appState.syncRevision;
    final targets = appState.lastSyncTargets;
    if (targets.contains('history') ||
        targets.contains('chat') ||
        targets.contains('email') ||
        targets.contains('schedule') ||
        targets.contains('settings')) {
      _load();
    }
  }

  @override
  void dispose() {
    _appState?.removeListener(_handleWorkspaceSync);
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await apiGet('/chat/history?limit=50');
      final items = (data is Map && data['history'] is List)
          ? List<Map<String, dynamic>>.from(data['history'])
          : <Map<String, dynamic>>[];
      setState(() => history = items);
    } catch (_) {
      // keep whatever we had; a transient failure shouldn't blank the log
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _confirmClearAll() async {
    final t = context.read<LanguageController>().t;
    final colors = context.read<ThemeController>().colors;
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        decoration: BoxDecoration(
          color: colors.panel,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
          border: Border.all(color: colors.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 42,
                height: 4,
                decoration: BoxDecoration(
                  color: colors.border,
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
            ),
            const SizedBox(height: 18),
            Text(
              t('Xóa lịch sử', 'Clear history'),
              style: TextStyle(
                color: colors.text,
                fontWeight: FontWeight.w700,
                fontSize: 18,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              t(
                'Bạn chắc chắn muốn xóa toàn bộ lịch sử chat, email và lịch?',
                'Are you sure you want to clear all chat, email, and calendar history?',
              ),
              style: TextStyle(
                color: colors.textMuted,
                fontSize: 13,
                height: 1.45,
              ),
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: AppButton(
                    title: t('Hủy', 'Cancel'),
                    variant: AppButtonVariant.secondary,
                    onPressed: () => Navigator.pop(ctx, false),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: AppButton(
                    title: t('Xóa', 'Clear'),
                    onPressed: () => Navigator.pop(ctx, true),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await apiPost('/chat/clear-all');
      if (mounted) {
        setState(() {
          history = [];
          expandedId = null;
        });
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(t(
                  'Không xóa được nhật ký', 'Could not clear the audit log'))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    final visible = filter == 'all'
        ? history
        : history
            .where((h) => (h['action_type'] as String? ?? '').contains(filter))
            .toList();

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: t('Lịch sử', 'History'),
          refreshing: loading,
          onRefresh: _load,
          children: [
            AppCard(
              child: Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                        color: colors.primarySoft,
                        borderRadius: BorderRadius.circular(14)),
                    child: Icon(Icons.shield_outlined, color: colors.primary),
                  ),
                  const SizedBox(width: 11),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(t('Hoạt động gần đây', 'Recent activity'),
                            style: TextStyle(
                                color: colors.text,
                                fontWeight: FontWeight.w600,
                                fontSize: 13)),
                        Text(
                            t('${history.length} sự kiện gần nhất',
                                '${history.length} recent events'),
                            style: TextStyle(
                                color: colors.textMuted, fontSize: 10.5)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  _FilterChip(
                      label: t('Tất cả', 'All'),
                      value: 'all',
                      current: filter,
                      onTap: (v) => setState(() => filter = v)),
                  _FilterChip(
                      label: 'Chat',
                      value: 'chat',
                      current: filter,
                      onTap: (v) => setState(() => filter = v)),
                  _FilterChip(
                      label: t('Email', 'Email'),
                      value: 'email',
                      current: filter,
                      onTap: (v) => setState(() => filter = v)),
                  _FilterChip(
                      label: t('Lịch', 'Calendar'),
                      value: 'schedule',
                      current: filter,
                      onTap: (v) => setState(() => filter = v)),
                ],
              ),
            ),
            if (visible.isEmpty)
              AppCard(
                  child: AppEmptyState(
                      icon: Icons.history_outlined,
                      title: t('Chưa có sự kiện', 'No events yet')))
            else
              ...visible.map((item) {
                final actionType = item['action_type'] as String? ?? '';
                final id = item['id'] as int? ?? 0;
                final expanded = expandedId == id;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: GestureDetector(
                    onTap: () =>
                        setState(() => expandedId = expanded ? null : id),
                    child: AppCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                  _actionIcons[actionType] ??
                                      Icons.circle_outlined,
                                  size: 17,
                                  color: colors.primary),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(_humanize(actionType),
                                    style: TextStyle(
                                        color: colors.text,
                                        fontWeight: FontWeight.w600,
                                        fontSize: 12.5)),
                              ),
                              Icon(
                                  expanded
                                      ? Icons.expand_less
                                      : Icons.expand_more,
                                  size: 16,
                                  color: colors.textMuted),
                            ],
                          ),
                          Padding(
                            padding: const EdgeInsets.only(top: 8, left: 25),
                            child: Text(
                              (item['user_message'] as String?) ??
                                  (item['assistant_response'] as String?) ??
                                  '',
                              maxLines: expanded ? null : 2,
                              overflow: expanded
                                  ? TextOverflow.visible
                                  : TextOverflow.ellipsis,
                              style: TextStyle(
                                  color: colors.textMuted,
                                  fontSize: 11,
                                  height: 1.4),
                            ),
                          ),
                          if (expanded && item['assistant_response'] != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 8, left: 25),
                              child: Text(
                                item['assistant_response'] as String,
                                style: TextStyle(
                                    color: colors.text,
                                    fontSize: 11.5,
                                    height: 1.4),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                );
              }),
            if (history.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 2, bottom: 8),
                child: AppButton(
                  title: t('Xóa lịch sử', 'Clear history'),
                  variant: AppButtonVariant.secondary,
                  icon: Icons.delete_outline_rounded,
                  onPressed: _confirmClearAll,
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _humanize(String value) {
    if (value.isEmpty) return 'Sự kiện';
    final text = value.replaceAll('_', ' ');
    return text[0].toUpperCase() + text.substring(1);
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final String value;
  final String current;
  final ValueChanged<String> onTap;
  const _FilterChip(
      {required this.label,
      required this.value,
      required this.current,
      required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final active = value == current;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: GestureDetector(
        onTap: () => onTap(value),
        child: Container(
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            color: active ? colors.primary : colors.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: active ? colors.primary : colors.border),
          ),
          child: Text(label,
              style: TextStyle(
                  color: active ? Colors.white : colors.textMuted,
                  fontWeight: FontWeight.w600,
                  fontSize: 12)),
        ),
      ),
    );
  }
}
