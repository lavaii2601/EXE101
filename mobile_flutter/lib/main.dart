import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'screens/welcome_screen.dart';
import 'screens/login_screen.dart';
import 'screens/main_shell.dart';
import 'state/app_state.dart';
import 'state/language_controller.dart';
import 'state/theme_controller.dart';
import 'state/workspace_controller.dart';
import 'theme/app_theme.dart';

void main() {
  runApp(const FlowMateApp());
}

class FlowMateApp extends StatelessWidget {
  const FlowMateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ThemeController()),
        ChangeNotifierProvider(create: (_) => LanguageController()),
        ChangeNotifierProvider(create: (_) => AppState()..bootstrap()),
        ChangeNotifierProvider(create: (_) => WorkspaceController()),
        // Single shared listener for the flowmateai://oauth-callback deep
        // link the backend redirects to once Google OAuth consent finishes.
        Provider(create: (_) => AppLinks()),
      ],
      child: Consumer<ThemeController>(
        builder: (context, theme, _) {
          return MaterialApp(
            title: 'FlowMate AI',
            debugShowCheckedModeBanner: false,
            theme: buildAppTheme(theme.colors),
            home: const _RootFlow(),
          );
        },
      ),
    );
  }
}

class _RootFlow extends StatefulWidget {
  const _RootFlow();

  @override
  State<_RootFlow> createState() => _RootFlowState();
}

class _RootFlowState extends State<_RootFlow> {
  bool showWelcome = true;

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    final colors = context.watch<ThemeController>().colors;

    if (appState.isAuthenticated == null) {
      return Scaffold(backgroundColor: colors.background, body: const SizedBox.shrink());
    }

    if (appState.isAuthenticated == false) {
      if (showWelcome) {
        return WelcomeScreen(
          onGetStarted: () => setState(() => showWelcome = false),
          onLogIn: () => setState(() => showWelcome = false),
        );
      }
      return LoginScreen(onLoggedIn: () => appState.onLoggedIn());
    }

    return const MainShell();
  }
}
