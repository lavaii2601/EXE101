import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../api/google_auth.dart';
import '../config/user_modes.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';
import 'student_tools_screen.dart';

class OverviewScreen extends StatefulWidget {
  final void Function(int tabIndex)? onNavigate;
  final VoidCallback? onChangeMode;
  const OverviewScreen({super.key, this.onNavigate, this.onChangeMode});

  @override
  State<OverviewScreen> createState() => _OverviewScreenState();
}

class _OverviewScreenState extends State<OverviewScreen> {
  late String date;
  List<dynamic> schedules = [];
  List<dynamic> emails = [];
  Map<String, dynamic> checklist = {
    'revision': 0,
    'completed': {},
    'custom_items': []
  };
  bool loading = false;
  bool connectingGmail = false;
  // {'error': 'premium_required'} on a 403, null while loading/on any other
  // failure (mirrors mobile/src/screens/OverviewScreen.js's analytics state).
  Map<String, dynamic>? analytics;

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
        await showGoogleAuthErrorDialog(
          context,
          error,
          title: t('Kết nối Gmail thất bại', 'Failed to connect Gmail'),
          onRetry: _connectGmail,
        );
      }
    } finally {
      if (mounted) setState(() => connectingGmail = false);
    }
  }

  AppState? _appState;
  int _lastHandledSyncRevision = 0;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    date =
        '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    _load();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Cross-device sync: another device/the web app changed something this
    // dashboard summarizes while it was open -- AppState's poller (see
    // state/app_state.dart) notifies here so it doesn't sit stale until
    // manually reopened. Set up once per AppState instance
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
    if (targets.contains('overview') ||
        targets.contains('email') ||
        targets.contains('schedule') ||
        targets.contains('history')) {
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
      final results = await Future.wait([
        apiGet('/overview/daily?date=$date&max_results=50')
            .catchError((_) => {}),
        apiGet('/schedule/checklist?date=$date').catchError((_) => {}),
      ]);
      final overview = results[0] as Map<String, dynamic>? ?? {};
      final checklistData = results[1] as Map<String, dynamic>? ?? {};
      setState(() {
        schedules = (overview['schedules'] as List?) ?? [];
        emails = (overview['email_rows'] as List?) ??
            (overview['emails'] as List?) ??
            [];
        checklist = {
          'revision': checklistData['revision'] ?? 0,
          'completed': checklistData['completed'] ?? {},
          'custom_items': checklistData['custom_items'] ?? [],
        };
      });
    } finally {
      if (mounted) setState(() => loading = false);
    }
    await _loadAnalytics();
  }

  Future<void> _loadAnalytics() async {
    try {
      final data = await apiGet('/overview/analytics?days=7&end_date=$date');
      if (mounted) {
        setState(() =>
            analytics = data is Map ? data.cast<String, dynamic>() : null);
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => analytics =
          error.status == 403 && error.data['error'] == 'premium_required'
              ? {'error': 'premium_required'}
              : null);
    } catch (_) {
      if (mounted) setState(() => analytics = null);
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
      final saved =
          await apiPut('/schedule/checklist', {'date': date, ...nextState});
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
    final base = hour < 5
        ? 'Chào bạn'
        : hour < 12
            ? 'Chào buổi sáng'
            : hour < 18
                ? 'Chào buổi chiều'
                : 'Chào buổi tối';
    return name.isNotEmpty ? '$base, $name' : base;
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final appState = context.watch<AppState>();
    final name = (appState.profile?['name'] as String?) ?? '';
    final gmailConnected = appState.profile?['gmail_connected'] == true;
    final mode = getUserMode(appState.profile?['user_mode'] as String?);

    final checklistItems = _buildChecklistItems();
    final completedCount =
        checklistItems.where((c) => c['completed'] == true).length;
    final deadlines = schedules.where((s) => _isDeadline(s)).toList();
    final analyticsCard = _buildAnalyticsCard(colors, t);

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: '',
          refreshing: loading,
          onRefresh: _load,
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(14),
                border:
                    Border.all(color: colors.primary.withValues(alpha: 0.2)),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    colors.primary.withValues(alpha: 0.12),
                    const Color(0xFF0D9488).withValues(alpha: 0.08)
                  ],
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(date,
                      style: TextStyle(
                          color: colors.primary,
                          fontWeight: FontWeight.w600,
                          fontSize: 10,
                          letterSpacing: 1)),
                  const SizedBox(height: 2),
                  Text(_greeting('', '', name),
                      style: TextStyle(
                          color: colors.text,
                          fontWeight: FontWeight.w700,
                          fontSize: 18)),
                  const SizedBox(height: 10),
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(12),
                      onTap: widget.onChangeMode,
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 9),
                        decoration: BoxDecoration(
                          color: colors.panel.withValues(alpha: 0.68),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                              color: colors.border.withValues(alpha: 0.8)),
                        ),
                        child: Row(
                          children: [
                            Icon(mode.icon, size: 16, color: colors.primary),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                mode.label,
                                style: TextStyle(
                                  color: colors.text,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 12.5,
                                ),
                              ),
                            ),
                            Icon(Icons.keyboard_arrow_down_rounded,
                                size: 18, color: colors.textMuted),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    schedules.isEmpty && emails.isEmpty
                        ? t('Ngày $date chưa có email, deadline hoặc task nổi bật.',
                            'Nothing notable for $date yet.')
                        : t('Ngày này có ${emails.length} email, ${schedules.length} mục lịch/task và ${deadlines.length} deadline.',
                            '${emails.length} emails, ${schedules.length} schedule items, ${deadlines.length} deadlines today.'),
                    style: TextStyle(
                        color: colors.textMuted, fontSize: 13, height: 1.4),
                  ),
                ],
              ),
            ),
            Row(
              children: [
                Expanded(
                    child: _StatCard(
                        label: t('Deadline', 'Deadline'),
                        value: deadlines.length)),
                const SizedBox(width: 8),
                Expanded(
                    child: _StatCard(
                        label: t('Email', 'Email'), value: emails.length)),
                const SizedBox(width: 8),
                Expanded(
                    child: _StatCard(
                        label: t('Lịch', 'Calendar'), value: schedules.length)),
              ],
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
                          decoration: BoxDecoration(
                              color: colors.panel,
                              borderRadius: BorderRadius.circular(14)),
                          child: Icon(Icons.mark_email_unread_outlined,
                              color: colors.primary),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                  t('Kết nối Gmail để bắt đầu',
                                      'Connect Gmail to get started'),
                                  style: TextStyle(
                                      color: colors.text,
                                      fontWeight: FontWeight.w700,
                                      fontSize: 14)),
                              const SizedBox(height: 4),
                              Text(
                                t('Cho phép FlowMate đọc email và lịch của bạn để tóm tắt công việc hằng ngày.',
                                    'Allow FlowMate to read your email and calendar to summarize your day.'),
                                style: TextStyle(
                                    color: colors.textMuted,
                                    fontSize: 12,
                                    height: 1.4),
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
            if (mode.value == 'student')
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t('CÔNG CỤ SINH VIÊN', 'STUDENT TOOLS'),
                        style: TextStyle(
                            color: colors.primary,
                            fontWeight: FontWeight.w700,
                            fontSize: 10,
                            letterSpacing: 1)),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Expanded(
                          child: AppButton(
                            title: t('Tóm tắt tài liệu', 'Summarize material'),
                            variant: AppButtonVariant.secondary,
                            onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) =>
                                        const StudySummarizerScreen())),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: AppButton(
                            title: t('Tính GPA', 'Calculate GPA'),
                            variant: AppButtonVariant.secondary,
                            onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) =>
                                        const GpaCalculatorScreen())),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            AppCard(
              padding: const EdgeInsets.all(14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: colors.warning.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(Icons.flag_outlined,
                        size: 18, color: colors.warning),
                  ),
                  const SizedBox(width: 11),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(t('ƯU TIÊN', 'PRIORITY'),
                            style: TextStyle(
                                color: colors.warning,
                                fontWeight: FontWeight.w700,
                                fontSize: 9.5,
                                letterSpacing: 0.8)),
                        const SizedBox(height: 2),
                        Text(
                          deadlines.isEmpty
                              ? t('Không có deadline sắp tới',
                                  'No upcoming deadlines')
                              : (deadlines.first['title'] as String? ??
                                  t('Deadline gần nhất', 'Nearest deadline')),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              color: colors.text,
                              fontWeight: FontWeight.w600,
                              fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                  if (deadlines.length > 1)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: colors.panelSoft,
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text('+${deadlines.length - 1}',
                          style: TextStyle(
                              color: colors.textMuted,
                              fontWeight: FontWeight.w700,
                              fontSize: 10)),
                    ),
                ],
              ),
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
                            Text(t('CHECKLIST', 'CHECKLIST'),
                                style: TextStyle(
                                    color: colors.primary,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 10,
                                    letterSpacing: 1)),
                            Text(t('Việc trong ngày', "Today's items"),
                                style: TextStyle(
                                    color: colors.text,
                                    fontWeight: FontWeight.w600,
                                    fontSize: 14)),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 9, vertical: 5),
                        decoration: BoxDecoration(
                          color: colors.primarySoft,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          '$completedCount/${checklistItems.length} ${t('mục', 'items')}',
                          style: TextStyle(
                            color: colors.primary,
                            fontWeight: FontWeight.w700,
                            fontSize: 10.5,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  if (checklistItems.isEmpty)
                    AppEmptyState(
                        title: t('Checklist đang trống', 'Checklist is empty'))
                  else
                    ...checklistItems.map((item) => _ChecklistRow(
                          title: item['title'] as String,
                          completed: item['completed'] as bool,
                          onTap: () => _toggleChecklistItem(
                              item['id'] as String, item['completed'] as bool),
                        )),
                ],
              ),
            ),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('EMAIL', 'EMAIL'),
                      style: TextStyle(
                          color: colors.primary,
                          fontWeight: FontWeight.w700,
                          fontSize: 10,
                          letterSpacing: 1)),
                  Text(t('Mail quan trọng trong ngày', "Today's key emails"),
                      style: TextStyle(
                          color: colors.text,
                          fontWeight: FontWeight.w600,
                          fontSize: 14)),
                  const SizedBox(height: 8),
                  if (emails.isEmpty)
                    AppEmptyState(
                        icon: Icons.mail_outline,
                        title: t('Chưa có email nổi bật', 'No notable emails'))
                  else
                    ...emails.take(5).map((e) => _EmailRow(
                        subject: e['subject'] as String? ?? '',
                        sender: e['sender'] as String? ?? '')),
                ],
              ),
            ),
            if (analyticsCard != null) analyticsCard,
          ],
        ),
      ),
    );
  }

  Widget? _buildAnalyticsCard(
      AppColors colors, String Function(String, [String?]) t) {
    if (analytics?['error'] == 'premium_required') {
      return AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t('PHÂN TÍCH TUẦN', 'WEEKLY ANALYTICS'),
                style: TextStyle(
                    color: colors.primary,
                    fontWeight: FontWeight.w700,
                    fontSize: 10,
                    letterSpacing: 1)),
            const SizedBox(height: 6),
            Text(
                t('Phân tích tuần là tính năng Premium. Nâng cấp để xem xu hướng hoàn thành task và email theo ngày.',
                    'Weekly analytics is a Premium feature. Upgrade to see your task and email trends by day.'),
                style: TextStyle(color: colors.textMuted, fontSize: 12.5, height: 1.4)),
            const SizedBox(height: 10),
            AppButton(
              title: t('Mở khóa Premium', 'Unlock Premium'),
              variant: AppButtonVariant.secondary,
              onPressed: () => widget.onNavigate?.call(5),
            ),
          ],
        ),
      );
    }

    final daily = analytics?['daily'] is List
        ? List<Map<String, dynamic>>.from(analytics!['daily'] as List)
        : <Map<String, dynamic>>[];
    if (daily.isEmpty) return null;
    final totals = analytics?['totals'] is Map
        ? (analytics!['totals'] as Map).cast<String, dynamic>()
        : <String, dynamic>{};
    final weekdayLabels = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];
    final maxActivity = daily
        .map((d) => [
              (d['tasks_total'] as num?)?.toInt() ?? 0,
              (d['emails_total'] as num?)?.toInt() ?? 0
            ].reduce((a, b) => a > b ? a : b))
        .fold<int>(1, (a, b) => a > b ? a : b);
    final busiestDate = totals['busiest_date'] as String?;
    final busiestDay = daily.firstWhere(
        (d) => d['date'] == busiestDate, orElse: () => const {});
    final busiestLabel = busiestDay.isEmpty
        ? '—'
        : weekdayLabels[((busiestDay['weekday'] as num?)?.toInt() ?? 0) % 7];
    final rangeDays = (analytics?['range'] as Map?)?['days'] ?? daily.length;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('PHÂN TÍCH $rangeDays NGÀY', '$rangeDays-DAY ANALYTICS'),
              style: TextStyle(
                  color: colors.primary,
                  fontWeight: FontWeight.w700,
                  fontSize: 10,
                  letterSpacing: 1)),
          Text(t('Xu hướng hoạt động', 'Activity trend'),
              style: TextStyle(
                  color: colors.text,
                  fontWeight: FontWeight.w600,
                  fontSize: 14)),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                  child: _AnalyticsKpi(
                      value: '${totals['completion_rate'] ?? 0}%',
                      label: t('Hoàn thành task', 'Tasks done'))),
              Expanded(
                  child: _AnalyticsKpi(
                      value: '${totals['emails_total'] ?? 0}',
                      label: t('Email đã xử lý', 'Emails handled'))),
              Expanded(
                  child: _AnalyticsKpi(
                      value: '${totals['deadlines_total'] ?? 0}',
                      label: t('Deadline (${rangeDays}n)', 'Deadlines (${rangeDays}d)'))),
              Expanded(
                  child: _AnalyticsKpi(
                      value: busiestLabel,
                      label: t('Ngày bận nhất', 'Busiest day'))),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: 80,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: daily.map((d) {
                final taskTotal = (d['tasks_total'] as num?)?.toInt() ?? 0;
                final emailTotal = (d['emails_total'] as num?)?.toInt() ?? 0;
                final weekday = (d['weekday'] as num?)?.toInt() ?? 0;
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              width: 6,
                              height: 58 * taskTotal / maxActivity,
                              color: colors.primary,
                            ),
                            const SizedBox(width: 2),
                            Container(
                              width: 6,
                              height: 58 * emailTotal / maxActivity,
                              color: colors.success,
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(weekdayLabels[weekday % 7],
                            style:
                                TextStyle(color: colors.textMuted, fontSize: 10)),
                      ],
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _LegendDot(color: colors.primary, label: t('Task/Lịch', 'Tasks')),
              const SizedBox(width: 14),
              _LegendDot(color: colors.success, label: t('Email', 'Email')),
            ],
          ),
        ],
      ),
    );
  }

  bool _isDeadline(dynamic item) {
    final text =
        '${item['title'] ?? ''} ${item['description'] ?? ''}'.toLowerCase();
    return RegExp(r'deadline|hạn|nộp|due|submit').hasMatch(text);
  }

  List<Map<String, dynamic>> _buildChecklistItems() {
    final completed =
        Map<String, dynamic>.from(checklist['completed'] as Map? ?? {});
    final customItems = (checklist['custom_items'] as List? ?? [])
        .whereType<Map>()
        .map((item) => {
              'id': item['id'].toString(),
              'title': item['title'] as String? ?? '',
              'completed': item['completed'] == true ||
                  completed[item['id'].toString()] == true,
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
    }).toList();
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
          Text('$value',
              style: TextStyle(
                  color: colors.text,
                  fontWeight: FontWeight.w600,
                  fontSize: 20)),
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
  const _ChecklistRow(
      {required this.title, required this.completed, required this.onTap});

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
                border: Border.all(
                    color: completed ? colors.primary : colors.border,
                    width: 2),
              ),
              child: completed
                  ? const Icon(Icons.check, size: 14, color: Colors.white)
                  : null,
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

class _AnalyticsKpi extends StatelessWidget {
  final String value;
  final String label;
  const _AnalyticsKpi({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value,
            style: TextStyle(
                color: colors.text, fontWeight: FontWeight.w700, fontSize: 15)),
        Text(label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: colors.textMuted, fontSize: 10.5)),
      ],
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendDot({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label, style: TextStyle(color: colors.textMuted, fontSize: 11)),
      ],
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
    final initial =
        sender.trim().isNotEmpty ? sender.trim()[0].toUpperCase() : '?';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration:
                BoxDecoration(color: colors.primary, shape: BoxShape.circle),
            child: Center(
                child: Text(initial,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 13))),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(subject.isEmpty ? 'Email không tiêu đề' : subject,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        color: colors.text,
                        fontWeight: FontWeight.w600,
                        fontSize: 13)),
                Text(sender,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: colors.textMuted, fontSize: 11)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
