import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/client.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';

const _dayNamesVi = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN'];
const _dayNamesEn = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key});

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  List<dynamic> schedules = [];
  List<List<dynamic>> weekDays = List.generate(7, (_) => []);
  List<dynamic> suggestions = [];
  late DateTime currentWeekStart;
  bool loading = false;
  bool suggestionsLoading = false;
  bool showForm = false;
  Map<String, dynamic>? editingSchedule;

  final titleController = TextEditingController();
  final descriptionController = TextEditingController();
  final locationController = TextEditingController();
  final attendeesController = TextEditingController();
  final durationController = TextEditingController(text: '60');
  DateTime? startTime;
  DateTime? endTime;

  @override
  void initState() {
    super.initState();
    currentWeekStart = _monday(DateTime.now());
    _load(syncGoogle: true, silent: true);
    _loadSuggestions();
  }

  @override
  void dispose() {
    titleController.dispose();
    descriptionController.dispose();
    locationController.dispose();
    attendeesController.dispose();
    durationController.dispose();
    super.dispose();
  }

  static DateTime _monday(DateTime d) {
    final date = DateTime(d.year, d.month, d.day);
    return date.subtract(Duration(days: date.weekday - 1));
  }

  static String _dateParam(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  static String _isoLocal(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}'
      'T${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}:00';

  Future<void> _load({bool syncGoogle = false, bool silent = false}) async {
    if (!silent) setState(() => loading = true);
    if (syncGoogle) {
      try {
        await apiPost('/schedule/sync', {});
      } catch (_) {}
    }
    try {
      final results = await Future.wait([
        apiGet('/schedule/unified?max_results=50&live=0'),
        apiGet('/schedule/week?start=${_dateParam(currentWeekStart)}&sync=0'),
      ]);
      final unified = results[0];
      final week = results[1];
      final days = (week is Map && week['days'] is List) ? week['days'] as List : [];
      if (mounted) {
        setState(() {
          schedules = (unified is Map && unified['items'] is List) ? unified['items'] as List : [];
          weekDays = List.generate(7, (i) => i < days.length && days[i] is List ? days[i] as List : <dynamic>[]);
        });
      }
    } catch (_) {
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _loadSuggestions() async {
    setState(() => suggestionsLoading = true);
    try {
      final data = await apiGet('/email/meeting-suggestions');
      if (mounted) setState(() => suggestions = (data is Map && data['suggestions'] is List) ? data['suggestions'] as List : []);
    } catch (_) {
    } finally {
      if (mounted) setState(() => suggestionsLoading = false);
    }
  }

  Future<void> _scanSuggestions() async {
    final t = context.read<LanguageController>().t;
    setState(() => suggestionsLoading = true);
    try {
      final data = await apiPost('/email/meeting-suggestions/scan', {});
      if (mounted) setState(() => suggestions = (data is Map && data['suggestions'] is List) ? data['suggestions'] as List : []);
    } catch (error) {
      if (mounted) _showMessage(t('Không quét được email', 'Could not scan email'), error.toString());
    } finally {
      if (mounted) setState(() => suggestionsLoading = false);
    }
  }

  Future<void> _dismissSuggestion(Map suggestion) async {
    try {
      await apiPatch('/email/meeting-suggestions/${suggestion['id']}/status', {'status': 'dismissed'});
      await _loadSuggestions();
    } catch (_) {}
  }

  Future<void> _createFromSuggestion(Map suggestion) async {
    final t = context.read<LanguageController>().t;
    final startRaw = suggestion['start_time'] as String?;
    if (startRaw == null || startRaw.isEmpty) {
      setState(() {
        editingSchedule = null;
        titleController.text = (suggestion['title'] ?? suggestion['subject'] ?? 'Lịch hẹn từ email') as String;
        descriptionController.text = (suggestion['description'] ?? suggestion['snippet'] ?? '') as String;
        startTime = null;
        endTime = null;
        showForm = true;
      });
      _showMessage(t('Cần bổ sung thời gian', 'Needs a start time'),
          t('Gợi ý này chưa có giờ bắt đầu, hãy nhập thời gian để tạo lịch.', 'This suggestion has no start time yet -- enter one to create the schedule.'));
      return;
    }
    setState(() => loading = true);
    try {
      final start = DateTime.tryParse(startRaw) ?? DateTime.now();
      final endRaw = suggestion['end_time'] as String?;
      final end = (endRaw != null && endRaw.isNotEmpty) ? DateTime.tryParse(endRaw) : null;
      final data = await apiPost('/schedule/create', {
        'title': suggestion['title'] ?? suggestion['subject'] ?? 'Lịch hẹn từ email',
        'description': suggestion['description'] ?? suggestion['snippet'] ?? '',
        'start_time': _isoLocal(start),
        'end_time': _isoLocal(end ?? start.add(const Duration(minutes: 60))),
      });
      final scheduleId = data is Map ? data['schedule_id'] : null;
      await apiPatch('/email/meeting-suggestions/${suggestion['id']}/status', {'status': 'created', 'schedule_id': scheduleId});
      await _loadSuggestions();
      await _load();
    } catch (error) {
      _showMessage(t('Không tạo được lịch', 'Could not create schedule'), error.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  void _openCreateForm() {
    setState(() {
      editingSchedule = null;
      titleController.clear();
      descriptionController.clear();
      locationController.clear();
      attendeesController.clear();
      durationController.text = '60';
      startTime = null;
      endTime = null;
      showForm = true;
    });
  }

  void _openEditForm(Map<String, dynamic> schedule) {
    final start = DateTime.tryParse((schedule['start_time'] as String?) ?? '');
    final end = DateTime.tryParse((schedule['end_time'] as String?) ?? '');
    final attendees = schedule['attendees'];
    setState(() {
      editingSchedule = schedule;
      titleController.text = (schedule['title'] as String?) ?? '';
      descriptionController.text = (schedule['description'] as String?) ?? '';
      locationController.text = (schedule['location'] as String?) ?? '';
      attendeesController.text = attendees is List ? attendees.join(', ') : (attendees as String? ?? '');
      durationController.text = (start != null && end != null) ? end.difference(start).inMinutes.toString() : '60';
      startTime = start;
      endTime = end;
      showForm = true;
    });
  }

  Future<void> _submitForm() async {
    final t = context.read<LanguageController>().t;
    if (titleController.text.trim().isEmpty || startTime == null) {
      _showMessage(t('Thiếu thông tin', 'Missing info'), t('Vui lòng nhập tiêu đề và thời gian bắt đầu.', 'Please enter a title and start time.'));
      return;
    }
    final duration = int.tryParse(durationController.text.trim()) ?? 60;
    final end = endTime ?? startTime!.add(Duration(minutes: duration));
    final payload = {
      'title': titleController.text.trim(),
      'description': descriptionController.text.trim(),
      'start_time': _isoLocal(startTime!),
      'end_time': _isoLocal(end),
      'duration_minutes': duration,
      'location': locationController.text.trim(),
      'attendees': attendeesController.text.trim().split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
    };
    setState(() => loading = true);
    try {
      if (editingSchedule != null) {
        await apiPut('/schedule/${editingSchedule!['local_id']}', {...payload, 'expected_updated_at': editingSchedule!['updated_at']});
      } else {
        await apiPost('/schedule/create', payload);
      }
      setState(() {
        showForm = false;
        editingSchedule = null;
      });
      await _load();
    } catch (error) {
      _showMessage(t('Không lưu được lịch', 'Could not save schedule'), error.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _updateStatus(Map<String, dynamic> schedule, String status) async {
    try {
      await apiPatch('/schedule/${schedule['local_id']}/update-status', {'status': status, 'expected_updated_at': schedule['updated_at']});
      await _load();
    } catch (error) {
      _showMessage(context.read<LanguageController>().t('Không cập nhật được lịch', 'Could not update schedule'), error.toString());
    }
  }

  Future<void> _deleteSchedule(Map<String, dynamic> schedule) async {
    try {
      await apiDelete('/schedule/${schedule['local_id']}');
      if (editingSchedule != null && editingSchedule!['local_id'] == schedule['local_id']) {
        setState(() {
          showForm = false;
          editingSchedule = null;
        });
      }
      await _load();
    } catch (error) {
      _showMessage(context.read<LanguageController>().t('Không xóa được lịch', 'Could not delete schedule'), error.toString());
    }
  }

  void _showMessage(String title, String message) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
      ),
    );
  }

  Future<void> _pickDateTime(bool isStart) async {
    final initial = (isStart ? startTime : endTime) ?? DateTime.now();
    final date = await showDatePicker(context: context, initialDate: initial, firstDate: DateTime(2020), lastDate: DateTime(2100));
    if (date == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(initial));
    if (time == null) return;
    final combined = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    setState(() {
      if (isStart) {
        startTime = combined;
      } else {
        endTime = combined;
      }
    });
  }

  void _shiftWeek(int direction) {
    setState(() => currentWeekStart = _monday(currentWeekStart.add(Duration(days: 7 * direction))));
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final lang = context.watch<LanguageController>().language;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: t('Lịch', 'Calendar'),
          refreshing: loading,
          onRefresh: () => _load(syncGoogle: true),
          actions: AppButton(
            title: showForm ? t('Đóng', 'Close') : t('Tạo mới', 'New'),
            variant: AppButtonVariant.secondary,
            onPressed: () => showForm ? setState(() => showForm = false) : _openCreateForm(),
          ),
          children: [
            if (showForm)
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      editingSchedule != null ? t('Sửa lịch hẹn', 'Edit schedule') : t('Tạo lịch hẹn', 'New schedule'),
                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 15),
                    ),
                    const SizedBox(height: 10),
                    AppField(label: t('Tiêu đề', 'Title'), controller: titleController, hint: t('Họp phụ huynh', 'Meeting title')),
                    AppField(label: t('Mô tả', 'Description'), controller: descriptionController, multiline: true),
                    _DateTimeField(label: t('Bắt đầu', 'Start'), value: startTime, onTap: () => _pickDateTime(true), language: lang),
                    _DateTimeField(label: t('Kết thúc', 'End'), value: endTime, onTap: () => _pickDateTime(false), language: lang),
                    AppField(label: t('Thời lượng (phút)', 'Duration (minutes)'), controller: durationController, keyboardType: TextInputType.number),
                    AppField(label: t('Địa điểm', 'Location'), controller: locationController, hint: t('Phòng họp / online', 'Meeting room / online')),
                    AppField(label: t('Người tham dự', 'Attendees'), controller: attendeesController, hint: 'a@example.com, b@example.com'),
                    const SizedBox(height: 4),
                    if (editingSchedule != null)
                      Row(
                        children: [
                          Expanded(
                            child: AppButton(
                              title: t('Xóa lịch hẹn', 'Delete'),
                              variant: AppButtonVariant.danger,
                              onPressed: () => _deleteSchedule(editingSchedule!),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: AppButton(title: t('Lưu thay đổi', 'Save'), onPressed: _submitForm, loading: loading),
                          ),
                        ],
                      )
                    else
                      AppButton(title: t('Tạo lịch hẹn', 'Create schedule'), onPressed: _submitForm, loading: loading),
                  ],
                ),
              ),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('THỜI KHÓA BIỂU', 'TIMETABLE'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 2),
                            Text(_formatWeekRange(currentWeekStart, lang), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 14)),
                          ],
                        ),
                      ),
                      IconButton(icon: Icon(Icons.chevron_left, color: colors.primary), onPressed: () => _shiftWeek(-1)),
                      IconButton(
                        icon: Icon(Icons.today_outlined, color: colors.primary, size: 18),
                        onPressed: () {
                          setState(() => currentWeekStart = _monday(DateTime.now()));
                          _load();
                        },
                      ),
                      IconButton(icon: Icon(Icons.chevron_right, color: colors.primary), onPressed: () => _shiftWeek(1)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  ..._buildTimetable(colors, t, lang),
                ],
              ),
            ),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('GỢI Ý TỪ EMAIL', 'FROM EMAIL'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 2),
                            Text(t('Cuộc họp phát hiện được', 'Detected meetings'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 14)),
                          ],
                        ),
                      ),
                      IntrinsicWidth(
                        child: AppButton(title: t('Quét email', 'Scan'), variant: AppButtonVariant.secondary, onPressed: _scanSuggestions, loading: suggestionsLoading),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  if (suggestions.isEmpty)
                    Text(t('Chưa có gợi ý lịch mới.', 'No new schedule suggestions yet.'), style: TextStyle(color: colors.textMuted, fontSize: 13))
                  else
                    ...suggestions.map((raw) {
                      final s = Map<String, dynamic>.from(raw as Map);
                      final startRaw = s['start_time'] as String?;
                      final start = (startRaw != null && startRaw.isNotEmpty) ? DateTime.tryParse(startRaw) : null;
                      return Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text((s['title'] ?? s['subject'] ?? t('Lịch hẹn từ email', 'Meeting from email')) as String,
                                style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 13)),
                            const SizedBox(height: 2),
                            Text('${t('Từ', 'From')}: ${s['sender'] ?? t('Không xác định', 'Unknown')}', style: TextStyle(color: colors.textMuted, fontSize: 11.5)),
                            Text(start != null ? _formatShort(start, lang) : t('Chưa xác định thời gian', 'No time set'),
                                style: TextStyle(color: colors.textMuted, fontSize: 11.5)),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                Expanded(child: AppButton(title: t('Tạo lịch', 'Create'), onPressed: () => _createFromSuggestion(s))),
                                const SizedBox(width: 8),
                                Expanded(child: AppButton(title: t('Bỏ qua', 'Dismiss'), variant: AppButtonVariant.secondary, onPressed: () => _dismissSuggestion(s))),
                              ],
                            ),
                          ],
                        ),
                      );
                    }),
                ],
              ),
            ),
            if (schedules.isEmpty)
              AppCard(child: AppEmptyState(icon: Icons.event_busy_outlined, title: t('Chưa có lịch sắp tới', 'No upcoming schedule')))
            else
              ...schedules.map((raw) {
                final s = Map<String, dynamic>.from(raw as Map);
                final hasLocalId = s['local_id'] != null;
                final status = s['status'] as String?;
                final isCompleted = status == 'completed';
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: AppCard(
                    borderColor: colors.primary.withValues(alpha: 0.2),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(s['title'] as String? ?? '', style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 15)),
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                _Badge(text: _sourceLabel(s, t), color: colors.primary),
                                if (status != null && status != 'pending') ...[
                                  const SizedBox(height: 4),
                                  _Badge(text: _statusLabel(status, t), color: isCompleted ? colors.success : colors.danger),
                                ],
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(_formatRange(s['start_time'] as String?, s['end_time'] as String?, lang), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 12)),
                        if ((s['description'] as String?)?.isNotEmpty == true) ...[
                          const SizedBox(height: 6),
                          Text(s['description'] as String, style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4)),
                        ],
                        if ((s['location'] as String?)?.isNotEmpty == true) ...[
                          const SizedBox(height: 4),
                          Text('${t('Địa điểm', 'Location')}: ${s['location']}', style: TextStyle(color: colors.textMuted, fontSize: 12)),
                        ],
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            if (hasLocalId) ...[
                              IntrinsicWidth(
                                child: AppButton(
                                  title: isCompleted ? t('Bỏ hoàn thành', 'Undo') : t('Hoàn tất', 'Complete'),
                                  variant: AppButtonVariant.secondary,
                                  onPressed: () => _updateStatus(s, isCompleted ? 'pending' : 'completed'),
                                ),
                              ),
                              IntrinsicWidth(child: AppButton(title: t('Sửa', 'Edit'), variant: AppButtonVariant.secondary, onPressed: () => _openEditForm(s))),
                              IntrinsicWidth(child: AppButton(title: t('Hủy', 'Cancel'), variant: AppButtonVariant.danger, onPressed: () => _updateStatus(s, 'cancelled'))),
                            ] else if (s['html_link'] != null || s['web_link'] != null)
                              IntrinsicWidth(
                                child: AppButton(
                                  title: t('Mở lịch', 'Open'),
                                  variant: AppButtonVariant.secondary,
                                  onPressed: () => launchUrl(Uri.parse((s['html_link'] ?? s['web_link']) as String), mode: LaunchMode.externalApplication),
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildTimetable(dynamic colors, String Function(String, [String?]) t, String lang) {
    final today = _dateParam(DateTime.now());
    final names = lang == 'en' ? _dayNamesEn : _dayNamesVi;
    return List.generate(7, (i) {
      final dayDate = currentWeekStart.add(Duration(days: i));
      final isToday = _dateParam(dayDate) == today;
      final events = List<dynamic>.from(weekDays[i])
        ..removeWhere((e) => e is! Map || (e['start_time'] as String?) == null)
        ..sort((a, b) => ((a as Map)['start_time'] as String).compareTo((b as Map)['start_time'] as String));
      return Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(vertical: 6),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: isToday ? colors.primary : colors.border))),
              child: Row(
                children: [
                  Text('${names[i]}, ${dayDate.day.toString().padLeft(2, '0')}/${dayDate.month.toString().padLeft(2, '0')}',
                      style: TextStyle(color: isToday ? colors.primary : colors.textMuted, fontWeight: isToday ? FontWeight.w800 : FontWeight.w600, fontSize: 13)),
                  if (isToday) ...[
                    const SizedBox(width: 8),
                    _Badge(text: t('Hôm nay', 'Today'), color: colors.primary),
                  ],
                ],
              ),
            ),
            if (events.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Text(t('Không có lịch hẹn', 'No events'), style: TextStyle(color: colors.textMuted, fontSize: 12)),
              )
            else
              ...events.map((raw) {
                final e = Map<String, dynamic>.from(raw as Map);
                final start = DateTime.tryParse(e['start_time'] as String);
                final end = (e['end_time'] as String?) != null ? DateTime.tryParse(e['end_time'] as String) : null;
                final timeText = start == null
                    ? ''
                    : '${start.hour.toString().padLeft(2, '0')}:${start.minute.toString().padLeft(2, '0')}'
                        '${end != null ? '–${end.hour.toString().padLeft(2, '0')}:${end.minute.toString().padLeft(2, '0')}' : ''}';
                return InkWell(
                  onTap: () {
                    if (e['local_id'] != null) {
                      _openEditForm(e);
                    } else if (e['html_link'] != null || e['web_link'] != null) {
                      launchUrl(Uri.parse((e['html_link'] ?? e['web_link']) as String), mode: LaunchMode.externalApplication);
                    }
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    decoration: BoxDecoration(border: Border(bottom: BorderSide(color: colors.border))),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(width: 78, child: Text(timeText, style: TextStyle(color: colors.primary, fontWeight: FontWeight.w600, fontSize: 12))),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(e['title'] as String? ?? t('Sự kiện', 'Event'), maxLines: 2, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                              Text(_sourceLabel(e, t), style: TextStyle(color: colors.textMuted, fontSize: 10.5, fontWeight: FontWeight.w600)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
          ],
        ),
      );
    });
  }

  String _sourceLabel(Map schedule, String Function(String, [String?]) t) {
    final provider = (schedule['provider'] ?? schedule['source'] ?? '') as String;
    if (schedule['source'] == 'synced') return t('Đã đồng bộ', 'Synced');
    if (schedule['source'] == 'google' || provider == 'google') return 'Google';
    return 'FlowMate';
  }

  String _statusLabel(String status, String Function(String, [String?]) t) {
    if (status == 'completed') return t('Đã hoàn thành', 'Completed');
    if (status == 'cancelled') return t('Đã hủy', 'Cancelled');
    if (status == 'dismissed') return t('Đã bỏ qua', 'Dismissed');
    return status;
  }

  String _formatWeekRange(DateTime start, String lang) {
    final end = start.add(const Duration(days: 6));
    String fmt(DateTime d) => lang == 'en' ? '${d.month}/${d.day}' : '${d.day}/${d.month}';
    return '${fmt(start)} - ${fmt(end)}/${end.year}';
  }

  String _formatRange(String? startValue, String? endValue, String lang) {
    if (startValue == null) return '';
    final start = DateTime.tryParse(startValue);
    if (start == null) return startValue;
    final startText = _formatFull(start, lang);
    if (endValue == null) return startText;
    final end = DateTime.tryParse(endValue);
    if (end == null) return startText;
    return '$startText - ${_formatFull(end, lang)}';
  }

  String _formatFull(DateTime d, String lang) =>
      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

  String _formatShort(DateTime d, String lang) {
    final names = lang == 'en' ? _dayNamesEn : _dayNamesVi;
    return '${names[d.weekday - 1]}, ${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }
}

class _Badge extends StatelessWidget {
  final String text;
  final Color color;
  const _Badge({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(999)),
      child: Text(text, style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 10.5)),
    );
  }
}

class _DateTimeField extends StatelessWidget {
  final String label;
  final DateTime? value;
  final VoidCallback onTap;
  final String language;
  const _DateTimeField({required this.label, required this.value, required this.onTap, required this.language});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final text = value == null
        ? ''
        : '${value!.day.toString().padLeft(2, '0')}/${value!.month.toString().padLeft(2, '0')}/${value!.year}  '
            '${value!.hour.toString().padLeft(2, '0')}:${value!.minute.toString().padLeft(2, '0')}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w600, fontSize: 12)),
          const SizedBox(height: 6),
          InkWell(
            onTap: onTap,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
              decoration: BoxDecoration(
                color: colors.panelSoft,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: colors.border, width: 1.5),
              ),
              child: Row(
                children: [
                  Icon(Icons.calendar_today_outlined, size: 16, color: colors.textMuted),
                  const SizedBox(width: 10),
                  Text(
                    text.isEmpty ? (language == 'en' ? 'Select date & time' : 'Chọn ngày giờ') : text,
                    style: TextStyle(color: text.isEmpty ? colors.inputPlaceholder : colors.text, fontSize: 14),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
