import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();
const _themeKey = 'flowmate.theme';
const _accentKey = 'flowmate.accent';

class AccentDef {
  final Color primary;
  final Color primaryDark;
  const AccentDef(this.primary, this.primaryDark);
}

const Map<String, AccentDef> kAccents = {
  'blue': AccentDef(Color(0xFF0B5ED7), Color(0xFF0847A6)),
  'green': AccentDef(Color(0xFF4F7D1C), Color(0xFF3B6114)),
  'cyan': AccentDef(Color(0xFF167D91), Color(0xFF105E6D)),
  'yellow': AccentDef(Color(0xFFA56800), Color(0xFF7E4F00)),
};

/// Palette shape mirrors ThemeContext.js buildColors() exactly (same key
/// names/values) so screens ported from the RN app map 1:1.
class AppColors {
  final Color background;
  final Color panel;
  final Color panelSoft;
  final Color text;
  final Color textMuted;
  final Color border;
  final Color primary;
  final Color primaryDark;
  final Color primarySoft;
  final Color danger;
  final Color success;
  final Color warning;
  final Color secondaryBg;
  final Color secondaryText;
  final Color inputPlaceholder;

  const AppColors({
    required this.background,
    required this.panel,
    required this.panelSoft,
    required this.text,
    required this.textMuted,
    required this.border,
    required this.primary,
    required this.primaryDark,
    required this.primarySoft,
    required this.danger,
    required this.success,
    required this.warning,
    required this.secondaryBg,
    required this.secondaryText,
    required this.inputPlaceholder,
  });

  static AppColors build(bool isDark, String accentKey) {
    final accent = kAccents[accentKey] ?? kAccents['blue']!;
    if (isDark) {
      return AppColors(
        background: const Color(0xFF071827),
        panel: const Color(0xFF0E2335),
        panelSoft: const Color(0xFF153149),
        text: const Color(0xFFF3FBFD),
        textMuted: const Color(0xFFA7C2CC),
        border: const Color(0xFF82D6E5).withValues(alpha: 0.16),
        primary: accent.primary,
        primaryDark: accent.primaryDark,
        primarySoft: accent.primary.withValues(alpha: 0.14),
        danger: const Color(0xFFEF4444),
        success: const Color(0xFF8BC34A),
        warning: const Color(0xFFF6C667),
        secondaryBg: const Color(0xFF17384A),
        secondaryText: const Color(0xFF82D6E5),
        inputPlaceholder: const Color(0xFF74909B),
      );
    }
    return AppColors(
      background: const Color(0xFFF4FAFB),
      panel: const Color(0xFFFFFFFF),
      panelSoft: const Color(0xFFEAF7F9),
      text: const Color(0xFF173042),
      textMuted: const Color(0xFF587181),
      border: const Color(0xFFCBE7EC),
      primary: accent.primary,
      primaryDark: accent.primaryDark,
      primarySoft: accent.primary.withValues(alpha: 0.09),
      danger: const Color(0xFFDC2626),
      success: const Color(0xFF4F7D1C),
      warning: const Color(0xFFA56800),
      secondaryBg: const Color(0xFFDFF4F7),
      secondaryText: const Color(0xFF176B7B),
      inputPlaceholder: const Color(0xFF78939D),
    );
  }
}

class ThemeController extends ChangeNotifier {
  bool isDark = false;
  String accent = 'blue';

  ThemeController() {
    _load();
  }

  AppColors get colors => AppColors.build(isDark, accent);

  Future<void> _load() async {
    final storedTheme = await _storage.read(key: _themeKey);
    final storedAccent = await _storage.read(key: _accentKey);
    if (storedTheme == 'dark' || storedTheme == 'light') {
      isDark = storedTheme == 'dark';
    }
    if (storedAccent != null && kAccents.containsKey(storedAccent)) {
      accent = storedAccent;
    }
    notifyListeners();
  }

  Future<void> toggleTheme() async {
    isDark = !isDark;
    notifyListeners();
    await _storage.write(key: _themeKey, value: isDark ? 'dark' : 'light');
  }

  Future<void> setAccent(String next) async {
    if (!kAccents.containsKey(next)) return;
    accent = next;
    notifyListeners();
    await _storage.write(key: _accentKey, value: next);
  }
}
