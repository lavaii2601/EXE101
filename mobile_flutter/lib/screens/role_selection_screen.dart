import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../config/user_modes.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/app_button.dart';

class RoleSelectionScreen extends StatefulWidget {
  final String? initialValue;
  final Future<void> Function(String mode) onContinue;

  const RoleSelectionScreen(
      {super.key, this.initialValue, required this.onContinue});

  @override
  State<RoleSelectionScreen> createState() => _RoleSelectionScreenState();
}

class _RoleSelectionScreenState extends State<RoleSelectionScreen> {
  String? selected;
  bool saving = false;

  @override
  void initState() {
    super.initState();
    selected = widget.initialValue;
  }

  Future<void> _continue() async {
    if (selected == null) return;
    setState(() => saving = true);
    try {
      await widget.onContinue(selected!);
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Scaffold(
      backgroundColor: colors.background,
      body: FlowMateBackdrop(
        child: SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 18, 24, 14),
                child: Column(
                  children: [
                    Container(
                      width: 58,
                      height: 58,
                      decoration: BoxDecoration(
                        boxShadow: [
                          BoxShadow(
                              color: const Color(0xFF0058DE)
                                  .withValues(alpha: 0.28),
                              blurRadius: 20,
                              offset: const Offset(0, 8)),
                        ],
                      ),
                      child: Image.asset('assets/images/logo.png',
                          fit: BoxFit.contain),
                    ),
                    const SizedBox(height: 10),
                    Text('FLOWMATE AI',
                        style: TextStyle(
                            color: colors.primary,
                            fontWeight: FontWeight.w800,
                            fontSize: 11,
                            letterSpacing: 1.4)),
                    const SizedBox(height: 4),
                    Text(t('Chọn chế độ của bạn', 'Choose your mode'),
                        style: TextStyle(
                            color: colors.text,
                            fontWeight: FontWeight.w900,
                            fontSize: 24,
                            letterSpacing: -0.5)),
                    const SizedBox(height: 6),
                    Text(
                      t(
                        'FlowMate sẽ thay đổi ưu tiên email, gợi ý lịch và cách AI phản hồi theo vai trò.',
                        'FlowMate adapts email priorities, schedule suggestions, and AI replies to your role.',
                      ),
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          color: colors.textMuted, fontSize: 12.5, height: 1.4),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                  child: Column(
                    children: [
                      ...kUserModes.map((mode) {
                        final active = selected == mode.value;
                        return Padding(
                            padding: const EdgeInsets.only(bottom: 9),
                            child: InkWell(
                              borderRadius:
                                  BorderRadius.circular(AppRadius.card),
                              onTap: () =>
                                  setState(() => selected = mode.value),
                              child: AnimatedContainer(
                                duration: const Duration(milliseconds: 180),
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 13, vertical: 11),
                                decoration: BoxDecoration(
                                  color: active
                                      ? colors.primarySoft
                                      : colors.panel,
                                  borderRadius:
                                      BorderRadius.circular(AppRadius.card),
                                  border: Border.all(
                                      color: active
                                          ? colors.primary
                                          : colors.border,
                                      width: 1.5),
                                  boxShadow: [
                                    BoxShadow(
                                        color: Colors.black
                                            .withValues(alpha: 0.035),
                                        blurRadius: 12,
                                        offset: const Offset(0, 5)),
                                  ],
                                ),
                                child: Row(
                                  children: [
                                    Container(
                                      width: 42,
                                      height: 42,
                                      decoration: BoxDecoration(
                                        color: active
                                            ? colors.primary
                                            : colors.panelSoft,
                                        borderRadius: BorderRadius.circular(
                                            AppRadius.control),
                                      ),
                                      child: Icon(mode.icon,
                                          size: 18,
                                          color: active
                                              ? Colors.white
                                              : colors.primary),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(mode.label,
                                              style: TextStyle(
                                                  color: colors.text,
                                                  fontWeight: FontWeight.w800,
                                                  fontSize: 14)),
                                          const SizedBox(height: 3),
                                          Text(mode.description,
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: TextStyle(
                                                  color: colors.textMuted,
                                                  fontSize: 10.5,
                                                  height: 1.3)),
                                        ],
                                      ),
                                    ),
                                    Icon(
                                        active
                                            ? Icons.check_circle_rounded
                                            : Icons
                                                .radio_button_unchecked_rounded,
                                        size: 21,
                                        color: active
                                            ? colors.primary
                                            : colors.border),
                                  ],
                                ),
                              ),
                            ));
                      }),
                      const SizedBox(height: 10),
                      AppButton(
                        title: t('Tiếp tục', 'Continue'),
                        onPressed: selected == null ? null : _continue,
                        loading: saving,
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
