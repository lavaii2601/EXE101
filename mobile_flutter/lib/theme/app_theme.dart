import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../state/theme_controller.dart';

class AppRadius {
  static const control = 12.0;
  static const button = 14.0;
  static const card = 20.0;
}

const List<Color> kOrbGradient = [
  Color(0xFF55BEFE),
  Color(0xFF5A54FB),
  Color(0xFF8171FD),
  Color(0xFFD65EFC),
];

ThemeData buildAppTheme(AppColors colors) {
  final brightness = colors.background.computeLuminance() < 0.5 ? Brightness.dark : Brightness.light;
  final base = ThemeData(
    useMaterial3: true,
    brightness: brightness,
    scaffoldBackgroundColor: colors.background,
    colorScheme: ColorScheme.fromSeed(seedColor: colors.primary, brightness: brightness),
    fontFamily: GoogleFonts.poppins().fontFamily,
  );
  return base.copyWith(
    textTheme: GoogleFonts.poppinsTextTheme(base.textTheme).apply(
      bodyColor: colors.text,
      displayColor: colors.text,
    ),
  );
}
