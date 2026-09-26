import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../config/app_icons.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';

/// Shared policy/process/FAQ documents for the active Business workspace
/// ("Kien thuc doanh nghiep" / Business Knowledge), reached from Settings.
/// Mirrors the web client's "Kiến thức" page (web/frontend/js/workhub.js's
/// loadWorkspaceKnowledgePage/submitWorkspaceKnowledgeNew/
/// deleteWorkspaceKnowledgeDoc) and the RN client's WorkspaceKnowledgeScreen,
/// both on top of routes/workspace_knowledge.py's /api/workspace-knowledge
/// endpoints.
class WorkspaceKnowledgeScreen extends StatefulWidget {
  const WorkspaceKnowledgeScreen({super.key});

  @override
  State<WorkspaceKnowledgeScreen> createState() => _WorkspaceKnowledgeScreenState();
}

class _WorkspaceKnowledgeScreenState extends State<WorkspaceKnowledgeScreen> {
  List<Map<String, dynamic>> documents = [];
  bool loading = false;
  bool saving = false;

  final titleController = TextEditingController();
  final contentController = TextEditingController();
  final tagsController = TextEditingController();

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
    // Cross-device sync: another device/the web app added or removed a
    // document while this screen was open -- see schedule_screen.dart for
    // the same pattern.
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
    if (appState.lastSyncTargets.contains('workspace_knowledge')) {
      _load();
    }
  }

  @override
  void dispose() {
    _appState?.removeListener(_handleWorkspaceSync);
    titleController.dispose();
    contentController.dispose();
    tagsController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final workspace = context.read<WorkspaceController>();
    if (!workspace.isBusiness) {
      setState(() => documents = []);
      return;
    }
    setState(() => loading = true);
    try {
      final data = await apiGet('/workspace-knowledge');
      if (data is Map && data['success'] == true) {
        documents = List<Map<String, dynamic>>.from(
          ((data['documents'] as List?) ?? []).map((d) => Map<String, dynamic>.from(d as Map)),
        );
      }
    } catch (_) {}
    if (mounted) setState(() => loading = false);
  }

  Future<void> _createDocument() async {
    final t = context.read<LanguageController>().t;
    final title = titleController.text.trim();
    final content = contentController.text.trim();
    if (title.isEmpty || content.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(t('Vui lòng nhập tiêu đề và nội dung.', 'Please enter a title and content.'))),
      );
      return;
    }
    setState(() => saving = true);
    try {
      await apiPost('/workspace-knowledge', {
        'title': title,
        'content': content,
        if (tagsController.text.trim().isNotEmpty) 'tags': tagsController.text.trim(),
      });
      titleController.clear();
      contentController.clear();
      tagsController.clear();
      await _load();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${t('Không lưu được tài liệu', 'Could not save document')}: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _deleteDocument(Map<String, dynamic> document) async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Xóa tài liệu?', 'Delete document?')),
        content: Text(document['title'] as String? ?? ''),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Xóa', 'Delete'))),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await apiDelete('/workspace-knowledge/${document['id']}');
      if (mounted) {
        setState(() => documents = documents.where((d) => d['id'] != document['id']).toList());
      }
    } catch (_) {
      if (mounted) {
        final t = context.read<LanguageController>().t;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không xóa được tài liệu', 'Could not delete document'))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final workspace = context.watch<WorkspaceController>();

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 6, 20, 6),
              child: Row(
                children: [
                  IconButton(
                    icon: Icon(AppIcons.emailBack, color: colors.text),
                    onPressed: () => Navigator.pop(context),
                  ),
                  Expanded(
                    child: Text(
                      t('Kiến thức doanh nghiệp', 'Workspace Knowledge'),
                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17),
                    ),
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
                    if (!workspace.isBusiness)
                      AppEmptyState(
                        icon: Icons.menu_book_outlined,
                        title: t(
                          'Hãy chọn một không gian doanh nghiệp để xem tài liệu dùng chung.',
                          'Choose a business workspace to view shared documents.',
                        ),
                      )
                    else ...[
                      if (workspace.canManage) ...[
                        AppCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                t('THÊM TÀI LIỆU', 'ADD DOCUMENT'),
                                style: TextStyle(
                                  color: colors.primary,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 10,
                                  letterSpacing: 1,
                                ),
                              ),
                              const SizedBox(height: 10),
                              AppField(label: t('Tiêu đề', 'Title'), controller: titleController),
                              AppField(
                                label: t('Nội dung', 'Content'),
                                controller: contentController,
                                hint: t('Policy, quy trình, FAQ...', 'Policy, process, or FAQ content...'),
                                multiline: true,
                              ),
                              AppField(
                                label: t('Nhãn', 'Tags'),
                                controller: tagsController,
                                hint: t('Phân tách bằng dấu phẩy', 'Separated by commas'),
                              ),
                              const SizedBox(height: 4),
                              AppButton(
                                title: t('Lưu tài liệu', 'Save document'),
                                onPressed: _createDocument,
                                loading: saving,
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 14),
                      ],
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            t('TÀI LIỆU DOANH NGHIỆP', 'WORKSPACE DOCUMENTS'),
                            style: TextStyle(
                              color: colors.primary,
                              fontWeight: FontWeight.w700,
                              fontSize: 10,
                              letterSpacing: 1,
                            ),
                          ),
                          Text(
                            '${documents.length}',
                            style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w700, fontSize: 12),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      if (loading)
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 30),
                          child: Center(child: CircularProgressIndicator()),
                        )
                      else if (documents.isEmpty)
                        AppEmptyState(
                          icon: Icons.menu_book_outlined,
                          title: t('Chưa có tài liệu doanh nghiệp.', 'No workspace documents yet.'),
                        )
                      else
                        ...documents.map((document) {
                          final tags = (document['tags'] as String? ?? '')
                              .split(',')
                              .map((tag) => tag.trim())
                              .where((tag) => tag.isNotEmpty)
                              .toList();
                          return Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(13),
                            decoration: BoxDecoration(
                              color: colors.panelSoft,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: colors.border),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Icon(Icons.description_outlined, size: 18, color: colors.textMuted),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        document['title'] as String? ?? '',
                                        style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13.5),
                                      ),
                                    ),
                                    if (workspace.canManage)
                                      IconButton(
                                        icon: Icon(Icons.delete_outline, size: 18, color: colors.danger),
                                        onPressed: () => _deleteDocument(document),
                                        constraints: const BoxConstraints(),
                                        padding: const EdgeInsets.only(left: 8),
                                      ),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  document['content'] as String? ?? '',
                                  style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4),
                                ),
                                if (tags.isNotEmpty) ...[
                                  const SizedBox(height: 8),
                                  Wrap(
                                    spacing: 6,
                                    runSpacing: 6,
                                    children: tags
                                        .map((tag) => Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                              decoration: BoxDecoration(
                                                color: colors.secondaryBg,
                                                borderRadius: BorderRadius.circular(999),
                                              ),
                                              child: Text(
                                                tag,
                                                style: TextStyle(
                                                  color: colors.secondaryText,
                                                  fontWeight: FontWeight.w600,
                                                  fontSize: 10,
                                                ),
                                              ),
                                            ))
                                        .toList(),
                                  ),
                                ],
                              ],
                            ),
                          );
                        }),
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
