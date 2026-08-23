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

  const RoleSelectionScreen({super.key, this.initialValue, required this.onContinue});

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
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(26, 30, 26, 16),
              child: Column(
                children: [
                  Container(
                    width: 80,
                    height: 80,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(22),
                      gradient: const LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: kOrbGradient,
                      ),
                      boxShadow: [
                        BoxShadow(color: const Color(0xFF5A54FB).withValues(alpha: 0.5), blurRadius: 22, offset: const Offset(0, 10)),
                      ],
                    ),
                    child: const Icon(Icons.calendar_month_outlined, color: Colors.white, size: 34),
                  ),
                  const SizedBox(height: 16),
                  Text('FLOWMATE AI',
                      style: TextStyle(color: colors.primary, fontWeight: FontWeight.w800, fontSize: 11, letterSpacing: 1.4)),
                  const SizedBox(height: 6),
                  Text(t('Chọn chế độ của bạn', 'Choose your mode'),
                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w900, fontSize: 22)),
                  const SizedBox(height: 8),
                  Text(
                    t(
                      'FlowMate sẽ thay đổi ưu tiên email, gợi ý lịch và cách AI phản hồi theo vai trò.',
                      'FlowMate adapts email priorities, schedule suggestions, and AI replies to your role.',
                    ),
                    textAlign: TextAlign.center,
                    style: TextStyle(color: colors.textMuted, height: 1.4),
                  ),
                ],
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                child: Column(
                  children: [
                    GridView.count(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      crossAxisCount: 2,
                      crossAxisSpacing: 10,
                      mainAxisSpacing: 10,
                      childAspectRatio: 0.92,
                      children: kUserModes.map((mode) {
                        final active = selected == mode.value;
                        return GestureDetector(
                          onTap: () => setState(() => selected = mode.value),
                          child: Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: active ? colors.primarySoft : colors.panel,
                              borderRadius: BorderRadius.circular(AppRadius.card),
                              border: Border.all(color: active ? colors.primary : colors.border, width: 1.5),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Container(
                                  width: 38,
                                  height: 38,
                                  decoration: BoxDecoration(
                                    color: active ? colors.primary : colors.panelSoft,
                                    borderRadius: BorderRadius.circular(AppRadius.control),
                                  ),
                                  child: Icon(mode.icon, size: 18, color: active ? Colors.white : colors.primary),
                                ),
                                const SizedBox(height: 12),
                                Text(mode.label, style: TextStyle(color: colors.text, fontWeight: FontWeight.w800, fontSize: 14)),
                                const SizedBox(height: 5),
                                Expanded(
                                  child: Text(
                                    mode.description,
                                    style: TextStyle(color: colors.textMuted, fontSize: 11, height: 1.3),
                                    overflow: TextOverflow.fade,
                                  ),
                                ),
                                if (active)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 6),
                                    child: Row(
                                      children: [
                                        Icon(Icons.check_circle, size: 13, color: colors.primary),
                                        const SizedBox(width: 4),
                                        Text(t('Đã chọn', 'Selected'),
                                            style: TextStyle(color: colors.primary, fontWeight: FontWeight.w800, fontSize: 11)),
                                      ],
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 18),
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
    );
  }
}

