import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/theme_controller.dart';

/// Mirrors components/Screen.js: a title row (with optional trailing
/// actions) above a scrollable, pull-to-refresh body.
class AppScreen extends StatelessWidget {
  final String title;
  final List<Widget> children;
  final Widget? actions;
  final bool refreshing;
  final Future<void> Function()? onRefresh;

  const AppScreen({
    super.key,
    required this.title,
    required this.children,
    this.actions,
    this.refreshing = false,
    this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 12),
          child: Row(
            children: [
              Expanded(
                child: Text(title, style: TextStyle(color: colors.text, fontWeight: FontWeight.w800, fontSize: 26, letterSpacing: -0.5)),
              ),
              if (actions != null) IntrinsicWidth(child: actions!),
            ],
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            color: colors.primary,
            onRefresh: onRefresh ?? () async {},
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
              children: [
                for (final child in children) Padding(padding: const EdgeInsets.only(bottom: 14), child: child),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
