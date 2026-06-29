import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import { apiGet, apiPost, apiPut } from '../api/client';
import { useTheme } from '../theme/ThemeContext';

export default function OverviewScreen({ onAgentSync, syncEvent }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [date, setDate] = useState(() => formatDateForApi(new Date()));
  const [emails, setEmails] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [emailError, setEmailError] = useState('');
  const [refreshNote, setRefreshNote] = useState('');
  const [checklistState, setChecklistState] = useState({ completed: {}, custom_items: [] });
  const [quickInput, setQuickInput] = useState('');
  const [quickLoading, setQuickLoading] = useState(false);
  const [quickMessage, setQuickMessage] = useState('');
  const [planSuggestion, setPlanSuggestion] = useState(null);

  const loadOverview = useCallback(async (options = {}) => {
    const force = options?.force === true;
    setLoading(true);
    setEmailError('');
    setRefreshNote('');
    try {
      const [overviewResult, checklistResult] = await Promise.allSettled([
        apiGet(`/overview/daily?date=${encodeURIComponent(date)}&max_results=50${force ? '&force=1' : ''}`),
        apiGet(`/schedule/checklist?date=${encodeURIComponent(date)}`),
      ]);

      if (overviewResult.status === 'fulfilled') {
        setSchedules(dedupeSchedules(overviewResult.value.schedules || [])
          .filter((item) => isSameDay(item.start_time, date))
          .sort((a, b) => new Date(a.start_time) - new Date(b.start_time)));
        setEmails(overviewResult.value.email_rows || overviewResult.value.emails || []);
        setRefreshNote(overviewResult.value.refreshing
          ? 'AI đang cập nhật email trong nền. Lịch/task đã sẵn sàng để xem ngay.'
          : '');
      } else {
        setSchedules([]);
        setEmails([]);
        setEmailError(overviewResult.reason?.message || 'Không tải được tổng hợp trong ngày.');
      }

      if (checklistResult.status === 'fulfilled') {
        setChecklistState(normalizeChecklistState(checklistResult.value));
      } else {
        setChecklistState({ completed: {}, custom_items: [] });
      }
    } catch (error) {
      Alert.alert('Không tổng hợp được dữ liệu', error.message);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { loadOverview(); }, [loadOverview]);
  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['overview', 'email', 'schedule', 'calendar', 'history'])) {
      loadOverview({ force: hasSyncTarget(syncEvent, ['email']) });
    }
  }, [loadOverview, syncEvent]);

  const deadlines = schedules.filter((item) => priorityLabel(item) === 'Deadline');
  const openTasks = schedules.filter((item) => item.status !== 'completed');
  const meetingEmails = emails.filter((item) => item.is_meeting);
  const insight = buildInsight({ emails, schedules, date });
  const sourceText = buildSourceText({ emails, schedules });
  const checklistItems = useMemo(
    () => buildChecklistItems({ schedules, checklistState }),
    [schedules, checklistState]
  );
  const completedCount = checklistItems.filter((item) => item.completed).length;
  const planItems = planSuggestion?.items || [];
  const selectedPlanCount = planItems.filter((item) => item.selected !== false).length;

  const saveChecklist = useCallback(async (nextState) => {
    try {
      const saved = await apiPut('/schedule/checklist', { date, ...nextState });
      setChecklistState(normalizeChecklistState(saved));
    } catch (error) {
      Alert.alert('Không lưu được checklist', error.message);
    }
  }, [date]);

  const toggleChecklistItem = useCallback((item) => {
    const nextCompletedValue = !item.completed;
    const nextCompleted = {
      ...checklistState.completed,
      [item.id]: nextCompletedValue,
    };
    const customItems = item.kind === 'custom'
      ? (checklistState.custom_items || []).map((entry) => (
        entry.id === item.id ? { ...entry, completed: nextCompletedValue } : entry
      ))
      : (checklistState.custom_items || []);
    const nextState = { completed: nextCompleted, custom_items: customItems };
    setChecklistState(nextState);
    saveChecklist(nextState);
  }, [checklistState, saveChecklist]);

  const refreshAfterQuickChange = useCallback(async (targetDate) => {
    const nextDate = normalizeApiDate(targetDate);
    if (nextDate && nextDate !== date) {
      setDate(nextDate);
      return;
    }
    await loadOverview();
  }, [date, loadOverview]);

  const handleQuickAdd = useCallback(async () => {
    const text = quickInput.trim();
    if (!text) {
      Alert.alert('Thiếu nội dung', 'Nhập một task hoặc danh sách hoạt động.');
      return;
    }

    setQuickLoading(true);
    setQuickMessage('');
    try {
      const data = await apiPost('/schedule/quick-add', { text, date });
      if (data.kind === 'suggested_plan') {
        setPlanSuggestion(normalizePlanSuggestion(data));
        if (data.date && data.date !== date) setDate(data.date);
        setQuickMessage(data.message || 'FlowMate đã xếp khung giờ đề xuất.');
        return;
      }

      setPlanSuggestion(null);
      setQuickInput('');
      setQuickMessage(data.message || (data.kind === 'activity' ? 'Đã thêm vào lịch.' : 'Đã thêm vào checklist.'));

      if (data.kind === 'task') {
        setChecklistState(normalizeChecklistState(data));
        onAgentSync?.(['overview']);
      } else {
        await refreshAfterQuickChange(data.classification?.target_date || data.schedule?.start_time);
        onAgentSync?.(['schedule', 'calendar', 'overview', 'history'], data);
      }
    } catch (error) {
      Alert.alert('Không thêm nhanh được', error.message);
    } finally {
      setQuickLoading(false);
    }
  }, [date, onAgentSync, quickInput, refreshAfterQuickChange]);

  const updatePlanDraftItem = useCallback((index, key, value) => {
    setPlanSuggestion((current) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item, itemIndex) => (
          itemIndex === index ? { ...item, [key]: value } : item
        )),
      };
    });
  }, []);

  const togglePlanDraftItem = useCallback((index) => {
    setPlanSuggestion((current) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item, itemIndex) => (
          itemIndex === index ? { ...item, selected: item.selected === false } : item
        )),
      };
    });
  }, []);

  const applyPlanSuggestion = useCallback(async () => {
    const selectedItems = (planSuggestion?.items || []).filter((item) => item.selected !== false);
    if (!selectedItems.length) {
      Alert.alert('Chưa chọn hoạt động', 'Chọn ít nhất một hoạt động để tạo lịch.');
      return;
    }

    setQuickLoading(true);
    setQuickMessage('');
    try {
      const data = await apiPost('/schedule/plan-day/apply', {
        items: selectedItems.map(toPlanPayload),
      });
      const targetDate = planSuggestion?.date;
      setPlanSuggestion(null);
      setQuickInput('');
      setQuickMessage(data.message || `Đã tạo ${selectedItems.length} lịch.`);
      await refreshAfterQuickChange(targetDate);
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history'], data);
      Alert.alert('Đã tạo lịch', `FlowMate đã tạo ${data.created_count || selectedItems.length} hoạt động.`);
    } catch (error) {
      Alert.alert('Không áp dụng được lịch', error.message);
    } finally {
      setQuickLoading(false);
    }
  }, [onAgentSync, planSuggestion, refreshAfterQuickChange]);

  const renderPlanSuggestion = () => {
    if (!planSuggestion) return null;
    return (
      <View style={styles.planBox}>
        <View style={styles.planHeader}>
          <View style={styles.planHeaderText}>
            <Text style={styles.planTitle}>Gợi ý {formatReportDate(planSuggestion.date || date)}</Text>
            <Text style={styles.planMeta}>{selectedPlanCount}/{planItems.length} hoạt động được chọn</Text>
          </View>
          <Text style={styles.planBadge}>AI</Text>
        </View>
        {planItems.map((item, index) => (
          <View
            key={`${item.title || 'item'}-${item.start_time || index}-${index}`}
            style={[styles.planItem, item.selected === false && styles.planItemMuted]}
          >
            <TouchableOpacity
              style={[styles.checkbox, item.selected !== false && styles.checkboxChecked]}
              onPress={() => togglePlanDraftItem(index)}
              activeOpacity={0.78}
            >
              <Text style={[styles.checkboxText, item.selected !== false && styles.checkboxTextChecked]}>
                {item.selected !== false ? '✓' : ''}
              </Text>
            </TouchableOpacity>
            <View style={styles.planItemBody}>
              <Field
                label="Hoạt động"
                value={item.title || ''}
                onChangeText={(value) => updatePlanDraftItem(index, 'title', value)}
                placeholder="Tên hoạt động"
              />
              <View style={styles.planTimeGrid}>
                <View style={styles.planTimeField}>
                  <Field
                    label="Bắt đầu"
                    value={toEditableDateTime(item.start_time)}
                    onChangeText={(value) => updatePlanDraftItem(index, 'start_time', value)}
                    placeholder="2026-06-30T07:00"
                  />
                </View>
                <View style={styles.planTimeField}>
                  <Field
                    label="Kết thúc"
                    value={toEditableDateTime(item.end_time)}
                    onChangeText={(value) => updatePlanDraftItem(index, 'end_time', value)}
                    placeholder="2026-06-30T08:00"
                  />
                </View>
              </View>
              {item.reason ? <Text style={styles.planReason}>{item.reason}</Text> : null}
            </View>
          </View>
        ))}
        <Button
          title="Áp dụng lịch đã chọn"
          onPress={applyPlanSuggestion}
          loading={quickLoading}
          disabled={selectedPlanCount === 0}
        />
      </View>
    );
  };

  return (
    <Screen
      title="Tổng hợp"
      refreshing={loading}
      onRefresh={() => loadOverview()}
      actions={<Button title="Tổng hợp lại" variant="secondary" onPress={() => loadOverview({ force: true })} loading={loading} />}
    >
      <Card style={styles.heroCard}>
        <Text style={styles.kicker}>FLOWMATE AI</Text>
        <Text style={styles.heroTitle}>{formatReportDate(date)}</Text>
        <Text style={styles.heroText}>{insight}</Text>
        {refreshNote ? <Text style={styles.refreshNote}>{refreshNote}</Text> : null}
        <Text style={styles.sourceText}>{sourceText}</Text>
      </Card>

      <Card style={styles.dateCard}>
        <Field
          label="Ngày cần tổng hợp"
          value={date}
          onChangeText={setDate}
          placeholder="2026-06-26"
        />
        <Button title="Xem ngày này" onPress={() => loadOverview()} loading={loading} />
      </Card>

      <Card style={styles.quickCard}>
        <View style={styles.sectionHeader}>
          <Text style={styles.kicker}>THÊM NHANH</Text>
          <Text style={styles.sectionTitle}>Task và hoạt động trong ngày</Text>
        </View>
        <Field
          label="Nhập task hoặc hoạt động"
          value={quickInput}
          onChangeText={setQuickInput}
          placeholder="Yoga 30 phút, chăm mèo cưng, dọn nhà"
          multiline
        />
        <View style={styles.quickActions}>
          <Button
            title="Thêm nhanh"
            onPress={handleQuickAdd}
            loading={quickLoading}
            disabled={!quickInput.trim()}
            style={styles.quickButton}
          />
          {planSuggestion ? (
            <Button
              title="Đóng gợi ý"
              variant="secondary"
              onPress={() => setPlanSuggestion(null)}
              disabled={quickLoading}
              style={styles.quickButton}
            />
          ) : null}
        </View>
        {quickMessage ? <Text style={styles.quickMessage}>{quickMessage}</Text> : null}
        {renderPlanSuggestion()}
      </Card>

      <View style={styles.statsGrid}>
        <StatCard label="Deadline" value={deadlines.length} styles={styles} />
        <StatCard label="Email" value={emails.length} styles={styles} />
        <StatCard label="Task mở" value={openTasks.length} styles={styles} />
        <StatCard label="Mail họp" value={meetingEmails.length} styles={styles} />
      </View>

      <Card>
        <View style={styles.sectionHeader}>
          <Text style={styles.kicker}>CHECKLIST</Text>
          <Text style={styles.sectionTitle}>Việc người dùng cần hoàn tất</Text>
          <Text style={styles.checklistMeta}>{completedCount}/{checklistItems.length} đã xong</Text>
        </View>
        {checklistItems.length === 0 ? (
          <EmptyState title="Checklist đang trống" detail="Tạo lịch/task ở tab Lịch để FlowMate đưa vào checklist." />
        ) : checklistItems.map((item) => (
          <View key={item.id} style={styles.checklistItem}>
            <TouchableOpacity
              style={[styles.checkbox, item.completed && styles.checkboxChecked]}
              onPress={() => toggleChecklistItem(item)}
              activeOpacity={0.78}
            >
              <Text style={[styles.checkboxText, item.completed && styles.checkboxTextChecked]}>
                {item.completed ? '✓' : ''}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.checklistBody}
              onPress={() => toggleChecklistItem(item)}
              activeOpacity={0.78}
            >
              <Text style={[styles.checklistTitle, item.completed && styles.checklistTitleDone]}>
                {item.title}
              </Text>
              {item.meta ? <Text style={styles.itemMeta} numberOfLines={2}>{item.meta}</Text> : null}
            </TouchableOpacity>
            <Text style={styles.checklistSource}>{item.sourceLabel || 'Lịch'}</Text>
          </View>
        ))}
      </Card>

      <Card>
        <View style={styles.sectionHeader}>
          <Text style={styles.kicker}>DEADLINE & TASK</Text>
          <Text style={styles.sectionTitle}>Việc cần xử lý hôm nay</Text>
        </View>
        {schedules.length === 0 ? (
          <EmptyState title="Chưa có task trong ngày" detail="FlowMate chưa tìm thấy deadline hoặc lịch hẹn cho ngày này." />
        ) : schedules.slice(0, 6).map((item, index) => (
          <View key={`${item.id}-${item.start_time}-${index}`} style={styles.item}>
            <View style={styles.itemIndex}><Text style={styles.itemIndexText}>{index + 1}</Text></View>
            <View style={styles.itemBody}>
              <Text style={styles.itemTitle}>{item.title || 'Task không tiêu đề'}</Text>
              <Text style={styles.itemMeta}>{formatScheduleTime(item.start_time, item.end_time)}</Text>
              {item.description ? <Text style={styles.itemPreview} numberOfLines={3}>{stripHtml(item.description)}</Text> : null}
            </View>
            <View style={styles.chipStack}>
              <Text style={styles.chip}>{priorityLabel(item)}</Text>
              <Text style={[styles.chip, providerStyle(item.provider || item.source, styles)]}>{providerLabel(item.provider || item.source)}</Text>
            </View>
          </View>
        ))}
      </Card>

      <Card>
        <View style={styles.sectionHeader}>
          <Text style={styles.kicker}>EMAIL</Text>
          <Text style={styles.sectionTitle}>Mail quan trọng trong ngày</Text>
        </View>
        {emailError ? <Text style={styles.errorText}>{emailError}</Text> : null}
        {emails.length === 0 && !emailError ? (
          <EmptyState title="Chưa có email nổi bật" detail="Không tìm thấy email cần tóm tắt trong ngày này." />
        ) : emails.slice(0, 6).map((item, index) => (
          <View key={`${item.subject}-${index}`} style={styles.item}>
            <View style={styles.itemIndex}><Text style={styles.itemIndexText}>{index + 1}</Text></View>
            <View style={styles.itemBody}>
              <Text style={styles.itemTitle}>{item.subject || 'Email không tiêu đề'}</Text>
              <Text style={styles.itemMeta} numberOfLines={1}>{item.sender || 'Người gửi'}</Text>
              <Text style={styles.itemPreview} numberOfLines={4}>{item.summary || 'Chưa có tóm tắt.'}</Text>
            </View>
            <View style={styles.chipStack}>
              <Text style={[styles.chip, providerStyle(item.provider, styles)]}>{providerLabel(item.provider)}</Text>
              {item.is_meeting ? <Text style={[styles.chip, styles.meetingChip]}>Họp</Text> : null}
            </View>
          </View>
        ))}
      </Card>
    </Screen>
  );
}

function StatCard({ label, value, styles }) {
  return (
    <Card style={styles.statCard}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </Card>
  );
}

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
}

function normalizeChecklistState(value) {
  return {
    completed: value?.completed && typeof value.completed === 'object' ? value.completed : {},
    custom_items: Array.isArray(value?.custom_items) ? value.custom_items : [],
  };
}

function normalizePlanSuggestion(value) {
  return {
    ...value,
    items: Array.isArray(value?.items)
      ? value.items.map((item) => ({ ...item, selected: true }))
      : [],
  };
}

function toPlanPayload(item) {
  return {
    title: item.title || '',
    description: item.description || '',
    start_time: item.start_time || '',
    end_time: item.end_time || '',
    duration_minutes: item.duration_minutes ? Number(item.duration_minutes) : undefined,
    reason: item.reason || '',
  };
}

function buildChecklistItems({ schedules, checklistState }) {
  const completed = checklistState.completed || {};
  const customItems = (checklistState.custom_items || [])
    .filter((item) => item && item.title)
    .map((item) => {
      const id = String(item.id || '');
      return {
        id,
        kind: 'custom',
        title: item.title || 'Task không tiêu đề',
        meta: customChecklistMeta(item),
        completed: Boolean(item.completed || completed[id]),
        sourceLabel: item.source === 'manual' ? 'Task' : providerLabel(item.source),
      };
    });
  const scheduleItems = schedules
    .filter((item) => item.status !== 'cancelled' && item.status !== 'dismissed')
    .map((item) => {
      const id = `schedule:${scheduleFingerprint(item)}`;
      return {
        id,
        kind: 'schedule',
        title: item.title || 'Task không tiêu đề',
        meta: formatScheduleTime(item.start_time, item.end_time),
        completed: Boolean(completed[id] || item.status === 'completed'),
        sourceLabel: 'Lịch',
      };
    });
  return [...customItems, ...scheduleItems];
}

function customChecklistMeta(item) {
  if (item.due_at) return `Hạn ${formatScheduleTime(item.due_at)}`;
  if (item.due_date) return `Hạn ${formatReportDate(item.due_date)}`;
  if (item.ai_reason) return item.ai_reason;
  return 'Thêm nhanh';
}

function buildInsight({ emails, schedules, date }) {
  const deadlines = schedules.filter((item) => priorityLabel(item) === 'Deadline');
  if (!emails.length && !schedules.length) {
    return `Ngày ${formatReportDate(date)} chưa có email, deadline hoặc task nổi bật.`;
  }
  const firstSchedule = schedules[0];
  const firstEmail = emails[0];
  const parts = [
    `Ngày này có ${emails.length} email được tổng hợp, ${schedules.length} mục lịch/task và ${deadlines.length} deadline cần chú ý.`,
  ];
  if (firstSchedule) parts.push(`Ưu tiên đầu tiên: ${firstSchedule.title || 'Sự kiện'} lúc ${formatScheduleTime(firstSchedule.start_time, firstSchedule.end_time)}.`);
  if (firstEmail) parts.push(`Email nên xem trước: ${firstEmail.subject || 'Không tiêu đề'}.`);
  return parts.join(' ');
}

function providerLabel(provider) {
  if (provider === 'outlook' || provider === 'microsoft') return 'Outlook';
  if (provider === 'google') return 'Google';
  return 'Gmail';
}

function providerStyle(provider, styles) {
  return provider === 'outlook' || provider === 'microsoft'
    ? styles.outlookChip
    : styles.gmailChip;
}

function buildSourceText({ emails, schedules }) {
  const providers = new Set();
  emails.forEach((item) => providers.add(providerLabel(item.provider || 'gmail')));
  schedules.forEach((item) => providers.add(providerLabel(item.provider || item.source || 'google')));
  if (!providers.size) providers.add('Gmail');
  return `Nguồn: ${Array.from(providers).join(', ')}`;
}

function formatDateForApi(value) {
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function formatReportDate(value) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return `${String(date.getDate()).padStart(2, '0')}/${String(date.getMonth() + 1).padStart(2, '0')}/${date.getFullYear()}`;
}

function normalizeApiDate(value) {
  if (!value) return '';
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? '' : formatDateForApi(date);
}

function toEditableDateTime(value) {
  if (!value) return '';
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(text)) return text.slice(0, 16);
  return text;
}

function isSameDay(value, selectedDate) {
  if (!value || !selectedDate) return false;
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) && formatDateForApi(date) === selectedDate;
}

function priorityLabel(item) {
  const text = `${item?.title || ''} ${item?.description || ''}`.toLowerCase();
  if (/(deadline|hạn|nộp|due|submit|bàn giao)/i.test(text)) return 'Deadline';
  if (item?.status === 'completed') return 'Đã xong';
  return 'Task';
}

function formatScheduleTime(startValue, endValue) {
  const start = new Date(startValue);
  if (Number.isNaN(start.getTime())) return 'Chưa rõ thời gian';
  const startText = start.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  if (!endValue) return startText;
  const end = new Date(endValue);
  if (Number.isNaN(end.getTime())) return startText;
  return `${startText} - ${end.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`;
}

function stripHtml(value) {
  return String(value || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function scheduleFingerprint(schedule) {
  const title = String(schedule?.title || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const start = new Date(schedule?.start_time || '');
  const startKey = Number.isNaN(start.getTime()) ? String(schedule?.start_time || '') : start.toISOString().slice(0, 16);
  return `${title}|${startKey}`;
}

function dedupeSchedules(items = []) {
  const byGoogleId = new Map();
  const byFingerprint = new Map();
  const result = [];
  items.forEach((schedule) => {
    if (!schedule) return;
    const googleId = schedule.calendar_event_id || schedule.google_event_id || '';
    const fingerprint = scheduleFingerprint(schedule);
    const existing = (googleId && byGoogleId.get(googleId)) || byFingerprint.get(fingerprint);
    if (existing) return;
    result.push(schedule);
    if (googleId) byGoogleId.set(googleId, schedule);
    byFingerprint.set(fingerprint, schedule);
  });
  return result;
}

function makeStyles(colors) {
  const officeFont = 'Times New Roman';
  return StyleSheet.create({
    heroCard: {
      gap: 6,
      backgroundColor: colors.primarySoft,
      borderColor: `${colors.primary}33`,
    },
    kicker: {
      color: colors.primary,
      fontFamily: officeFont,
      fontSize: 10,
      fontWeight: '600',
      letterSpacing: 0,
      textTransform: 'uppercase',
    },
    heroTitle: { color: colors.text, fontFamily: officeFont, fontSize: 18, fontWeight: '600' },
    heroText: { color: colors.textMuted, fontFamily: officeFont, fontSize: 13, lineHeight: 19 },
    refreshNote: { marginTop: 4, color: colors.primary, fontFamily: officeFont, fontSize: 12, fontWeight: '500', lineHeight: 18 },
    sourceText: { marginTop: 4, color: colors.textMuted, fontFamily: officeFont, fontSize: 11, fontWeight: '500' },
    dateCard: { gap: 8 },
    quickCard: { gap: 8 },
    quickActions: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    quickButton: {
      flexGrow: 1,
      flexBasis: '45%',
    },
    quickMessage: {
      color: colors.success,
      fontFamily: officeFont,
      fontSize: 12,
      fontWeight: '600',
      lineHeight: 18,
    },
    planBox: {
      marginTop: 6,
      paddingTop: 12,
      borderTopColor: colors.border,
      borderTopWidth: 1,
      gap: 10,
    },
    planHeader: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 8,
    },
    planHeaderText: { flex: 1, minWidth: 0 },
    planTitle: { color: colors.text, fontFamily: officeFont, fontSize: 14, fontWeight: '700' },
    planMeta: { marginTop: 3, color: colors.textMuted, fontFamily: officeFont, fontSize: 11, fontWeight: '500' },
    planBadge: {
      overflow: 'hidden',
      borderRadius: 999,
      paddingHorizontal: 8,
      paddingVertical: 4,
      backgroundColor: `${colors.primary}18`,
      color: colors.primary,
      fontFamily: officeFont,
      fontSize: 10,
      fontWeight: '700',
    },
    planItem: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 8,
      paddingTop: 10,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    planItemMuted: { opacity: 0.52 },
    planItemBody: { flex: 1, minWidth: 0 },
    planTimeGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    planTimeField: {
      flexGrow: 1,
      flexBasis: '46%',
      minWidth: 128,
    },
    planReason: {
      marginTop: -2,
      marginBottom: 8,
      color: colors.textMuted,
      fontFamily: officeFont,
      fontSize: 11,
      fontWeight: '500',
      lineHeight: 16,
    },
    statsGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    statCard: {
      flexGrow: 1,
      flexBasis: '46%',
      minHeight: 68,
      justifyContent: 'center',
    },
    statValue: { color: colors.text, fontFamily: officeFont, fontSize: 20, fontWeight: '600' },
    statLabel: { marginTop: 3, color: colors.textMuted, fontFamily: officeFont, fontSize: 12, fontWeight: '500' },
    sectionHeader: { marginBottom: 4 },
    sectionTitle: { marginTop: 2, color: colors.text, fontFamily: officeFont, fontSize: 14, fontWeight: '600' },
    checklistMeta: { marginTop: 4, color: colors.textMuted, fontFamily: officeFont, fontSize: 11, fontWeight: '500' },
    checklistItem: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingVertical: 10,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    checkbox: {
      width: 24,
      height: 24,
      borderRadius: 8,
      borderWidth: 2,
      borderColor: colors.border,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.panel,
    },
    checkboxChecked: {
      borderColor: colors.primary,
      backgroundColor: colors.primary,
    },
    checkboxText: {
      color: colors.panel,
      fontFamily: officeFont,
      fontWeight: '600',
      lineHeight: 16,
    },
    checkboxTextChecked: { color: '#ffffff' },
    checklistBody: { flex: 1, minWidth: 0 },
    checklistTitle: { color: colors.text, fontFamily: officeFont, fontSize: 13, fontWeight: '600', lineHeight: 18 },
    checklistTitleDone: {
      color: colors.textMuted,
      textDecorationLine: 'line-through',
    },
    checklistSource: {
      color: colors.textMuted,
      fontFamily: officeFont,
      fontSize: 10,
      fontWeight: '500',
      textTransform: 'uppercase',
    },
    item: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 8,
      paddingVertical: 10,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    itemIndex: {
      width: 24,
      height: 24,
      overflow: 'hidden',
      borderRadius: 8,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: `${colors.primary}18`,
    },
    itemIndexText: { color: colors.primary, fontFamily: officeFont, fontSize: 11, fontWeight: '600' },
    itemBody: { flex: 1, minWidth: 0 },
    itemTitle: { color: colors.text, fontFamily: officeFont, fontSize: 13, fontWeight: '600', lineHeight: 18 },
    itemMeta: { marginTop: 3, color: colors.textMuted, fontFamily: officeFont, fontSize: 11, fontWeight: '500' },
    itemPreview: { marginTop: 6, color: colors.textMuted, fontFamily: officeFont, fontSize: 12, lineHeight: 18 },
    chip: {
      overflow: 'hidden',
      borderRadius: 999,
      paddingHorizontal: 8,
      paddingVertical: 4,
      backgroundColor: 'rgba(13,148,136,0.13)',
      color: '#0f766e',
      fontFamily: officeFont,
      fontSize: 10,
      fontWeight: '600',
    },
    chipStack: { alignItems: 'flex-end', gap: 5 },
    gmailChip: {
      color: colors.primary,
      backgroundColor: `${colors.primary}18`,
    },
    outlookChip: {
      color: '#0369a1',
      backgroundColor: 'rgba(14,165,233,0.16)',
    },
    meetingChip: {
      backgroundColor: 'rgba(245,158,11,0.16)',
      color: '#b45309',
    },
    errorText: {
      marginTop: 10,
      color: colors.danger,
      fontFamily: officeFont,
      fontSize: 12,
      fontWeight: '600',
    },
  });
}
