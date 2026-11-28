import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../theme/app_theme.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';

/// Shared header row (back button + title) matching
/// email_detail_screen.dart's convention -- this app doesn't use AppBar for
/// pushed screens.
class _ToolHeader extends StatelessWidget {
  final String title;
  const _ToolHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 6, 20, 6),
      child: Row(
        children: [
          IconButton(
            icon: Icon(Icons.arrow_back, color: colors.text),
            onPressed: () => Navigator.pop(context),
          ),
          Expanded(
            child: Text(title,
                style: TextStyle(
                    color: colors.text,
                    fontWeight: FontWeight.w700,
                    fontSize: 17)),
          ),
        ],
      ),
    );
  }
}

class StudySummarizerScreen extends StatefulWidget {
  const StudySummarizerScreen({super.key});

  @override
  State<StudySummarizerScreen> createState() => _StudySummarizerScreenState();
}

class _StudySummarizerScreenState extends State<StudySummarizerScreen> {
  final titleController = TextEditingController();
  final contentController = TextEditingController();
  String? summary;
  String? quotaLabel;
  bool loading = false;

  @override
  void dispose() {
    titleController.dispose();
    contentController.dispose();
    super.dispose();
  }

  Future<void> _summarize() async {
    final t = context.read<LanguageController>().t;
    final content = contentController.text.trim();
    if (content.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(t('Hãy dán nội dung cần tóm tắt',
              'Paste content to summarize first'))));
      return;
    }
    setState(() {
      loading = true;
      summary = null;
    });
    try {
      final data = await apiPost('/chat/summarize-study', {
        'title': titleController.text.trim(),
        'content': content,
      });
      final quota =
          data is Map && data['ai_quota'] is Map ? data['ai_quota'] as Map : null;
      final remaining = quota?['remaining'];
      final limit = quota?['limit'];
      setState(() {
        summary = data is Map ? data['summary'] as String? : null;
        quotaLabel = remaining != null && limit != null
            ? t('Còn $remaining/$limit lượt hôm nay',
                '$remaining/$limit left today')
            : null;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      final message = error.data['error'] == 'ai_limit_reached'
          ? t('Bạn đã dùng hết lượt tóm tắt miễn phí hôm nay.',
              "You've used all your free summaries today.")
          : t('Không thể tóm tắt', 'Unable to summarize');
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(t('Không thể tóm tắt', 'Unable to summarize'))));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: FlowMateBackdrop(
        child: SafeArea(
          child: Column(
            children: [
              _ToolHeader(
                  title:
                      t('Tóm tắt tài liệu học tập', 'Summarize study material')),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
                  children: [
                    Text(
                      t(
                        'Dán bài giảng, ghi chú hoặc tài liệu học tập để Bob tóm tắt các ý chính.',
                        'Paste lecture notes or study material for Bob to summarize the key points.',
                      ),
                      style: TextStyle(
                          color: colors.textMuted, fontSize: 13, height: 1.4),
                    ),
                    const SizedBox(height: 14),
                    AppField(
                      label: t('Tiêu đề (không bắt buộc)', 'Title (optional)'),
                      controller: titleController,
                    ),
                    AppField(
                      label: t('Nội dung', 'Content'),
                      controller: contentController,
                      multiline: true,
                      hint: t('Dán nội dung vào đây...', 'Paste content here...'),
                    ),
                    const SizedBox(height: 6),
                    AppButton(
                      title: t('Tóm tắt', 'Summarize'),
                      onPressed: _summarize,
                      loading: loading,
                    ),
                    if (summary != null) ...[
                      const SizedBox(height: 16),
                      AppCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(summary!,
                                style: TextStyle(
                                    color: colors.text,
                                    fontSize: 13.5,
                                    height: 1.5)),
                            if (quotaLabel != null) ...[
                              const SizedBox(height: 8),
                              Text(quotaLabel!,
                                  style: TextStyle(
                                      color: colors.textMuted,
                                      fontSize: 11.5,
                                      fontWeight: FontWeight.w600)),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GpaRow {
  final name = TextEditingController();
  final credits = TextEditingController();
  final grade = TextEditingController();

  void dispose() {
    name.dispose();
    credits.dispose();
    grade.dispose();
  }
}

class GpaCalculatorScreen extends StatefulWidget {
  const GpaCalculatorScreen({super.key});

  @override
  State<GpaCalculatorScreen> createState() => _GpaCalculatorScreenState();
}

class _GpaCalculatorScreenState extends State<GpaCalculatorScreen> {
  final rows = <_GpaRow>[];
  String? result;
  bool calculated = false;
  bool loading = false;

  @override
  void initState() {
    super.initState();
    rows.addAll([_GpaRow(), _GpaRow(), _GpaRow()]);
  }

  @override
  void dispose() {
    for (final row in rows) {
      row.dispose();
    }
    super.dispose();
  }

  void _addRow() => setState(() => rows.add(_GpaRow()));

  void _removeRow(int index) {
    final removed = rows.removeAt(index);
    removed.dispose();
    setState(() {});
  }

  Future<void> _calculate() async {
    final t = context.read<LanguageController>().t;
    final courses = rows
        .map((row) => {
              'name': row.name.text.trim(),
              'credits': row.credits.text.trim(),
              'grade': row.grade.text.trim(),
            })
        .where((course) =>
            course['name']!.isNotEmpty &&
            course['credits']!.isNotEmpty &&
            course['grade']!.isNotEmpty)
        .toList();
    if (courses.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(t('Hãy nhập ít nhất một môn hợp lệ',
              'Enter at least one valid course'))));
      return;
    }
    setState(() => loading = true);
    try {
      final data = await apiPost('/courses/calculate', {'courses': courses});
      final gpa = data is Map ? data['gpa'] : null;
      setState(() {
        result = gpa == null
            ? t('Chưa đủ dữ liệu hợp lệ', 'Not enough valid data')
            : 'GPA: $gpa';
        calculated = true;
      });
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content:
                Text(t('Không thể tính GPA', 'Unable to calculate GPA'))));
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: FlowMateBackdrop(
        child: SafeArea(
          child: Column(
            children: [
              _ToolHeader(title: t('Tính GPA', 'Calculate GPA')),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
                  children: [
                    Text(
                      t(
                        'Nhập môn học, số tín chỉ và điểm (theo thang điểm bạn đang dùng) để tính GPA trung bình theo tín chỉ.',
                        'Enter courses, credits, and grade (on whatever scale you use) to compute a credit-weighted GPA.',
                      ),
                      style: TextStyle(
                          color: colors.textMuted, fontSize: 13, height: 1.4),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      t('Free: tính tại chỗ, không lưu lại.',
                          "Free: computes on the spot, nothing is saved."),
                      style: TextStyle(color: colors.textMuted, fontSize: 11.5),
                    ),
                    const SizedBox(height: 14),
                    for (var i = 0; i < rows.length; i++)
                      _GpaRowFields(
                        row: rows[i],
                        colors: colors,
                        t: t,
                        onRemove: rows.length > 1 ? () => _removeRow(i) : null,
                      ),
                    AppButton(
                      title: t('+ Thêm môn', '+ Add course'),
                      variant: AppButtonVariant.secondary,
                      onPressed: _addRow,
                    ),
                    const SizedBox(height: 10),
                    AppButton(
                      title: t('Tính GPA', 'Calculate'),
                      onPressed: _calculate,
                      loading: loading,
                    ),
                    if (calculated) ...[
                      const SizedBox(height: 14),
                      AppCard(
                        child: Text(result ?? '',
                            style: TextStyle(
                                color: colors.text,
                                fontWeight: FontWeight.w700,
                                fontSize: 15)),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GpaRowFields extends StatelessWidget {
  final _GpaRow row;
  final AppColors colors;
  final String Function(String, [String?]) t;
  final VoidCallback? onRemove;

  const _GpaRowFields({
    required this.row,
    required this.colors,
    required this.t,
    required this.onRemove,
  });

  InputDecoration _decoration(String hint) {
    return InputDecoration(
      hintText: hint,
      hintStyle: TextStyle(color: colors.inputPlaceholder, fontSize: 12.5),
      filled: true,
      fillColor: colors.panelSoft,
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: colors.border)),
      enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: colors.border)),
      focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: colors.primary)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            flex: 3,
            child: TextField(
              controller: row.name,
              style: TextStyle(color: colors.text, fontSize: 13),
              decoration: _decoration(t('Tên môn', 'Course name')),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            flex: 2,
            child: TextField(
              controller: row.credits,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              style: TextStyle(color: colors.text, fontSize: 13),
              decoration: _decoration(t('TC', 'Cr')),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            flex: 2,
            child: TextField(
              controller: row.grade,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              style: TextStyle(color: colors.text, fontSize: 13),
              decoration: _decoration(t('Điểm', 'Grade')),
            ),
          ),
          if (onRemove != null)
            IconButton(
              icon: Icon(Icons.close, size: 18, color: colors.textMuted),
              onPressed: onRemove,
            ),
        ],
      ),
    );
  }
}
