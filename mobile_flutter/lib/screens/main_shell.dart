import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/profile_header.dart';
import 'chat_screen.dart';
import 'email_screen.dart';
import 'history_screen.dart';
import 'overview_screen.dart';
import 'role_selection_screen.dart';
import 'schedule_screen.dart';
import 'settings_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int tabIndex = 0;
  bool modePickerOpen = false;

  static const _tabs = [
    (icon: Icons.bar_chart_outlined, activeIcon: Icons.bar_chart, labelVi: 'Tổng hợp', labelEn: 'Overview'),
    (icon: Icons.chat_bubble_outline, activeIcon: Icons.chat_bubble, labelVi: 'Chat', labelEn: 'Chat'),
    (icon: Icons.mail_outline, activeIcon: Icons.mail, labelVi: 'Email', labelEn: 'Email'),
    (icon: Icons.calendar_today_outlined, activeIcon: Icons.calendar_today, labelVi: 'Lịch', labelEn: 'Calendar'),
    (icon: Icons.history_outlined, activeIcon: Icons.history, labelVi: 'Lịch sử', labelEn: 'History'),
    (icon: Icons.settings_outlined, activeIcon: Icons.settings, labelVi: 'Cài đặt', labelEn: 'Settings'),
  ];

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    if (appState.userMode == null || appState.userMode!.isEmpty || modePickerOpen) {
      return RoleSelectionScreen(
        initialValue: appState.userMode,
        onContinue: (mode) async {
          await appState.saveUserMode(mode);
          setState(() => modePickerOpen = false);
        },
      );
    }

    final screens = [
      OverviewScreen(onNavigate: (tab) => setState(() => tabIndex = tab)),
      const ChatScreen(),
      const EmailScreen(),
      const ScheduleScreen(),
      const HistoryScreen(),
      SettingsScreen(onChangeMode: () => setState(() => modePickerOpen = true)),
    ];

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            ProfileHeader(
              profile: appState.profile,
              onRefresh: appState.refreshShell,
              onChangeMode: () => setState(() => modePickerOpen = true),
            ),
            Expanded(child: IndexedStack(index: tabIndex, children: screens)),
          ],
        ),
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: colors.panel,
          border: Border(top: BorderSide(color: colors.border)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 64,
            child: Stack(
              children: [
                // The "liquid" part: a single pill that glides to the active
                // tab's slot instead of each tab snapping its own color.
                AnimatedAlign(
                  duration: const Duration(milliseconds: 320),
                  curve: Curves.easeOutCubic,
                  alignment: Alignment(-1 + (2 * tabIndex) / (_tabs.length - 1), 0),
                  child: FractionallySizedBox(
                    widthFactor: 1 / _tabs.length,
                    heightFactor: 1,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: colors.primary.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: const SizedBox.expand(),
                      ),
                    ),
                  ),
                ),
                Row(
                  children: List.generate(_tabs.length, (i) {
                    final tab = _tabs[i];
                    final active = tabIndex == i;
                    return Expanded(
                      child: InkWell(
                        onTap: () => setState(() => tabIndex = i),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(active ? tab.activeIcon : tab.icon, size: 21, color: active ? colors.primary : colors.textMuted),
                            const SizedBox(height: 2),
                            Text(
                              t(tab.labelVi, tab.labelEn),
                              style: TextStyle(
                                color: active ? colors.primary : colors.textMuted,
                                fontSize: 9.5,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
