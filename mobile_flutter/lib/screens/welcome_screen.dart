import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/config.dart';
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
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const _Illustration(),
              const SizedBox(height: 40),
              Text(
                'Chào mừng đến với FlowMate AI',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.4,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Hành trình làm việc hiệu quả và tập trung rõ ràng bắt đầu từ đây.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textMuted, fontSize: 14.5, height: 1.5),
              ),
              const SizedBox(height: 40),
              AppButton(title: 'Bắt đầu', icon: Icons.arrow_forward, onPressed: onGetStarted),
              const SizedBox(height: 16),
              Center(
                child: TextButton(
                  onPressed: onLogIn,
                  child: Text(
                    'Đăng nhập',
                    style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600, fontSize: 14),
                  ),
                ),
              ),
              const SizedBox(height: 30),
              const _PolicyCard(),
              const SizedBox(height: 4),
              Text(
                "Bằng việc tiếp tục, bạn đồng ý với Điều khoản dịch vụ, Chính sách quyền riêng tư của FlowMate AI "
                "và các quyền hiển thị trên màn hình xác nhận của Google.",
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textMuted, fontSize: 11.5, height: 1.5),
              ),
              const SizedBox(height: 10),
              Center(
                child: TextButton(
                  onPressed: () => _open(kPrivacyUrl),
                  child: Text('Đọc chính sách bảo mật',
                      style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600, fontSize: 12.5)),
                ),
              ),
              Center(
                child: TextButton(
                  onPressed: () => _open(kTermsUrl),
                  child: Text('Đọc điều khoản dịch vụ',
                      style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600, fontSize: 12.5)),
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
  const _Illustration();

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
              color: AppColors.panel,
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.border),
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
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: AppColors.orbGradient,
              ),
              boxShadow: [
                BoxShadow(color: const Color(0xFF5A54FB).withValues(alpha: 0.5), blurRadius: 22, offset: const Offset(0, 10)),
              ],
            ),
            child: const Icon(Icons.auto_awesome, color: Colors.white, size: 52),
          ),
          Positioned(top: 8, right: 4, child: _FloatChip(icon: Icons.mail, color: AppColors.primary)),
          Positioned(bottom: 18, left: -2, child: _FloatChip(icon: Icons.calendar_today, color: AppColors.primary)),
          Positioned(
            bottom: 52,
            right: -10,
            child: _FloatChip(icon: Icons.check_circle, color: AppColors.success, size: 36),
          ),
        ],
      ),
    );
  }
}

class _FloatChip extends StatelessWidget {
  final IconData icon;
  final Color color;
  final double size;
  const _FloatChip({required this.icon, required this.color, this.size = 44});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(AppRadius.control),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 10, offset: const Offset(0, 4)),
        ],
      ),
      child: Icon(icon, size: size == 36 ? 16 : 18, color: color),
    );
  }
}

class _PolicyCard extends StatelessWidget {
  const _PolicyCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 14, offset: const Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Dữ liệu của bạn, do bạn kiểm soát',
              style: TextStyle(color: AppColors.text, fontWeight: FontWeight.w700, fontSize: 16)),
          const _PolicyLine(
            title: 'Gmail',
            detail: 'Đọc và tóm tắt email, deadline và yêu cầu công việc.',
          ),
          const _PolicyLine(
            title: 'Google Calendar',
            detail: 'Xem sự kiện và chỉ thay đổi sau khi bạn xác nhận.',
          ),
          const _PolicyLine(
            title: 'Quyền riêng tư',
            detail: 'Chỉ lưu tóm tắt và hành động, không lưu toàn bộ nội dung email trừ khi cần thiết.',
          ),
          const _PolicyLine(
            title: 'Kiểm soát',
            detail: 'Ngắt kết nối Google và xóa lịch sử hoạt động bất cứ lúc nào.',
          ),
        ],
      ),
    );
  }
}

class _PolicyLine extends StatelessWidget {
  final String title;
  final String detail;
  const _PolicyLine({required this.title, required this.detail});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(color: AppColors.text, fontWeight: FontWeight.w600, fontSize: 13)),
          const SizedBox(height: 2),
          Text(detail, style: TextStyle(color: AppColors.textMuted, fontSize: 12.5, height: 1.4)),
        ],
      ),
    );
  }
}
