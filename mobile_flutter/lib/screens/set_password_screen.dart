import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/auth_api.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/app_button.dart';

/// Forced, one-time step after a Google "recover" flow restores access to
/// an account that only ever signed in via Google (no password set yet) --
/// see api/google_auth.dart's needsPassword and AppState.needsPassword.
/// Deliberately has no skip/close control.
class SetPasswordScreen extends StatefulWidget {
  const SetPasswordScreen({super.key});

  @override
  State<SetPasswordScreen> createState() => _SetPasswordScreenState();
}

class _SetPasswordScreenState extends State<SetPasswordScreen> {
  final passwordController = TextEditingController();
  bool showPassword = false;
  bool submitting = false;
  String? error;

  @override
  void dispose() {
    passwordController.dispose();
    super.dispose();
  }

  Future<void> _handleSubmit() async {
    final t = context.read<LanguageController>().t;
    if (passwordController.text.length < 8) {
      setState(() => error = t('Mật khẩu phải có ít nhất 8 ký tự.', 'Password must be at least 8 characters.'));
      return;
    }
    setState(() {
      submitting = true;
      error = null;
    });
    try {
      await setPassword(passwordController.text);
      if (mounted) context.read<AppState>().clearNeedsPassword();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => submitting = false);
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
                ),
                child: Column(
                  children: [
                    Text(
                      t('Đặt mật khẩu cho tài khoản', 'Set an account password'),
                      textAlign: TextAlign.center,
                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 20),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      t(
                        'Tài khoản này trước đây chỉ đăng nhập bằng Google. Hãy đặt một mật khẩu FlowMate để đăng nhập trực tiếp từ lần sau.',
                        'This account previously only signed in via Google. Set a FlowMate password to sign in directly from now on.',
                      ),
                      textAlign: TextAlign.center,
                      style: TextStyle(color: colors.textMuted, fontSize: 13),
                    ),
                    const SizedBox(height: 18),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(t('Mật khẩu mới', 'New Password'),
                          style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 12.5)),
                    ),
                    const SizedBox(height: 7),
                    TextField(
                      controller: passwordController,
                      obscureText: !showPassword,
                      style: TextStyle(color: colors.text),
                      decoration: InputDecoration(
                        prefixIcon: Icon(Icons.lock_outline, size: 18, color: colors.textMuted),
                        suffixIcon: IconButton(
                          icon: Icon(showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                              size: 18, color: colors.textMuted),
                          onPressed: () => setState(() => showPassword = !showPassword),
                        ),
                        hintText: '••••••••',
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
                    const SizedBox(height: 6),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(t('Tối thiểu 8 ký tự.', 'Must be at least 8 characters.'),
                          style: TextStyle(color: colors.textMuted, fontSize: 11)),
                    ),
                    if (error != null) ...[
                      const SizedBox(height: 10),
                      Text(error!, style: const TextStyle(color: Colors.redAccent, fontSize: 12.5)),
                    ],
                    const SizedBox(height: 22),
                    AppButton(
                      title: t('Lưu mật khẩu', 'Save Password'),
                      icon: Icons.arrow_forward,
                      onPressed: _handleSubmit,
                      loading: submitting,
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
