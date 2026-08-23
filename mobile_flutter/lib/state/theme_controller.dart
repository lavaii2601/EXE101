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
  'charcoal': AccentDef(Color(0xFF242423), Color(0xFF1E1E1D)),
  'blue': AccentDef(Color(0xFF2563EB), Color(0xFF1D4ED8)),
  'purple': AccentDef(Color(0xFF6C63FF), Color(0xFF5951E8)),
  'green': AccentDef(Color(0xFF059669), Color(0xFF047857)),
  'orange': AccentDef(Color(0xFFEA580C), Color(0xFFC2410C)),
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
    final accent = kAccents[accentKey] ?? kAccents['purple']!;
    if (isDark) {
      return AppColors(
        background: const Color(0xFF0B1020),
        panel: const Color(0xFF12182A),
        panelSoft: const Color(0xFF192137),
        text: const Color(0xFFF7F8FF),
        textMuted: const Color(0xFF9DA8C3),
        border: Colors.white.withValues(alpha: 0.08),
        primary: accent.primary,
        primaryDark: accent.primaryDark,
        primarySoft: accent.primary.withValues(alpha: 0.14),
        danger: const Color(0xFFEF4444),
        success: const Color(0xFF34D399),
        warning: const Color(0xFFFBBF24),
        secondaryBg: const Color(0xFF202A43),
        secondaryText: const Color(0xFFE5E9F7),
        inputPlaceholder: const Color(0xFF5C5C70),
      );
    }
    return AppColors(
      background: const Color(0xFFF4F6FC),
      panel: const Color(0xFFFFFFFF),
      panelSoft: const Color(0xFFF7F8FD),
      text: const Color(0xFF182033),
      textMuted: const Color(0xFF667085),
      border: const Color(0xFFE4E7F0),
      primary: accent.primary,
      primaryDark: accent.primaryDark,
      primarySoft: accent.primary.withValues(alpha: 0.09),
      danger: const Color(0xFFDC2626),
      success: const Color(0xFF16A34A),
      warning: const Color(0xFFD97706),
      secondaryBg: const Color(0xFFEEF0FF),
      secondaryText: const Color(0xFF4338CA),
      inputPlaceholder: const Color(0xFF9AA8BC),
    );
  }
}

class ThemeController extends ChangeNotifier {
  bool isDark = false;
  String accent = 'purple';

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
