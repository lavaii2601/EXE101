import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import 'app_button.dart';

/// Compact bar showing the active Business workspace, placed just below
/// ProfileHeader in MainShell. Tapping it opens a bottom sheet to switch
/// workspaces, create a new Business workspace, or accept an invitation by
/// pasting its token (no email delivery exists yet -- see design doc
/// section 1.1 -- so this is the real acceptance path for now, matching the
/// web client's `?invite=<token>` link that a user pastes/opens manually).
class OrgWorkspaceBar extends StatelessWidget {
  const OrgWorkspaceBar({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final workspace = context.watch<WorkspaceController>();
    final active = workspace.current;
    final isBusiness = active?['type'] == 'business';

    return InkWell(
      onTap: () => _openSwitcherSheet(context),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
        decoration: BoxDecoration(
          color: colors.panelSoft,
          border: Border(bottom: BorderSide(color: colors.border)),
        ),
        child: Row(
          children: [
            Text(isBusiness ? '🏢' : '👤', style: const TextStyle(fontSize: 16)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                active != null ? (active['name'] as String? ?? '') : t('Cá nhân', 'Personal'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13),
              ),
            ),
            Icon(Icons.unfold_more, size: 16, color: colors.textMuted),
          ],
        ),
      ),
    );
  }

  void _openSwitcherSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => const _OrgWorkspaceSwitcherSheet(),
    );
  }
}

class _OrgWorkspaceSwitcherSheet extends StatelessWidget {
  const _OrgWorkspaceSwitcherSheet();

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final workspace = context.watch<WorkspaceController>();

    return Container(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 24),
      decoration: BoxDecoration(color: colors.panel, borderRadius: const BorderRadius.vertical(top: Radius.circular(24))),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('Không gian làm việc', 'Workspaces'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
          const SizedBox(height: 12),
          if (workspace.loading)
            const Padding(padding: EdgeInsets.symmetric(vertical: 16), child: Center(child: CircularProgressIndicator()))
          else
            ...workspace.workspaces.map((w) {
              final active = w['id'] == workspace.currentWorkspaceId;
              return ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Text(w['type'] == 'business' ? '🏢' : '👤', style: const TextStyle(fontSize: 18)),
                title: Text(w['name'] as String? ?? '', style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                subtitle: w['member_role'] != null
                    ? Text(_roleLabel(w['member_role'] as String, t), style: TextStyle(color: colors.textMuted, fontSize: 11.5))
                    : null,
                trailing: active ? Icon(Icons.check_circle, color: colors.primary) : null,
                onTap: () {
                  workspace.switchWorkspace(w['id'] as String);
                  Navigator.pop(context);
                },
              );
            }),
          const SizedBox(height: 8),
          AppButton(
            title: t('+ Tạo không gian doanh nghiệp', '+ Create Business workspace'),
            variant: AppButtonVariant.secondary,
            onPressed: () {
              Navigator.pop(context);
              _openCreateWorkspaceDialog(context);
            },
          ),
          const SizedBox(height: 8),
          AppButton(
            title: t('Nhập mã lời mời', 'Enter invite code'),
            variant: AppButtonVariant.secondary,
            onPressed: () {
              Navigator.pop(context);
              _openAcceptInviteDialog(context);
            },
          ),
        ],
      ),
    );
  }

  String _roleLabel(String role, String Function(String, [String?]) t) {
    if (role == 'owner') return t('Chủ sở hữu', 'Owner');
    if (role == 'admin') return t('Quản trị', 'Admin');
    return t('Thành viên', 'Worker');
  }

  void _openCreateWorkspaceDialog(BuildContext context) {
    final controller = TextEditingController();
    final workspace = context.read<WorkspaceController>();
    final t = context.read<LanguageController>().t;
    showDialog(
      context: context,
      builder: (dialogContext) => _NamedActionDialog(
        title: t('Tạo không gian doanh nghiệp', 'Create Business workspace'),
        hint: t('Tên công ty / nhóm', 'Company / team name'),
        controller: controller,
        submitLabel: t('Tạo', 'Create'),
        onSubmit: () => workspace.createBusinessWorkspace(controller.text.trim()),
        successMessage: t('Đã tạo không gian doanh nghiệp', 'Business workspace created'),
      ),
    );
  }

  void _openAcceptInviteDialog(BuildContext context) {
    final controller = TextEditingController();
    final workspace = context.read<WorkspaceController>();
    final t = context.read<LanguageController>().t;
    showDialog(
      context: context,
      builder: (dialogContext) => _NamedActionDialog(
        title: t('Nhập mã lời mời', 'Enter invite code'),
        hint: t('Dán mã lời mời tại đây', 'Paste the invite code here'),
        controller: controller,
        submitLabel: t('Tham gia', 'Join'),
        onSubmit: () => workspace.acceptInvitation(_extractToken(controller.text.trim())),
        successMessage: t('Đã tham gia không gian doanh nghiệp', 'Joined the Business workspace'),
      ),
    );
  }

  /// Accepts either a raw token or a full web invite link
  /// (".../app?invite=<token>") so users can paste whichever they were sent.
  String _extractToken(String input) {
    final uri = Uri.tryParse(input);
    final fromQuery = uri?.queryParameters['invite'];
    return (fromQuery != null && fromQuery.isNotEmpty) ? fromQuery : input;
  }
}

class _NamedActionDialog extends StatefulWidget {
  final String title;
  final String hint;
  final TextEditingController controller;
  final String submitLabel;
  final Future<dynamic> Function() onSubmit;
  final String successMessage;

  const _NamedActionDialog({
    required this.title,
    required this.hint,
    required this.controller,
    required this.submitLabel,
    required this.onSubmit,
    required this.successMessage,
  });

  @override
  State<_NamedActionDialog> createState() => _NamedActionDialogState();
}

class _NamedActionDialogState extends State<_NamedActionDialog> {
  bool submitting = false;
  String? error;

  Future<void> _submit() async {
    if (widget.controller.text.trim().isEmpty) return;
    setState(() {
      submitting = true;
      error = null;
    });
    try {
      await widget.onSubmit();
      if (mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(widget.successMessage)));
      }
    } catch (e) {
      setState(() {
        submitting = false;
        error = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(controller: widget.controller, decoration: InputDecoration(hintText: widget.hint), autofocus: true),
          if (error != null) ...[
            const SizedBox(height: 8),
            Text(error!, style: const TextStyle(color: Colors.red, fontSize: 12.5)),
          ],
        ],
      ),
      actions: [
        TextButton(onPressed: submitting ? null : () => Navigator.pop(context), child: const Text('Hủy')),
        TextButton(onPressed: submitting ? null : _submit, child: Text(widget.submitLabel)),
      ],
    );
  }
}
