import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';
import 'app_button.dart';

enum AppNoticeTone { info, warning, error }

Future<void> showAppNoticeDialog(
  BuildContext context, {
  required String title,
  required String message,
  String actionLabel = 'Đã hiểu',
  AppNoticeTone tone = AppNoticeTone.info,
  bool barrierDismissible = true,
}) {
  return showGeneralDialog<void>(
    context: context,
    barrierDismissible: barrierDismissible,
    barrierLabel: 'Dismiss notice',
    barrierColor: Colors.black.withValues(alpha: 0.48),
    transitionDuration: const Duration(milliseconds: 180),
    pageBuilder: (dialogContext, animation, secondaryAnimation) {
      return _AppNoticeCard(
        title: title,
        message: message,
        actionLabel: actionLabel,
        tone: tone,
      );
    },
    transitionBuilder: (context, animation, secondaryAnimation, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: Curves.easeOutCubic,
      );
      return FadeTransition(
        opacity: curved,
        child: ScaleTransition(
          scale: Tween<double>(begin: 0.96, end: 1).animate(curved),
          child: child,
        ),
      );
    },
  );
}

class _AppNoticeCard extends StatelessWidget {
  final String title;
  final String message;
  final String actionLabel;
  final AppNoticeTone tone;

  const _AppNoticeCard({
    required this.title,
    required this.message,
    required this.actionLabel,
    required this.tone,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final (icon, accent) = switch (tone) {
      AppNoticeTone.error => (Icons.error_outline_rounded, colors.danger),
      AppNoticeTone.warning => (Icons.warning_amber_rounded, colors.warning),
      AppNoticeTone.info => (Icons.info_outline_rounded, colors.primary),
    };

    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 360),
        child: Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            color: colors.panel,
            borderRadius: BorderRadius.circular(AppRadius.card),
            border: Border.all(color: colors.border),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.16),
                blurRadius: 30,
                offset: const Offset(0, 14),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 50,
                height: 50,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, color: accent, size: 24),
              ),
              const SizedBox(height: 14),
              Text(
                title,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: colors.text,
                  fontWeight: FontWeight.w700,
                  fontSize: 17,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                message,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: colors.textMuted,
                  fontSize: 13,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 20),
              AppButton(
                title: actionLabel,
                onPressed: () => Navigator.of(context).pop(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
