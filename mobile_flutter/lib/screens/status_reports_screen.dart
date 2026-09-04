import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../config/app_icons.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';

/// Manual Done/Doing/Blocked/Next/Risks Status Reports for the active
/// Business workspace (Phase 3, design doc section 8.5), reached from
/// Settings. Mirrors the web client's "Báo cáo" page (web/frontend/
/// index.html status-reports-page + its app.js loadStatusReportsPage/
/// submitStatusReportDraft/publishStatusReport functions) and
/// routes/work_hub.py's /api/status-reports endpoints. No Bob-AI-drafting
/// in this slice -- every report is filled in and reviewed by hand before
/// publishing, and publishing is one-way (content becomes immutable).
class StatusReportsScreen extends StatefulWidget {
  const StatusReportsScreen({super.key});

  @override
  State<StatusReportsScreen> createState() => _StatusReportsScreenState();
}

class _StatusReportsScreenState extends State<StatusReportsScreen> {
  List<Map<String, dynamic>> projects = [];
  List<Map<String, dynamic>> drafts = [];
  List<Map<String, dynamic>> published = [];
  bool loading = false;
  bool saving = false;

  String? selectedProjectId;
  final doneController = TextEditingController();
  final doingController = TextEditingController();
  final blockedController = TextEditingController();
  final nextController = TextEditingController();
  final risksController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    doneController.dispose();
    doingController.dispose();
    blockedController.dispose();
    nextController.dispose();
    risksController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await apiGet('/projects');
      if (data is Map && data['success'] == true) {
        projects = List<Map<String, dynamic>>.from(
          ((data['projects'] as List?) ?? []).map((p) => Map<String, dynamic>.from(p as Map)),
        );
      }
    } catch (_) {}
    try {
      final data = await apiGet('/status-reports?status=draft');
      if (data is Map && data['success'] == true) {
        drafts = List<Map<String, dynamic>>.from(
          ((data['reports'] as List?) ?? []).map((r) => Map<String, dynamic>.from(r as Map)),
        );
      }
    } catch (_) {}
    try {
      final data = await apiGet('/status-reports?status=published');
      if (data is Map && data['success'] == true) {
        published = List<Map<String, dynamic>>.from(
          ((data['reports'] as List?) ?? []).map((r) => Map<String, dynamic>.from(r as Map)),
        );
      }
    } catch (_) {}
    if (mounted) setState(() => loading = false);
  }

  String? _projectName(String? projectId) {
    if (projectId == null) return null;
    final match = projects.where((p) => p['id'] == projectId);
    return match.isEmpty ? null : match.first['name'] as String?;
  }

  Future<void> _saveDraft() async {
    setState(() => saving = true);
    try {
      await apiPost('/status-reports', {
        if (selectedProjectId != null) 'project_id': selectedProjectId,
        'done_text': doneController.text.trim(),
        'doing_text': doingController.text.trim(),
        'blocked_text': blockedController.text.trim(),
        'next_text': nextController.text.trim(),
        'risks_text': risksController.text.trim(),
      });
      doneController.clear();
      doingController.clear();
      blockedController.clear();
      nextController.clear();
      risksController.clear();
      selectedProjectId = null;
      if (mounted) {
        final t = context.read<LanguageController>().t;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('Đã lưu báo cáo nháp', 'Draft saved'))));
      }
      await _load();
    } catch (_) {
      if (mounted) {
        final t = context.read<LanguageController>().t;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không lưu được báo cáo', 'Could not save report'))),
        );
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _publish(String reportId) async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Công bố báo cáo?', 'Publish report?')),
        content: Text(t(
          'Công bố vào không gian doanh nghiệp. Sau khi công bố sẽ không thể chỉnh sửa nội dung nữa.',
          'This publishes it to the workspace. Once published, its content can no longer be edited.',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Công bố', 'Publish'))),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await apiPost('/status-reports/$reportId/publish', {});
      await _load();
    } catch (error) {
      if (mounted) {
        final message = error.toString().contains('report_empty')
            ? t('Báo cáo trống, hãy điền ít nhất một mục trước khi công bố.', 'The report is empty -- fill in at least one field before publishing.')
            : t('Không công bố được báo cáo', 'Could not publish report');
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      }
    }
  }

  Future<void> _deleteDraft(String reportId) async {
    try {
      await apiDelete('/status-reports/$reportId');
      await _load();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 6, 20, 6),
              child: Row(
                children: [
                  IconButton(icon: Icon(AppIcons.emailBack, color: colors.text), onPressed: () => Navigator.pop(context)),
                  Expanded(
                    child: Text(t('Báo cáo trạng thái', 'Status Reports'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
                  ),
                ],
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  children: [
                    if (loading)
                      const Padding(padding: EdgeInsets.symmetric(vertical: 40), child: Center(child: CircularProgressIndicator()))
                    else ...[
                      AppCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('BÁO CÁO MỚI', 'NEW REPORT'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 10),
                            DropdownButtonFormField<String?>(
                              value: selectedProjectId,
                              hint: Text(t('Không gắn với dự án cụ thể', 'Not tied to a specific project'), style: TextStyle(color: colors.textMuted, fontSize: 12.5)),
                              items: [
                                DropdownMenuItem<String?>(value: null, child: Text(t('Không gắn với dự án cụ thể', 'Not tied to a specific project'), style: TextStyle(color: colors.text, fontSize: 12.5))),
                                ...projects.map((p) => DropdownMenuItem<String?>(value: p['id'] as String, child: Text(p['name'] as String? ?? '', style: TextStyle(color: colors.text, fontSize: 12.5)))),
                              ],
                              onChanged: (v) => setState(() => selectedProjectId = v),
                            ),
                            const SizedBox(height: 8),
                            AppField(label: 'Done', controller: doneController, hint: t('Đã hoàn thành', 'What got done'), multiline: true),
                            AppField(label: 'Doing', controller: doingController, hint: t('Đang làm', 'What you are doing'), multiline: true),
                            AppField(label: 'Blocked', controller: blockedController, hint: t('Đang vướng', 'What is blocked'), multiline: true),
                            AppField(label: 'Next', controller: nextController, hint: t('Sắp tới', 'What is next'), multiline: true),
                            AppField(label: 'Risks', controller: risksController, hint: t('Rủi ro', 'Risks'), multiline: true),
                            const SizedBox(height: 8),
                            AppButton(title: t('Lưu nháp', 'Save draft'), onPressed: _saveDraft, loading: saving),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      AppCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('NHÁP CỦA TÔI', 'MY DRAFTS'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 10),
                            if (drafts.isEmpty)
                              Text(t('Chưa có báo cáo nháp.', 'No drafts yet.'), style: TextStyle(color: colors.textMuted, fontSize: 13)),
                            ...drafts.map((report) => _ReportCard(
                                  report: report,
                                  projectName: _projectName(report['project_id'] as String?),
                                  colors: colors,
                                  t: t,
                                  actions: Row(
                                    children: [
                                      TextButton(
                                        onPressed: () => _publish(report['id'] as String),
                                        child: Text(t('Công bố', 'Publish'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 12)),
                                      ),
                                      TextButton(
                                        onPressed: () => _deleteDraft(report['id'] as String),
                                        child: Text(t('Xoá', 'Delete'), style: TextStyle(color: colors.danger, fontSize: 12)),
                                      ),
                                    ],
                                  ),
                                )),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      AppCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('ĐÃ CÔNG BỐ', 'PUBLISHED'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 10),
                            if (published.isEmpty)
                              Text(t('Chưa có báo cáo nào được công bố.', 'No published reports yet.'), style: TextStyle(color: colors.textMuted, fontSize: 13)),
                            ...published.map((report) => _ReportCard(
                                  report: report,
                                  projectName: _projectName(report['project_id'] as String?),
                                  colors: colors,
                                  t: t,
                                )),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReportCard extends StatelessWidget {
  final Map<String, dynamic> report;
  final String? projectName;
  final AppColors colors;
  final String Function(String, [String?]) t;
  final Widget? actions;

  const _ReportCard({
    required this.report,
    required this.projectName,
    required this.colors,
    required this.t,
    this.actions,
  });

  @override
  Widget build(BuildContext context) {
    final fields = [
      ['Done', report['done_text'] as String? ?? ''],
      ['Doing', report['doing_text'] as String? ?? ''],
      ['Blocked', report['blocked_text'] as String? ?? ''],
      ['Next', report['next_text'] as String? ?? ''],
      ['Risks', report['risks_text'] as String? ?? ''],
    ].where((pair) => pair[1].trim().isNotEmpty).toList();

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: colors.panelSoft, borderRadius: BorderRadius.circular(12), border: Border.all(color: colors.border)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(report['report_date'] as String? ?? '', style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                    Text(projectName ?? t('Không gắn dự án', 'No project'), style: TextStyle(color: colors.textMuted, fontSize: 11)),
                  ],
                ),
              ),
              if (actions != null) actions!,
            ],
          ),
          const SizedBox(height: 6),
          ...fields.map((pair) => Padding(
                padding: const EdgeInsets.only(top: 4),
                child: RichText(
                  text: TextSpan(
                    style: TextStyle(color: colors.text, fontSize: 12, height: 1.4),
                    children: [
                      TextSpan(text: '${pair[0]}: ', style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700)),
                      TextSpan(text: pair[1]),
                    ],
                  ),
                ),
              )),
        ],
      ),
    );
  }
}
