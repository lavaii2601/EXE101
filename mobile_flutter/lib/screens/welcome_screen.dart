import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/config.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/app_button.dart';

class WelcomeScreen extends StatelessWidget {
  final VoidCallback onGetStarted;
  final VoidCallback onLogIn;

  const WelcomeScreen(
      {super.key, required this.onGetStarted, required this.onLogIn});

  Future<void> _open(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Scaffold(
      backgroundColor: colors.background,
      body: FlowMateBackdrop(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _Illustration(colors: colors),
                const SizedBox(height: 12),
                Text(
                  t('EMAIL  /  LỊCH  /  CÔNG VIỆC',
                      'EMAIL  /  CALENDAR  /  WORK'),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      color: colors.textMuted,
                      fontSize: 9,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.7),
                ),
                const SizedBox(height: 18),
                Text(
                  t('Chào mừng đến với FlowMate AI', 'Welcome to FlowMate AI'),
                  style: TextStyle(
                      color: colors.text,
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                      height: 1.08,
                      letterSpacing: -0.8),
                ),
                const SizedBox(height: 10),
                Text(
                  t(
                    'Hành trình làm việc hiệu quả và tập trung rõ ràng bắt đầu từ đây.',
                    'Your journey to effortless productivity and clear focus begins here.',
                  ),
                  style: TextStyle(
                      color: colors.textMuted, fontSize: 13, height: 1.45),
                ),
                const SizedBox(height: 20),
                AppButton(
                    title: t('Bắt đầu', 'Get Started'),
                    icon: Icons.arrow_forward,
                    onPressed: onGetStarted),
                const SizedBox(height: 5),
                Center(
                  child: TextButton(
                    onPressed: onLogIn,
                    child: Text(t('Đăng nhập', 'Log In'),
                        style: TextStyle(
                            color: colors.primary,
                            fontWeight: FontWeight.w600,
                            fontSize: 14)),
                  ),
                ),
                const SizedBox(height: 14),
                _PolicyCard(colors: colors, t: t),
                const SizedBox(height: 12),
                Text(
                  t(
                    "Bằng việc tiếp tục, bạn đồng ý với Điều khoản dịch vụ, Chính sách quyền riêng tư của FlowMate AI "
                        "và các quyền hiển thị trên màn hình xác nhận của Google.",
                    "By continuing, you agree to FlowMate AI's Terms of Service, Privacy Policy, and the permissions "
                        "shown on Google's consent screen.",
                  ),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      color: colors.textMuted, fontSize: 11.5, height: 1.5),
                ),
                Wrap(
                  alignment: WrapAlignment.center,
                  children: [
                    TextButton(
                      onPressed: () => _open(kPrivacyUrl),
                      child: Text(t('Chính sách bảo mật', 'Privacy policy'),
                          style: TextStyle(
                              color: colors.primary,
                              fontWeight: FontWeight.w600,
                              fontSize: 11.5)),
                    ),
                    TextButton(
                      onPressed: () => _open(kTermsUrl),
                      child: Text(t('Điều khoản dịch vụ', 'Terms of service'),
                          style: TextStyle(
                              color: colors.primary,
                              fontWeight: FontWeight.w600,
                              fontSize: 11.5)),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Illustration extends StatelessWidget {
  final AppColors colors;
  const _Illustration({required this.colors});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 150,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: 96,
            height: 96,
            decoration: BoxDecoration(
              color: colors.panel.withValues(alpha: 0.72),
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: colors.border.withValues(alpha: 0.7)),
              boxShadow: [
                BoxShadow(
                    color: const Color(0xFF0058DE).withValues(alpha: 0.18),
                    blurRadius: 28,
                    offset: const Offset(0, 12)),
              ],
            ),
          ),
          Container(
            width: 74,
            height: 74,
            decoration: BoxDecoration(boxShadow: [
              BoxShadow(
                  color: const Color(0xFF0058DE).withValues(alpha: 0.3),
                  blurRadius: 22,
                  offset: const Offset(0, 8)),
            ]),
            child: Image.asset('assets/images/logo.png', fit: BoxFit.contain),
          ),
          Positioned(
              left: 28,
              top: 26,
              child: _FloatChip(
                  icon: Icons.mail_outline_rounded,
                  color: colors.primary,
                  colors: colors,
                  size: 36)),
          Positioned(
              right: 28,
              top: 24,
              child: _FloatChip(
                  icon: Icons.calendar_today_outlined,
                  color: colors.primary,
                  colors: colors,
                  size: 36)),
          Positioned(
              right: 44,
              bottom: 18,
              child: _FloatChip(
                  icon: Icons.check_rounded,
                  color: colors.success,
                  colors: colors,
                  size: 34)),
          Positioned(
              left: 69,
              top: 50,
              right: 69,
              child: Divider(
                  color: colors.primary.withValues(alpha: 0.2), thickness: 1)),
        ],
      ),
    );
  }
}

class _FloatChip extends StatelessWidget {
  final IconData icon;
  final Color color;
  final AppColors colors;
  final double size;
  const _FloatChip(
      {required this.icon,
      required this.color,
      required this.colors,
      this.size = 44});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: colors.panel,
        borderRadius: BorderRadius.circular(AppRadius.control),
        border: Border.all(color: colors.border),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 10,
              offset: const Offset(0, 4)),
        ],
      ),
      child: Icon(icon, size: size == 36 ? 16 : 18, color: color),
    );
  }
}

class _PolicyCard extends StatelessWidget {
  final AppColors colors;
  final String Function(String, [String?]) t;
  const _PolicyCard({required this.colors, required this.t});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colors.panel,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: colors.border),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 14,
              offset: const Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              t('Dữ liệu của bạn, do bạn kiểm soát', 'Your data, your control'),
              style: TextStyle(
                  color: colors.text,
                  fontWeight: FontWeight.w700,
                  fontSize: 16)),
          _PolicyLine(
            colors: colors,
            title: 'Gmail',
            detail: t('Đọc và tóm tắt email, deadline và yêu cầu công việc.',
                'Read and summarize messages, deadlines, and requests.'),
          ),
          _PolicyLine(
            colors: colors,
            title: 'Google Calendar',
            detail: t('Xem sự kiện và chỉ thay đổi sau khi bạn xác nhận.',
                'Show events and create changes only after confirmation.'),
          ),
          _PolicyLine(
            colors: colors,
            title: t('Quyền riêng tư', 'Privacy'),
            detail: t(
                'Chỉ lưu tóm tắt và hành động, không lưu toàn bộ nội dung email trừ khi cần thiết.',
                'Store summaries and actions, not full email content unless needed.'),
          ),
          _PolicyLine(
            colors: colors,
            title: t('Kiểm soát', 'Control'),
            detail: t(
                'Ngắt kết nối Google và xóa lịch sử hoạt động bất cứ lúc nào.',
                'Disconnect Google and delete activity history at any time.'),
          ),
        ],
      ),
    );
  }
}

class _PolicyLine extends StatelessWidget {
  final AppColors colors;
  final String title;
  final String detail;
  const _PolicyLine(
      {required this.colors, required this.title, required this.detail});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: TextStyle(
                  color: colors.text,
                  fontWeight: FontWeight.w600,
                  fontSize: 13)),
          const SizedBox(height: 2),
          Text(detail,
              style: TextStyle(
                  color: colors.textMuted, fontSize: 12.5, height: 1.4)),
        ],
      ),
    );
  }
}
