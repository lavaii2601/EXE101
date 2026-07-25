import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Modal, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import { apiGet, apiPost, apiPut } from '../api/client';
import { useTheme } from '../theme/ThemeContext';

export default function OverviewScreen({ onAgentSync, syncEvent, onNavigate, userMode, subscription }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const isStudent = userMode === 'student';
  const isPremium = !!(subscription?.is_premium || subscription?.tier === 'premium');

  const [date, setDate] = useState(() => formatDateForApi(new Date()));
  const [emails, setEmails] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [emailError, setEmailError] = useState('');
  const [refreshNote, setRefreshNote] = useState('');
  const [checklistState, setChecklistState] = useState({ revision: 0, completed: {}, custom_items: [] });
  const [quickInput, setQuickInput] = useState('');
  const [quickLoading, setQuickLoading] = useState(false);
  const [quickMessage, setQuickMessage] = useState('');
  const [planSuggestion, setPlanSuggestion] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [selectedEmail, setSelectedEmail] = useState(null);

  // Student-mode-only widgets (deadline countdown, checklist subject tag,
  // study-material summarizer, GPA calculator) -- see entitlements.py's
  // STUDENT_*_LIMITS on the backend for what free vs premium unlocks.
  const [upcomingDeadlines, setUpcomingDeadlines] = useState(null);
  const [subjectEditItem, setSubjectEditItem] = useState(null);
  const [subjectEditValue, setSubjectEditValue] = useState('');
  const [groupedVisible, setGroupedVisible] = useState(false);
  const [groupedSubjects, setGroupedSubjects] = useState([]);
  const [summarizerVisible, setSummarizerVisible] = useState(false);
  const [summaryTitle, setSummaryTitle] = useState('');
  const [summaryContent, setSummaryContent] = useState('');
  const [summaryResult, setSummaryResult] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [gpaVisible, setGpaVisible] = useState(false);
  const [gpaRows, setGpaRows] = useState([{ name: '', credits: '', grade: '' }, { name: '', credits: '', grade: '' }, { name: '', credits: '', grade: '' }]);
  const [gpaResult, setGpaResult] = useState(null);
  const [gpaCalculated, setGpaCalculated] = useState(false);
  const [gpaLoading, setGpaLoading] = useState(false);

  const loadOverview = useCallback(async (options = {}) => {
    const force = options?.force === true;
    setLoading(true);
    setEmailError('');
    setRefreshNote('');
    try {
      const [overviewResult, checklistResult, analyticsResult] = await Promise.allSettled([
        apiGet(`/overview/daily?date=${encodeURIComponent(date)}&max_results=50${force ? '&force=1' : ''}`),
        apiGet(`/schedule/checklist?date=${encodeURIComponent(date)}`),
        apiGet(`/overview/analytics?days=7&end_date=${encodeURIComponent(date)}`),
      ]);

      if (overviewResult.status === 'fulfilled') {
        setSchedules(dedupeSchedules(overviewResult.value.schedules || [])
          .filter((item) => isSameDay(item.start_time, date))
          .sort((a, b) => new Date(a.start_time) - new Date(b.start_time)));
        setEmails(overviewResult.value.email_rows || overviewResult.value.emails || []);
        setRefreshNote(overviewResult.value.refreshing
          ? 'AI đang cập nhật email trong nền. Lịch/task đã sẵn sàng để xem ngay.'
          : '');
        // Only present for Student mode (routes/overview.py::_attach_student_deadlines).
        setUpcomingDeadlines(Array.isArray(overviewResult.value.upcoming_deadlines)
          ? overviewResult.value.upcoming_deadlines
          : null);
      } else {
        setSchedules([]);
        setEmails([]);
        setEmailError(overviewResult.reason?.message || 'Không tải được tổng hợp trong ngày.');
      }

      if (checklistResult.status === 'fulfilled') {
        setChecklistState(normalizeChecklistState(checklistResult.value));
      } else {
        setChecklistState({ revision: 0, completed: {}, custom_items: [] });
      }

      if (analyticsResult.status === 'fulfilled') {
        setAnalytics(analyticsResult.value);
      } else if (analyticsResult.reason?.status === 403 && analyticsResult.reason?.data?.error === 'premium_required') {
        // apiGet() throws on non-2xx responses (unlike the web client, which
        // resolves regardless of status), so the free-tier 403 from
        // routes/overview.py::weekly_analytics lands here, not in the
        // 'fulfilled' branch above.
        setAnalytics({ error: 'premium_required' });
      } else {
        setAnalytics(null);
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
      const saved = await apiPut('/schedule/checklist', {
        date,
        ...nextState,
        revision: Number(nextState?.revision ?? checklistState.revision ?? 0),
      });
      setChecklistState(normalizeChecklistState(saved));
    } catch (error) {
      if (error.status === 409) {
        setChecklistState(normalizeChecklistState(error.data));
        Alert.alert(
          'Checklist vừa thay đổi',
          'Web hoặc một thiết bị khác đã lưu trước. Đã tải lại bản mới nhất để tránh ghi đè.',
        );
        return;
      }
      Alert.alert('Không lưu được checklist', error.message);
    }
  }, [checklistState.revision, date]);

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
    const nextState = { revision: checklistState.revision, completed: nextCompleted, custom_items: customItems };
    setChecklistState(nextState);
    saveChecklist(nextState);
  }, [checklistState, saveChecklist]);

  const removeChecklistItem = useCallback((item) => {
    if (item.kind !== 'custom') return;
    const customItems = (checklistState.custom_items || []).filter((entry) => entry.id !== item.id);
    const nextState = {
      revision: checklistState.revision,
      completed: checklistState.completed || {},
      custom_items: customItems,
    };
    setChecklistState(nextState);
    saveChecklist(nextState);
  }, [checklistState, saveChecklist]);

  const sortChecklist = useCallback(() => {
    const sortedCustomItems = sortChecklistEntries(checklistState.custom_items || []);
    const nextState = {
      revision: checklistState.revision,
      completed: checklistState.completed || {},
      custom_items: sortedCustomItems,
    };
    setChecklistState(nextState);
    saveChecklist(nextState);
    setQuickMessage('Đã sắp xếp checklist theo ưu tiên.');
  }, [checklistState, saveChecklist]);

  // ---- Student-mode-only handlers ----

  const openSubjectEditor = useCallback((item) => {
    setSubjectEditItem(item);
    setSubjectEditValue(item.subject || '');
  }, []);

  const saveSubjectEdit = useCallback(() => {
    if (!subjectEditItem) return;
    const customItems = (checklistState.custom_items || []).map((entry) => (
      entry.id === subjectEditItem.id ? { ...entry, subject: subjectEditValue.trim().slice(0, 60) } : entry
    ));
    const nextState = { revision: checklistState.revision, completed: checklistState.completed || {}, custom_items: customItems };
    setChecklistState(nextState);
    saveChecklist(nextState);
    setSubjectEditItem(null);
  }, [checklistState, saveChecklist, subjectEditItem, subjectEditValue]);

  const openGroupedBySubject = useCallback(async () => {
    if (!isPremium) {
      Alert.alert(
        'Tính năng Premium',
        'Xem checklist theo môn học là tính năng Premium.',
        [
          { text: 'Để sau', style: 'cancel' },
          { text: 'Nâng cấp', onPress: () => onNavigate?.('settings') },
        ],
      );
      return;
    }
    try {
      const data = await apiGet(`/schedule/checklist?date=${encodeURIComponent(date)}&group_by=subject`);
      setGroupedSubjects(Array.isArray(data.grouped_by_subject) ? data.grouped_by_subject : []);
      setGroupedVisible(true);
    } catch (error) {
      Alert.alert('Không tải được', error.message);
    }
  }, [date, isPremium, onNavigate]);

  const submitStudySummary = useCallback(async () => {
    const content = summaryContent.trim();
    if (!content) {
      Alert.alert('Thiếu nội dung', 'Hãy dán nội dung cần tóm tắt.');
      return;
    }
    setSummaryLoading(true);
    try {
      const data = await apiPost('/chat/summarize-study', { title: summaryTitle.trim(), content });
      setSummaryResult(data.summary || '');
    } catch (error) {
      if (error.status === 403 && error.data?.error === 'ai_limit_reached') {
        Alert.alert('Hết lượt miễn phí', `Bạn đã dùng hết ${error.data.limit} lượt tóm tắt miễn phí hôm nay.`);
      } else {
        Alert.alert('Không thể tóm tắt', error.message);
      }
    } finally {
      setSummaryLoading(false);
    }
  }, [summaryContent, summaryTitle]);

  const updateGpaRow = useCallback((index, field, value) => {
    setGpaRows((rows) => rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }, []);

  const addGpaRow = useCallback(() => {
    setGpaRows((rows) => [...rows, { name: '', credits: '', grade: '' }]);
  }, []);

  const removeGpaRow = useCallback((index) => {
    setGpaRows((rows) => rows.filter((_, i) => i !== index));
  }, []);

  const calculateGpa = useCallback(async () => {
    const courses = gpaRows
      .map((row) => ({ name: row.name.trim(), credits: row.credits, grade: row.grade }))
      .filter((row) => row.name && row.credits !== '' && row.grade !== '');
    if (!courses.length) {
      Alert.alert('Chưa đủ dữ liệu', 'Hãy nhập ít nhất một môn hợp lệ.');
      return;
    }
    setGpaLoading(true);
    try {
      const data = await apiPost('/courses/calculate', { courses });
      setGpaResult(data.gpa);
      setGpaCalculated(true);
    } catch (error) {
      Alert.alert('Không thể tính GPA', error.message);
    } finally {
      setGpaLoading(false);
    }
  }, [gpaRows]);

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

  const renderAnalytics = () => {
    if (analytics?.error === 'premium_required') {
      return (
        <Card>
          <View style={styles.sectionHeader}>
            <Text style={styles.kicker}>PHÂN TÍCH TUẦN</Text>
            <Text style={styles.sectionTitle}>Xu hướng hoạt động</Text>
          </View>
          <Text style={styles.analyticsLockedText}>
            Phân tích tuần là tính năng Premium. Nâng cấp để xem xu hướng hoàn thành task và email theo ngày.
          </Text>
          <Button title="Mở khóa Premium" onPress={() => onNavigate?.('settings')} />
        </Card>
      );
    }

    const daily = Array.isArray(analytics?.daily) ? analytics.daily : [];
    if (!daily.length) return null;
    const totals = analytics.totals || {};
    const weekdayLabels = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];
    const maxActivity = Math.max(1, ...daily.map((d) => Math.max(d.tasks_total || 0, d.emails_total || 0)));
    const todayIso = formatDateForApi(new Date());
    const busiestEntry = daily.find((d) => d.date === totals.busiest_date);
    const busiestLabel = busiestEntry ? weekdayLabels[busiestEntry.weekday] ?? '—' : '—';
    const rangeDays = analytics.range?.days || daily.length;

    return (
      <Card>
        <View style={styles.sectionHeader}>
          <Text style={styles.kicker}>{`PHÂN TÍCH ${rangeDays} NGÀY`}</Text>
          <Text style={styles.sectionTitle}>Xu hướng hoạt động</Text>
        </View>
        <View style={styles.kpiGrid}>
          <View style={styles.kpiCell}>
            <Text style={styles.kpiValue}>{totals.completion_rate ?? 0}%</Text>
            <Text style={styles.kpiLabel}>Hoàn thành task</Text>
          </View>
          <View style={styles.kpiCell}>
            <Text style={styles.kpiValue}>{totals.emails_total ?? 0}</Text>
            <Text style={styles.kpiLabel}>Email đã xử lý</Text>
          </View>
          <View style={styles.kpiCell}>
            <Text style={styles.kpiValue}>{totals.deadlines_total ?? 0}</Text>
            <Text style={styles.kpiLabel}>{`Deadline (${rangeDays}n)`}</Text>
          </View>
          <View style={styles.kpiCell}>
            <Text style={styles.kpiValue}>{busiestLabel}</Text>
            <Text style={styles.kpiLabel}>Ngày bận nhất</Text>
          </View>
        </View>
        <View style={styles.barChart}>
          {daily.map((d) => {
            const taskH = Math.round(((d.tasks_total || 0) / maxActivity) * 100);
            const emailH = Math.round(((d.emails_total || 0) / maxActivity) * 100);
            const isToday = d.date === todayIso;
            return (
              <View key={d.date} style={styles.barCol}>
                <View style={styles.barTrack}>
                  <View style={[styles.barTask, { height: `${taskH}%` }]} />
                  <View style={[styles.barEmail, { height: `${emailH}%` }]} />
                </View>
                <Text style={[styles.barLabel, isToday && styles.barLabelToday]}>
                  {weekdayLabels[d.weekday] ?? ''}
                </Text>
              </View>
            );
          })}
        </View>
        <View style={styles.barLegend}>
          <View style={styles.legendRow}><View style={[styles.legendDot, styles.legendTask]} /><Text style={styles.legendText}>Task/Lịch</Text></View>
          <View style={styles.legendRow}><View style={[styles.legendDot, styles.legendEmail]} /><Text style={styles.legendText}>Email</Text></View>
        </View>
      </Card>
    );
  };

  return (
    <Screen
      title="Tổng hợp"
      refreshing={loading}
      onRefresh={() => loadOverview()}
      actions={<Button title="Tổng hợp lại" variant="secondary" onPress={() => loadOverview({ force: true })} loading={loading} />}
    >
      <LinearGradient
        colors={[`${colors.primary}1f`, '#0d948814']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.heroCard}
      >
        <View style={styles.heroTopRow}>
          <View style={styles.heroTopText}>
            <Text style={styles.kicker}>FLOWMATE AI</Text>
            <Text style={styles.heroTitle}>{formatReportDate(date)}</Text>
          </View>
          <View style={styles.heroScore}>
            <Text style={styles.heroScoreValue}>{openTasks.length + emails.length}</Text>
            <Text style={styles.heroScoreLabel}>việc cần xem</Text>
          </View>
        </View>
        <Text style={styles.heroText}>{insight}</Text>
        {refreshNote ? <Text style={styles.refreshNote}>{refreshNote}</Text> : null}
        <Text style={styles.sourceText}>{sourceText}</Text>
      </LinearGradient>

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
          placeholder="Hãy nhập hoạt động trong ngày vào checklist"
          multiline
          inputStyle={styles.quickInputField}
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

      {upcomingDeadlines ? (
        <Card>
          <View style={styles.sectionHeader}>
            <Text style={styles.kicker}>ĐẾM NGƯỢC</Text>
            <Text style={styles.sectionTitle}>Deadline sắp tới</Text>
          </View>
          {upcomingDeadlines.length === 0 ? (
            <Text style={styles.itemMeta}>Chưa có deadline nào sắp tới.</Text>
          ) : upcomingDeadlines.map((deadline) => (
            <View key={deadline.id} style={styles.countdownRow}>
              <Text style={[
                styles.countdownDays,
                deadline.days_until <= 3 && styles.countdownUrgent,
                deadline.days_until > 3 && deadline.days_until <= 7 && styles.countdownSoon,
              ]}>
                {deadline.days_until <= 0 ? 'Hôm nay' : `Còn ${deadline.days_until} ngày`}
              </Text>
              <Text style={styles.countdownTitle} numberOfLines={1}>{deadline.title}</Text>
            </View>
          ))}
          {!isPremium ? (
            <Text style={styles.studentUpsellText}>
              Free chỉ hiện deadline gần nhất. Nâng cấp Premium để xem đầy đủ danh sách.
            </Text>
          ) : null}
        </Card>
      ) : null}

      {isStudent ? (
        <Card>
          <View style={styles.sectionHeader}>
            <Text style={styles.kicker}>CÔNG CỤ SINH VIÊN</Text>
            <Text style={styles.sectionTitle}>Học tập & điểm số</Text>
          </View>
          <View style={styles.studentToolsRow}>
            <Button title="Tóm tắt tài liệu" variant="secondary" style={styles.studentToolButton} onPress={() => setSummarizerVisible(true)} />
            <Button title="Tính GPA" variant="secondary" style={styles.studentToolButton} onPress={() => setGpaVisible(true)} />
          </View>
        </Card>
      ) : null}

      <Card>
        <View style={styles.checklistHeaderRow}>
          <View style={styles.checklistHeaderText}>
            <Text style={styles.kicker}>CHECKLIST</Text>
            <Text style={styles.sectionTitle}>Việc và lịch được AI sắp xếp</Text>
            <Text style={styles.checklistMeta}>{completedCount}/{checklistItems.length} đã xong</Text>
            <View style={styles.checklistProgressTrack}>
              <View style={[
                styles.checklistProgressFill,
                { width: `${checklistItems.length ? Math.round((completedCount / checklistItems.length) * 100) : 0}%` },
              ]} />
            </View>
          </View>
          <View style={styles.checklistHeaderButtons}>
            {isStudent ? (
              <TouchableOpacity style={styles.sortButton} onPress={openGroupedBySubject} activeOpacity={0.78}>
                <Text style={styles.sortButtonText}>Xem theo môn</Text>
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity style={styles.sortButton} onPress={sortChecklist} activeOpacity={0.78}>
              <Text style={styles.sortButtonText}>Sắp xếp AI</Text>
            </TouchableOpacity>
          </View>
        </View>
        {checklistItems.length === 0 ? (
          <EmptyState title="Checklist đang trống" detail="Thêm việc hoặc lịch ở ô Thêm nhanh phía trên." />
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
              {isStudent && item.kind === 'custom' ? (
                <TouchableOpacity onPress={() => openSubjectEditor(item)} hitSlop={{ top: 4, bottom: 4, left: 4, right: 4 }}>
                  {item.subject ? (
                    <Text style={styles.subjectChip}>{item.subject}</Text>
                  ) : (
                    <Text style={styles.subjectAddText}>+ Môn học</Text>
                  )}
                </TouchableOpacity>
              ) : null}
            </TouchableOpacity>
            <View style={styles.checklistActions}>
              <Text style={styles.checklistSource}>{item.sourceLabel || 'Lịch'}</Text>
              {item.kind === 'custom' ? (
                <TouchableOpacity
                  style={styles.checklistRemove}
                  onPress={() => removeChecklistItem(item)}
                  activeOpacity={0.78}
                  hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                >
                  <Text style={styles.checklistRemoveText}>×</Text>
                </TouchableOpacity>
              ) : null}
            </View>
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
          <TouchableOpacity
            key={`${item.subject}-${index}`}
            style={styles.item}
            activeOpacity={0.78}
            onPress={() => setSelectedEmail(item)}
          >
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
          </TouchableOpacity>
        ))}
      </Card>

      {renderAnalytics()}

      <Modal visible={!!selectedEmail} animationType="slide" onRequestClose={() => setSelectedEmail(null)}>
        <Screen title="Chi tiết email" actions={<Button title="Đóng" variant="secondary" onPress={() => setSelectedEmail(null)} />}>
          {selectedEmail ? (
            <Card>
              <Text style={styles.itemTitle}>{selectedEmail.subject || 'Email không tiêu đề'}</Text>
              <Text style={styles.itemMeta}>{selectedEmail.sender || 'Người gửi'}</Text>
              <Text style={styles.itemPreview}>{selectedEmail.summary || 'Chưa có tóm tắt AI cho email này.'}</Text>
              {selectedEmail.is_meeting ? <Text style={[styles.chip, styles.meetingChip, styles.detailChip]}>Có thể là lịch họp</Text> : null}
              <Button
                title="Mở trong hộp thư"
                style={styles.detailButton}
                onPress={() => {
                  setSelectedEmail(null);
                  onNavigate?.('emails');
                }}
              />
            </Card>
          ) : null}
        </Screen>
      </Modal>

      <Modal visible={!!subjectEditItem} animationType="fade" transparent onRequestClose={() => setSubjectEditItem(null)}>
        <View style={styles.centeredModalOverlay}>
          <View style={styles.centeredModalCard}>
            <Text style={styles.sectionTitle}>Môn học</Text>
            <Field label="Tên môn" value={subjectEditValue} onChangeText={setSubjectEditValue} placeholder="Ví dụ: Toán cao cấp" />
            <View style={styles.studentToolsActions}>
              <Button title="Hủy" variant="secondary" onPress={() => setSubjectEditItem(null)} />
              <Button title="Lưu" onPress={saveSubjectEdit} />
            </View>
          </View>
        </View>
      </Modal>

      <Modal visible={groupedVisible} animationType="slide" onRequestClose={() => setGroupedVisible(false)}>
        <Screen title="Checklist theo môn" actions={<Button title="Đóng" variant="secondary" onPress={() => setGroupedVisible(false)} />}>
          <Card>
            {groupedSubjects.length === 0 ? (
              <EmptyState title="Checklist đang trống" detail="Chưa có việc nào để nhóm theo môn." />
            ) : groupedSubjects.map((group) => (
              <View key={group.subject}>
                <Text style={styles.groupSubjectHeading}>{group.subject}</Text>
                {group.items.map((item) => (
                  <View key={item.id} style={styles.countdownRow}>
                    <Text style={styles.countdownTitle} numberOfLines={1}>{item.title}</Text>
                    {item.completed ? <Text style={styles.checklistSource}>Xong</Text> : null}
                  </View>
                ))}
              </View>
            ))}
          </Card>
        </Screen>
      </Modal>

      <Modal visible={summarizerVisible} animationType="slide" onRequestClose={() => setSummarizerVisible(false)}>
        <Screen title="Tóm tắt tài liệu học tập" actions={<Button title="Đóng" variant="secondary" onPress={() => setSummarizerVisible(false)} />}>
          <Card>
            <Text style={styles.itemMeta}>Dán bài giảng, ghi chú hoặc tài liệu học tập để Bob tóm tắt các ý chính.</Text>
            <Field label="Tiêu đề (không bắt buộc)" value={summaryTitle} onChangeText={setSummaryTitle} placeholder="Ví dụ: Bài giảng chương 3" />
            <Field label="Nội dung" value={summaryContent} onChangeText={setSummaryContent} placeholder="Dán nội dung vào đây..." multiline inputStyle={styles.summaryTextarea} />
            {!isPremium ? <Text style={styles.studentUpsellText}>Free: 5 lượt/ngày. Premium: không giới hạn.</Text> : null}
            <Button title="Tóm tắt" onPress={submitStudySummary} loading={summaryLoading} style={styles.detailButton} />
            {summaryResult ? (
              <View style={styles.summaryResultBox}>
                <Text style={styles.itemPreview}>{summaryResult}</Text>
              </View>
            ) : null}
          </Card>
        </Screen>
      </Modal>

      <Modal visible={gpaVisible} animationType="slide" onRequestClose={() => setGpaVisible(false)}>
        <Screen title="Tính GPA" actions={<Button title="Đóng" variant="secondary" onPress={() => setGpaVisible(false)} />}>
          <Card>
            <Text style={styles.itemMeta}>Nhập môn học, tín chỉ và điểm (theo thang điểm bạn đang dùng).</Text>
            {!isPremium ? (
              <Text style={styles.studentUpsellText}>Free: tính tại chỗ, không lưu lại. Nâng cấp Premium để lưu danh sách môn.</Text>
            ) : null}
            {gpaRows.map((row, index) => (
              <View key={index} style={styles.gpaRow}>
                <TextInput
                  style={[styles.gpaInput, styles.gpaInputName]}
                  value={row.name}
                  onChangeText={(value) => updateGpaRow(index, 'name', value)}
                  placeholder="Môn"
                  placeholderTextColor={colors.inputPlaceholder}
                />
                <TextInput
                  style={styles.gpaInput}
                  value={String(row.credits)}
                  onChangeText={(value) => updateGpaRow(index, 'credits', value)}
                  placeholder="TC"
                  placeholderTextColor={colors.inputPlaceholder}
                  keyboardType="numeric"
                />
                <TextInput
                  style={styles.gpaInput}
                  value={String(row.grade)}
                  onChangeText={(value) => updateGpaRow(index, 'grade', value)}
                  placeholder="Điểm"
                  placeholderTextColor={colors.inputPlaceholder}
                  keyboardType="numeric"
                />
                <TouchableOpacity style={styles.checklistRemove} onPress={() => removeGpaRow(index)} hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}>
                  <Text style={styles.checklistRemoveText}>×</Text>
                </TouchableOpacity>
              </View>
            ))}
            <View style={styles.studentToolsActions}>
              <Button title="+ Thêm môn" variant="secondary" onPress={addGpaRow} />
              <Button title="Tính GPA" onPress={calculateGpa} loading={gpaLoading} />
            </View>
            {gpaCalculated ? (
              <View style={styles.gpaResultBox}>
                <Text style={styles.gpaResultText}>{gpaResult === null ? 'Chưa đủ dữ liệu hợp lệ' : `GPA: ${gpaResult}`}</Text>
              </View>
            ) : null}
          </Card>
        </Screen>
      </Modal>
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
    revision: Math.max(0, Number(value?.revision) || 0),
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
        sourceLabel: item.source === 'ai' ? 'AI' : 'Tự thêm',
        pinned: Boolean(item.pinned),
        priority_score: Number(item.priority_score || 0),
        due_at: item.due_at || '',
        due_date: item.due_date || '',
        created_at: item.created_at || '',
        subject: item.subject || '',
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
        pinned: false,
        priority_score: /(deadline|hạn|nộp|due|submit|bàn giao)/i.test(item.title || '') ? 80 : 55,
        start_time: item.start_time || '',
        created_at: item.start_time || '',
      };
    });
  return [...customItems, ...scheduleItems].sort(compareChecklistItems);
}

function checklistDateValue(item) {
  const raw = item.due_at || item.start_time || item.due_date || '';
  if (!raw) return Number.MAX_SAFE_INTEGER;
  const normalized = String(raw).includes('T') ? String(raw) : `${raw}T23:59:59`;
  const time = new Date(normalized).getTime();
  return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time;
}

function compareChecklistItems(a, b) {
  const completedDiff = Number(Boolean(a.completed)) - Number(Boolean(b.completed));
  if (completedDiff) return completedDiff;
  const pinnedDiff = Number(!a.pinned) - Number(!b.pinned);
  if (pinnedDiff) return pinnedDiff;
  const dateDiff = checklistDateValue(a) - checklistDateValue(b);
  if (dateDiff) return dateDiff;
  const priorityDiff = Number(b.priority_score || 0) - Number(a.priority_score || 0);
  if (priorityDiff) return priorityDiff;
  return String(a.created_at || '').localeCompare(String(b.created_at || ''));
}

function sortChecklistEntries(items = []) {
  return [...items].sort(compareChecklistItems);
}

function customChecklistMeta(item) {
  const dueDate = item.due_date || (item.due_at ? String(item.due_at).slice(0, 10) : '');
  if (!dueDate) return item.ai_reason || 'Chưa có hạn rõ ràng';
  const date = new Date(`${dueDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return item.ai_reason || dueDate;
  const label = date.toLocaleDateString('vi-VN', { weekday: 'short', day: '2-digit', month: '2-digit' });
  return item.ai_reason ? `${label} · ${item.ai_reason}` : label;
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
  const fontRegular  = 'Poppins_400Regular';
  const fontMedium   = 'Poppins_500Medium';
  const fontSemiBold = 'Poppins_600SemiBold';
  const fontBold     = 'Poppins_700Bold';
  return StyleSheet.create({
    heroCard: {
      gap: 6,
      padding: 18,
      borderRadius: 14,
      borderWidth: 1,
      borderColor: `${colors.primary}33`,
      ...colors.shadow,
    },
    kicker: {
      color: colors.primary,
      fontFamily: fontSemiBold,
      fontSize: 10,
      letterSpacing: 1,
      textTransform: 'uppercase',
    },
    heroTitle: { color: colors.text, fontFamily: fontSemiBold, fontSize: 18 },
    heroTopRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
    heroTopText: { flex: 1, minWidth: 0 },
    heroScore: {
      minWidth: 64,
      alignItems: 'center',
      paddingHorizontal: 10,
      paddingVertical: 8,
      borderRadius: 12,
      backgroundColor: colors.primary,
      ...colors.shadow,
    },
    heroScoreValue: { color: '#FFFFFF', fontFamily: fontBold, fontSize: 18 },
    heroScoreLabel: { marginTop: 1, color: '#FFFFFF', fontFamily: fontMedium, fontSize: 9, textAlign: 'center' },
    heroText: { color: colors.textMuted, fontFamily: fontRegular, fontSize: 13, lineHeight: 19 },
    refreshNote: { marginTop: 4, color: colors.primary, fontFamily: fontMedium, fontSize: 12, lineHeight: 18 },
    sourceText: { marginTop: 4, color: colors.textMuted, fontFamily: fontMedium, fontSize: 11 },
    dateCard: { gap: 8 },
    quickCard: { gap: 8 },
    quickInputField: { minHeight: 48 },
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
      fontFamily: fontSemiBold,
      fontSize: 12,
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
    planTitle: { color: colors.text, fontFamily: fontBold, fontSize: 14 },
    planMeta: { marginTop: 3, color: colors.textMuted, fontFamily: fontMedium, fontSize: 11 },
    planBadge: {
      overflow: 'hidden',
      borderRadius: 999,
      paddingHorizontal: 8,
      paddingVertical: 4,
      backgroundColor: `${colors.primary}18`,
      color: colors.primary,
      fontFamily: fontBold,
      fontSize: 10,
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
      fontFamily: fontMedium,
      fontSize: 11,
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
      minHeight: 76,
      borderRadius: 12,
      padding: 13,
      justifyContent: 'center',
    },
    statValue: { color: colors.text, fontFamily: fontSemiBold, fontSize: 22 },
    statLabel: { marginTop: 3, color: colors.textMuted, fontFamily: fontMedium, fontSize: 11 },
    sectionHeader: { marginBottom: 4 },
    sectionTitle: { marginTop: 2, color: colors.text, fontFamily: fontSemiBold, fontSize: 14 },
    analyticsLockedText: {
      marginTop: 10,
      marginBottom: 12,
      color: colors.textMuted,
      fontFamily: fontMedium,
      fontSize: 12,
      lineHeight: 18,
    },
    checklistMeta: { marginTop: 4, color: colors.textMuted, fontFamily: fontMedium, fontSize: 11 },
    checklistProgressTrack: {
      marginTop: 6,
      height: 6,
      borderRadius: 999,
      overflow: 'hidden',
      backgroundColor: `${colors.primary}18`,
    },
    checklistProgressFill: {
      height: 6,
      borderRadius: 999,
      backgroundColor: colors.primary,
    },
    checklistHeaderRow: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 8,
      marginBottom: 4,
    },
    checklistHeaderText: { flex: 1, minWidth: 0 },
    checklistHeaderButtons: { flexDirection: 'row', gap: 6 },
    // Student-mode-only widgets (deadline countdown, subject tag/chip,
    // study-material summarizer, GPA calculator modals).
    countdownRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 10,
      paddingVertical: 8,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    countdownDays: { color: colors.textMuted, fontFamily: fontBold, fontSize: 12 },
    countdownSoon: { color: colors.warning },
    countdownUrgent: { color: colors.danger },
    countdownTitle: { flex: 1, color: colors.text, fontFamily: fontMedium, fontSize: 13 },
    studentUpsellText: {
      marginTop: 10,
      color: colors.textMuted,
      fontFamily: fontMedium,
      fontSize: 11,
      lineHeight: 16,
    },
    studentToolsRow: { flexDirection: 'row', gap: 8 },
    studentToolButton: { flex: 1 },
    subjectChip: {
      alignSelf: 'flex-start',
      marginTop: 4,
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: 999,
      backgroundColor: 'rgba(99,102,241,0.14)',
      color: '#4338ca',
      fontFamily: fontSemiBold,
      fontSize: 10,
    },
    subjectAddText: {
      marginTop: 4,
      color: colors.textMuted,
      fontFamily: fontMedium,
      fontSize: 11,
    },
    centeredModalOverlay: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.4)',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    },
    centeredModalCard: {
      width: '100%',
      maxWidth: 420,
      borderRadius: 16,
      padding: 18,
      backgroundColor: colors.panel,
    },
    studentToolsActions: {
      flexDirection: 'row',
      justifyContent: 'flex-end',
      gap: 10,
      marginTop: 10,
    },
    groupSubjectHeading: {
      marginTop: 12,
      marginBottom: 2,
      color: colors.text,
      fontFamily: fontBold,
      fontSize: 13,
    },
    summaryTextarea: { minHeight: 140 },
    summaryResultBox: {
      marginTop: 12,
      padding: 12,
      borderRadius: 10,
      backgroundColor: `${colors.primary}0d`,
    },
    gpaRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginBottom: 8,
    },
    gpaInput: {
      width: 64,
      minHeight: 40,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: 8,
      backgroundColor: colors.panel,
      color: colors.text,
      paddingHorizontal: 8,
      fontFamily: fontRegular,
      fontSize: 12,
    },
    gpaInputName: { flex: 1, width: undefined },
    gpaResultBox: {
      marginTop: 12,
      padding: 12,
      borderRadius: 10,
      backgroundColor: 'rgba(99,102,241,0.12)',
      alignItems: 'center',
    },
    gpaResultText: { color: '#4338ca', fontFamily: fontBold, fontSize: 15 },
    sortButton: {
      borderRadius: 999,
      paddingHorizontal: 10,
      paddingVertical: 6,
      backgroundColor: `${colors.primary}18`,
    },
    sortButtonText: {
      color: colors.primary,
      fontFamily: fontBold,
      fontSize: 11,
    },
    checklistActions: { alignItems: 'flex-end', gap: 4 },
    checklistRemove: {
      width: 20,
      height: 20,
      borderRadius: 6,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: `${colors.danger}18`,
    },
    checklistRemoveText: {
      color: colors.danger,
      fontFamily: fontBold,
      fontSize: 13,
      lineHeight: 14,
    },
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
      fontFamily: fontSemiBold,
      lineHeight: 16,
    },
    checkboxTextChecked: { color: '#ffffff' },
    checklistBody: { flex: 1, minWidth: 0 },
    checklistTitle: { color: colors.text, fontFamily: fontSemiBold, fontSize: 13, lineHeight: 18 },
    checklistTitleDone: {
      color: colors.textMuted,
      textDecorationLine: 'line-through',
    },
    checklistSource: {
      color: colors.textMuted,
      fontFamily: fontMedium,
      fontSize: 10,
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
    itemIndexText: { color: colors.primary, fontFamily: fontSemiBold, fontSize: 11 },
    itemBody: { flex: 1, minWidth: 0 },
    itemTitle: { color: colors.text, fontFamily: fontSemiBold, fontSize: 13, lineHeight: 18 },
    itemMeta: { marginTop: 3, color: colors.textMuted, fontFamily: fontMedium, fontSize: 11 },
    itemPreview: { marginTop: 6, color: colors.textMuted, fontFamily: fontRegular, fontSize: 12, lineHeight: 18 },
    chip: {
      overflow: 'hidden',
      borderRadius: 999,
      paddingHorizontal: 8,
      paddingVertical: 4,
      backgroundColor: 'rgba(13,148,136,0.13)',
      color: '#0f766e',
      fontFamily: fontSemiBold,
      fontSize: 10,
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
      fontFamily: fontSemiBold,
      fontSize: 12,
    },
    detailButton: { marginTop: 14 },
    detailChip: { marginTop: 10, alignSelf: 'flex-start' },
    kpiGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
      marginTop: 4,
    },
    kpiCell: {
      flexGrow: 1,
      flexBasis: '46%',
      padding: 10,
      borderRadius: 10,
      backgroundColor: colors.panelSoft,
    },
    kpiValue: { color: colors.text, fontFamily: fontBold, fontSize: 16 },
    kpiLabel: { marginTop: 2, color: colors.textMuted, fontFamily: fontMedium, fontSize: 10 },
    barChart: {
      marginTop: 14,
      flexDirection: 'row',
      alignItems: 'flex-end',
      justifyContent: 'space-between',
      height: 90,
    },
    barCol: { flex: 1, alignItems: 'center', gap: 6 },
    barTrack: {
      width: 14,
      height: 66,
      borderRadius: 7,
      overflow: 'hidden',
      backgroundColor: `${colors.primary}12`,
      justifyContent: 'flex-end',
    },
    barTask: { width: '100%', backgroundColor: colors.primary },
    barEmail: { width: '100%', backgroundColor: '#0d9488' },
    barLabel: { color: colors.textMuted, fontFamily: fontMedium, fontSize: 10 },
    barLabelToday: { color: colors.primary, fontFamily: fontBold },
    barLegend: { flexDirection: 'row', gap: 14, marginTop: 10 },
    legendRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    legendDot: { width: 8, height: 8, borderRadius: 4 },
    legendTask: { backgroundColor: colors.primary },
    legendEmail: { backgroundColor: '#0d9488' },
    legendText: { color: colors.textMuted, fontFamily: fontMedium, fontSize: 10 },
  });
}
