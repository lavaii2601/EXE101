import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../config/app_icons.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';

/// Member/invitation management for the active Business workspace, reached
/// from Settings. Mirrors the web client's "Thành viên" page
/// (web/frontend/index.html workspace-members-page + its app.js
/// loadOrgWorkspaceMembers/submitOrgWorkspaceInvite functions).
class WorkspaceMembersScreen extends StatefulWidget {
  const WorkspaceMembersScreen({super.key});

  @override
  State<WorkspaceMembersScreen> createState() => _WorkspaceMembersScreenState();
}

class _WorkspaceMembersScreenState extends State<WorkspaceMembersScreen> {
  List<dynamic> members = [];
  List<dynamic> pendingInvitations = [];
  Map<String, dynamic>? subscriptionInfo;
  List<dynamic> seatRequests = [];
  bool loading = false;
  bool inviting = false;
  String? inviteResultLink;
  final emailController = TextEditingController();
  String inviteRole = 'worker';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    emailController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final workspaceId = context.read<WorkspaceController>().currentWorkspaceId;
    if (workspaceId == null) return;
    setState(() => loading = true);
    try {
      final data = await apiGet('/workspaces/$workspaceId/members');
      if (data is Map && data['success'] == true) {
        members = (data['members'] as List?) ?? [];
      }
    } catch (_) {}

    try {
      final data = await apiGet('/workspaces/$workspaceId/subscription');
      if (data is Map && data['success'] == true) {
        subscriptionInfo = Map<String, dynamic>.from(data);
      }
    } catch (_) {}

    if (!mounted) return;
    if (context.read<WorkspaceController>().canManage) {
      try {
        final data = await apiGet('/workspaces/$workspaceId/invitations');
        if (data is Map && data['success'] == true) {
          pendingInvitations = ((data['invitations'] as List?) ?? [])
              .where((i) => (i as Map)['status'] == 'pending')
              .toList();
        }
      } catch (_) {}

      try {
        final data = await apiGet('/workspaces/$workspaceId/seat-requests');
        if (data is Map && data['success'] == true) {
          seatRequests = ((data['seat_requests'] as List?) ?? [])
              .where((r) => (r as Map)['status'] == 'pending_owner')
              .toList();
        }
      } catch (_) {}
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> _resolveSeatRequest(String requestId, String action) async {
    final workspaceId = context.read<WorkspaceController>().currentWorkspaceId;
    if (workspaceId == null) return;
    try {
      await apiPost('/workspaces/$workspaceId/seat-requests/$requestId/$action', {});
      _load();
    } catch (_) {}
  }

  String _accessStateLabel(String? state, String Function(String, [String?]) t) {
    if (state == 'active') return t('Đang hoạt động', 'Active');
    if (state == 'grace') return t('Sắp hết hạn', 'Expiring soon');
    if (state == 'read_only') return t('Chỉ đọc (đã hết hạn)', 'Read-only (expired)');
    return t('Chưa có gói', 'No subscription yet');
  }

  Color _accessStateColor(String? state, AppColors colors) {
    if (state == 'active') return colors.success;
    if (state == 'grace') return colors.warning;
    if (state == 'read_only') return colors.danger;
    return colors.textMuted;
  }

  Future<void> _submitInvite() async {
    final workspaceId = context.read<WorkspaceController>().currentWorkspaceId;
    final t = context.read<LanguageController>().t;
    final email = emailController.text.trim();
    if (workspaceId == null || email.isEmpty) return;
    setState(() {
      inviting = true;
      inviteResultLink = null;
    });
    try {
      final data = await apiPost('/workspaces/$workspaceId/invitations', {'email': email, 'role': inviteRole});
      if (data is Map && data['success'] == true) {
        final token = (data['invitation'] as Map)['token'] as String?;
        setState(() => inviteResultLink = token);
        emailController.clear();
        await _load();
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('${t('Không gửi được lời mời', 'Could not send invitation')}: $error')));
      }
    } finally {
      if (mounted) setState(() => inviting = false);
    }
  }

  Future<void> _revokeInvitation(String invitationId) async {
    final workspaceId = context.read<WorkspaceController>().currentWorkspaceId;
    if (workspaceId == null) return;
    try {
      await apiDelete('/workspaces/$workspaceId/invitations/$invitationId');
      _load();
    } catch (_) {}
  }

  Future<void> _changeRole(String userId, String role) async {
    final workspaceId = context.read<WorkspaceController>().currentWorkspaceId;
    if (workspaceId == null) return;
    try {
      await apiPatch('/workspaces/$workspaceId/members/$userId/role', {'role': role});
      _load();
    } catch (_) {}
  }

  Future<void> _removeMember(String userId) async {
    final workspaceId = context.read<WorkspaceController>().currentWorkspaceId;
    final t = context.read<LanguageController>().t;
    if (workspaceId == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Xóa thành viên', 'Remove member')),
        content: Text(t('Xóa thành viên này khỏi không gian làm việc?', 'Remove this member from the workspace?')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Xóa', 'Remove'))),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await apiPost('/workspaces/$workspaceId/members/$userId/disable', {});
      _load();
    } catch (_) {}
  }

  String _roleLabel(String role, String Function(String, [String?]) t) {
    if (role == 'owner') return t('Chủ sở hữu', 'Owner');
    if (role == 'admin') return t('Quản trị', 'Admin');
    return t('Thành viên', 'Worker');
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final workspace = context.watch<WorkspaceController>();
    final canManage = workspace.canManage;

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
                    child: Text(t('Thành viên', 'Members'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
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
                      if (subscriptionInfo != null) ...[
                        AppCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t('GÓI DOANH NGHIỆP', 'BUSINESS PLAN'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                              const SizedBox(height: 10),
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      (subscriptionInfo!['subscription'] as Map?)?['plan_name'] as String? ?? t('Chưa có gói doanh nghiệp', 'No Business plan yet'),
                                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 14),
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: _accessStateColor(subscriptionInfo!['access_state'] as String?, colors).withValues(alpha: 0.14),
                                      borderRadius: BorderRadius.circular(999),
                                    ),
                                    child: Text(
                                      _accessStateLabel(subscriptionInfo!['access_state'] as String?, t),
                                      style: TextStyle(color: _accessStateColor(subscriptionInfo!['access_state'] as String?, colors), fontWeight: FontWeight.w700, fontSize: 10.5),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 6),
                              Text(
                                '${t('Chỗ đang dùng', 'Seats used')}: ${subscriptionInfo!['active_seats']} / ${subscriptionInfo!['seat_capacity']}',
                                style: TextStyle(color: colors.textMuted, fontSize: 12.5),
                              ),
                              if (subscriptionInfo!['access_state'] == 'grace') ...[
                                const SizedBox(height: 10),
                                Text(
                                  t(
                                    'Gói đã hết hạn, đang trong 7 ngày gia hạn. Sau đó không gian sẽ chuyển sang chỉ đọc.',
                                    'Your plan has expired and is in the 7-day grace period. After that, this workspace becomes read-only.',
                                  ),
                                  style: TextStyle(color: colors.warning, fontSize: 12),
                                ),
                              ],
                              if (subscriptionInfo!['access_state'] == 'read_only') ...[
                                const SizedBox(height: 10),
                                Text(
                                  t(
                                    'Không gian đang ở chế độ chỉ đọc do gói đã hết hạn. Gia hạn để tiếp tục chỉnh sửa.',
                                    'This workspace is read-only because its plan expired. Renew to resume editing.',
                                  ),
                                  style: TextStyle(color: colors.danger, fontSize: 12),
                                ),
                              ],
                            ],
                          ),
                        ),
                        const SizedBox(height: 14),
                      ],
                      AppCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('DANH SÁCH THÀNH VIÊN', 'MEMBER LIST'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 10),
                            ...members.map((raw) {
                              final m = Map<String, dynamic>.from(raw as Map);
                              final role = m['role'] as String? ?? 'worker';
                              return Padding(
                                padding: const EdgeInsets.only(bottom: 10),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(m['name'] as String? ?? m['email'] as String? ?? m['user_id'] as String, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                                          Text(m['email'] as String? ?? '', style: TextStyle(color: colors.textMuted, fontSize: 11.5)),
                                        ],
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                                      decoration: BoxDecoration(color: colors.primarySoft, borderRadius: BorderRadius.circular(999)),
                                      child: Text(_roleLabel(role, t), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10.5)),
                                    ),
                                    if (canManage && role != 'owner') ...[
                                      const SizedBox(width: 6),
                                      IconButton(
                                        icon: Icon(Icons.swap_horiz, size: 18, color: colors.textMuted),
                                        tooltip: t('Đổi vai trò', 'Change role'),
                                        onPressed: () => _changeRole(m['user_id'] as String, role == 'admin' ? 'worker' : 'admin'),
                                      ),
                                      IconButton(
                                        icon: Icon(Icons.person_remove_outlined, size: 18, color: colors.danger),
                                        tooltip: t('Xóa', 'Remove'),
                                        onPressed: () => _removeMember(m['user_id'] as String),
                                      ),
                                    ],
                                  ],
                                ),
                              );
                            }),
                            if (members.isEmpty) Text(t('Chưa có thành viên nào.', 'No members yet.'), style: TextStyle(color: colors.textMuted, fontSize: 13)),
                          ],
                        ),
                      ),
                      if (canManage) ...[
                        const SizedBox(height: 14),
                        AppCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t('MỜI THÀNH VIÊN', 'INVITE MEMBER'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                              const SizedBox(height: 10),
                              AppField(label: t('Email', 'Email'), controller: emailController, hint: 'email@congty.com', keyboardType: TextInputType.emailAddress),
                              Row(
                                children: [
                                  ChoiceChip(
                                    label: const Text('Worker'),
                                    selected: inviteRole == 'worker',
                                    onSelected: (_) => setState(() => inviteRole = 'worker'),
                                  ),
                                  const SizedBox(width: 8),
                                  ChoiceChip(
                                    label: const Text('Admin'),
                                    selected: inviteRole == 'admin',
                                    onSelected: (_) => setState(() => inviteRole = 'admin'),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              AppButton(title: t('Gửi lời mời', 'Send invitation'), onPressed: _submitInvite, loading: inviting),
                              if (inviteResultLink != null) ...[
                                const SizedBox(height: 10),
                                Text(
                                  t('Đã tạo lời mời. Gửi mã này cho người được mời:', 'Invitation created. Send this code to the invitee:'),
                                  style: TextStyle(color: colors.textMuted, fontSize: 12),
                                ),
                                const SizedBox(height: 4),
                                SelectableText(inviteResultLink!, style: TextStyle(color: colors.primary, fontSize: 12, fontWeight: FontWeight.w600)),
                              ],
                              if (pendingInvitations.isNotEmpty) ...[
                                const SizedBox(height: 14),
                                Text(t('LỜI MỜI ĐANG CHỜ', 'PENDING INVITATIONS'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                                const SizedBox(height: 8),
                                ...pendingInvitations.map((raw) {
                                  final inv = Map<String, dynamic>.from(raw as Map);
                                  return Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: Row(
                                      children: [
                                        Expanded(
                                          child: Text(inv['email_normalized'] as String? ?? '', style: TextStyle(color: colors.text, fontSize: 12.5)),
                                        ),
                                        TextButton(
                                          onPressed: () => _revokeInvitation(inv['id'] as String),
                                          child: Text(t('Thu hồi', 'Revoke'), style: TextStyle(color: colors.danger, fontSize: 12)),
                                        ),
                                      ],
                                    ),
                                  );
                                }),
                              ],
                            ],
                          ),
                        ),
                        if (seatRequests.isNotEmpty) ...[
                          const SizedBox(height: 14),
                          AppCard(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(t('YÊU CẦU THÊM CHỖ', 'SEAT REQUESTS'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                                const SizedBox(height: 10),
                                ...seatRequests.map((raw) {
                                  final r = Map<String, dynamic>.from(raw as Map);
                                  return Padding(
                                    padding: const EdgeInsets.only(bottom: 10),
                                    child: Row(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                '${t('Cần thêm', 'Needs')} ${r['requested_seats']} ${t('chỗ', 'seat(s)')}',
                                                style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13),
                                              ),
                                              Text(r['requested_by_user_id'] as String? ?? '', style: TextStyle(color: colors.textMuted, fontSize: 11.5)),
                                            ],
                                          ),
                                        ),
                                        TextButton(
                                          onPressed: () => _resolveSeatRequest(r['id'] as String, 'approve'),
                                          child: Text(t('Duyệt', 'Approve'), style: TextStyle(color: colors.success, fontSize: 12, fontWeight: FontWeight.w700)),
                                        ),
                                        TextButton(
                                          onPressed: () => _resolveSeatRequest(r['id'] as String, 'reject'),
                                          child: Text(t('Từ chối', 'Reject'), style: TextStyle(color: colors.danger, fontSize: 12)),
                                        ),
                                      ],
                                    ),
                                  );
                                }),
                              ],
                            ),
                          ),
                        ],
                      ],
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
