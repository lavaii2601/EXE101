import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../config/app_icons.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';

const List<String> _kProjectStatuses = ['planning', 'active', 'on_hold', 'completed', 'archived'];
const List<String> _kTaskStatusCycle = ['todo', 'in_progress', 'blocked', 'done'];
const List<String> _kTaskPriorities = ['low', 'medium', 'high', 'urgent'];

String _statusLabel(String value, String Function(String, [String?]) t) {
  const labels = {
    'planning': ['Lên kế hoạch', 'Planning'],
    'active': ['Đang triển khai', 'Active'],
    'on_hold': ['Tạm dừng', 'On hold'],
    'completed': ['Hoàn thành', 'Completed'],
    'archived': ['Lưu trữ', 'Archived'],
    'todo': ['Cần làm', 'To do'],
    'in_progress': ['Đang làm', 'In progress'],
    'blocked': ['Đang vướng', 'Blocked'],
    'done': ['Xong', 'Done'],
    'cancelled': ['Đã huỷ', 'Cancelled'],
    'low': ['Thấp', 'Low'],
    'medium': ['Trung bình', 'Medium'],
    'high': ['Cao', 'High'],
    'urgent': ['Khẩn cấp', 'Urgent'],
  };
  final pair = labels[value];
  return pair == null ? value : t(pair[0], pair[1]);
}

/// Shared projects/tasks for the active Business workspace (Phase 3 "Work
/// Hub"), reached from Settings. Mirrors the web client's "Công việc" page
/// (web/frontend/index.html work-hub-page + its app.js loadWorkHubPage/
/// renderWorkHubProjects/renderWorkHubTasks functions) and
/// routes/work_hub.py's /api/projects, /api/tasks endpoints.
class WorkHubScreen extends StatefulWidget {
  const WorkHubScreen({super.key});

  @override
  State<WorkHubScreen> createState() => _WorkHubScreenState();
}

class _WorkHubScreenState extends State<WorkHubScreen> {
  List<Map<String, dynamic>> projects = [];
  List<Map<String, dynamic>> tasks = [];
  String? selectedProjectId;
  bool loading = false;
  bool loadingTasks = false;

  final projectNameController = TextEditingController();
  final projectDescriptionController = TextEditingController();
  String projectStatus = 'planning';
  String projectVisibility = 'workspace';
  DateTime? projectStartDate;
  DateTime? projectDueDate;
  bool creatingProject = false;

  final taskTitleController = TextEditingController();
  String taskPriority = 'medium';
  DateTime? taskDueDate;
  bool creatingTask = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    projectNameController.dispose();
    projectDescriptionController.dispose();
    taskTitleController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await apiGet('/projects');
      if (data is Map && data['success'] == true) {
        projects = List<Map<String, dynamic>>.from(
          ((data['projects'] as List?) ?? []).map((p) => Map<String, dynamic>.from(p as Map)),
        );
      }
    } catch (_) {}
    if (mounted) setState(() => loading = false);
    if (selectedProjectId != null && projects.any((p) => p['id'] == selectedProjectId)) {
      await _loadTasks(selectedProjectId!);
    } else if (selectedProjectId != null && mounted) {
      // The previously selected project no longer exists (deleted elsewhere) --
      // clear it and re-render so the stale tasks card doesn't linger on screen.
      setState(() {
        selectedProjectId = null;
        tasks = [];
      });
    }
  }

  Future<void> _loadTasks(String projectId) async {
    setState(() {
      selectedProjectId = projectId;
      loadingTasks = true;
    });
    try {
      final data = await apiGet('/tasks?project_id=$projectId');
      if (data is Map && data['success'] == true) {
        tasks = List<Map<String, dynamic>>.from(
          ((data['tasks'] as List?) ?? []).map((t) => Map<String, dynamic>.from(t as Map)),
        );
      }
    } catch (_) {}
    if (mounted) setState(() => loadingTasks = false);
  }

  Future<void> _createProject() async {
    final name = projectNameController.text.trim();
    if (name.isEmpty) return;
    setState(() => creatingProject = true);
    try {
      await apiPost('/projects', {
        'name': name,
        if (projectDescriptionController.text.trim().isNotEmpty)
          'description': projectDescriptionController.text.trim(),
        'status': projectStatus,
        'visibility': projectVisibility,
        if (projectStartDate != null) 'start_date': _isoDate(projectStartDate!),
        if (projectDueDate != null) 'due_date': _isoDate(projectDueDate!),
      });
      projectNameController.clear();
      projectDescriptionController.clear();
      setState(() {
        projectStatus = 'planning';
        projectVisibility = 'workspace';
        projectStartDate = null;
        projectDueDate = null;
      });
      await _load();
    } catch (_) {
      if (mounted) {
        final t = context.read<LanguageController>().t;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không tạo được dự án', 'Could not create project'))),
        );
      }
    } finally {
      if (mounted) setState(() => creatingProject = false);
    }
  }

  Future<void> _deleteProject(String projectId) async {
    final t = context.read<LanguageController>().t;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Xoá dự án?', 'Delete project?')),
        content: Text(t(
          'Toàn bộ nhiệm vụ trong dự án cũng sẽ bị xoá.',
          'All of its tasks will be deleted too.',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Xoá', 'Delete'))),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await apiDelete('/projects/$projectId');
      if (selectedProjectId == projectId) {
        selectedProjectId = null;
        tasks = [];
      }
      await _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không xoá được dự án', 'Could not delete project'))),
        );
      }
    }
  }

  Future<void> _createTask() async {
    if (selectedProjectId == null) return;
    final title = taskTitleController.text.trim();
    if (title.isEmpty) return;
    setState(() => creatingTask = true);
    try {
      await apiPost('/tasks', {
        'project_id': selectedProjectId,
        'title': title,
        'priority': taskPriority,
        if (taskDueDate != null) 'due_date': _isoDate(taskDueDate!),
      });
      taskTitleController.clear();
      setState(() {
        taskPriority = 'medium';
        taskDueDate = null;
      });
      await _loadTasks(selectedProjectId!);
    } catch (_) {
      if (mounted) {
        final t = context.read<LanguageController>().t;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không tạo được nhiệm vụ', 'Could not create task'))),
        );
      }
    } finally {
      if (mounted) setState(() => creatingTask = false);
    }
  }

  Future<void> _cycleTaskStatus(Map<String, dynamic> task) async {
    final current = task['status'] as String? ?? 'todo';
    final nextIndex = (_kTaskStatusCycle.indexOf(current) + 1) % _kTaskStatusCycle.length;
    final nextStatus = _kTaskStatusCycle[nextIndex];
    try {
      final data = await apiPatch('/tasks/${task['id']}', {'status': nextStatus});
      if (data is Map && data['success'] == true) {
        setState(() => task['status'] = (data['task'] as Map)['status']);
      }
    } catch (_) {}
  }

  Future<void> _deleteTask(String taskId) async {
    try {
      await apiDelete('/tasks/$taskId');
      if (selectedProjectId != null) await _loadTasks(selectedProjectId!);
    } catch (_) {}
  }

  String _isoDate(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

  Future<DateTime?> _pickDate(DateTime? initial) {
    final now = DateTime.now();
    return showDatePicker(
      context: context,
      initialDate: initial ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 5),
    );
  }

  Color _badgeColor(String status, AppColors colors) {
    if (status == 'blocked') return colors.danger;
    if (status == 'done' || status == 'completed') return colors.success;
    return colors.primary;
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final workspace = context.watch<WorkspaceController>();
    final canManage = workspace.canManage;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 6, 20, 6),
              child: Row(
                children: [
                  IconButton(icon: Icon(AppIcons.emailBack, color: colors.text), onPressed: () => Navigator.pop(context)),
                  Expanded(
                    child: Text(t('Công việc', 'Work Hub'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
                  ),
                ],
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  children: [
                    if (loading)
                      const Padding(padding: EdgeInsets.symmetric(vertical: 40), child: Center(child: CircularProgressIndicator()))
                    else ...[
                      if (canManage) ...[
                        AppCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t('DỰ ÁN MỚI', 'NEW PROJECT'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                              const SizedBox(height: 10),
                              AppField(label: t('Tên dự án', 'Project name'), controller: projectNameController),
                              AppField(label: t('Mô tả', 'Description'), controller: projectDescriptionController, multiline: true),
                              Row(
                                children: [
                                  Expanded(
                                    child: DropdownButtonFormField<String>(
                                      value: projectStatus,
                                      items: _kProjectStatuses
                                          .map((s) => DropdownMenuItem(value: s, child: Text(_statusLabel(s, t), style: TextStyle(color: colors.text, fontSize: 12.5))))
                                          .toList(),
                                      onChanged: (v) => setState(() => projectStatus = v ?? projectStatus),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: DropdownButtonFormField<String>(
                                      value: projectVisibility,
                                      items: [
                                        DropdownMenuItem(value: 'workspace', child: Text(t('Cả không gian', 'Whole workspace'), style: TextStyle(color: colors.text, fontSize: 12.5))),
                                        DropdownMenuItem(value: 'private', child: Text(t('Riêng tư', 'Private'), style: TextStyle(color: colors.text, fontSize: 12.5))),
                                      ],
                                      onChanged: (v) => setState(() => projectVisibility = v ?? projectVisibility),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Row(
                                children: [
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: () async {
                                        final picked = await _pickDate(projectStartDate);
                                        if (picked != null) setState(() => projectStartDate = picked);
                                      },
                                      child: Text(projectStartDate == null ? t('Ngày bắt đầu', 'Start date') : _isoDate(projectStartDate!), style: const TextStyle(fontSize: 12)),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: () async {
                                        final picked = await _pickDate(projectDueDate);
                                        if (picked != null) setState(() => projectDueDate = picked);
                                      },
                                      child: Text(projectDueDate == null ? t('Hạn chót', 'Due date') : _isoDate(projectDueDate!), style: const TextStyle(fontSize: 12)),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              AppButton(title: t('Tạo dự án', 'Create project'), onPressed: _createProject, loading: creatingProject),
                            ],
                          ),
                        ),
                        const SizedBox(height: 14),
                      ],
                      AppCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('DỰ ÁN', 'PROJECTS'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                            const SizedBox(height: 10),
                            if (projects.isEmpty)
                              Text(t('Chưa có dự án nào.', 'No projects yet.'), style: TextStyle(color: colors.textMuted, fontSize: 13)),
                            ...projects.map((project) {
                              final isActive = project['id'] == selectedProjectId;
                              return Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: InkWell(
                                  onTap: () => _loadTasks(project['id'] as String),
                                  child: Container(
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      color: isActive ? colors.primarySoft : colors.panelSoft,
                                      borderRadius: BorderRadius.circular(12),
                                      border: Border.all(color: isActive ? colors.primary : colors.border),
                                    ),
                                    child: Row(
                                      children: [
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(project['name'] as String? ?? '', style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                                              Text(
                                                project['due_date'] != null ? '${t('Hạn', 'Due')} ${project['due_date']}' : t('Không có hạn', 'No due date'),
                                                style: TextStyle(color: colors.textMuted, fontSize: 11),
                                              ),
                                            ],
                                          ),
                                        ),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                          decoration: BoxDecoration(color: _badgeColor(project['status'] as String? ?? '', colors).withValues(alpha: 0.14), borderRadius: BorderRadius.circular(999)),
                                          child: Text(_statusLabel(project['status'] as String? ?? '', t), style: TextStyle(color: _badgeColor(project['status'] as String? ?? '', colors), fontWeight: FontWeight.w700, fontSize: 10)),
                                        ),
                                        if (canManage)
                                          IconButton(
                                            icon: Icon(Icons.delete_outline, size: 18, color: colors.danger),
                                            onPressed: () => _deleteProject(project['id'] as String),
                                          ),
                                      ],
                                    ),
                                  ),
                                ),
                              );
                            }),
                          ],
                        ),
                      ),
                      if (selectedProjectId != null) ...[
                        const SizedBox(height: 14),
                        AppCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t('NHIỆM VỤ', 'TASKS'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                              const SizedBox(height: 10),
                              AppField(label: t('Tên nhiệm vụ', 'Task title'), controller: taskTitleController),
                              Row(
                                children: [
                                  Expanded(
                                    child: DropdownButtonFormField<String>(
                                      value: taskPriority,
                                      items: _kTaskPriorities
                                          .map((p) => DropdownMenuItem(value: p, child: Text(_statusLabel(p, t), style: TextStyle(color: colors.text, fontSize: 12.5))))
                                          .toList(),
                                      onChanged: (v) => setState(() => taskPriority = v ?? taskPriority),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: () async {
                                        final picked = await _pickDate(taskDueDate);
                                        if (picked != null) setState(() => taskDueDate = picked);
                                      },
                                      child: Text(taskDueDate == null ? t('Hạn chót', 'Due date') : _isoDate(taskDueDate!), style: const TextStyle(fontSize: 12)),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 10),
                              AppButton(title: t('Thêm nhiệm vụ', 'Add task'), variant: AppButtonVariant.secondary, onPressed: _createTask, loading: creatingTask),
                              const SizedBox(height: 12),
                              if (loadingTasks)
                                const Center(child: CircularProgressIndicator())
                              else if (tasks.isEmpty)
                                Text(t('Chưa có nhiệm vụ nào.', 'No tasks yet.'), style: TextStyle(color: colors.textMuted, fontSize: 13))
                              else
                                ...tasks.map((task) => Padding(
                                      padding: const EdgeInsets.only(bottom: 8),
                                      child: Container(
                                        padding: const EdgeInsets.all(10),
                                        decoration: BoxDecoration(color: colors.panelSoft, borderRadius: BorderRadius.circular(12), border: Border.all(color: colors.border)),
                                        child: Row(
                                          children: [
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment: CrossAxisAlignment.start,
                                                children: [
                                                  Text(task['title'] as String? ?? '', style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                                                  Text(
                                                    '${_statusLabel(task['priority'] as String? ?? '', t)}${task['due_date'] != null ? ' · ${task['due_date']}' : ''}',
                                                    style: TextStyle(color: colors.textMuted, fontSize: 11),
                                                  ),
                                                ],
                                              ),
                                            ),
                                            GestureDetector(
                                              onTap: () => _cycleTaskStatus(task),
                                              child: Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                                decoration: BoxDecoration(color: _badgeColor(task['status'] as String? ?? '', colors).withValues(alpha: 0.14), borderRadius: BorderRadius.circular(999)),
                                                child: Text(_statusLabel(task['status'] as String? ?? '', t), style: TextStyle(color: _badgeColor(task['status'] as String? ?? '', colors), fontWeight: FontWeight.w700, fontSize: 10)),
                                              ),
                                            ),
                                            IconButton(
                                              icon: Icon(Icons.delete_outline, size: 18, color: colors.danger),
                                              onPressed: () => _deleteTask(task['id'] as String),
                                            ),
                                          ],
                                        ),
                                      ),
                                    )),
                            ],
                          ),
                        ),
                      ],
                    ],
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
