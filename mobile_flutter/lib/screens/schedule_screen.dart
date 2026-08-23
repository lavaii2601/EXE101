import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key});

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  List<dynamic> schedules = [];
  bool loading = false;
  bool showCreateForm = false;

  final titleController = TextEditingController();
  final descriptionController = TextEditingController();
  final startController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    titleController.dispose();
    descriptionController.dispose();
    startController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await apiGet('/schedule/unified?max_results=50&live=0');
      setState(() => schedules = (data is Map && data['items'] is List) ? data['items'] as List : []);
    } catch (_) {
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _createSchedule() async {
    if (titleController.text.trim().isEmpty || startController.text.trim().isEmpty) {
      _showError(context.read<LanguageController>().t('Thiếu thông tin', 'Missing info'),
          context.read<LanguageController>().t('Vui lòng nhập tiêu đề và thời gian bắt đầu.', 'Please enter a title and start time.'));
      return;
    }
    setState(() => loading = true);
    try {
      await apiPost('/schedule/create', {
        'title': titleController.text.trim(),
        'description': descriptionController.text.trim(),
        'start_time': startController.text.trim(),
      });
      titleController.clear();
      descriptionController.clear();
      startController.clear();
      setState(() => showCreateForm = false);
      await _load();
    } catch (error) {
      _showError(context.read<LanguageController>().t('Không tạo được lịch', 'Could not create schedule'), error.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  void _showError(String title, String message) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: t('Lịch', 'Calendar'),
          refreshing: loading,
          onRefresh: _load,
          actions: AppButton(
            title: showCreateForm ? t('Đóng', 'Close') : t('Tạo mới', 'New'),
            variant: AppButtonVariant.secondary,
            onPressed: () => setState(() => showCreateForm = !showCreateForm),
          ),
          children: [
            if (showCreateForm)
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    AppField(label: t('Tiêu đề', 'Title'), controller: titleController, hint: t('Họp phụ huynh', 'Meeting title')),
                    AppField(label: t('Mô tả', 'Description'), controller: descriptionController, multiline: true),
                    AppField(
                      label: t('Bắt đầu', 'Start time'),
                      controller: startController,
                      hint: '2026-06-05T09:00:00',
                    ),
                    const SizedBox(height: 6),
                    AppButton(title: t('Tạo lịch hẹn', 'Create schedule'), onPressed: _createSchedule, loading: loading),
                  ],
                ),
              ),
            if (schedules.isEmpty)
              AppCard(child: AppEmptyState(icon: Icons.event_busy_outlined, title: t('Chưa có lịch sắp tới', 'No upcoming schedule')))
            else
              ...schedules.map((s) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: AppCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(s['title'] as String? ?? '', style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 15)),
                          const SizedBox(height: 4),
                          Text(_formatDate(s['start_time'] as String?), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 12)),
                          if ((s['description'] as String?)?.isNotEmpty == true) ...[
                            const SizedBox(height: 6),
                            Text(s['description'] as String, style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4)),
                          ],
                        ],
                      ),
                    ),
                  )),
          ],
        ),
      ),
    );
  }

  String _formatDate(String? value) {
    if (value == null) return '';
    final dt = DateTime.tryParse(value);
    if (dt == null) return value;
    return '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
