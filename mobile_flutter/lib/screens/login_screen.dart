import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/auth_api.dart';
import '../api/session.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
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
    final t = context.read<LanguageController>().t;
    if (isSignup && nameController.text.trim().isEmpty) {
      _showMessage(t('Thiếu thông tin', 'Missing info'), t('Vui lòng nhập họ tên.', 'Please enter your full name.'));
      return;
    }
    if (emailController.text.trim().isEmpty || passwordController.text.isEmpty) {
      _showMessage(t('Thiếu thông tin', 'Missing info'),
          t('Vui lòng nhập email và mật khẩu.', 'Please enter your email and password.'));
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
          : await loginWithEmail(email: emailController.text.trim(), password: passwordController.text);
      await setMobileSession(userId: result.userId, accessToken: result.accessToken);
      widget.onLoggedIn();
    } catch (error) {
      _showMessage(
        isSignup ? t('Không tạo được tài khoản', 'Could not create account') : t('Không đăng nhập được', 'Sign-in failed'),
        error.toString(),
      );
    } finally {
      if (mounted) setState(() => submitting = false);
    }
  }

  void _handleGoogleSignIn() {
    final t = context.read<LanguageController>().t;
    // Native Google Sign-In needs its own OAuth client setup
    // (google-services.json, SHA-1 fingerprint) -- out of scope for this
    // first Flutter pass. The React Native app's flow is the reference
    // implementation once that's wired up here.
    _showMessage(t('Sắp có', 'Coming soon'),
        t('Đăng nhập Google trên bản Flutter đang được hoàn thiện.', 'Google sign-in on the Flutter build is still in progress.'));
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'FlowMate AI',
                textAlign: TextAlign.center,
                style: TextStyle(color: colors.text, fontWeight: FontWeight.w800, fontSize: 22, letterSpacing: -0.4),
              ),
              const SizedBox(height: 18),
              Container(
                padding: const EdgeInsets.all(22),
                decoration: BoxDecoration(
                  color: colors.panel,
                  borderRadius: BorderRadius.circular(AppRadius.card),
                  border: Border.all(color: colors.border),
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
                        gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: kOrbGradient),
                        boxShadow: [
                          BoxShadow(color: const Color(0xFF5A54FB).withValues(alpha: 0.4), blurRadius: 16, offset: const Offset(0, 8)),
                        ],
                      ),
                      child: const Icon(Icons.auto_awesome, color: Colors.white, size: 26),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      isSignup ? t('Tạo tài khoản', 'Create Account') : t('Chào mừng trở lại', 'Welcome Back'),
                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 20),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      isSignup
                          ? t('Tham gia FlowMate AI ngay hôm nay.', 'Join FlowMate AI today.')
                          : t('Vui lòng nhập thông tin để đăng nhập.', 'Please enter your details to sign in.'),
                      style: TextStyle(color: colors.textMuted, fontSize: 13),
                    ),
                    if (isSignup) ...[
                      const SizedBox(height: 18),
                      _LabeledField(
                        colors: colors,
                        label: t('Họ và tên', 'Full Name'),
                        icon: Icons.person_outline,
                        controller: nameController,
                        hint: t('Nhập họ và tên', 'Enter your full name'),
                      ),
                    ],
                    const SizedBox(height: 18),
                    _LabeledField(
                      colors: colors,
                      label: 'Email',
                      icon: Icons.mail_outline,
                      controller: emailController,
                      hint: 'name@company.com',
                      keyboardType: TextInputType.emailAddress,
                    ),
                    const SizedBox(height: 18),
                    Row(
                      children: [
                        Text(t('Mật khẩu', 'Password'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 12.5)),
                        const Spacer(),
                        if (!isSignup)
                          TextButton(
                            style: TextButton.styleFrom(padding: EdgeInsets.zero, minimumSize: Size.zero),
                            onPressed: () => _showMessage(
                              t('Sắp có', 'Coming soon'),
                              t('Khôi phục mật khẩu qua email sẽ có trong bản cập nhật tới.',
                                  'Email password recovery is coming in a future update.'),
                            ),
                            child: Text(t('Quên mật khẩu?', 'Forgot Password?'),
                                style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 12)),
                          ),
                      ],
                    ),
                    const SizedBox(height: 7),
                    _PasswordField(
                      colors: colors,
                      controller: passwordController,
                      show: showPassword,
                      hint: isSignup ? t('Tạo mật khẩu', 'Create a password') : '••••••••',
                      onToggle: () => setState(() => showPassword = !showPassword),
                    ),
                    if (isSignup) ...[
                      const SizedBox(height: 6),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(t('Tối thiểu 8 ký tự.', 'Must be at least 8 characters.'),
                            style: TextStyle(color: colors.textMuted, fontSize: 11)),
                      ),
                    ],
                    const SizedBox(height: 22),
                    AppButton(
                      title: isSignup ? t('Tạo tài khoản', 'Create Account') : t('Đăng nhập', 'Sign In'),
                      icon: isSignup ? Icons.arrow_forward : null,
                      onPressed: _handleSubmit,
                      loading: submitting,
                    ),
                    const SizedBox(height: 18),
                    Row(
                      children: [
                        Expanded(child: Divider(color: colors.border)),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 10),
                          child: Text(t('HOẶC TIẾP TỤC VỚI', 'OR CONTINUE WITH'),
                              style: TextStyle(color: colors.textMuted, fontSize: 11, letterSpacing: 0.4)),
                        ),
                        Expanded(child: Divider(color: colors.border)),
                      ],
                    ),
                    const SizedBox(height: 18),
                    AppButton(title: 'Google', variant: AppButtonVariant.secondary, onPressed: _handleGoogleSignIn),
                    const SizedBox(height: 20),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          isSignup ? t('Đã có tài khoản?', 'Already have an account?') : t('Chưa có tài khoản?', "Don't have an account?"),
                          style: TextStyle(color: colors.textMuted, fontSize: 13),
                        ),
                        TextButton(
                          onPressed: _toggleMode,
                          child: Text(
                            isSignup ? t('Đăng nhập', 'Sign In') : t('Đăng ký', 'Sign up'),
                            style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 13),
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
  final AppColors colors;
  final String label;
  final IconData icon;
  final TextEditingController controller;
  final String hint;
  final TextInputType? keyboardType;

  const _LabeledField({
    required this.colors,
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
        Text(label, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 12.5)),
        const SizedBox(height: 7),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          style: TextStyle(color: colors.text),
          decoration: InputDecoration(
            prefixIcon: Icon(icon, size: 18, color: colors.textMuted),
            hintText: hint,
            hintStyle: TextStyle(color: colors.inputPlaceholder),
            filled: true,
            fillColor: colors.panelSoft,
            contentPadding: const EdgeInsets.symmetric(vertical: 12),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.control),
              borderSide: BorderSide(color: colors.border, width: 1.5),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.control),
              borderSide: BorderSide(color: colors.border, width: 1.5),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.control),
              borderSide: BorderSide(color: colors.primary, width: 1.5),
            ),
          ),
        ),
      ],
    );
  }
}

class _PasswordField extends StatelessWidget {
  final AppColors colors;
  final TextEditingController controller;
  final bool show;
  final String hint;
  final VoidCallback onToggle;

  const _PasswordField({
    required this.colors,
    required this.controller,
    required this.show,
    required this.hint,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: !show,
      style: TextStyle(color: colors.text),
      decoration: InputDecoration(
        prefixIcon: Icon(Icons.lock_outline, size: 18, color: colors.textMuted),
        suffixIcon: IconButton(
          icon: Icon(show ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 18, color: colors.textMuted),
          onPressed: onToggle,
        ),
        hintText: hint,
        hintStyle: TextStyle(color: colors.inputPlaceholder),
        filled: true,
        fillColor: colors.panelSoft,
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.control),
          borderSide: BorderSide(color: colors.border, width: 1.5),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.control),
          borderSide: BorderSide(color: colors.border, width: 1.5),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.control),
          borderSide: BorderSide(color: colors.primary, width: 1.5),
        ),
      ),
    );
  }
}
