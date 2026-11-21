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
                padding: const EdgeInsets.fromLTRB(20, 26, 20, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                        t('Chọn chế độ sử dụng', 'Choose how you use FlowMate'),
                        style: TextStyle(
                            color: colors.text,
                            fontWeight: FontWeight.w900,
                            fontSize: 23,
                            letterSpacing: -0.5)),
                    const SizedBox(height: 7),
                    Text(
                      t(
                        'Chọn vai trò phù hợp nhất với công việc của bạn.',
                        'Choose the role that best matches your work.',
                      ),
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
                                    horizontal: 13, vertical: 10),
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
                                      width: 36,
                                      height: 36,
                                      decoration: BoxDecoration(
                                        color: active
                                            ? colors.primary
                                            : colors.panelSoft,
                                        borderRadius: BorderRadius.circular(
                                            AppRadius.control),
                                      ),
                                      child: Icon(mode.icon,
                                          size: 17,
                                          color: active
                                              ? Colors.white
                                              : colors.primary),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Text(mode.label,
                                          style: TextStyle(
                                              color: colors.text,
                                              fontWeight: FontWeight.w700,
                                              fontSize: 13.5)),
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
