import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/auth_api.dart';
import '../api/client.dart';
import '../api/config.dart';
import '../api/google_auth.dart';
import '../config/user_modes.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_screen.dart';
import 'sharing_center_screen.dart';
import 'status_reports_screen.dart';
import 'work_hub_screen.dart';
import 'workspace_knowledge_screen.dart';
import 'workspace_members_screen.dart';

class SettingsScreen extends StatefulWidget {
  final VoidCallback onChangeMode;
  const SettingsScreen({super.key, required this.onChangeMode});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> with WidgetsBindingObserver {
  bool connectingGmail = false;
  bool startingPayment = false;
  bool waitingForPaymentReturn = false;
  bool deletingAccount = false;
  List<GoogleAccount> gmailAccounts = [];
  String? gmailAccountBusy;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadGmailAccounts();
  }

  Future<void> _loadGmailAccounts() async {
    try {
      final accounts = await listGoogleAccounts();
      if (mounted) setState(() => gmailAccounts = accounts);
    } catch (_) {
      if (mounted) setState(() => gmailAccounts = []);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !waitingForPaymentReturn) return;
    waitingForPaymentReturn = false;
    context.read<AppState>().refreshShell().then((_) {
      if (!mounted) return;
      final t = context.read<LanguageController>().t;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(t(
          'Đã làm mới trạng thái Premium sau khi quay lại từ SEPay.',
          'Premium status refreshed after returning from SEPay.',
        )),
      ));
    });
  }

  Future<void> _startSepayCheckout(String planCode) async {
    final t = context.read<LanguageController>().t;
    final profile = context.read<AppState>().profile;
    final subscription = profile?['subscription'] is Map
        ? Map<String, dynamic>.from(profile!['subscription'] as Map)
        : <String, dynamic>{};
    final isPremium = subscription['is_premium'] == true || subscription['tier'] == 'premium';
    setState(() => startingPayment = true);
    try {
      final data = await apiPost('/payments/sepay/checkout', {
        'action': isPremium ? 'renew' : 'purchase',
        'plan_code': planCode,
        'payment_method': 'BANK_TRANSFER',
      });
      final checkoutUrl = data is Map ? data['checkout_url'] as String? : null;
      final checkoutUri = checkoutUrl == null ? null : Uri.tryParse(checkoutUrl);
      if (checkoutUri == null) {
        throw const FormatException('SEPay checkout URL is missing');
      }
      waitingForPaymentReturn = true;
      final launched = await launchUrl(checkoutUri, mode: LaunchMode.externalApplication);
      if (!launched) throw Exception('Could not open SEPay');
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('${t('Không thể tạo đơn SEPay', 'Could not create SEPay checkout')}: ${error.message}'),
        ));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('${t('Không thể mở SEPay', 'Could not open SEPay')}: $error'),
        ));
      }
    } finally {
      if (mounted) setState(() => startingPayment = false);
    }
  }

  Future<void> _showPremiumPlans() async {
    final t = context.read<LanguageController>().t;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('FlowMate Premium', 'FlowMate Premium')),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.calendar_month_outlined),
              title: Text(t('Premium tháng', 'Monthly Premium')),
              subtitle: Text(t('49.000đ · 30 ngày', '49,000 VND · 30 days')),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.pop(dialogContext);
                _startSepayCheckout('premium_monthly');
              },
            ),
            const Divider(),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.workspace_premium_outlined),
              title: Text(t('Premium năm', 'Annual Premium')),
              subtitle: Text(t('520.000đ · 365 ngày', '520,000 VND · 365 days')),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.pop(dialogContext);
                _startSepayCheckout('premium_yearly');
              },
            ),
            const SizedBox(height: 8),
            Text(
              t(
                'Thanh toán một lần qua SEPay. Gói được kích hoạt sau khi IPN xác nhận.',
                'One-time payment via SEPay. The plan activates after IPN confirmation.',
              ),
              style: Theme.of(dialogContext).textTheme.bodySmall,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text(t('Đóng', 'Close')),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmDeleteAccount() async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Xóa tài khoản FlowMate?', 'Delete your FlowMate account?')),
        content: Text(t(
          'Thao tác này xóa vĩnh viễn hồ sơ, lịch, chat, dữ liệu cá nhân, kết nối Google và gói cá nhân. '
              'Workspace doanh nghiệp chỉ có bạn sẽ bị xóa; workspace còn thành viên sẽ được chuyển cho một thành viên đang hoạt động. Không thể hoàn tác.',
          'This permanently deletes your profile, schedules, chats, personal data, Google connection, and personal plan. '
              'Business workspaces with no other member are deleted; workspaces with active members are transferred to one of them. This cannot be undone.',
        )),
        actions: [
          TextButton(
            onPressed: () => launchUrl(
              Uri.parse(kAccountDeletionUrl),
              mode: LaunchMode.externalApplication,
            ),
            child: Text(t('Xem chính sách', 'View policy')),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(t('Hủy', 'Cancel')),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(t('Xóa vĩnh viễn', 'Delete permanently')),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    final appState = context.read<AppState>();
    setState(() => deletingAccount = true);
    try {
      await apiPost('/user/account/delete', const {'confirmation': 'DELETE'});
      await appState.logout();
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('${t('Không thể xóa tài khoản', 'Could not delete account')}: ${error.message}'),
        ));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('${t('Không thể xóa tài khoản', 'Could not delete account')}: $error'),
        ));
      }
    } finally {
      if (mounted) setState(() => deletingAccount = false);
    }
  }

  Future<void> _connectGmail() async {
    final t = context.read<LanguageController>().t;
    final appLinks = context.read<AppLinks>();
    setState(() => connectingGmail = true);
    try {
      final result = await connectGoogleAccount(appLinks);
      if (result.connected && mounted) {
        await context.read<AppState>().refreshShell();
        await _loadGmailAccounts();
      }
    } catch (error) {
      if (mounted) {
        await showGoogleAuthErrorDialog(
          context, error,
          title: t('Kết nối Gmail thất bại', 'Failed to connect Gmail'),
          onRetry: _connectGmail,
        );
      }
    } finally {
      if (mounted) setState(() => connectingGmail = false);
    }
  }

  Future<void> _switchGmailAccount(String accountEmail) async {
    final t = context.read<LanguageController>().t;
    setState(() => gmailAccountBusy = accountEmail);
    try {
      final accounts = await activateGoogleAccount(accountEmail);
      if (!mounted) return;
      setState(() => gmailAccounts = accounts);
      await context.read<AppState>().refreshShell();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${t('Không chuyển được tài khoản', 'Could not switch account')}: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => gmailAccountBusy = null);
    }
  }

  Future<void> _confirmRemoveGmailAccount(String accountEmail) async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Gỡ liên kết tài khoản', 'Unlink account')),
        content: Text(t(
          'Gỡ liên kết $accountEmail? FlowMate sẽ ngừng truy cập Gmail/Calendar của tài khoản này.',
          "Unlink $accountEmail? FlowMate will stop accessing this account's Gmail/Calendar.",
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Gỡ', 'Remove'))),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => gmailAccountBusy = accountEmail);
    try {
      final accounts = await removeGoogleAccount(accountEmail);
      if (!mounted) return;
      setState(() => gmailAccounts = accounts);
      await context.read<AppState>().refreshShell();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${t('Không gỡ được tài khoản', 'Could not remove account')}: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => gmailAccountBusy = null);
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

  Future<void> _confirmLogoutAllDevices(BuildContext context) async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Đăng xuất khỏi tất cả thiết bị?', 'Sign out of all devices?')),
        content: Text(t(
          'Mọi phiên đăng nhập trên điện thoại/máy tính khác sẽ bị hủy ngay lập tức. Dùng khi bạn nghi ngờ bị mất thiết bị hoặc lộ tài khoản.',
          'Every session on another phone or computer is revoked immediately. Use this if you suspect a device was lost or your account was compromised.',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Đăng xuất tất cả', 'Sign out everywhere'))),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await logoutAllDevices();
    } catch (_) {
      // The server-side revocation may have already succeeded even if this
      // response was lost (e.g. network dropped) -- either way, this
      // device's own token is now dead or about to be, so still log it out
      // locally below.
    } finally {
      if (context.mounted) {
        await context.read<AppState>().logout();
      }
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
    // Business-workspace collaboration (Thành viên/Công việc/Báo cáo/Chia
    // sẻ) is scoped to the "worker" and "business" user modes -- switching
    // to another mode (student, freelancer, mentor, teacher, creator)
    // hides these even if the account is still an active Business
    // workspace member, since the whole Worker Business Subscription
    // feature set is framed around the worker persona, not a
    // general-purpose feature for every mode.
    final canShowBusinessFeatures = mode.value == 'worker' || mode.value == 'business';
    final gmailReady = profile?['gmail_connected'] == true;
    final subscription = profile?['subscription'] is Map
        ? Map<String, dynamic>.from(profile!['subscription'] as Map)
        : <String, dynamic>{};
    final isPremium = subscription['is_premium'] == true || subscription['tier'] == 'premium';
    final remainingDays = subscription['remaining_days'] as num? ?? 0;

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
              label: 'PREMIUM',
              children: [
                _Row(
                  icon: Icons.workspace_premium_outlined,
                  iconBg: const Color(0xFFFFF3CD),
                  iconColor: const Color(0xFFD97706),
                  title: isPremium
                      ? t('FlowMate Premium', 'FlowMate Premium')
                      : (kExternalPaymentsEnabled
                          ? t('Nâng cấp Premium', 'Upgrade to Premium')
                          : t('FlowMate Premium', 'FlowMate Premium')),
                  subtitle: kExternalPaymentsEnabled
                      ? (isPremium
                          ? t('Còn $remainingDays ngày · Chạm để gia hạn', '$remainingDays days left · Tap to renew')
                          : t('Từ 49.000đ/tháng · Thanh toán qua SEPay', 'From 49,000 VND/month · Pay with SEPay'))
                      : (isPremium
                          ? t('Còn $remainingDays ngày', '$remainingDays days remaining')
                          : t('Không bán gói số trong bản Google Play.', 'Digital plans are not sold in the Google Play edition.')),
                  onTap: kExternalPaymentsEnabled && !startingPayment ? _showPremiumPlans : null,
                  trailing: kExternalPaymentsEnabled && startingPayment
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : null,
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
                if (gmailReady && gmailAccounts.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        t('Tài khoản Gmail đã liên kết', 'Linked Gmail accounts'),
                        style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w700, fontSize: 11, letterSpacing: 0.4),
                      ),
                      TextButton(
                        onPressed: connectingGmail ? null : _connectGmail,
                        style: TextButton.styleFrom(padding: EdgeInsets.zero, minimumSize: Size.zero),
                        child: Text('+ ${t('Thêm', 'Add')}', style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 12)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ...gmailAccounts.map((account) => _LinkedAccountRow(
                        account: account,
                        busy: gmailAccountBusy == account.accountEmail,
                        onSwitch: () => _switchGmailAccount(account.accountEmail),
                        onRemove: () => _confirmRemoveGmailAccount(account.accountEmail),
                      )),
                ],
              ],
            ),
            if (workspace.isBusiness && canShowBusinessFeatures)
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
                  _Row(
                    icon: Icons.menu_book_outlined,
                    iconBg: colors.primarySoft,
                    iconColor: colors.primary,
                    title: t('Kiến thức', 'Knowledge'),
                    subtitle: t('Policy, quy trình, FAQ dùng chung', 'Shared policies, processes, FAQs'),
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const WorkspaceKnowledgeScreen())),
                  ),
                ],
              ),
            // Not workspace-scoped (GET /api/user/sharing spans every
            // workspace the caller belongs to), so gated on membership in
            // ANY Business workspace rather than workspace.isBusiness
            // (which only reflects the currently active one).
            if (workspace.workspaces.any((w) => w['type'] == 'business') && canShowBusinessFeatures)
              _Section(
                label: t('RIÊNG TƯ', 'PRIVACY'),
                children: [
                  _Row(
                    icon: Icons.share_outlined,
                    iconBg: colors.primarySoft,
                    iconColor: colors.primary,
                    title: t('Trung tâm chia sẻ', 'Sharing Center'),
                    subtitle: t('Nội dung cá nhân bạn đã chia sẻ', 'Personal content you have shared'),
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const SharingCenterScreen())),
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
                AppButton(
                  title: t('Đăng xuất khỏi tất cả thiết bị', 'Sign out of all devices'),
                  variant: AppButtonVariant.secondary,
                  onPressed: () => _confirmLogoutAllDevices(context),
                ),
                const SizedBox(height: 10),
                AppButton(title: t('Đăng xuất', 'Sign out'), variant: AppButtonVariant.danger, onPressed: () => _confirmLogout(context)),
                const SizedBox(height: 10),
                AppButton(
                  title: t('Xóa tài khoản vĩnh viễn', 'Delete account permanently'),
                  variant: AppButtonVariant.danger,
                  onPressed: _confirmDeleteAccount,
                  loading: deletingAccount,
                ),
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

class _LinkedAccountRow extends StatelessWidget {
  final GoogleAccount account;
  final bool busy;
  final VoidCallback onSwitch;
  final VoidCallback onRemove;

  const _LinkedAccountRow({
    required this.account,
    required this.busy,
    required this.onSwitch,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final label = account.accountName.isNotEmpty ? account.accountName : account.accountEmail;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        border: Border.all(color: colors.border),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 16,
            backgroundColor: colors.primary,
            backgroundImage: account.accountPicture.isNotEmpty ? NetworkImage(account.accountPicture) : null,
            child: account.accountPicture.isEmpty
                ? Text(label.isNotEmpty ? label[0].toUpperCase() : '?', style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w700))
                : null,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                Text(account.accountEmail, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.textMuted, fontSize: 11)),
              ],
            ),
          ),
          if (busy)
            const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
          else if (account.isActive)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
              decoration: BoxDecoration(color: colors.success.withValues(alpha: 0.13), borderRadius: BorderRadius.circular(999)),
              child: Text('Active', style: TextStyle(color: colors.success, fontSize: 10, fontWeight: FontWeight.w700)),
            )
          else
            TextButton(
              onPressed: onSwitch,
              style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4), minimumSize: Size.zero),
              child: Text('Switch', style: TextStyle(color: colors.primary, fontSize: 11, fontWeight: FontWeight.w600)),
            ),
          if (!busy)
            TextButton(
              onPressed: onRemove,
              style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4), minimumSize: Size.zero),
              child: Text('Remove', style: TextStyle(color: colors.danger, fontSize: 11, fontWeight: FontWeight.w600)),
            ),
        ],
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
