import 'package:flutter/material.dart';
import 'screens/welcome_screen.dart';
import 'screens/login_screen.dart';
import 'theme/app_theme.dart';

void main() {
  runApp(const FlowMateApp());
}

class FlowMateApp extends StatelessWidget {
  const FlowMateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'FlowMate AI',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: const _RootFlow(),
    );
  }
}

/// Minimal placeholder flow for this first Flutter pass: Welcome -> Login
/// -> "signed in" confirmation. The rest of the app (tabs, Overview, Email,
/// Schedule...) still lives in the React Native build until this proves out.
class _RootFlow extends StatefulWidget {
  const _RootFlow();

  @override
  State<_RootFlow> createState() => _RootFlowState();
}

class _RootFlowState extends State<_RootFlow> {
  bool showWelcome = true;
  bool loggedIn = false;

  @override
  Widget build(BuildContext context) {
    if (loggedIn) {
      return const _SignedInPlaceholder();
    }
    if (showWelcome) {
      return WelcomeScreen(
        onGetStarted: () => setState(() => showWelcome = false),
        onLogIn: () => setState(() => showWelcome = false),
      );
    }
    return LoginScreen(onLoggedIn: () => setState(() => loggedIn = true));
  }
}

class _SignedInPlaceholder extends StatelessWidget {
  const _SignedInPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle, color: AppColors.success, size: 56),
            const SizedBox(height: 16),
            Text('Đăng nhập thành công',
                style: TextStyle(color: AppColors.text, fontWeight: FontWeight.w700, fontSize: 18)),
            const SizedBox(height: 8),
            Text('Các tab Tổng hợp/Chat/Email... sẽ được chuyển sang Flutter ở bước tiếp theo.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textMuted, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}
