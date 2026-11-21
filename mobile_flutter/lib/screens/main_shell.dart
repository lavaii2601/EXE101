import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';
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

  static const _baseTabs = [
    (
      icon: Icons.bar_chart_outlined,
      activeIcon: Icons.bar_chart,
      labelVi: 'Tổng hợp',
      labelEn: 'Overview'
    ),
    (
      icon: Icons.chat_bubble_outline,
      activeIcon: Icons.chat_bubble,
      labelVi: 'Chat',
      labelEn: 'Chat'
    ),
    (
      icon: Icons.mail_outline,
      activeIcon: Icons.mail,
      labelVi: 'Email',
      labelEn: 'Email'
    ),
    (
      icon: Icons.calendar_today_outlined,
      activeIcon: Icons.calendar_today,
      labelVi: 'Lịch',
      labelEn: 'Calendar'
    ),
    (
      icon: Icons.history_outlined,
      activeIcon: Icons.history,
      labelVi: 'Lịch sử',
      labelEn: 'History'
    ),
    (
      icon: Icons.settings_outlined,
      activeIcon: Icons.settings,
      labelVi: 'Cài đặt',
      labelEn: 'Settings'
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    if (appState.userMode == null ||
        appState.userMode!.isEmpty ||
        modePickerOpen) {
      return RoleSelectionScreen(
        initialValue: appState.userMode,
        onContinue: (mode) async {
          await appState.saveUserMode(mode);
          setState(() => modePickerOpen = false);
        },
      );
    }

    const tabs = _baseTabs;

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
      body: FlowMateBackdrop(
        child: SafeArea(
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
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: colors.panel,
          border: Border(
              top: BorderSide(color: colors.border.withValues(alpha: 0.72))),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 18,
              offset: const Offset(0, -4),
            ),
          ],
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 62,
            child: Row(
              children: List.generate(tabs.length, (i) {
                final tab = tabs[i];
                final active = tabIndex == i;
                return Expanded(
                  child: Semantics(
                    selected: active,
                    button: true,
                    label: t(tab.labelVi, tab.labelEn),
                    child: InkWell(
                      onTap: () => setState(() => tabIndex = i),
                      child: Column(
                        children: [
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 220),
                            width: active ? 24 : 0,
                            height: 3,
                            decoration: BoxDecoration(
                              color:
                                  active ? colors.primary : Colors.transparent,
                              borderRadius: const BorderRadius.vertical(
                                  bottom: Radius.circular(3)),
                            ),
                          ),
                          const Spacer(),
                          Icon(
                            active ? tab.activeIcon : tab.icon,
                            size: 20,
                            color: active ? colors.primary : colors.textMuted,
                          ),
                          const SizedBox(height: 3),
                          Text(
                            t(tab.labelVi, tab.labelEn),
                            maxLines: 1,
                            style: TextStyle(
                              color: active ? colors.primary : colors.textMuted,
                              fontSize: 9,
                              fontWeight:
                                  active ? FontWeight.w700 : FontWeight.w500,
                            ),
                          ),
                          const SizedBox(height: 7),
                        ],
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}
