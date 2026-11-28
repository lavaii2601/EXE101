import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/client.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_notice_dialog.dart';
import '../widgets/app_screen.dart';

/// One row of a server-suggested day plan (POST /schedule/quick-add's
/// kind == 'suggested_plan') -- title is user-editable before applying,
/// start/end/duration/reason stay as the server computed them (editing a
/// conflict-avoiding time slot isn't supported here; deselect + re-run the
/// quick-add text instead).
class _PlanItem {
  final TextEditingController title;
  final String startTime;
  final String? endTime;
  final int? durationMinutes;
  final String reason;
  bool selected = true;

  _PlanItem({
    required String title,
    required this.startTime,
    this.endTime,
    this.durationMinutes,
    required this.reason,
  }) : title = TextEditingController(text: title);

  void dispose() => title.dispose();
}

const _dayNamesVi = [
  'Thứ 2',
  'Thứ 3',
  'Thứ 4',
  'Thứ 5',
  'Thứ 6',
  'Thứ 7',
  'CN'
];
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

  final quickAddController = TextEditingController();
  bool quickAddLoading = false;
  bool planApplying = false;
  String? planDate;
  List<_PlanItem>? planItems;

  final titleController = TextEditingController();
  final descriptionController = TextEditingController();
  final locationController = TextEditingController();
  final attendeesController = TextEditingController();
  final durationController = TextEditingController(text: '60');
  DateTime? startTime;
  DateTime? endTime;

  AppState? _appState;
  int _lastHandledSyncRevision = 0;

  @override
  void initState() {
    super.initState();
    currentWeekStart = _monday(DateTime.now());
    _load(syncGoogle: true, silent: true);
    _loadSuggestions();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Cross-device sync: another device/the web app changed a schedule or
    // email while this screen was open -- AppState's poller (see
    // state/app_state.dart) notifies here so this tab doesn't sit stale
    // until the user manually reopens it. Set up once per AppState
    // instance (didChangeDependencies can fire more than once).
    final appState = context.read<AppState>();
    if (_appState != appState) {
      _appState?.removeListener(_handleWorkspaceSync);
      _appState = appState;
      _lastHandledSyncRevision = appState.syncRevision;
      appState.addListener(_handleWorkspaceSync);
    }
  }

  void _handleWorkspaceSync() {
    final appState = _appState;
    if (appState == null || appState.syncRevision == _lastHandledSyncRevision) {
      return;
    }
    _lastHandledSyncRevision = appState.syncRevision;
    final targets = appState.lastSyncTargets;
    if (targets.contains('schedule')) {
      _load(silent: true);
    }
    if (targets.contains('email')) {
      _loadSuggestions();
    }
  }

  @override
  void dispose() {
    _appState?.removeListener(_handleWorkspaceSync);
    quickAddController.dispose();
    _clearPlanItems();
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
      final days =
          (week is Map && week['days'] is List) ? week['days'] as List : [];
      if (mounted) {
        setState(() {
          schedules = (unified is Map && unified['items'] is List)
              ? unified['items'] as List
              : [];
          weekDays = List.generate(
              7,
              (i) => i < days.length && days[i] is List
                  ? days[i] as List
                  : <dynamic>[]);
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
      if (mounted) {
        setState(() => suggestions =
            (data is Map && data['suggestions'] is List)
                ? data['suggestions'] as List
                : []);
      }
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
      if (mounted) {
        setState(() => suggestions =
            (data is Map && data['suggestions'] is List)
                ? data['suggestions'] as List
                : []);
      }
    } catch (error) {
      if (mounted) {
        _showMessage(t('Không quét được email', 'Could not scan email'),
            error.toString());
      }
    } finally {
      if (mounted) setState(() => suggestionsLoading = false);
    }
  }

  Future<void> _dismissSuggestion(Map suggestion) async {
    try {
      await apiPatch('/email/meeting-suggestions/${suggestion['id']}/status',
          {'status': 'dismissed'});
      await _loadSuggestions();
    } catch (_) {}
  }

  Future<void> _createFromSuggestion(Map suggestion) async {
    final t = context.read<LanguageController>().t;
    final startRaw = suggestion['start_time'] as String?;
    if (startRaw == null || startRaw.isEmpty) {
      setState(() {
        editingSchedule = null;
        titleController.text = (suggestion['title'] ??
            suggestion['subject'] ??
            'Lịch hẹn từ email') as String;
        descriptionController.text = (suggestion['description'] ??
            suggestion['snippet'] ??
            '') as String;
        startTime = null;
        endTime = null;
        showForm = true;
      });
      _showMessage(
          t('Cần bổ sung thời gian', 'Needs a start time'),
          t('Gợi ý này chưa có giờ bắt đầu, hãy nhập thời gian để tạo lịch.',
              'This suggestion has no start time yet -- enter one to create the schedule.'));
      return;
    }
    setState(() => loading = true);
    try {
      final start = DateTime.tryParse(startRaw)?.toLocal() ?? DateTime.now();
      final endRaw = suggestion['end_time'] as String?;
      final end = (endRaw != null && endRaw.isNotEmpty)
          ? DateTime.tryParse(endRaw)?.toLocal()
          : null;
      final data = await apiPost('/schedule/create', {
        'title':
            suggestion['title'] ?? suggestion['subject'] ?? 'Lịch hẹn từ email',
        'description': suggestion['description'] ?? suggestion['snippet'] ?? '',
        'start_time': _isoLocal(start),
        'end_time': _isoLocal(end ?? start.add(const Duration(minutes: 60))),
      });
      final scheduleId = data is Map ? data['schedule_id'] : null;
      await apiPatch('/email/meeting-suggestions/${suggestion['id']}/status',
          {'status': 'created', 'schedule_id': scheduleId});
      await _loadSuggestions();
      await _load();
    } catch (error) {
      _showMessage(t('Không tạo được lịch', 'Could not create schedule'),
          error.toString());
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
    final start =
        DateTime.tryParse((schedule['start_time'] as String?) ?? '')
            ?.toLocal();
    final end = DateTime.tryParse((schedule['end_time'] as String?) ?? '')
        ?.toLocal();
    final attendees = schedule['attendees'];
    setState(() {
      editingSchedule = schedule;
      titleController.text = (schedule['title'] as String?) ?? '';
      descriptionController.text = (schedule['description'] as String?) ?? '';
      locationController.text = (schedule['location'] as String?) ?? '';
      attendeesController.text = attendees is List
          ? attendees.join(', ')
          : (attendees as String? ?? '');
      durationController.text = (start != null && end != null)
          ? end.difference(start).inMinutes.toString()
          : '60';
      startTime = start;
      endTime = end;
      showForm = true;
    });
  }

  Future<void> _submitForm() async {
    final t = context.read<LanguageController>().t;
    if (titleController.text.trim().isEmpty || startTime == null) {
      _showMessage(
          t('Thiếu thông tin', 'Missing info'),
          t('Vui lòng nhập tiêu đề và thời gian bắt đầu.',
              'Please enter a title and start time.'));
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
      'attendees': attendeesController.text
          .trim()
          .split(',')
          .map((e) => e.trim())
          .where((e) => e.isNotEmpty)
          .toList(),
    };
    setState(() => loading = true);
    try {
      if (editingSchedule != null) {
        await apiPut('/schedule/${editingSchedule!['local_id']}', {
          ...payload,
          'expected_updated_at': editingSchedule!['updated_at']
        });
      } else {
        await apiPost('/schedule/create', payload);
      }
      setState(() {
        showForm = false;
        editingSchedule = null;
      });
      await _load();
    } on ApiException catch (error) {
      if (error.status == 409) {
        // The web app or another device saved first -- expected_updated_at
        // is now stale. Close the form (its editingSchedule/timestamp can
        // only get staler if left open) and reload, mirroring the RN
        // client, instead of leaving the user retrying against data the
        // server already rejected once.
        setState(() {
          showForm = false;
          editingSchedule = null;
        });
        await _load();
        _showMessage(
          t('Lịch vừa thay đổi', 'Schedule just changed'),
          t(
            'Web hoặc một thiết bị khác đã lưu trước. Dữ liệu mới nhất đã được tải lại để tránh ghi đè.',
            'The web app or another device saved first. The latest data was reloaded to avoid overwriting it.',
          ),
        );
        return;
      }
      _showMessage(t('Không lưu được lịch', 'Could not save schedule'),
          error.toString());
    } catch (error) {
      _showMessage(t('Không lưu được lịch', 'Could not save schedule'),
          error.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _updateStatus(
      Map<String, dynamic> schedule, String status) async {
    final t = context.read<LanguageController>().t;
    try {
      await apiPatch('/schedule/${schedule['local_id']}/update-status',
          {'status': status, 'expected_updated_at': schedule['updated_at']});
      await _load();
    } on ApiException catch (error) {
      if (error.status == 409) {
        await _load();
        _showMessage(
          t('Lịch vừa thay đổi', 'Schedule just changed'),
          t(
            'Web hoặc một thiết bị khác đã cập nhật lịch này. Dữ liệu mới nhất đã được tải lại.',
            'The web app or another device updated this schedule. The latest data was reloaded.',
          ),
        );
        return;
      }
      _showMessage(t('Không cập nhật được lịch', 'Could not update schedule'),
          error.toString());
    } catch (error) {
      _showMessage(t('Không cập nhật được lịch', 'Could not update schedule'),
          error.toString());
    }
  }

  Future<void> _deleteSchedule(Map<String, dynamic> schedule) async {
    final t = context.read<LanguageController>().t;
    try {
      await apiDelete('/schedule/${schedule['local_id']}');
      if (editingSchedule != null &&
          editingSchedule!['local_id'] == schedule['local_id']) {
        setState(() {
          showForm = false;
          editingSchedule = null;
        });
      }
      await _load();
    } catch (error) {
      if (mounted) {
        _showMessage(t('Không xóa được lịch', 'Could not delete schedule'),
            error.toString());
      }
    }
  }

  void _showMessage(String title, String message) {
    final t = context.read<LanguageController>().t;
    showAppNoticeDialog(
      context,
      title: title,
      message: message,
      actionLabel: t('Đã hiểu', 'Got it'),
      tone: AppNoticeTone.warning,
    );
  }

  Future<void> _pickDateTime(bool isStart) async {
    final initial = (isStart ? startTime : endTime) ?? DateTime.now();
    final date = await showDatePicker(
        context: context,
        initialDate: initial,
        firstDate: DateTime(2020),
        lastDate: DateTime(2100));
    if (date == null || !mounted) return;
    final time = await showTimePicker(
        context: context, initialTime: TimeOfDay.fromDateTime(initial));
    if (time == null) return;
    final combined =
        DateTime(date.year, date.month, date.day, time.hour, time.minute);
    setState(() {
      if (isStart) {
        startTime = combined;
      } else {
        endTime = combined;
      }
    });
  }

  void _shiftWeek(int direction) {
    setState(() => currentWeekStart =
        _monday(currentWeekStart.add(Duration(days: 7 * direction))));
    _load();
  }

  void _clearPlanItems() {
    for (final item in planItems ?? <_PlanItem>[]) {
      item.dispose();
    }
    planItems = null;
    planDate = null;
  }

  Future<void> _handleQuickAdd() async {
    final t = context.read<LanguageController>().t;
    final text = quickAddController.text.trim();
    if (text.isEmpty) {
      _showMessage(t('Thiếu nội dung', 'Missing text'),
          t('Nhập một task hoặc danh sách hoạt động.',
              'Enter a task or a list of activities.'));
      return;
    }
    setState(() {
      quickAddLoading = true;
      _clearPlanItems();
    });
    try {
      final data = await apiPost('/schedule/quick-add', {'text': text});
      if (data is Map && data['kind'] == 'suggested_plan') {
        final items = (data['items'] as List? ?? [])
            .whereType<Map>()
            .map((raw) => _PlanItem(
                  title: (raw['title'] as String?) ?? '',
                  startTime: (raw['start_time'] as String?) ?? '',
                  endTime: raw['end_time'] as String?,
                  durationMinutes: (raw['duration_minutes'] as num?)?.toInt(),
                  reason: (raw['reason'] as String?) ?? '',
                ))
            .where((item) => item.startTime.isNotEmpty)
            .toList();
        setState(() {
          planDate = data['date'] as String?;
          planItems = items;
        });
        return;
      }
      quickAddController.clear();
      final message = data is Map ? data['message'] as String? : null;
      _showMessage(
          t('Đã thêm', 'Added'),
          message ??
              (data is Map && data['kind'] == 'activity'
                  ? t('Đã thêm vào lịch.', 'Added to your calendar.')
                  : t('Đã thêm vào checklist.', 'Added to your checklist.')));
      await _load();
    } catch (error) {
      if (mounted) {
        _showMessage(t('Không thêm nhanh được', 'Could not quick-add'),
            error.toString());
      }
    } finally {
      if (mounted) setState(() => quickAddLoading = false);
    }
  }

  void _cancelPlan() => setState(_clearPlanItems);

  Future<void> _applyPlan() async {
    final t = context.read<LanguageController>().t;
    final selected = (planItems ?? []).where((item) => item.selected).toList();
    if (selected.isEmpty) {
      _showMessage(t('Chưa chọn hoạt động', 'No activity selected'),
          t('Chọn ít nhất một hoạt động để tạo lịch.',
              'Select at least one activity to create a schedule.'));
      return;
    }
    setState(() => planApplying = true);
    try {
      final data = await apiPost('/schedule/plan-day/apply', {
        'date': planDate,
        'items': selected
            .map((item) => {
                  'title': item.title.text.trim(),
                  'start_time': item.startTime,
                  'end_time': item.endTime ?? '',
                  'duration_minutes': item.durationMinutes,
                  'reason': item.reason,
                })
            .toList(),
      });
      quickAddController.clear();
      setState(_clearPlanItems);
      await _load();
      final createdCount = data is Map ? data['created_count'] : null;
      _showMessage(
          t('Đã tạo lịch', 'Schedule created'),
          t('FlowMate đã tạo ${createdCount ?? selected.length} hoạt động.',
              'FlowMate created ${createdCount ?? selected.length} activities.'));
    } catch (error) {
      if (mounted) {
        _showMessage(t('Không áp dụng được lịch', 'Could not apply the plan'),
            error.toString());
      }
    } finally {
      if (mounted) setState(() => planApplying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final lang = context.watch<LanguageController>().language;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: t('Lịch', 'Calendar'),
          refreshing: loading,
          onRefresh: () => _load(syncGoogle: true),
          children: [
            AppButton(
              title: showForm ? t('Đóng', 'Close') : t('Tạo mới', 'New'),
              icon: showForm ? Icons.close_rounded : Icons.add_rounded,
              variant: showForm
                  ? AppButtonVariant.secondary
                  : AppButtonVariant.primary,
              onPressed: () => showForm
                  ? setState(() => showForm = false)
                  : _openCreateForm(),
            ),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('TẠO NHANH BẰNG AI', 'QUICK CREATE WITH AI'),
                      style: TextStyle(
                          color: colors.primary,
                          fontWeight: FontWeight.w700,
                          fontSize: 10,
                          letterSpacing: 1)),
                  const SizedBox(height: 4),
                  Text(
                      t('Nhập một việc hoặc cả danh sách hoạt động, FlowMate sẽ tự xếp lịch.',
                          "Enter a task or a list of activities, FlowMate will schedule them."),
                      style: TextStyle(color: colors.textMuted, fontSize: 12)),
                  const SizedBox(height: 10),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: TextField(
                      controller: quickAddController,
                      minLines: 1,
                      maxLines: 3,
                      style: TextStyle(color: colors.text, fontSize: 14),
                      decoration: InputDecoration(
                        hintText: t(
                            'Ví dụ: Ăn trưa lúc 12h, họp nhóm 3 giờ chiều',
                            'E.g. Lunch at 12, team meeting at 3pm'),
                        hintStyle: TextStyle(color: colors.inputPlaceholder),
                        filled: true,
                        fillColor: colors.panelSoft,
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide(color: colors.border, width: 1.5)),
                        enabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide(color: colors.border, width: 1.5)),
                        focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide(color: colors.primary, width: 1.5)),
                      ),
                    ),
                  ),
                  AppButton(
                    title: t('Tạo nhanh', 'Quick create'),
                    onPressed: _handleQuickAdd,
                    loading: quickAddLoading,
                  ),
                ],
              ),
            ),
            if (planItems != null)
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                        t('Gợi ý lịch cho ${planItems!.length} hoạt động',
                            'Suggested schedule for ${planItems!.length} activities'),
                        style: TextStyle(
                            color: colors.text,
                            fontWeight: FontWeight.w700,
                            fontSize: 14)),
                    const SizedBox(height: 8),
                    for (final item in planItems!)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Checkbox(
                              value: item.selected,
                              activeColor: colors.primary,
                              onChanged: (value) =>
                                  setState(() => item.selected = value ?? true),
                            ),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  TextField(
                                    controller: item.title,
                                    style: TextStyle(
                                        color: colors.text, fontSize: 13),
                                    decoration: const InputDecoration(
                                        isDense: true,
                                        border: InputBorder.none,
                                        contentPadding: EdgeInsets.zero),
                                  ),
                                  Text(
                                      _formatRange(
                                          item.startTime, item.endTime, lang),
                                      style: TextStyle(
                                          color: colors.primary,
                                          fontWeight: FontWeight.w600,
                                          fontSize: 11.5)),
                                  if (item.reason.isNotEmpty)
                                    Text(item.reason,
                                        style: TextStyle(
                                            color: colors.textMuted,
                                            fontSize: 11)),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    Row(
                      children: [
                        Expanded(
                          child: AppButton(
                            title: t('Áp dụng', 'Apply'),
                            onPressed: _applyPlan,
                            loading: planApplying,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: AppButton(
                            title: t('Bỏ qua', 'Dismiss'),
                            variant: AppButtonVariant.secondary,
                            onPressed: planApplying ? null : _cancelPlan,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            if (showForm)
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      editingSchedule != null
                          ? t('Sửa lịch hẹn', 'Edit schedule')
                          : t('Tạo lịch hẹn', 'New schedule'),
                      style: TextStyle(
                          color: colors.text,
                          fontWeight: FontWeight.w700,
                          fontSize: 15),
                    ),
                    const SizedBox(height: 10),
                    AppField(
                        label: t('Tiêu đề', 'Title'),
                        controller: titleController,
                        hint: t('Họp phụ huynh', 'Meeting title')),
                    AppField(
                        label: t('Mô tả', 'Description'),
                        controller: descriptionController,
                        multiline: true),
                    _DateTimeField(
                        label: t('Bắt đầu', 'Start'),
                        value: startTime,
                        onTap: () => _pickDateTime(true),
                        language: lang),
                    _DateTimeField(
                        label: t('Kết thúc', 'End'),
                        value: endTime,
                        onTap: () => _pickDateTime(false),
                        language: lang),
                    AppField(
                        label: t('Thời lượng (phút)', 'Duration (minutes)'),
                        controller: durationController,
                        keyboardType: TextInputType.number),
                    AppField(
                        label: t('Địa điểm', 'Location'),
                        controller: locationController,
                        hint: t('Phòng họp / online', 'Meeting room / online')),
                    AppField(
                        label: t('Người tham dự', 'Attendees'),
                        controller: attendeesController,
                        hint: 'a@example.com, b@example.com'),
                    const SizedBox(height: 4),
                    if (editingSchedule != null)
                      Row(
                        children: [
                          Expanded(
                            child: AppButton(
                              title: t('Xóa lịch hẹn', 'Delete'),
                              variant: AppButtonVariant.danger,
                              onPressed: () =>
                                  _deleteSchedule(editingSchedule!),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: AppButton(
                                title: t('Lưu thay đổi', 'Save'),
                                onPressed: _submitForm,
                                loading: loading),
                          ),
                        ],
                      )
                    else
                      AppButton(
                          title: t('Tạo lịch hẹn', 'Create schedule'),
                          onPressed: _submitForm,
                          loading: loading),
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
                            Text(t('THỜI KHÓA BIỂU', 'TIMETABLE'),
                                style: TextStyle(
                                    color: colors.primary,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 10,
                                    letterSpacing: 1)),
                            const SizedBox(height: 2),
                            Text(_formatWeekRange(currentWeekStart, lang),
                                style: TextStyle(
                                    color: colors.text,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 14)),
                          ],
                        ),
                      ),
                      IconButton(
                          icon: Icon(Icons.chevron_left, color: colors.primary),
                          onPressed: () => _shiftWeek(-1)),
                      IconButton(
                        icon: Icon(Icons.today_outlined,
                            color: colors.primary, size: 18),
                        onPressed: () {
                          setState(
                              () => currentWeekStart = _monday(DateTime.now()));
                          _load();
                        },
                      ),
                      IconButton(
                          icon:
                              Icon(Icons.chevron_right, color: colors.primary),
                          onPressed: () => _shiftWeek(1)),
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
                            Text(t('GỢI Ý TỪ EMAIL', 'FROM EMAIL'),
                                style: TextStyle(
                                    color: colors.primary,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 10,
                                    letterSpacing: 1)),
                            const SizedBox(height: 2),
                            Text(
                                t('Cuộc họp phát hiện được',
                                    'Detected meetings'),
                                style: TextStyle(
                                    color: colors.text,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 14)),
                          ],
                        ),
                      ),
                      IntrinsicWidth(
                        child: AppButton(
                            title: t('Quét email', 'Scan'),
                            variant: AppButtonVariant.secondary,
                            onPressed: _scanSuggestions,
                            loading: suggestionsLoading),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  if (suggestions.isEmpty)
                    Text(
                        t('Chưa có gợi ý lịch mới.',
                            'No new schedule suggestions yet.'),
                        style: TextStyle(color: colors.textMuted, fontSize: 13))
                  else
                    ...suggestions.map((raw) {
                      final s = Map<String, dynamic>.from(raw as Map);
                      final startRaw = s['start_time'] as String?;
                      final start = (startRaw != null && startRaw.isNotEmpty)
                          ? DateTime.tryParse(startRaw)?.toLocal()
                          : null;
                      return Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                                (s['title'] ??
                                    s['subject'] ??
                                    t('Lịch hẹn từ email',
                                        'Meeting from email')) as String,
                                style: TextStyle(
                                    color: colors.text,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 13)),
                            const SizedBox(height: 2),
                            Text(
                                '${t('Từ', 'From')}: ${s['sender'] ?? t('Không xác định', 'Unknown')}',
                                style: TextStyle(
                                    color: colors.textMuted, fontSize: 11.5)),
                            Text(
                                start != null
                                    ? _formatShort(start, lang)
                                    : t('Chưa xác định thời gian',
                                        'No time set'),
                                style: TextStyle(
                                    color: colors.textMuted, fontSize: 11.5)),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                Expanded(
                                    child: AppButton(
                                        title: t('Tạo lịch', 'Create'),
                                        onPressed: () =>
                                            _createFromSuggestion(s))),
                                const SizedBox(width: 8),
                                Expanded(
                                    child: AppButton(
                                        title: t('Bỏ qua', 'Dismiss'),
                                        variant: AppButtonVariant.secondary,
                                        onPressed: () =>
                                            _dismissSuggestion(s))),
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
              AppCard(
                  child: AppEmptyState(
                      icon: Icons.event_busy_outlined,
                      title: t('Chưa có lịch sắp tới', 'No upcoming schedule')))
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
                              child: Text(s['title'] as String? ?? '',
                                  style: TextStyle(
                                      color: colors.text,
                                      fontWeight: FontWeight.w700,
                                      fontSize: 15)),
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                _Badge(
                                    text: _sourceLabel(s, t),
                                    color: colors.primary),
                                if (status != null && status != 'pending') ...[
                                  const SizedBox(height: 4),
                                  _Badge(
                                      text: _statusLabel(status, t),
                                      color: isCompleted
                                          ? colors.success
                                          : colors.danger),
                                ],
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                            _formatRange(s['start_time'] as String?,
                                s['end_time'] as String?, lang),
                            style: TextStyle(
                                color: colors.primary,
                                fontWeight: FontWeight.w600,
                                fontSize: 12)),
                        if ((s['description'] as String?)?.isNotEmpty ==
                            true) ...[
                          const SizedBox(height: 6),
                          Text(s['description'] as String,
                              style: TextStyle(
                                  color: colors.textMuted,
                                  fontSize: 12,
                                  height: 1.4)),
                        ],
                        if ((s['location'] as String?)?.isNotEmpty == true) ...[
                          const SizedBox(height: 4),
                          Text('${t('Địa điểm', 'Location')}: ${s['location']}',
                              style: TextStyle(
                                  color: colors.textMuted, fontSize: 12)),
                        ],
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            if (hasLocalId) ...[
                              IntrinsicWidth(
                                child: AppButton(
                                  title: isCompleted
                                      ? t('Bỏ hoàn thành', 'Undo')
                                      : t('Hoàn tất', 'Complete'),
                                  variant: AppButtonVariant.secondary,
                                  onPressed: () => _updateStatus(
                                      s, isCompleted ? 'pending' : 'completed'),
                                ),
                              ),
                              IntrinsicWidth(
                                  child: AppButton(
                                      title: t('Sửa', 'Edit'),
                                      variant: AppButtonVariant.secondary,
                                      onPressed: () => _openEditForm(s))),
                              IntrinsicWidth(
                                  child: AppButton(
                                      title: t('Hủy', 'Cancel'),
                                      variant: AppButtonVariant.danger,
                                      onPressed: () =>
                                          _updateStatus(s, 'cancelled'))),
                            ] else if (s['html_link'] != null ||
                                s['web_link'] != null)
                              IntrinsicWidth(
                                child: AppButton(
                                  title: t('Mở lịch', 'Open'),
                                  variant: AppButtonVariant.secondary,
                                  onPressed: () => launchUrl(
                                      Uri.parse((s['html_link'] ??
                                          s['web_link']) as String),
                                      mode: LaunchMode.externalApplication),
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

  List<Widget> _buildTimetable(
      dynamic colors, String Function(String, [String?]) t, String lang) {
    final today = _dateParam(DateTime.now());
    final names = lang == 'en' ? _dayNamesEn : _dayNamesVi;
    return List.generate(7, (i) {
      final dayDate = currentWeekStart.add(Duration(days: i));
      final isToday = _dateParam(dayDate) == today;
      final events = List<dynamic>.from(weekDays[i])
        ..removeWhere((e) => e is! Map || (e['start_time'] as String?) == null)
        ..sort((a, b) => ((a as Map)['start_time'] as String)
            .compareTo((b as Map)['start_time'] as String));
      return Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(vertical: 6),
              decoration: BoxDecoration(
                  border: Border(
                      bottom: BorderSide(
                          color: isToday ? colors.primary : colors.border))),
              child: Row(
                children: [
                  Text(
                      '${names[i]}, ${dayDate.day.toString().padLeft(2, '0')}/${dayDate.month.toString().padLeft(2, '0')}',
                      style: TextStyle(
                          color: isToday ? colors.primary : colors.textMuted,
                          fontWeight:
                              isToday ? FontWeight.w800 : FontWeight.w600,
                          fontSize: 13)),
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
                child: Text(t('Không có lịch hẹn', 'No events'),
                    style: TextStyle(color: colors.textMuted, fontSize: 12)),
              )
            else
              ...events.map((raw) {
                final e = Map<String, dynamic>.from(raw as Map);
                final start =
                    DateTime.tryParse(e['start_time'] as String)?.toLocal();
                final end = (e['end_time'] as String?) != null
                    ? DateTime.tryParse(e['end_time'] as String)?.toLocal()
                    : null;
                final timeText = start == null
                    ? ''
                    : '${start.hour.toString().padLeft(2, '0')}:${start.minute.toString().padLeft(2, '0')}'
                        '${end != null ? '–${end.hour.toString().padLeft(2, '0')}:${end.minute.toString().padLeft(2, '0')}' : ''}';
                return InkWell(
                  onTap: () {
                    if (e['local_id'] != null) {
                      _openEditForm(e);
                    } else if (e['html_link'] != null ||
                        e['web_link'] != null) {
                      launchUrl(
                          Uri.parse(
                              (e['html_link'] ?? e['web_link']) as String),
                          mode: LaunchMode.externalApplication);
                    }
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    decoration: BoxDecoration(
                        border:
                            Border(bottom: BorderSide(color: colors.border))),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                            width: 78,
                            child: Text(timeText,
                                style: TextStyle(
                                    color: colors.primary,
                                    fontWeight: FontWeight.w600,
                                    fontSize: 12))),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                  e['title'] as String? ??
                                      t('Sự kiện', 'Event'),
                                  maxLines: 2,
                                  style: TextStyle(
                                      color: colors.text,
                                      fontWeight: FontWeight.w600,
                                      fontSize: 13)),
                              Text(_sourceLabel(e, t),
                                  style: TextStyle(
                                      color: colors.textMuted,
                                      fontSize: 10.5,
                                      fontWeight: FontWeight.w600)),
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
    final provider =
        (schedule['provider'] ?? schedule['source'] ?? '') as String;
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
    String fmt(DateTime d) =>
        lang == 'en' ? '${d.month}/${d.day}' : '${d.day}/${d.month}';
    return '${fmt(start)} - ${fmt(end)}/${end.year}';
  }

  String _formatRange(String? startValue, String? endValue, String lang) {
    if (startValue == null) return '';
    // .toLocal() is a no-op for an already-naive (local, no offset) string --
    // safe here -- but required for a tz-aware "+00:00" string (every
    // schedule read back from Postgres), which otherwise displays as raw
    // UTC instead of Vietnam wall-clock time.
    final start = DateTime.tryParse(startValue)?.toLocal();
    if (start == null) return startValue;
    final startText = _formatFull(start, lang);
    if (endValue == null) return startText;
    final end = DateTime.tryParse(endValue)?.toLocal();
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
      decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(999)),
      child: Text(text,
          style: TextStyle(
              color: color, fontWeight: FontWeight.w700, fontSize: 10.5)),
    );
  }
}

class _DateTimeField extends StatelessWidget {
  final String label;
  final DateTime? value;
  final VoidCallback onTap;
  final String language;
  const _DateTimeField(
      {required this.label,
      required this.value,
      required this.onTap,
      required this.language});

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
          Text(label,
              style: TextStyle(
                  color: colors.textMuted,
                  fontWeight: FontWeight.w600,
                  fontSize: 12)),
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
                  Icon(Icons.calendar_today_outlined,
                      size: 16, color: colors.textMuted),
                  const SizedBox(width: 10),
                  Text(
                    text.isEmpty
                        ? (language == 'en'
                            ? 'Select date & time'
                            : 'Chọn ngày giờ')
                        : text,
                    style: TextStyle(
                        color: text.isEmpty
                            ? colors.inputPlaceholder
                            : colors.text,
                        fontSize: 14),
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
