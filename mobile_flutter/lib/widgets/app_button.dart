import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';

enum AppButtonVariant { primary, secondary, danger }

class AppButton extends StatelessWidget {
  final String title;
  final VoidCallback? onPressed;
  final AppButtonVariant variant;
  final bool loading;
  final IconData? icon;

  const AppButton({
    super.key,
    required this.title,
    required this.onPressed,
    this.variant = AppButtonVariant.primary,
    this.loading = false,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final isSecondary = variant == AppButtonVariant.secondary;
    final isDanger = variant == AppButtonVariant.danger;
    final background = isDanger ? colors.danger : (isSecondary ? colors.secondaryBg : colors.primary);
    final foreground = isSecondary ? colors.secondaryText : Colors.white;

    return SizedBox(
      width: double.infinity,
      height: 48,
      child: ElevatedButton(
        onPressed: loading ? null : onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: background,
          foregroundColor: foreground,
          disabledBackgroundColor: background.withValues(alpha: 0.5),
          elevation: isSecondary ? 0 : 4,
          shadowColor: colors.primary.withValues(alpha: 0.35),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.button)),
        ),
        child: loading
            ? SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.4, color: foreground))
            : Row(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(title, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: foreground)),
                  if (icon != null) ...[
                    const SizedBox(width: 8),
                    Icon(icon, size: 18, color: foreground),
                  ],
                ],
              ),
      ),
    );
  }
}
