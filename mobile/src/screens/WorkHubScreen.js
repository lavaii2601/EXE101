import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Modal, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { useOrgWorkspace } from '../state/OrgWorkspaceContext';
import { apiDelete, apiGet, apiPatch, apiPost } from '../api/client';
import Button from '../components/Button';
import DateTimeField from '../components/DateTimeField';

const PROJECT_STATUSES = ['planning', 'active', 'on_hold', 'completed', 'archived'];
const TASK_STATUS_CYCLE = ['todo', 'in_progress', 'blocked', 'done'];
const TASK_PRIORITIES = ['low', 'medium', 'high', 'urgent'];

const LABELS = {
  planning: ['Lên kế hoạch', 'Planning'],
  active: ['Đang triển khai', 'Active'],
  on_hold: ['Tạm dừng', 'On hold'],
  completed: ['Hoàn thành', 'Completed'],
  archived: ['Lưu trữ', 'Archived'],
  todo: ['Cần làm', 'To do'],
  in_progress: ['Đang làm', 'In progress'],
  blocked: ['Đang vướng', 'Blocked'],
  done: ['Xong', 'Done'],
  cancelled: ['Đã huỷ', 'Cancelled'],
  low: ['Thấp', 'Low'],
  medium: ['Trung bình', 'Medium'],
  high: ['Cao', 'High'],
  urgent: ['Khẩn cấp', 'Urgent'],
  workspace: ['Cả không gian', 'Whole workspace'],
  private: ['Riêng tư', 'Private'],
};

function statusLabel(value, t) {
  const pair = LABELS[value];
  return pair ? t(...pair) : value;
}

function badgeColor(status, colors) {
  if (status === 'blocked') return colors.danger;
  if (status === 'done' || status === 'completed') return colors.success;
  return colors.primary;
}

// Only the date part matters for project/task due dates (backend columns
// are DATE, not TIMESTAMPTZ) -- DateTimeField produces a full local ISO
// datetime string, so keep just its leading YYYY-MM-DD.
function toDateOnly(isoLocal) {
  return isoLocal ? isoLocal.slice(0, 10) : undefined;
}

// Shared projects/tasks for the active Business workspace (Phase 3 "Work
// Hub"), reached from Settings. Mirrors the web client's "Công việc" page
// and the Flutter client's WorkHubScreen, both built on top of
// routes/work_hub.py's /api/projects, /api/tasks endpoints.
export default function WorkHubScreen({ visible, onClose }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const workspace = useOrgWorkspace();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const canManage = workspace?.canManage;

  const [projects, setProjects] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingTasks, setLoadingTasks] = useState(false);

  const [projectName, setProjectName] = useState('');
  const [projectDescription, setProjectDescription] = useState('');
  const [projectStatus, setProjectStatus] = useState('planning');
  const [projectVisibility, setProjectVisibility] = useState('workspace');
  const [projectDueDate, setProjectDueDate] = useState('');
  const [creatingProject, setCreatingProject] = useState(false);

  const [taskTitle, setTaskTitle] = useState('');
  const [taskPriority, setTaskPriority] = useState('medium');
  const [taskDueDate, setTaskDueDate] = useState('');
  const [creatingTask, setCreatingTask] = useState(false);

  const loadTasks = useCallback(async (projectId) => {
    setLoadingTasks(true);
    try {
      const data = await apiGet(`/tasks?project_id=${encodeURIComponent(projectId)}`);
      if (data?.success) setTasks(data.tasks || []);
    } catch { /* keep whatever was already shown */ }
    setLoadingTasks(false);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    let list = [];
    try {
      const data = await apiGet('/projects');
      if (data?.success) list = data.projects || [];
    } catch { /* keep whatever was already shown */ }
    setProjects(list);
    setLoading(false);

    if (selectedProjectId && list.some((p) => p.id === selectedProjectId)) {
      await loadTasks(selectedProjectId);
    } else if (selectedProjectId) {
      setSelectedProjectId(null);
      setTasks([]);
    }
    // selectedProjectId intentionally omitted -- this reload path only cares
    // about the value at call time, re-running it on every selection change
    // would refetch projects needlessly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadTasks]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  const selectProject = (projectId) => {
    setSelectedProjectId(projectId);
    loadTasks(projectId);
  };

  const createProject = async () => {
    if (!projectName.trim()) return;
    setCreatingProject(true);
    try {
      await apiPost('/projects', {
        name: projectName.trim(),
        description: projectDescription.trim() || undefined,
        status: projectStatus,
        visibility: projectVisibility,
        due_date: toDateOnly(projectDueDate),
      });
      setProjectName('');
      setProjectDescription('');
      setProjectStatus('planning');
      setProjectVisibility('workspace');
      setProjectDueDate('');
      await load();
    } catch (error) {
      Alert.alert(t('Không tạo được dự án', 'Could not create project'), error.message);
    } finally {
      setCreatingProject(false);
    }
  };

  const deleteProject = (projectId) => {
    Alert.alert(
      t('Xoá dự án?', 'Delete project?'),
      t('Toàn bộ nhiệm vụ trong dự án cũng sẽ bị xoá.', 'All of its tasks will be deleted too.'),
      [
        { text: t('Hủy', 'Cancel'), style: 'cancel' },
        {
          text: t('Xoá', 'Delete'),
          style: 'destructive',
          onPress: async () => {
            try {
              await apiDelete(`/projects/${projectId}`);
              if (selectedProjectId === projectId) {
                setSelectedProjectId(null);
                setTasks([]);
              }
              await load();
            } catch (error) {
              Alert.alert(t('Không xoá được dự án', 'Could not delete project'), error.message);
            }
          },
        },
      ]
    );
  };

  const createTask = async () => {
    if (!selectedProjectId || !taskTitle.trim()) return;
    setCreatingTask(true);
    try {
      await apiPost('/tasks', {
        project_id: selectedProjectId,
        title: taskTitle.trim(),
        priority: taskPriority,
        due_date: toDateOnly(taskDueDate),
      });
      setTaskTitle('');
      setTaskPriority('medium');
      setTaskDueDate('');
      await loadTasks(selectedProjectId);
    } catch (error) {
      Alert.alert(t('Không tạo được nhiệm vụ', 'Could not create task'), error.message);
    } finally {
      setCreatingTask(false);
    }
  };

  const cycleTaskStatus = async (task) => {
    const nextStatus = TASK_STATUS_CYCLE[(TASK_STATUS_CYCLE.indexOf(task.status) + 1) % TASK_STATUS_CYCLE.length];
    try {
      const data = await apiPatch(`/tasks/${task.id}`, { status: nextStatus });
      if (data?.success) {
        setTasks((current) => current.map((item) => (item.id === task.id ? { ...item, status: data.task.status } : item)));
      }
    } catch { /* no-op: badge stays as-is, user can retry */ }
  };

  const deleteTask = async (taskId) => {
    try {
      await apiDelete(`/tasks/${taskId}`);
      if (selectedProjectId) await loadTasks(selectedProjectId);
    } catch { /* no-op: list stays as-is, user can retry */ }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.root}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={22} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>{t('Công việc', 'Work Hub')}</Text>
        </View>

        <ScrollView contentContainerStyle={styles.body}>
          {loading ? (
            <ActivityIndicator style={{ marginVertical: 40 }} color={colors.primary} />
          ) : (
            <>
              {canManage ? (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>{t('DỰ ÁN MỚI', 'NEW PROJECT')}</Text>
                  <Text style={styles.fieldLabel}>{t('Tên dự án', 'Project name')}</Text>
                  <TextInput
                    style={styles.input}
                    value={projectName}
                    onChangeText={setProjectName}
                    placeholderTextColor={colors.inputPlaceholder}
                  />
                  <Text style={styles.fieldLabel}>{t('Mô tả', 'Description')}</Text>
                  <TextInput
                    style={[styles.input, styles.multiline]}
                    value={projectDescription}
                    onChangeText={setProjectDescription}
                    multiline
                    placeholderTextColor={colors.inputPlaceholder}
                  />
                  <Text style={styles.fieldLabel}>{t('Trạng thái', 'Status')}</Text>
                  <View style={styles.chipRow}>
                    {PROJECT_STATUSES.map((s) => (
                      <TouchableOpacity
                        key={s}
                        style={[styles.chip, projectStatus === s && styles.chipActive]}
                        onPress={() => setProjectStatus(s)}
                      >
                        <Text style={styles.chipText}>{statusLabel(s, t)}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <Text style={styles.fieldLabel}>{t('Hiển thị', 'Visibility')}</Text>
                  <View style={styles.chipRow}>
                    {['workspace', 'private'].map((v) => (
                      <TouchableOpacity
                        key={v}
                        style={[styles.chip, projectVisibility === v && styles.chipActive]}
                        onPress={() => setProjectVisibility(v)}
                      >
                        <Text style={styles.chipText}>{statusLabel(v, t)}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <DateTimeField label={t('Hạn chót', 'Due date')} value={projectDueDate} onChange={setProjectDueDate} />
                  <Button title={t('Tạo dự án', 'Create project')} onPress={createProject} loading={creatingProject} />
                </View>
              ) : null}

              <View style={styles.section}>
                <Text style={styles.sectionLabel}>{t('DỰ ÁN', 'PROJECTS')}</Text>
                {projects.map((project) => {
                  const isActive = project.id === selectedProjectId;
                  return (
                    <TouchableOpacity
                      key={project.id}
                      style={[styles.itemRow, isActive && styles.itemRowActive]}
                      onPress={() => selectProject(project.id)}
                      activeOpacity={0.8}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle}>{project.name}</Text>
                        <Text style={styles.itemMeta}>
                          {project.due_date ? `${t('Hạn', 'Due')} ${project.due_date}` : t('Không có hạn', 'No due date')}
                        </Text>
                      </View>
                      <View style={[styles.badge, { backgroundColor: `${badgeColor(project.status, colors)}24` }]}>
                        <Text style={[styles.badgeText, { color: badgeColor(project.status, colors) }]}>{statusLabel(project.status, t)}</Text>
                      </View>
                      {canManage ? (
                        <TouchableOpacity onPress={() => deleteProject(project.id)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} style={{ marginLeft: 10 }}>
                          <Ionicons name="trash-outline" size={18} color={colors.danger} />
                        </TouchableOpacity>
                      ) : null}
                    </TouchableOpacity>
                  );
                })}
                {!projects.length ? <Text style={styles.emptyText}>{t('Chưa có dự án nào.', 'No projects yet.')}</Text> : null}
              </View>

              {selectedProjectId ? (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>{t('NHIỆM VỤ', 'TASKS')}</Text>
                  <Text style={styles.fieldLabel}>{t('Tên nhiệm vụ', 'Task title')}</Text>
                  <TextInput
                    style={styles.input}
                    value={taskTitle}
                    onChangeText={setTaskTitle}
                    placeholderTextColor={colors.inputPlaceholder}
                  />
                  <Text style={styles.fieldLabel}>{t('Độ ưu tiên', 'Priority')}</Text>
                  <View style={styles.chipRow}>
                    {TASK_PRIORITIES.map((p) => (
                      <TouchableOpacity
                        key={p}
                        style={[styles.chip, taskPriority === p && styles.chipActive]}
                        onPress={() => setTaskPriority(p)}
                      >
                        <Text style={styles.chipText}>{statusLabel(p, t)}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <DateTimeField label={t('Hạn chót', 'Due date')} value={taskDueDate} onChange={setTaskDueDate} />
                  <Button title={t('Thêm nhiệm vụ', 'Add task')} variant="secondary" onPress={createTask} loading={creatingTask} />

                  <View style={{ marginTop: 14 }}>
                    {loadingTasks ? (
                      <ActivityIndicator color={colors.primary} />
                    ) : tasks.length ? (
                      tasks.map((task) => (
                        <View key={task.id} style={styles.itemRow}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.itemTitle}>{task.title}</Text>
                            <Text style={styles.itemMeta}>
                              {statusLabel(task.priority, t)}{task.due_date ? ` · ${task.due_date}` : ''}
                            </Text>
                          </View>
                          <TouchableOpacity
                            style={[styles.badge, { backgroundColor: `${badgeColor(task.status, colors)}24` }]}
                            onPress={() => cycleTaskStatus(task)}
                          >
                            <Text style={[styles.badgeText, { color: badgeColor(task.status, colors) }]}>{statusLabel(task.status, t)}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={() => deleteTask(task.id)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} style={{ marginLeft: 10 }}>
                            <Ionicons name="trash-outline" size={18} color={colors.danger} />
                          </TouchableOpacity>
                        </View>
                      ))
                    ) : (
                      <Text style={styles.emptyText}>{t('Chưa có nhiệm vụ nào.', 'No tasks yet.')}</Text>
                    )}
                  </View>
                </View>
              ) : null}
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    header: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 16, paddingVertical: 12 },
    headerTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 17 },
    body: { paddingHorizontal: 16, paddingBottom: 32, gap: 14 },

    section: {
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: radius.card,
      padding: 16,
      ...colors.shadow,
    },
    sectionLabel: {
      color: colors.primary,
      fontSize: 10,
      fontFamily: 'Poppins_700Bold',
      letterSpacing: 1.2,
      textTransform: 'uppercase',
      marginBottom: 10,
    },
    fieldLabel: { color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 12, marginBottom: 6 },
    input: {
      minHeight: 46,
      borderColor: colors.border,
      borderWidth: 1.5,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      color: colors.text,
      fontFamily: 'Poppins_400Regular',
      fontSize: 14,
      paddingHorizontal: 14,
      marginBottom: 12,
    },
    multiline: { minHeight: 70, paddingTop: 12, textAlignVertical: 'top' },

    chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
    chip: {
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: radius.pill,
      backgroundColor: colors.panelSoft,
      borderWidth: 1,
      borderColor: colors.border,
    },
    chipActive: { backgroundColor: colors.secondaryBg, borderColor: colors.primary },
    chipText: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 12.5 },

    itemRow: {
      flexDirection: 'row',
      alignItems: 'center',
      padding: 10,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      borderWidth: 1,
      borderColor: colors.border,
      marginBottom: 8,
    },
    itemRowActive: { borderColor: colors.primary, backgroundColor: colors.secondaryBg },
    itemTitle: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    itemMeta: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11, marginTop: 2 },
    badge: { borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 4 },
    badgeText: { fontFamily: 'Poppins_700Bold', fontSize: 10 },
    emptyText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13 },
  });
}
