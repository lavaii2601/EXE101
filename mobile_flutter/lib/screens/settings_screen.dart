import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/google_auth.dart';
import '../config/user_modes.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_screen.dart';
import 'status_reports_screen.dart';
import 'work_hub_screen.dart';
import 'workspace_members_screen.dart';

class SettingsScreen extends StatefulWidget {
  final VoidCallback onChangeMode;
  const SettingsScreen({super.key, required this.onChangeMode});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
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

  Future<void> _confirmLogout(BuildContext context) async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Đăng xuất', 'Sign out')),
        content: Text(t('Bạn có chắc muốn đăng xuất?', 'Are you sure you want to sign out?')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Đăng xuất', 'Sign out'))),
        ],
      ),
    );
    if (confirmed == true && context.mounted) {
      await context.read<AppState>().logout();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = context.watch<ThemeController>();
    final lang = context.watch<LanguageController>();
    final appState = context.watch<AppState>();
    final workspace = context.watch<WorkspaceController>();
    final colors = theme.colors;
    final t = lang.t;
    final profile = appState.profile;
    final mode = getUserMode(profile?['user_mode'] as String?);
    final gmailReady = profile?['gmail_connected'] == true;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: t('Cài đặt', 'Settings'),
          onRefresh: appState.refreshShell,
          children: [
            _Section(
              label: t('TÀI KHOẢN', 'ACCOUNT'),
              children: [
                _Row(
                  icon: Icons.person_outline,
                  iconBg: colors.primarySoft,
                  iconColor: colors.primary,
                  title: (profile?['name'] as String?) ?? t('Người dùng', 'User'),
                  subtitle: (profile?['gmail_email'] as String?) ?? (profile?['email'] as String?) ?? '',
                ),
                const Divider(),
                _Row(
                  icon: mode.icon,
                  iconBg: colors.primarySoft,
                  iconColor: colors.primary,
                  title: t('Chế độ người dùng', 'User mode'),
                  subtitle: '${mode.label} · ${t('Chạm để thay đổi', 'Tap to change')}',
                  onTap: widget.onChangeMode,
                ),
              ],
            ),
            _Section(
              label: t('GIAO DIỆN', 'APPEARANCE'),
              children: [
                _SwitchRow(
                  icon: theme.isDark ? Icons.dark_mode : Icons.light_mode,
                  iconBg: theme.isDark ? const Color(0xFF1E3A5F) : const Color(0xFFE8EEF8),
                  iconColor: theme.isDark ? const Color(0xFF93C5FD) : const Color(0xFFF59E0B),
                  title: t('Chế độ hiển thị', 'Display theme'),
                  subtitle: theme.isDark ? t('Đang dùng chế độ tối', 'Currently using dark mode') : t('Đang dùng chế độ sáng', 'Currently using light mode'),
                  value: theme.isDark,
                  onChanged: (_) => theme.toggleTheme(),
                ),
                const Divider(),
                Text(t('Màu sắc chủ đạo', 'Accent color'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                const SizedBox(height: 10),
                Row(
                  children: kAccents.entries.map((entry) {
                    final selected = theme.accent == entry.key;
                    return Padding(
                      padding: const EdgeInsets.only(right: 12),
                      child: GestureDetector(
                        onTap: () => theme.setAccent(entry.key),
                        child: Container(
                          width: 34,
                          height: 34,
                          decoration: BoxDecoration(
                            color: entry.value.primary,
                            shape: BoxShape.circle,
                            border: selected ? Border.all(color: Colors.white, width: 3) : null,
                            boxShadow: selected ? [const BoxShadow(color: Colors.black26, blurRadius: 4)] : null,
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const Divider(),
                Text(t('Ngôn ngữ', 'Language'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                const SizedBox(height: 10),
                Row(
                  children: [
                    _LangChip(label: 'Tiếng Việt', selected: lang.language == 'vi', onTap: () => lang.setLanguage('vi')),
                    const SizedBox(width: 8),
                    _LangChip(label: 'English', selected: lang.language == 'en', onTap: () => lang.setLanguage('en')),
                  ],
                ),
              ],
            ),
            _Section(
              label: t('KẾT NỐI DỊCH VỤ', 'CONNECTED SERVICES'),
              children: [
                _Row(
                  icon: Icons.mail_outline,
                  iconBg: const Color(0xFFDBEAFE),
                  iconColor: const Color(0xFFEA4335),
                  title: 'Gmail & Google Calendar',
                  subtitle: gmailReady
                      ? ((profile?['gmail_email'] as String?) ?? t('Đã kết nối', 'Connected'))
                      : t('Chưa kết nối', 'Not connected'),
                  trailing: gmailReady
                      ? Text(t('Đã kết nối', 'Connected'), style: TextStyle(color: colors.success, fontSize: 11, fontWeight: FontWeight.w700))
                      : null,
                ),
                if (!gmailReady) ...[
                  const SizedBox(height: 10),
                  AppButton(
                    title: t('Kết nối Gmail', 'Connect Gmail'),
                    variant: AppButtonVariant.secondary,
                    onPressed: _connectGmail,
                    loading: connectingGmail,
                  ),
                ],
              ],
            ),
            if (workspace.isBusiness)
              _Section(
                label: t('DOANH NGHIỆP', 'BUSINESS'),
                children: [
                  _Row(
                    icon: Icons.groups_outlined,
                    iconBg: colors.primarySoft,
                    iconColor: colors.primary,
                    title: t('Thành viên', 'Members'),
                    subtitle: (workspace.current?['name'] as String?) ?? '',
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const WorkspaceMembersScreen())),
                  ),
                  _Row(
                    icon: Icons.dashboard_outlined,
                    iconBg: colors.primarySoft,
                    iconColor: colors.primary,
                    title: t('Công việc', 'Work Hub'),
                    subtitle: t('Dự án và nhiệm vụ dùng chung', 'Shared projects and tasks'),
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const WorkHubScreen())),
                  ),
                  _Row(
                    icon: Icons.assignment_outlined,
                    iconBg: colors.primarySoft,
                    iconColor: colors.primary,
                    title: t('Báo cáo trạng thái', 'Status Reports'),
                    subtitle: t('Done / Doing / Blocked / Next / Risks', 'Done / Doing / Blocked / Next / Risks'),
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const StatusReportsScreen())),
                  ),
                ],
              ),
            _Section(
              label: t('VỀ ỨNG DỤNG', 'ABOUT'),
              children: [
                _Row(icon: Icons.info_outline, iconBg: colors.secondaryBg, iconColor: colors.secondaryText, title: t('Phiên bản', 'Version'), subtitle: '1.0.0 (Flutter)'),
              ],
            ),
            _Section(
              label: t('HỖ TRỢ', 'SUPPORT'),
              children: [
                _Row(
                  icon: Icons.call_outlined,
                  iconBg: colors.secondaryBg,
                  iconColor: colors.secondaryText,
                  title: t('Điện thoại', 'Phone'),
                  subtitle: t('Đội ngũ CSKH FlowMate: +84 945 999 076', 'FlowMate support team: +84 945 999 076'),
                  onTap: () => launchUrl(Uri.parse('tel:+84945999076')),
                ),
                _Row(
                  icon: Icons.mail_outline,
                  iconBg: colors.secondaryBg,
                  iconColor: colors.secondaryText,
                  title: t('Email', 'Email'),
                  subtitle: t('Đội ngũ CSKH FlowMate: lecaoduyanh123@gmail.com', 'FlowMate support team: lecaoduyanh123@gmail.com'),
                  onTap: () => launchUrl(Uri.parse('mailto:lecaoduyanh123@gmail.com')),
                ),
              ],
            ),
            _Section(
              label: t('DỮ LIỆU', 'DATA'),
              children: [
                AppButton(title: t('Làm mới trạng thái', 'Refresh status'), variant: AppButtonVariant.secondary, onPressed: appState.refreshShell),
                const SizedBox(height: 10),
                AppButton(title: t('Đăng xuất', 'Sign out'), variant: AppButtonVariant.danger, onPressed: () => _confirmLogout(context)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String label;
  final List<Widget> children;
  const _Section({required this.label, required this.children});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.panel,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1.2)),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final Color iconColor;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;
  final Widget? trailing;

  const _Row({
    required this.icon,
    required this.iconBg,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    this.onTap,
    this.trailing,
  });

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
              width: 38,
              height: 38,
              decoration: BoxDecoration(color: iconBg, borderRadius: BorderRadius.circular(12)),
              child: Icon(icon, size: 18, color: iconColor),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                  Text(subtitle, maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.textMuted, fontSize: 12)),
                ],
              ),
            ),
            if (trailing != null) trailing!
            else if (onTap != null) Icon(Icons.chevron_right, color: colors.textMuted),
          ],
        ),
      ),
    );
  }
}

class _SwitchRow extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final Color iconColor;
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  const _SwitchRow({
    required this.icon,
    required this.iconBg,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Row(
      children: [
        Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(color: iconBg, borderRadius: BorderRadius.circular(12)),
          child: Icon(icon, size: 18, color: iconColor),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
              Text(subtitle, style: TextStyle(color: colors.textMuted, fontSize: 12)),
            ],
          ),
        ),
        Switch(value: value, onChanged: onChanged, activeTrackColor: colors.primary),
      ],
    );
  }
}

class _LangChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _LangChip({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: selected ? colors.primary : colors.secondaryBg,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(label, style: TextStyle(color: selected ? Colors.white : colors.secondaryText, fontWeight: FontWeight.w700, fontSize: 13)),
      ),
    );
  }
}
