import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Linking, Modal, StyleSheet, Text, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import SegmentedControl from '../components/SegmentedControl';
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '../api/client';
import { useTheme } from '../theme/ThemeContext';

const modes = [
  { label: 'Lich tong hop', value: 'list' },
  { label: 'Tao moi',       value: 'create' },
];

const initialForm = {
  title: '', description: '', start_time: '', end_time: '',
  duration_minutes: '60', location: '', attendees: '',
};

export default function ScheduleScreen() {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [mode, setMode] = useState('list');
  const [currentWeekStart, setCurrentWeekStart] = useState(() => getMonday(new Date()));
  const [schedules, setSchedules] = useState([]);
  const [weekSummary, setWeekSummary] = useState({ current: [], next: [] });
  const [meetingSuggestions, setMeetingSuggestions] = useState([]);
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const [editForm, setEditForm] = useState(initialForm);
  const [loading, setLoading] = useState(false);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  const loadSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const nextWeekStart = new Date(currentWeekStart);
      nextWeekStart.setDate(nextWeekStart.getDate() + 7);

      const [data, currentWeek, nextWeek] = await Promise.all([
        apiGet('/schedule/unified?max_results=50&live=0'),
        apiGet(`/schedule/week?start=${formatDateForApi(currentWeekStart)}&sync=0`),
        apiGet(`/schedule/week?start=${formatDateForApi(nextWeekStart)}&sync=0`),
      ]);

      setSchedules(data.items || []);
      setCalendarConnected(Boolean(data.calendar_connected));
      setWeekSummary({
        current: flattenWeekSchedules(currentWeek.days),
        next: flattenWeekSchedules(nextWeek.days),
      });
    } catch (error) {
      Alert.alert('Loi tai lich', error.message);
    } finally {
      setLoading(false);
    }
  }, [currentWeekStart]);

  const loadMeetingSuggestions = useCallback(async () => {
    setSuggestionsLoading(true);
    try {
      const data = await apiGet('/email/meeting-suggestions');
      setMeetingSuggestions(data.suggestions || []);
    } catch (error) {
      if (error.status !== 401) Alert.alert('Loi tai goi y lich', error.message);
    } finally {
      setSuggestionsLoading(false);
    }
  }, []);

  useEffect(() => { loadSchedules(); }, [loadSchedules]);
  useEffect(() => { loadMeetingSuggestions(); }, [loadMeetingSuggestions]);

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const setEditField = (key, value) => setEditForm((current) => ({ ...current, [key]: value }));

  const createSchedule = async () => {
    if (!form.title || !form.start_time) {
      Alert.alert('Thieu thong tin', 'Vui long nhap tieu de va thoi gian bat dau.');
      return;
    }
    setLoading(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        start_time: form.start_time,
        end_time: form.end_time,
        duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : 60,
        location: form.location,
        attendees: splitAttendees(form.attendees),
      };
      await apiPost('/schedule/create', payload);
      setForm(initialForm);
      setMode('list');
      await loadSchedules();
      Alert.alert('Da tao lich');
    } catch (error) {
      Alert.alert('Khong tao duoc lich', error.message);
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (schedule, status) => {
    try {
      await apiPatch(`/schedule/${schedule.local_id}/update-status`, { status });
      await loadSchedules();
    } catch (error) {
      Alert.alert('Khong cap nhat duoc lich', error.message);
    }
  };

  const scanMeetingSuggestions = async () => {
    setSuggestionsLoading(true);
    try {
      const data = await apiPost('/email/meeting-suggestions/scan');
      setMeetingSuggestions(data.suggestions || []);
      Alert.alert('Da quet email', `Tim thay ${data.count || 0} goi y lich dang cho.`);
    } catch (error) {
      Alert.alert('Khong quet duoc email', error.message);
    } finally {
      setSuggestionsLoading(false);
    }
  };

  const updateMeetingSuggestionStatus = async (suggestionId, status, scheduleId = null) => {
    await apiPatch(`/email/meeting-suggestions/${suggestionId}/status`, {
      status,
      schedule_id: scheduleId,
    });
    await loadMeetingSuggestions();
  };

  const createScheduleFromSuggestion = async (suggestion) => {
    if (!suggestion.start_time) {
      setForm({
        title: suggestion.title || suggestion.subject || 'Lich hen tu email',
        description: suggestion.description || suggestion.snippet || '',
        start_time: '',
        end_time: '',
        duration_minutes: '60',
        location: suggestion.location || '',
        attendees: suggestion.attendees || '',
      });
      setMode('create');
      Alert.alert('Can bo sung thoi gian', 'Goi y nay chua co gio bat dau, hay nhap thoi gian de tao lich.');
      return;
    }

    setLoading(true);
    try {
      const data = await apiPost('/schedule/create', {
        title: suggestion.title || suggestion.subject || 'Lich hen tu email',
        description: suggestion.description || suggestion.snippet || '',
        start_time: normalizeDateTime(suggestion.start_time),
        end_time: normalizeDateTime(suggestion.end_time) || addMinutesIso(suggestion.start_time, 60),
        duration_minutes: durationMinutes(suggestion.start_time, suggestion.end_time) || 60,
        location: suggestion.location || '',
        attendees: splitAttendees(suggestion.attendees || ''),
      });
      await updateMeetingSuggestionStatus(suggestion.id, 'created', data.schedule_id);
      await loadSchedules();
      Alert.alert('Da tao lich tu email');
    } catch (error) {
      Alert.alert('Khong tao duoc lich', error.message);
    } finally {
      setLoading(false);
    }
  };

  const openEditSchedule = (schedule) => {
    setEditingSchedule(schedule);
    setEditForm({
      title: schedule.title || '',
      description: schedule.description || '',
      start_time: normalizeDateTime(schedule.start_time),
      end_time: normalizeDateTime(schedule.end_time),
      duration_minutes: String(durationMinutes(schedule.start_time, schedule.end_time) || 60),
      location: schedule.location || '',
      attendees: Array.isArray(schedule.attendees) ? schedule.attendees.join(', ') : (schedule.attendees || ''),
    });
  };

  const updateSchedule = async () => {
    if (!editingSchedule?.local_id || !editForm.title || !editForm.start_time) {
      Alert.alert('Thieu thong tin', 'Vui long nhap tieu de va thoi gian bat dau.');
      return;
    }
    setLoading(true);
    try {
      await apiPut(`/schedule/${editingSchedule.local_id}`, {
        title: editForm.title,
        description: editForm.description,
        start_time: editForm.start_time,
        end_time: editForm.end_time,
        duration_minutes: editForm.duration_minutes ? Number(editForm.duration_minutes) : 60,
        location: editForm.location,
        attendees: splitAttendees(editForm.attendees),
      });
      setEditingSchedule(null);
      setEditForm(initialForm);
      await loadSchedules();
      Alert.alert('Da cap nhat lich');
    } catch (error) {
      Alert.alert('Khong cap nhat duoc lich', error.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteSchedule = async (schedule) => {
    try {
      await apiDelete(`/schedule/${schedule.local_id}`);
      await loadSchedules();
    } catch (error) {
      Alert.alert('Khong xoa duoc lich', error.message);
    }
  };

  const deleteEvent = async (event) => {
    try {
      await apiDelete(`/calendar/delete/${event.google_event_id}`);
      await loadSchedules();
    } catch (error) {
      Alert.alert('Khong xoa duoc su kien', error.message);
    }
  };

  const shiftWeek = (direction) => {
    setCurrentWeekStart((current) => {
      const next = new Date(current);
      next.setDate(next.getDate() + direction * 7);
      return getMonday(next);
    });
  };

  const renderList = () => (
    <>
      <Card style={styles.summaryCard}>
        <View style={styles.summaryHeader}>
          <View>
            <Text style={styles.summaryKicker}>Tong hop lich hen</Text>
            <Text style={styles.summaryTitle}>{formatWeekRange(currentWeekStart)}</Text>
          </View>
          <Text style={styles.summaryTotal}>{weekSummary.current.length + weekSummary.next.length}</Text>
        </View>
        <View style={styles.weekNav}>
          <Button title="Tuan truoc" variant="secondary" onPress={() => shiftWeek(-1)} />
          <Button title="Tuan nay" variant="secondary" onPress={() => setCurrentWeekStart(getMonday(new Date()))} />
          <Button title="Tuan sau" variant="secondary" onPress={() => shiftWeek(1)} />
        </View>
        <View style={styles.weekGrid}>
          {renderWeekSummary('Tuan dang xem', weekSummary.current)}
          {renderWeekSummary('Tuan ke tiep', weekSummary.next)}
        </View>
      </Card>

      <Card style={styles.suggestionCard}>
        <View style={styles.summaryHeader}>
          <View>
            <Text style={styles.summaryKicker}>Goi y tu email</Text>
            <Text style={styles.summaryTitle}>Cuoc hop va lich hen phat hien</Text>
          </View>
          <Text style={styles.summaryTotal}>{meetingSuggestions.length}</Text>
        </View>
        <View style={styles.weekNav}>
          <Button title="Quet email" variant="secondary" onPress={scanMeetingSuggestions} loading={suggestionsLoading} />
          <Button title="Lam moi" variant="secondary" onPress={loadMeetingSuggestions} loading={suggestionsLoading} />
        </View>
        {meetingSuggestions.length === 0 ? (
          <Text style={styles.weekEmpty}>Chua co goi y lich moi.</Text>
        ) : (
          meetingSuggestions.map((suggestion) => (
            <View key={suggestion.id} style={styles.suggestionItem}>
              <Text style={styles.weekItemTitle}>{suggestion.title || suggestion.subject || 'Lich hen tu email'}</Text>
              <Text style={styles.weekItemTime}>Tu: {suggestion.sender || 'Khong xac dinh'}</Text>
              <Text style={styles.previewText} numberOfLines={3}>{suggestion.snippet || suggestion.description || ''}</Text>
              <Text style={styles.weekItemTime}>{suggestion.start_time ? formatShortDate(suggestion.start_time) : 'Chua xac dinh thoi gian'}</Text>
              <View style={styles.actions}>
                <Button title="Tao lich" onPress={() => createScheduleFromSuggestion(suggestion)} />
                <Button title="Bo qua" variant="secondary" onPress={() => updateMeetingSuggestionStatus(suggestion.id, 'dismissed')} />
              </View>
            </View>
          ))
        )}
      </Card>

      {schedules.length === 0 ? (
        <EmptyState title="Chua co lich sap toi" detail="Tao lich moi hoac dang nhap Gmail de dong bo Google Calendar." />
      ) : (
        schedules.map((schedule) => (
          <Card key={schedule.id}>
            <View style={styles.cardHeader}>
              <Text style={styles.title}>{schedule.title}</Text>
              <Text style={[
                styles.source,
                schedule.source === 'synced' ? styles.sourceSynced : styles.sourceDefault,
              ]}>
                {sourceLabel(schedule.source)}
              </Text>
            </View>
            <Text style={styles.time}>
              {formatDate(schedule.start_time)}
              {schedule.end_time ? ` - ${formatDate(schedule.end_time)}` : ''}
            </Text>
            {schedule.description ? <Text style={styles.description}>{schedule.description}</Text> : null}
            {schedule.location   ? <Text style={styles.meta}>Dia diem: {schedule.location}</Text>  : null}
            {schedule.attendees  ? <Text style={styles.meta}>Tham du: {schedule.attendees}</Text>   : null}
            <View style={styles.actions}>
              {schedule.local_id ? (
                <>
                  <Button title="Hoan tat" variant="secondary" onPress={() => updateStatus(schedule, 'completed')} />
                  <Button title="Sua" variant="secondary" onPress={() => openEditSchedule(schedule)} />
                  <Button title="Huy" variant="secondary" onPress={() => updateStatus(schedule, 'cancelled')} />
                  <Button title="Xoa" variant="danger" onPress={() => deleteSchedule(schedule)} />
                </>
              ) : (
                <Button title="Xoa khoi Google" variant="danger" onPress={() => deleteEvent(schedule)} />
              )}
            </View>
          </Card>
        ))
      )}
    </>
  );

  const renderWeekSummary = (title, items) => (
    <View style={styles.weekSummary}>
      <View style={styles.weekSummaryHeader}>
        <Text style={styles.weekTitle}>{title}</Text>
        <Text style={styles.weekCount}>{items.length} lich</Text>
      </View>
      {items.length === 0 ? (
        <Text style={styles.weekEmpty}>Chua co lich hen.</Text>
      ) : (
        items.slice(0, 3).map((item) => (
          <View key={`${item.id}-${item.start_time}`} style={styles.weekItem}>
            <Text style={styles.weekItemTime}>{formatShortDate(item.start_time)}</Text>
            <Text style={styles.weekItemTitle} numberOfLines={2}>{item.title || 'Su kien'}</Text>
          </View>
        ))
      )}
      {items.length > 3 ? (
        <Text style={styles.weekMore}>+{items.length - 3} lich khac</Text>
      ) : null}
    </View>
  );

  const renderCreate = () => (
    <Card>
      <Field label="Tieu de"          value={form.title}            onChangeText={(v) => setField('title', v)}            placeholder="Hop phu huynh" />
      <Field label="Mo ta"             value={form.description}      onChangeText={(v) => setField('description', v)}      placeholder="Noi dung lich hen" multiline />
      <Field label="Bat dau"           value={form.start_time}       onChangeText={(v) => setField('start_time', v)}       placeholder="2026-06-05T09:00:00" />
      <Field label="Ket thuc"          value={form.end_time}         onChangeText={(v) => setField('end_time', v)}         placeholder="2026-06-05T10:00:00" />
      <Field label="Thoi luong phut"   value={form.duration_minutes} onChangeText={(v) => setField('duration_minutes', v)} placeholder="60" keyboardType="number-pad" />
      <Field label="Dia diem"          value={form.location}         onChangeText={(v) => setField('location', v)}         placeholder="Phong hop / online" />
      <Field label="Nguoi tham du"     value={form.attendees}        onChangeText={(v) => setField('attendees', v)}        placeholder="a@example.com, b@example.com" />
      <Button title="Tao lich hen" onPress={createSchedule} loading={loading} />
    </Card>
  );

  return (
    <>
      <Screen
        title="Lich"
        refreshing={loading}
        onRefresh={loadSchedules}
        actions={<Button title={calendarConnected ? 'Da ket noi Google' : 'Ket noi Google'} variant="secondary" onPress={() => Linking.openURL('https://calendar.google.com')} />}
      >
        <SegmentedControl options={modes} value={mode} onChange={setMode} />
        {mode === 'create' ? renderCreate() : renderList()}
      </Screen>
      <Modal visible={!!editingSchedule} animationType="slide" onRequestClose={() => setEditingSchedule(null)}>
        <Screen title="Sua lich hen" actions={<Button title="Dong" variant="secondary" onPress={() => setEditingSchedule(null)} />}>
          <Card>
            <Field label="Tieu de"          value={editForm.title}            onChangeText={(v) => setEditField('title', v)}            placeholder="Hop phu huynh" />
            <Field label="Mo ta"             value={editForm.description}      onChangeText={(v) => setEditField('description', v)}      placeholder="Noi dung lich hen" multiline />
            <Field label="Bat dau"           value={editForm.start_time}       onChangeText={(v) => setEditField('start_time', v)}       placeholder="2026-06-05T09:00:00" />
            <Field label="Ket thuc"          value={editForm.end_time}         onChangeText={(v) => setEditField('end_time', v)}         placeholder="2026-06-05T10:00:00" />
            <Field label="Thoi luong phut"   value={editForm.duration_minutes} onChangeText={(v) => setEditField('duration_minutes', v)} placeholder="60" keyboardType="number-pad" />
            <Field label="Dia diem"          value={editForm.location}         onChangeText={(v) => setEditField('location', v)}         placeholder="Phong hop / online" />
            <Field label="Nguoi tham du"     value={editForm.attendees}        onChangeText={(v) => setEditField('attendees', v)}        placeholder="a@example.com, b@example.com" />
            <Button title="Luu thay doi" onPress={updateSchedule} loading={loading} />
          </Card>
        </Screen>
      </Modal>
    </>
  );
}

function splitAttendees(value) {
  return (value || '').split(',').map((item) => item.trim()).filter(Boolean);
}

function getMonday(date) {
  const d = new Date(date);
  const day = d.getDay();
  const diff = (day === 0 ? -6 : 1) - day;
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatDateForApi(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function flattenWeekSchedules(days) {
  return (days || [])
    .flatMap((dayEvents) => Array.isArray(dayEvents) ? dayEvents : [])
    .filter((schedule) => schedule && schedule.start_time)
    .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
}

function sourceLabel(source) {
  if (source === 'synced') return 'Da dong bo';
  if (source === 'google') return 'Google';
  return 'FlowMate';
}

function formatDate(value) {
  if (!value) return '';
  const raw = typeof value === 'string' ? value : value.dateTime || value.date || '';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString('vi-VN');
}

function formatShortDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('vi-VN', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatWeekRange(startValue) {
  const start = getMonday(startValue);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${start.toLocaleDateString('vi-VN')} - ${end.toLocaleDateString('vi-VN')}`;
}

function addMinutesIso(value, minutes) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  date.setMinutes(date.getMinutes() + minutes);
  return normalizeDateTime(date);
}

function normalizeDateTime(value) {
  if (!value) return '';
  const raw = typeof value === 'string' ? value : value.dateTime || value.date || '';
  if (!raw) return '';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const hh = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}T${hh}:${min}:00`;
}

function durationMinutes(startValue, endValue) {
  if (!startValue || !endValue) return null;
  const start = new Date(startValue);
  const end = new Date(endValue);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  const diff = Math.round((end.getTime() - start.getTime()) / 60000);
  return diff > 0 ? diff : null;
}

function makeStyles(colors) {
  return StyleSheet.create({
    title: { color: colors.text, fontWeight: '800', fontSize: 16, lineHeight: 22 },
    cardHeader: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
    source: { overflow: 'hidden', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4, fontSize: 11, fontWeight: '800' },
    sourceSynced: { color: colors.success, backgroundColor: `${colors.success}18` },
    sourceDefault: { color: colors.primary, backgroundColor: `${colors.primary}18` },
    time:  { marginTop: 6, color: colors.primary, fontWeight: '700' },
    description: { marginTop: 8,  color: colors.textMuted, lineHeight: 20 },
    meta:        { marginTop: 6,  color: colors.textMuted },
    actions:     { marginTop: 12, flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
    summaryCard: { gap: 12 },
    suggestionCard: { gap: 12 },
    summaryHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
    summaryKicker: { color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' },
    summaryTitle: { marginTop: 3, color: colors.text, fontSize: 16, fontWeight: '800' },
    summaryTotal: {
      minWidth: 42,
      paddingHorizontal: 10,
      paddingVertical: 7,
      overflow: 'hidden',
      borderRadius: 12,
      backgroundColor: `${colors.primary}14`,
      color: colors.primary,
      textAlign: 'center',
      fontWeight: '900',
      fontSize: 18,
    },
    weekNav: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
    weekGrid: { gap: 10 },
    weekSummary: {
      padding: 12,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: 14,
      backgroundColor: colors.panelSoft,
    },
    weekSummaryHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
    weekTitle: { color: colors.text, fontSize: 14, fontWeight: '800' },
    weekCount: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
    weekEmpty: { marginTop: 8, color: colors.textMuted, fontSize: 13 },
    weekItem: { marginTop: 10, paddingLeft: 10, borderLeftWidth: 3, borderLeftColor: colors.primary },
    weekItemTime: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
    weekItemTitle: { marginTop: 2, color: colors.text, fontSize: 13, fontWeight: '800', lineHeight: 18 },
    weekMore: { marginTop: 10, color: colors.textMuted, fontSize: 12, fontWeight: '700' },
    suggestionItem: {
      paddingTop: 12,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    previewText: { marginTop: 7, color: colors.textMuted, lineHeight: 19 },
  });
}
