import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';

class AppCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? borderColor;
  final Color? backgroundColor;

  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.borderColor,
    this.backgroundColor,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor ?? colors.panel,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: borderColor ?? colors.border),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.05), blurRadius: 14, offset: const Offset(0, 6)),
        ],
      ),
      child: child,
    );
  }
}

class AppEmptyState extends StatelessWidget {
  final String title;
  final String? detail;
  final IconData icon;

  const AppEmptyState({super.key, required this.title, this.detail, this.icon = Icons.inbox_outlined});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Padding(
      padding: const EdgeInsets.all(22),
      child: Column(
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(color: colors.primarySoft, borderRadius: BorderRadius.circular(16)),
            child: Icon(icon, size: 22, color: colors.primary),
          ),
          const SizedBox(height: 10),
          Text(title, textAlign: TextAlign.center, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
          if (detail != null) ...[
            const SizedBox(height: 6),
            Text(detail!, textAlign: TextAlign.center, style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4)),
          ],
        ],
      ),
    );
  }
}

class AppField extends StatelessWidget {
  final String label;
  final TextEditingController controller;
  final String? hint;
  final bool multiline;
  final TextInputType? keyboardType;

  const AppField({
    super.key,
    required this.label,
    required this.controller,
    this.hint,
    this.multiline = false,
    this.keyboardType,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w600, fontSize: 12)),
          const SizedBox(height: 6),
          TextField(
            controller: controller,
            maxLines: multiline ? 4 : 1,
            keyboardType: keyboardType,
            style: TextStyle(color: colors.text, fontSize: 14),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: TextStyle(color: colors.inputPlaceholder),
              filled: true,
              fillColor: colors.panelSoft,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(AppRadius.control),
                borderSide: BorderSide(color: colors.border, width: 1.5),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(AppRadius.control),
                borderSide: BorderSide(color: colors.border, width: 1.5),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(AppRadius.control),
                borderSide: BorderSide(color: colors.primary, width: 1.5),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
