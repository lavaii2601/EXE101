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

  const WelcomeScreen({super.key, required this.onGetStarted, required this.onLogIn});

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
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Illustration(colors: colors),
              const SizedBox(height: 40),
              Text(
                t('Chào mừng đến với FlowMate AI', 'Welcome to FlowMate AI'),
                textAlign: TextAlign.center,
                style: TextStyle(color: colors.text, fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -0.4),
              ),
              const SizedBox(height: 12),
              Text(
                t(
                  'Hành trình làm việc hiệu quả và tập trung rõ ràng bắt đầu từ đây.',
                  'Your journey to effortless productivity and clear focus begins here.',
                ),
                textAlign: TextAlign.center,
                style: TextStyle(color: colors.textMuted, fontSize: 14.5, height: 1.5),
              ),
              const SizedBox(height: 40),
              AppButton(title: t('Bắt đầu', 'Get Started'), icon: Icons.arrow_forward, onPressed: onGetStarted),
              const SizedBox(height: 16),
              Center(
                child: TextButton(
                  onPressed: onLogIn,
                  child: Text(t('Đăng nhập', 'Log In'),
                      style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 14)),
                ),
              ),
              const SizedBox(height: 30),
              _PolicyCard(colors: colors, t: t),
              const SizedBox(height: 4),
              Text(
                t(
                  "Bằng việc tiếp tục, bạn đồng ý với Điều khoản dịch vụ, Chính sách quyền riêng tư của FlowMate AI "
                      "và các quyền hiển thị trên màn hình xác nhận của Google.",
                  "By continuing, you agree to FlowMate AI's Terms of Service, Privacy Policy, and the permissions "
                      "shown on Google's consent screen.",
                ),
                textAlign: TextAlign.center,
                style: TextStyle(color: colors.textMuted, fontSize: 11.5, height: 1.5),
              ),
              const SizedBox(height: 10),
              Center(
                child: TextButton(
                  onPressed: () => _open(kPrivacyUrl),
                  child: Text(t('Đọc chính sách bảo mật', 'Read privacy policy'),
                      style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 12.5)),
                ),
              ),
              Center(
                child: TextButton(
                  onPressed: () => _open(kTermsUrl),
                  child: Text(t('Đọc điều khoản dịch vụ', 'Read terms of service'),
                      style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 12.5)),
                ),
              ),
            ],
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
      width: 240,
      height: 240,
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          Container(
            width: 240,
            height: 240,
            decoration: BoxDecoration(
              color: colors.panel,
              shape: BoxShape.circle,
              border: Border.all(color: colors.border),
              boxShadow: [
                BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 14, offset: const Offset(0, 6)),
              ],
            ),
          ),
          Container(
            width: 140,
            height: 140,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: kOrbGradient),
              boxShadow: [
                BoxShadow(color: const Color(0xFF5A54FB).withValues(alpha: 0.5), blurRadius: 22, offset: const Offset(0, 10)),
              ],
            ),
            child: const Icon(Icons.auto_awesome, color: Colors.white, size: 52),
          ),
          Positioned(top: 8, right: 4, child: _FloatChip(icon: Icons.mail, color: colors.primary, colors: colors)),
          Positioned(bottom: 18, left: -2, child: _FloatChip(icon: Icons.calendar_today, color: colors.primary, colors: colors)),
          Positioned(
            bottom: 52,
            right: -10,
            child: _FloatChip(icon: Icons.check_circle, color: colors.success, colors: colors, size: 36),
          ),
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
  const _FloatChip({required this.icon, required this.color, required this.colors, this.size = 44});

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
          BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 10, offset: const Offset(0, 4)),
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
          BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 14, offset: const Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('Dữ liệu của bạn, do bạn kiểm soát', 'Your data, your control'),
              style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 16)),
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
            detail: t('Chỉ lưu tóm tắt và hành động, không lưu toàn bộ nội dung email trừ khi cần thiết.',
                'Store summaries and actions, not full email content unless needed.'),
          ),
          _PolicyLine(
            colors: colors,
            title: t('Kiểm soát', 'Control'),
            detail: t('Ngắt kết nối Google và xóa lịch sử hoạt động bất cứ lúc nào.',
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
  const _PolicyLine({required this.colors, required this.title, required this.detail});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
          const SizedBox(height: 2),
          Text(detail, style: TextStyle(color: colors.textMuted, fontSize: 12.5, height: 1.4)),
        ],
      ),
    );
  }
}
