import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
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

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await apiGet('/chat/history?limit=50');
      final items = (data is Map && data['history'] is List) ? List<Map<String, dynamic>>.from(data['history']) : <Map<String, dynamic>>[];
      setState(() => history = items);
    } catch (_) {
      // keep whatever we had; a transient failure shouldn't blank the log
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    final visible = filter == 'all' ? history : history.where((h) => (h['action_type'] as String? ?? '').contains(filter)).toList();

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: 'AI Audit Log',
          refreshing: loading,
          onRefresh: _load,
          children: [
            AppCard(
              child: Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(color: colors.primarySoft, borderRadius: BorderRadius.circular(14)),
                    child: Icon(Icons.shield_outlined, color: colors.primary),
                  ),
                  const SizedBox(width: 11),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(t('Nhật ký quyết định & hành động', 'Decisions & actions log'),
                            style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                        Text(t('${history.length} sự kiện gần nhất', '${history.length} recent events'),
                            style: TextStyle(color: colors.textMuted, fontSize: 10.5)),
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
                  _FilterChip(label: t('Tất cả', 'All'), value: 'all', current: filter, onTap: (v) => setState(() => filter = v)),
                  _FilterChip(label: 'AI', value: 'chat', current: filter, onTap: (v) => setState(() => filter = v)),
                  _FilterChip(label: t('Email', 'Email'), value: 'email', current: filter, onTap: (v) => setState(() => filter = v)),
                  _FilterChip(label: t('Lịch', 'Calendar'), value: 'schedule', current: filter, onTap: (v) => setState(() => filter = v)),
                ],
              ),
            ),
            if (visible.isEmpty)
              AppCard(child: AppEmptyState(icon: Icons.history_outlined, title: t('Chưa có sự kiện', 'No events yet')))
            else
              ...visible.map((item) {
                final actionType = item['action_type'] as String? ?? '';
                final id = item['id'] as int? ?? 0;
                final expanded = expandedId == id;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: GestureDetector(
                    onTap: () => setState(() => expandedId = expanded ? null : id),
                    child: AppCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(_actionIcons[actionType] ?? Icons.circle_outlined, size: 17, color: colors.primary),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(_humanize(actionType),
                                    style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 12.5)),
                              ),
                              Icon(expanded ? Icons.expand_less : Icons.expand_more, size: 16, color: colors.textMuted),
                            ],
                          ),
                          Padding(
                            padding: const EdgeInsets.only(top: 8, left: 25),
                            child: Text(
                              (item['user_message'] as String?) ?? (item['assistant_response'] as String?) ?? '',
                              maxLines: expanded ? null : 2,
                              overflow: expanded ? TextOverflow.visible : TextOverflow.ellipsis,
                              style: TextStyle(color: colors.textMuted, fontSize: 11, height: 1.4),
                            ),
                          ),
                          if (expanded && item['assistant_response'] != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 8, left: 25),
                              child: Text(
                                item['assistant_response'] as String,
                                style: TextStyle(color: colors.text, fontSize: 11.5, height: 1.4),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                );
              }),
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
  const _FilterChip({required this.label, required this.value, required this.current, required this.onTap});

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
          child: Text(label, style: TextStyle(color: active ? Colors.white : colors.textMuted, fontWeight: FontWeight.w600, fontSize: 12)),
        ),
      ),
    );
  }
}
