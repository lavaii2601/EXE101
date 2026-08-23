import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Color tokens mirrored from the React Native app's ThemeContext.js
/// (light theme, purple accent) so the Flutter port starts pixel-close
/// instead of drifting to a new palette.
class AppColors {
  static const background = Color(0xFFF4F6FC);
  static const panel = Color(0xFFFFFFFF);
  static const panelSoft = Color(0xFFF7F8FD);
  static const text = Color(0xFF182033);
  static const textMuted = Color(0xFF667085);
  static const border = Color(0xFFE4E7F0);
  static const primary = Color(0xFF6C63FF);
  static const primaryDark = Color(0xFF5951E8);
  static const primarySoft = Color(0x186C63FF);
  static const secondaryBg = Color(0xFFEEF0FF);
  static const secondaryText = Color(0xFF4338CA);
  static const inputPlaceholder = Color(0xFF9AA8BC);
  static const success = Color(0xFF16A34A);
  static const danger = Color(0xFFDC2626);

  static const orbGradient = [
    Color(0xFF55BEFE),
    Color(0xFF5A54FB),
    Color(0xFF8171FD),
    Color(0xFFD65EFC),
  ];
}

class AppRadius {
  static const control = 12.0;
  static const button = 14.0;
  static const card = 20.0;
}

ThemeData buildAppTheme() {
  final base = ThemeData(
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.background,
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.light,
    ),
    fontFamily: GoogleFonts.poppins().fontFamily,
  );
  return base.copyWith(
    textTheme: GoogleFonts.poppinsTextTheme(base.textTheme),
  );
}
