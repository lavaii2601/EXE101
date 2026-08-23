import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../api/google_auth.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';

class OverviewScreen extends StatefulWidget {
  final void Function(int tabIndex)? onNavigate;
  const OverviewScreen({super.key, this.onNavigate});

  @override
  State<OverviewScreen> createState() => _OverviewScreenState();
}

class _OverviewScreenState extends State<OverviewScreen> {
  late String date;
  List<dynamic> schedules = [];
  List<dynamic> emails = [];
  Map<String, dynamic> checklist = {'revision': 0, 'completed': {}, 'custom_items': []};
  bool loading = false;
  bool connectingGmail = false;

  Future<void> _connectGmail() async {
    final t = context.read<LanguageController>().t;
    final appLinks = context.read<AppLinks>();
    setState(() => connectingGmail = true);
    try {
      final result = await connectGoogleAccount(appLinks);
      if (result.connected && mounted) {
        await context.read<AppState>().refreshShell();
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('${t('Kết nối Gmail thất bại', 'Failed to connect Gmail')}: $error')));
      }
    } finally {
      if (mounted) setState(() => connectingGmail = false);
    }
  }

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    date = '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    _load();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final results = await Future.wait([
        apiGet('/overview/daily?date=$date&max_results=50').catchError((_) => {}),
        apiGet('/schedule/checklist?date=$date').catchError((_) => {}),
      ]);
      final overview = results[0] as Map<String, dynamic>? ?? {};
      final checklistData = results[1] as Map<String, dynamic>? ?? {};
      setState(() {
        schedules = (overview['schedules'] as List?) ?? [];
        emails = (overview['email_rows'] as List?) ?? (overview['emails'] as List?) ?? [];
        checklist = {
          'revision': checklistData['revision'] ?? 0,
          'completed': checklistData['completed'] ?? {},
          'custom_items': checklistData['custom_items'] ?? [],
        };
      });
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _toggleChecklistItem(String id, bool currentlyCompleted) async {
    final completed = Map<String, dynamic>.from(checklist['completed'] as Map);
    completed[id] = !currentlyCompleted;
    final nextState = {
      'revision': checklist['revision'],
      'completed': completed,
      'custom_items': checklist['custom_items'],
    };
    setState(() => checklist = nextState);
    try {
      final saved = await apiPut('/schedule/checklist', {'date': date, ...nextState});
      if (saved is Map<String, dynamic>) {
        setState(() => checklist = {
              'revision': saved['revision'] ?? 0,
              'completed': saved['completed'] ?? {},
              'custom_items': saved['custom_items'] ?? [],
            });
      }
    } catch (_) {}
  }

  String _greeting(String t1, String t2, String name) {
    final hour = DateTime.now().hour;
    final base = hour < 5 ? 'Chào bạn' : hour < 12 ? 'Chào buổi sáng' : hour < 18 ? 'Chào buổi chiều' : 'Chào buổi tối';
    return name.isNotEmpty ? '$base, $name' : base;
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final appState = context.watch<AppState>();
    final name = (appState.profile?['name'] as String?) ?? '';
    final gmailConnected = appState.profile?['gmail_connected'] == true;

    final checklistItems = _buildChecklistItems();
    final completedCount = checklistItems.where((c) => c['completed'] == true).length;
    final deadlines = schedules.where((s) => _isDeadline(s)).toList();

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: t('Tổng hợp', 'Overview'),
          refreshing: loading,
          onRefresh: _load,
          actions: AppButton(title: t('Tải lại', 'Refresh'), variant: AppButtonVariant.secondary, onPressed: _load),
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: colors.primary.withValues(alpha: 0.2)),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [colors.primary.withValues(alpha: 0.12), const Color(0xFF0D9488).withValues(alpha: 0.08)],
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(date, style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 2),
                            Text(_greeting('', '', name), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 18)),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(color: colors.primary, borderRadius: BorderRadius.circular(12)),
                        child: Column(
                          children: [
                            Text('${schedules.length + emails.length}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 18)),
                            Text(t('việc cần xem', 'to review'), style: const TextStyle(color: Colors.white, fontSize: 9)),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    schedules.isEmpty && emails.isEmpty
                        ? t('Ngày $date chưa có email, deadline hoặc task nổi bật.', 'Nothing notable for $date yet.')
                        : t('Ngày này có ${emails.length} email, ${schedules.length} mục lịch/task và ${deadlines.length} deadline.',
                            '${emails.length} emails, ${schedules.length} schedule items, ${deadlines.length} deadlines today.'),
                    style: TextStyle(color: colors.textMuted, fontSize: 13, height: 1.4),
                  ),
                ],
              ),
            ),
            if (!gmailConnected)
              AppCard(
                borderColor: colors.primary.withValues(alpha: 0.33),
                backgroundColor: colors.primarySoft,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(color: colors.panel, borderRadius: BorderRadius.circular(14)),
                          child: Icon(Icons.mark_email_unread_outlined, color: colors.primary),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t('Kết nối Gmail để bắt đầu', 'Connect Gmail to get started'),
                                  style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 14)),
                              const SizedBox(height: 4),
                              Text(
                                t('Cho phép FlowMate đọc email và lịch của bạn để tóm tắt công việc hằng ngày.',
                                    'Allow FlowMate to read your email and calendar to summarize your day.'),
                                style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    AppButton(
                      title: t('Kết nối Gmail', 'Connect Gmail'),
                      icon: Icons.link,
                      onPressed: _connectGmail,
                      loading: connectingGmail,
                    ),
                  ],
                ),
              ),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('ĐẾM NGƯỢC', 'COUNTDOWN'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                  const SizedBox(height: 2),
                  Text(t('Deadline gần nhất', 'Nearest deadline'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                  const SizedBox(height: 10),
                  if (deadlines.isEmpty)
                    AppEmptyState(icon: Icons.flag_outlined, title: t('Không có deadline sắp tới', 'No upcoming deadlines'))
                  else
                    ...deadlines.take(3).map((d) => Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Row(
                            children: [
                              Icon(Icons.flag, size: 14, color: colors.danger),
                              const SizedBox(width: 8),
                              Expanded(child: Text(d['title'] as String? ?? '', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.text, fontSize: 13))),
                            ],
                          ),
                        )),
                ],
              ),
            ),
            Row(
              children: [
                Expanded(child: _StatCard(label: t('Deadline', 'Deadline'), value: deadlines.length)),
                const SizedBox(width: 8),
                Expanded(child: _StatCard(label: t('Email', 'Email'), value: emails.length)),
                const SizedBox(width: 8),
                Expanded(child: _StatCard(label: t('Task', 'Tasks'), value: schedules.length)),
              ],
            ),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('CHECKLIST', 'CHECKLIST'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            Text(t('Việc trong ngày', "Today's items"), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                            const SizedBox(height: 4),
                            Text('$completedCount/${checklistItems.length} ${t('đã xong', 'done')}', style: TextStyle(color: colors.textMuted, fontSize: 11)),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  if (checklistItems.isEmpty)
                    AppEmptyState(title: t('Checklist đang trống', 'Checklist is empty'))
                  else
                    ...checklistItems.map((item) => _ChecklistRow(
                          title: item['title'] as String,
                          completed: item['completed'] as bool,
                          onTap: () => _toggleChecklistItem(item['id'] as String, item['completed'] as bool),
                        )),
                ],
              ),
            ),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('EMAIL', 'EMAIL'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                  Text(t('Mail quan trọng trong ngày', "Today's key emails"), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                  const SizedBox(height: 8),
                  if (emails.isEmpty)
                    AppEmptyState(icon: Icons.mail_outline, title: t('Chưa có email nổi bật', 'No notable emails'))
                  else
                    ...emails.take(5).map((e) => _EmailRow(subject: e['subject'] as String? ?? '', sender: e['sender'] as String? ?? '')),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  bool _isDeadline(dynamic item) {
    final text = '${item['title'] ?? ''} ${item['description'] ?? ''}'.toLowerCase();
    return RegExp(r'deadline|hạn|nộp|due|submit').hasMatch(text);
  }

  List<Map<String, dynamic>> _buildChecklistItems() {
    final completed = Map<String, dynamic>.from(checklist['completed'] as Map? ?? {});
    final customItems = (checklist['custom_items'] as List? ?? [])
        .whereType<Map>()
        .map((item) => {
              'id': item['id'].toString(),
              'title': item['title'] as String? ?? '',
              'completed': item['completed'] == true || completed[item['id'].toString()] == true,
            })
        .toList();
    final scheduleItems = schedules
        .where((s) => s['status'] != 'cancelled' && s['status'] != 'dismissed')
        .map((s) {
          final id = 'schedule:${s['title']}-${s['start_time']}';
          return {
            'id': id,
            'title': s['title'] as String? ?? '',
            'completed': completed[id] == true || s['status'] == 'completed',
          };
        })
        .toList();
    return [...customItems, ...scheduleItems];
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final int value;
  const _StatCard({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return AppCard(
      padding: const EdgeInsets.symmetric(vertical: 13, horizontal: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$value', style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 20)),
          Text(label, style: TextStyle(color: colors.textMuted, fontSize: 11)),
        ],
      ),
    );
  }
}

class _ChecklistRow extends StatelessWidget {
  final String title;
  final bool completed;
  final VoidCallback onTap;
  const _ChecklistRow({required this.title, required this.completed, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                color: completed ? colors.primary : colors.panel,
                borderRadius: BorderRadius.circular(7),
                border: Border.all(color: completed ? colors.primary : colors.border, width: 2),
              ),
              child: completed ? const Icon(Icons.check, size: 14, color: Colors.white) : null,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                title,
                style: TextStyle(
                  color: completed ? colors.textMuted : colors.text,
                  fontSize: 13,
                  decoration: completed ? TextDecoration.lineThrough : null,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmailRow extends StatelessWidget {
  final String subject;
  final String sender;
  const _EmailRow({required this.subject, required this.sender});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final initial = sender.trim().isNotEmpty ? sender.trim()[0].toUpperCase() : '?';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(color: colors.primary, shape: BoxShape.circle),
            child: Center(child: Text(initial, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13))),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(subject.isEmpty ? 'Email không tiêu đề' : subject, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                Text(sender, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.textMuted, fontSize: 11)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
