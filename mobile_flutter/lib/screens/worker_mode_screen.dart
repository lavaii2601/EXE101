import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import 'sharing_center_screen.dart';
import 'status_reports_screen.dart';
import 'work_hub_screen.dart';
import 'workspace_knowledge_screen.dart';
import 'workspace_members_screen.dart';

const Map<String, dynamic> _kEmptyDashboard = {
  'total_projects': 0,
  'total_tasks': 0,
  'overdue_tasks': 0,
  'active_members': 0,
  'project_counts': {},
  'task_counts': {},
  'latest_reports': [],
};

/// Dashboard-style aggregator for the 5 Business workspace tools (Work Hub,
/// Status Reports, Workspace Knowledge, Members, Sharing Center): stat
/// tiles from GET /work-hub/dashboard plus shortcut rows into each tool.
/// Shown as its own tab (see main_shell.dart) whenever the signed-in
/// user's mode is 'worker' or 'business', mirroring the RN client's
/// WorkerModeScreen -- unlike RN's modal-overlay pattern, each tool here is
/// a normal pushed route (consistent with how every other Flutter business
/// screen in this app already navigates), so the dashboard just reloads
/// its own stats when a pushed screen is popped instead of toggling a
/// `visible` prop.
class WorkerModeScreen extends StatefulWidget {
  const WorkerModeScreen({super.key});

  @override
  State<WorkerModeScreen> createState() => _WorkerModeScreenState();
}

class _WorkerModeScreenState extends State<WorkerModeScreen> {
  Map<String, dynamic> dashboard = Map<String, dynamic>.from(_kEmptyDashboard);
  bool loading = false;

  AppState? _appState;
  int _lastHandledSyncRevision = 0;

  @override
  void initState() {
    super.initState();
    _loadDashboard();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
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
    if (appState == null || appState.syncRevision == _lastHandledSyncRevision) return;
    _lastHandledSyncRevision = appState.syncRevision;
    final targets = appState.lastSyncTargets;
    if (targets.contains('work_hub') || targets.contains('status_reports') || targets.contains('workspace_members')) {
      _loadDashboard();
    }
  }

  @override
  void dispose() {
    _appState?.removeListener(_handleWorkspaceSync);
    super.dispose();
  }

  Future<void> _loadDashboard() async {
    final workspace = context.read<WorkspaceController>();
    if (!workspace.isBusiness) {
      setState(() => dashboard = Map<String, dynamic>.from(_kEmptyDashboard));
      return;
    }
    setState(() => loading = true);
    try {
      final data = await apiGet('/work-hub/dashboard');
      if (data is Map && data['success'] == true) {
        dashboard = {..._kEmptyDashboard, ...Map<String, dynamic>.from(data['dashboard'] as Map? ?? {})};
      }
    } catch (_) {
      dashboard = Map<String, dynamic>.from(_kEmptyDashboard);
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> _openTool(Widget screen) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
    _loadDashboard();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final workspace = context.watch<WorkspaceController>();

    final taskCounts = Map<String, dynamic>.from(dashboard['task_counts'] as Map? ?? {});
    final openTasks = (num.tryParse('${taskCounts['todo'] ?? 0}') ?? 0)
        + (num.tryParse('${taskCounts['in_progress'] ?? 0}') ?? 0)
        + (num.tryParse('${taskCounts['blocked'] ?? 0}') ?? 0);

    final metrics = [
      (value: '${dashboard['total_projects'] ?? 0}', label: t('Dự án', 'Projects'), color: colors.primary),
      (value: '$openTasks', label: t('Đang làm', 'Open tasks'), color: colors.secondaryText),
      (value: '${dashboard['overdue_tasks'] ?? 0}', label: t('Quá hạn', 'Overdue'), color: colors.warning),
      (value: '${dashboard['active_members'] ?? 0}', label: t('Thành viên', 'Members'), color: colors.success),
    ];

    final actions = [
      (
        icon: Icons.grid_view_outlined,
        title: t('Dự án & nhiệm vụ', 'Projects & tasks'),
        detail: t('Theo dõi công việc dùng chung', 'Track shared work'),
        color: colors.primary,
        onTap: () => _openTool(const WorkHubScreen()),
      ),
      (
        icon: Icons.assignment_outlined,
        title: t('Báo cáo trạng thái', 'Status reports'),
        detail: 'Done / Doing / Blocked / Next / Risks',
        color: colors.success,
        onTap: () => _openTool(const StatusReportsScreen()),
      ),
      (
        icon: Icons.menu_book_outlined,
        title: t('Kiến thức doanh nghiệp', 'Workspace knowledge'),
        detail: t('Policy, quy trình, template và FAQ', 'Policies, processes, templates, and FAQs'),
        color: colors.secondaryText,
        onTap: () => _openTool(const WorkspaceKnowledgeScreen()),
      ),
      (
        icon: Icons.people_outline,
        title: t('Thành viên', 'Members'),
        detail: t('Vai trò, lời mời và chỗ ngồi', 'Roles, invitations, and seats'),
        color: colors.warning,
        onTap: () => _openTool(const WorkspaceMembersScreen()),
      ),
    ];

    final latestReports = List<Map<String, dynamic>>.from(
      ((dashboard['latest_reports'] as List?) ?? []).map((r) => Map<String, dynamic>.from(r as Map)),
    );

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadDashboard,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: colors.panel,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: colors.border),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(color: colors.primarySoft, borderRadius: BorderRadius.circular(15)),
                      child: Icon(Icons.work_outline, size: 24, color: colors.primary),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('WORKER MODE', style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 9.5, letterSpacing: 1.2)),
                          const SizedBox(height: 2),
                          Text(t('Không gian công việc', 'Work Hub'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 20)),
                          Text(
                            (workspace.current?['name'] as String?) ?? t('Không gian cá nhân', 'Personal workspace'),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(color: colors.textMuted, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    if (loading) SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: colors.primary)),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (!workspace.isBusiness)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: colors.secondaryBg,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: colors.border),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(Icons.business_outlined, size: 22, color: colors.secondaryText),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('Chọn không gian doanh nghiệp', 'Choose a business workspace'),
                                style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                            const SizedBox(height: 3),
                            Text(
                              t(
                                'Dùng thanh không gian phía trên để mở dự án, báo cáo và kiến thức dùng chung.',
                                'Use the workspace bar above to open shared projects, reports, and knowledge.',
                              ),
                              style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                )
              else ...[
                Row(
                  children: [
                    Expanded(child: _MetricCard(metric: metrics[0], colors: colors)),
                    const SizedBox(width: 10),
                    Expanded(child: _MetricCard(metric: metrics[1], colors: colors)),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(child: _MetricCard(metric: metrics[2], colors: colors)),
                    const SizedBox(width: 10),
                    Expanded(child: _MetricCard(metric: metrics[3], colors: colors)),
                  ],
                ),
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: colors.panel,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: colors.border),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t('CÔNG CỤ NHÓM', 'TEAM TOOLS'),
                          style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1.1)),
                      const SizedBox(height: 6),
                      for (final action in actions)
                        InkWell(
                          onTap: action.onTap,
                          child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 11),
                            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: colors.border, width: 0.5))),
                            child: Row(
                              children: [
                                Container(
                                  width: 40,
                                  height: 40,
                                  decoration: BoxDecoration(color: colors.secondaryBg, borderRadius: BorderRadius.circular(12)),
                                  child: Icon(action.icon, size: 20, color: action.color),
                                ),
                                const SizedBox(width: 11),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(action.title, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13.5)),
                                      const SizedBox(height: 2),
                                      Text(action.detail, style: TextStyle(color: colors.textMuted, fontSize: 11, height: 1.3), maxLines: 2, overflow: TextOverflow.ellipsis),
                                    ],
                                  ),
                                ),
                                Icon(Icons.chevron_right, size: 18, color: colors.textMuted),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: colors.panel,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: colors.border),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(t('BÁO CÁO GẦN ĐÂY', 'LATEST REPORTS'),
                              style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1.1)),
                          TextButton(
                            style: TextButton.styleFrom(padding: EdgeInsets.zero, minimumSize: Size.zero, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                            onPressed: () => _openTool(const StatusReportsScreen()),
                            child: Text(t('Xem tất cả', 'See all'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 11)),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      if (latestReports.isEmpty)
                        Text(t('Chưa có báo cáo được công bố.', 'No published reports yet.'),
                            style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4))
                      else
                        for (final report in latestReports.take(3))
                          _ReportRow(report: report, colors: colors, t: t, onTap: () => _openTool(const StatusReportsScreen())),
                    ],
                  ),
                ),
              ],
              if (workspace.workspaces.any((w) => w['type'] == 'business')) ...[
                const SizedBox(height: 14),
                InkWell(
                  onTap: () => _openTool(const SharingCenterScreen()),
                  borderRadius: BorderRadius.circular(16),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: colors.panel,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: colors.border),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(color: colors.secondaryBg, borderRadius: BorderRadius.circular(12)),
                          child: Icon(Icons.share_outlined, size: 20, color: colors.secondaryText),
                        ),
                        const SizedBox(width: 11),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t('Trung tâm chia sẻ', 'Sharing Center'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13.5)),
                              const SizedBox(height: 2),
                              Text(t('Kiểm soát nội dung cá nhân đã chia sẻ', 'Control personal content you shared'),
                                  style: TextStyle(color: colors.textMuted, fontSize: 11)),
                            ],
                          ),
                        ),
                        Icon(Icons.chevron_right, size: 18, color: colors.textMuted),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  final ({String value, String label, Color color}) metric;
  final AppColors colors;
  const _MetricCard({required this.metric, required this.colors});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 100),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.panel,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(width: 9, height: 9, decoration: BoxDecoration(color: metric.color, shape: BoxShape.circle)),
          const SizedBox(height: 8),
          Text(metric.value, style: TextStyle(color: colors.text, fontWeight: FontWeight.w800, fontSize: 23)),
          Text(metric.label, style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w500, fontSize: 11)),
        ],
      ),
    );
  }
}

class _ReportRow extends StatelessWidget {
  final Map<String, dynamic> report;
  final AppColors colors;
  final String Function(String, [String?]) t;
  final VoidCallback onTap;
  const _ReportRow({required this.report, required this.colors, required this.t, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final published = report['status'] == 'published';
    final statusColor = published ? colors.success : colors.warning;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(color: statusColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(10)),
              child: Icon(published ? Icons.done_all : Icons.edit_outlined, size: 18, color: statusColor),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    (report['author_name'] as String?) ?? (report['author_user_id'] as String?) ?? t('Thành viên', 'Member'),
                    style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13.5),
                  ),
                  Text((report['report_date'] as String?) ?? '', style: TextStyle(color: colors.textMuted, fontSize: 11)),
                ],
              ),
            ),
            Text(
              published ? t('Đã công bố', 'Published') : t('Bản nháp', 'Draft'),
              style: TextStyle(color: statusColor, fontWeight: FontWeight.w600, fontSize: 10),
            ),
          ],
        ),
      ),
    );
  }
}
