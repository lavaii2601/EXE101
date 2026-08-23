import 'package:flutter/material.dart';
import '../api/auth_api.dart';
import '../api/session.dart';
import '../theme/app_theme.dart';
import '../widgets/app_button.dart';

class LoginScreen extends StatefulWidget {
  final VoidCallback onLoggedIn;
  const LoginScreen({super.key, required this.onLoggedIn});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  bool isSignup = false;
  bool showPassword = false;
  bool submitting = false;

  final nameController = TextEditingController();
  final emailController = TextEditingController();
  final passwordController = TextEditingController();

  @override
  void dispose() {
    nameController.dispose();
    emailController.dispose();
    passwordController.dispose();
    super.dispose();
  }

  void _toggleMode() {
    setState(() {
      isSignup = !isSignup;
      passwordController.clear();
    });
  }

  void _showMessage(String title, String message) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Đã hiểu'))],
      ),
    );
  }

  Future<void> _handleSubmit() async {
    if (isSignup && nameController.text.trim().isEmpty) {
      _showMessage('Thiếu thông tin', 'Vui lòng nhập họ tên.');
      return;
    }
    if (emailController.text.trim().isEmpty || passwordController.text.isEmpty) {
      _showMessage('Thiếu thông tin', 'Vui lòng nhập email và mật khẩu.');
      return;
    }
    setState(() => submitting = true);
    try {
      final result = isSignup
          ? await registerWithEmail(
              name: nameController.text.trim(),
              email: emailController.text.trim(),
              password: passwordController.text,
            )
          : await loginWithEmail(
              email: emailController.text.trim(),
              password: passwordController.text,
            );
      await setMobileSession(userId: result.userId, accessToken: result.accessToken);
      widget.onLoggedIn();
    } catch (error) {
      _showMessage(
        isSignup ? 'Không tạo được tài khoản' : 'Không đăng nhập được',
        error.toString(),
      );
    } finally {
      if (mounted) setState(() => submitting = false);
    }
  }

  void _handleGoogleSignIn() {
    // Native Google Sign-In needs its own OAuth client setup
    // (google-services.json, SHA-1 fingerprint) -- out of scope for this
    // first Flutter screen pass. The React Native app's flow is the
    // reference implementation once that's wired up here.
    _showMessage('Sắp có', 'Đăng nhập Google trên bản Flutter đang được hoàn thiện.');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'FlowMate AI',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.text, fontWeight: FontWeight.w800, fontSize: 22, letterSpacing: -0.4),
              ),
              const SizedBox(height: 18),
              Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  color: AppColors.panel,
                  borderRadius: BorderRadius.circular(AppRadius.card),
                  border: Border.all(color: AppColors.border),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 14, offset: const Offset(0, 6)),
                  ],
                ),
                child: Column(
                  children: [
                    Container(
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(AppRadius.control),
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: AppColors.orbGradient,
                        ),
                        boxShadow: [
                          BoxShadow(color: const Color(0xFF5A54FB).withValues(alpha: 0.4), blurRadius: 16, offset: const Offset(0, 8)),
                        ],
                      ),
                      child: const Icon(Icons.auto_awesome, color: Colors.white, size: 26),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      isSignup ? 'Tạo tài khoản' : 'Chào mừng trở lại',
                      style: TextStyle(color: AppColors.text, fontWeight: FontWeight.w700, fontSize: 20),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      isSignup ? 'Tham gia FlowMate AI ngay hôm nay.' : 'Vui lòng nhập thông tin để đăng nhập.',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 13),
                    ),
                    if (isSignup) ...[
                      const SizedBox(height: 18),
                      _LabeledField(
                        label: 'Họ và tên',
                        icon: Icons.person_outline,
                        controller: nameController,
                        hint: 'Nhập họ và tên',
                      ),
                    ],
                    const SizedBox(height: 18),
                    _LabeledField(
                      label: 'Email',
                      icon: Icons.mail_outline,
                      controller: emailController,
                      hint: 'name@company.com',
                      keyboardType: TextInputType.emailAddress,
                    ),
                    const SizedBox(height: 18),
                    Row(
                      children: [
                        Text('Mật khẩu', style: TextStyle(color: AppColors.text, fontWeight: FontWeight.w600, fontSize: 12.5)),
                        const Spacer(),
                        if (!isSignup)
                          TextButton(
                            style: TextButton.styleFrom(padding: EdgeInsets.zero, minimumSize: Size.zero),
                            onPressed: () => _showMessage(
                              'Sắp có',
                              'Khôi phục mật khẩu qua email sẽ có trong bản cập nhật tới.',
                            ),
                            child: Text('Quên mật khẩu?',
                                style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600, fontSize: 12)),
                          ),
                      ],
                    ),
                    const SizedBox(height: 7),
                    _PasswordField(
                      controller: passwordController,
                      show: showPassword,
                      hint: isSignup ? 'Tạo mật khẩu' : '••••••••',
                      onToggle: () => setState(() => showPassword = !showPassword),
                    ),
                    if (isSignup) ...[
                      const SizedBox(height: 6),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text('Tối thiểu 8 ký tự.', style: TextStyle(color: AppColors.textMuted, fontSize: 11)),
                      ),
                    ],
                    const SizedBox(height: 22),
                    AppButton(
                      title: isSignup ? 'Tạo tài khoản' : 'Đăng nhập',
                      icon: isSignup ? Icons.arrow_forward : null,
                      onPressed: _handleSubmit,
                      loading: submitting,
                    ),
                    const SizedBox(height: 18),
                    Row(
                      children: [
                        Expanded(child: Divider(color: AppColors.border)),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 10),
                          child: Text('HOẶC TIẾP TỤC VỚI',
                              style: TextStyle(color: AppColors.textMuted, fontSize: 11, letterSpacing: 0.4)),
                        ),
                        Expanded(child: Divider(color: AppColors.border)),
                      ],
                    ),
                    const SizedBox(height: 18),
                    AppButton(
                      title: 'Google',
                      variant: AppButtonVariant.secondary,
                      onPressed: _handleGoogleSignIn,
                    ),
                    const SizedBox(height: 20),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          isSignup ? 'Đã có tài khoản?' : 'Chưa có tài khoản?',
                          style: TextStyle(color: AppColors.textMuted, fontSize: 13),
                        ),
                        TextButton(
                          onPressed: _toggleMode,
                          child: Text(
                            isSignup ? 'Đăng nhập' : 'Đăng ký',
                            style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700, fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LabeledField extends StatelessWidget {
  final String label;
  final IconData icon;
  final TextEditingController controller;
  final String hint;
  final TextInputType? keyboardType;

  const _LabeledField({
    required this.label,
    required this.icon,
    required this.controller,
    required this.hint,
    this.keyboardType,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: AppColors.text, fontWeight: FontWeight.w600, fontSize: 12.5)),
        const SizedBox(height: 7),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          decoration: InputDecoration(
            prefixIcon: Icon(icon, size: 18, color: AppColors.textMuted),
            hintText: hint,
            hintStyle: TextStyle(color: AppColors.inputPlaceholder),
            filled: true,
            fillColor: AppColors.panelSoft,
            contentPadding: const EdgeInsets.symmetric(vertical: 12),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.control),
              borderSide: BorderSide(color: AppColors.border, width: 1.5),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.control),
              borderSide: BorderSide(color: AppColors.border, width: 1.5),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.control),
              borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
            ),
          ),
        ),
      ],
    );
  }
}

class _PasswordField extends StatelessWidget {
  final TextEditingController controller;
  final bool show;
  final String hint;
  final VoidCallback onToggle;

  const _PasswordField({required this.controller, required this.show, required this.hint, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: !show,
      decoration: InputDecoration(
        prefixIcon: Icon(Icons.lock_outline, size: 18, color: AppColors.textMuted),
        suffixIcon: IconButton(
          icon: Icon(show ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 18, color: AppColors.textMuted),
          onPressed: onToggle,
        ),
        hintText: hint,
        hintStyle: TextStyle(color: AppColors.inputPlaceholder),
        filled: true,
        fillColor: AppColors.panelSoft,
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.control),
          borderSide: BorderSide(color: AppColors.border, width: 1.5),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.control),
          borderSide: BorderSide(color: AppColors.border, width: 1.5),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.control),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
      ),
    );
  }
}
