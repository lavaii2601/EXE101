import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../config/app_icons.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';

const Map<String, (String vi, String en)> _kSourceTypeLabels = {
  'email_summary': ('Email', 'Email'),
  'calendar_event': ('Lịch', 'Calendar'),
  'note': ('Ghi chú', 'Note'),
  'document_reference': ('Tài liệu', 'Document'),
};

/// "Trung tam chia se" (Sharing Center, Phase 4): everything the caller has
/// personally shared into any Business workspace, with a revoke action.
/// Reached from Settings. Not workspace-scoped -- GET /api/user/sharing
/// spans every workspace the caller belongs to. Mirrors the web/RN Sharing
/// Center screens built on the same routes/sharing.py endpoints.
class SharingCenterScreen extends StatefulWidget {
  const SharingCenterScreen({super.key});

  @override
  State<SharingCenterScreen> createState() => _SharingCenterScreenState();
}

class _SharingCenterScreenState extends State<SharingCenterScreen> {
  List<Map<String, dynamic>> artifacts = [];
  bool loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await apiGet('/user/sharing');
      if (data is Map && data['success'] == true) {
        artifacts = List<Map<String, dynamic>>.from(
          ((data['artifacts'] as List?) ?? []).map((a) => Map<String, dynamic>.from(a as Map)),
        );
      }
    } catch (_) {}
    if (mounted) setState(() => loading = false);
  }

  Future<void> _revoke(Map<String, dynamic> artifact) async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Thu hồi chia sẻ này?', 'Revoke this share?')),
        content: Text(t(
          'Không gian sẽ không còn thấy nội dung này nữa.',
          'The workspace will no longer see this content.',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Thu hồi', 'Revoke'))),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await apiDelete('/workspaces/${artifact['workspace_id']}/shared-artifacts/${artifact['id']}');
      await _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không thu hồi được', 'Could not revoke'))),
        );
      }
    }
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
                    child: Text(t('Trung tâm chia sẻ', 'Sharing Center'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
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
                    else if (artifacts.isEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 40),
                        child: Text(
                          t("Bạn chưa chia sẻ nội dung nào.", "You haven't shared anything yet."),
                          textAlign: TextAlign.center,
                          style: TextStyle(color: colors.textMuted, fontSize: 13),
                        ),
                      )
                    else
                      ...artifacts.map((artifact) {
                        final sourceType = artifact['source_type'] as String? ?? '';
                        final sourceLabel = _kSourceTypeLabels[sourceType];
                        return Container(
                          margin: const EdgeInsets.only(bottom: 8),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: colors.panelSoft,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: colors.border),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(artifact['title'] as String? ?? '', style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                                    const SizedBox(height: 2),
                                    Text(
                                      '${artifact['workspace_name'] ?? ''} · ${sourceLabel != null ? t(sourceLabel.$1, sourceLabel.$2) : sourceType}',
                                      style: TextStyle(color: colors.textMuted, fontSize: 11),
                                    ),
                                  ],
                                ),
                              ),
                              TextButton(
                                onPressed: () => _revoke(artifact),
                                child: Text(t('Thu hồi', 'Revoke'), style: TextStyle(color: colors.danger, fontWeight: FontWeight.w600, fontSize: 12.5)),
                              ),
                            ],
                          ),
                        );
                      }),
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
