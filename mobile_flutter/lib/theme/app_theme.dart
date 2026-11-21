import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/theme_controller.dart';

class AppRadius {
  static const control = 14.0;
  static const button = 12.0;
  static const card = 18.0;
}

const List<Color> kOrbGradient = [
  Color(0xFF87DEF1),
  Color(0xFF0058DE),
  Color(0xFF8BC24B),
  Color(0xFFF4C364),
];

/// Full-screen wash used by the Figma mobile redesign.  Keeping it here
/// makes authentication, onboarding and every tab share the same canvas.
LinearGradient flowMateBackgroundGradient(AppColors colors) {
  final isDark = colors.background.computeLuminance() < 0.5;
  return LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: isDark
        ? const [Color(0xFF071827), Color(0xFF0A2132), Color(0xFF0C2A38)]
        : const [Color(0xFFF4F7FB), Color(0xFFEAF4FF), Color(0xFFDDF3F6)],
    stops: const [0, 0.52, 1],
  );
}

class FlowMateBackdrop extends StatelessWidget {
  final Widget child;

  const FlowMateBackdrop({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return DecoratedBox(
      decoration: BoxDecoration(gradient: flowMateBackgroundGradient(colors)),
      child: child,
    );
  }
}

ThemeData buildAppTheme(AppColors colors) {
  final brightness = colors.background.computeLuminance() < 0.5
      ? Brightness.dark
      : Brightness.light;
  final base = ThemeData(
    useMaterial3: true,
    brightness: brightness,
    scaffoldBackgroundColor: colors.background,
    colorScheme:
        ColorScheme.fromSeed(seedColor: colors.primary, brightness: brightness),
    fontFamily: 'Poppins',
  );
  return base.copyWith(
    splashColor: colors.primary.withValues(alpha: 0.08),
    highlightColor: colors.primary.withValues(alpha: 0.04),
    dividerColor: colors.border,
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: colors.panelSoft,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.control),
        borderSide: BorderSide(color: colors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.control),
        borderSide: BorderSide(color: colors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.control),
        borderSide: BorderSide(color: colors.primary, width: 1.5),
      ),
    ),
    textTheme: base.textTheme.apply(
      fontFamily: 'Poppins',
      bodyColor: colors.text,
      displayColor: colors.text,
    ),
  );
}
