import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Linking, Modal, StyleSheet, Text, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import DateTimeField from '../components/DateTimeField';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import SegmentedControl from '../components/SegmentedControl';
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '../api/client';
import { useTheme } from '../theme/ThemeContext';
import { filterNewMeetingSuggestions, setPendingAgentNotice } from '../state/agentNotices';

const modes = [
  { label: 'Lịch tổng hợp', value: 'list' },
  { label: 'Tạo mới',        value: 'create' },
];

const initialForm = {
  title: '', description: '', start_time: '', end_time: '',
  duration_minutes: '60', location: '', attendees: '',
};

export default function ScheduleScreen({ onAgentSync, syncEvent }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [mode, setMode] = useState('list');
  const [currentWeekStart, setCurrentWeekStart] = useState(() => getMonday(new Date()));
  const [schedules, setSchedules] = useState([]);
  const [weekSummary, setWeekSummary] = useState({ current: [], next: [] });
  const [meetingSuggestions, setMeetingSuggestions] = useState([]);
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [connectedCalendars, setConnectedCalendars] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const [editForm, setEditForm] = useState(initialForm);
  const [loading, setLoading] = useState(false);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const loadSchedules = useCallback(async (options = {}) => {
    setLoading(true);
    try {
      if (options.syncGoogle) {
        try {
          await apiPost('/schedule/sync');
        } catch (error) {
          if (error.status !== 401 && !options.silentSync) {
            throw error;
          }
        }
      }

      const nextWeekStart = new Date(currentWeekStart);
      nextWeekStart.setDate(nextWeekStart.getDate() + 7);

      const [data, currentWeek, nextWeek] = await Promise.all([
        apiGet('/schedule/unified?max_results=50&live=0'),
        apiGet(`/schedule/week?start=${formatDateForApi(currentWeekStart)}&sync=0`),
        apiGet(`/schedule/week?start=${formatDateForApi(nextWeekStart)}&sync=0`),
      ]);

      setSchedules(data.items || []);
      const nextConnectedCalendars = [];
      if (data.calendar_connected || data.google_calendar_connected) nextConnectedCalendars.push('Google');
      if (data.outlook_calendar_connected) nextConnectedCalendars.push('Outlook');
      setConnectedCalendars(nextConnectedCalendars);
      setCalendarConnected(nextConnectedCalendars.length > 0);
      setWeekSummary({
        current: flattenWeekSchedules(currentWeek.days),
        next: flattenWeekSchedules(nextWeek.days),
      });
    } catch (error) {
      Alert.alert('Lỗi tải lịch', error.message);
    } finally {
      setLoading(false);
    }
  }, [currentWeekStart]);

  const loadMeetingSuggestions = useCallback(async () => {
    setSuggestionsLoading(true);
    try {
      const data = await apiGet('/email/meeting-suggestions');
      const suggestions = data.suggestions || [];
      setMeetingSuggestions(suggestions);
      notifyNewMeetingSuggestions(suggestions);
    } catch (error) {
      if (error.status !== 401) Alert.alert('Lỗi tải gợi ý lịch', error.message);
    } finally {
      setSuggestionsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSchedules();
  }, [loadSchedules]);
  useEffect(() => { loadMeetingSuggestions(); }, [loadMeetingSuggestions]);
  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['schedule', 'calendar'])) {
      loadSchedules({
        syncGoogle: hasSyncTarget(syncEvent, ['calendar']),
        silentSync: true,
      });
    }
    if (hasSyncTarget(syncEvent, ['email'])) {
      loadMeetingSuggestions();
    }
  }, [loadMeetingSuggestions, loadSchedules, syncEvent]);

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const setEditField = (key, value) => setEditForm((current) => ({ ...current, [key]: value }));

  const createSchedule = async () => {
    if (!form.title || !form.start_time) {
      Alert.alert('Thiếu thông tin', 'Vui lòng nhập tiêu đề và thời gian bắt đầu.');
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
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history']);
      Alert.alert('Đã tạo lịch');
    } catch (error) {
      Alert.alert('Không tạo được lịch', error.message);
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (schedule, status) => {
    try {
      await apiPatch(`/schedule/${schedule.local_id}/update-status`, { status });
      await loadSchedules();
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history']);
    } catch (error) {
      Alert.alert('Không cập nhật được lịch', error.message);
    }
  };

  const scanMeetingSuggestions = async () => {
    setSuggestionsLoading(true);
    try {
      const data = await apiPost('/email/meeting-suggestions/scan');
      const suggestions = data.suggestions || [];
      setMeetingSuggestions(suggestions);
      notifyNewMeetingSuggestions(suggestions);
      onAgentSync?.(['email', 'schedule', 'overview']);
      Alert.alert('Đã quét email', `Tìm thấy ${data.count || 0} gợi ý lịch đang chờ.`);
    } catch (error) {
      Alert.alert('Không quét được email', error.message);
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
    onAgentSync?.(['email', 'schedule', 'overview', 'history']);
  };

  const createScheduleFromSuggestion = async (suggestion) => {
    if (!suggestion.start_time) {
      setForm({
        title: suggestion.title || suggestion.subject || 'Lịch hẹn từ email',
        description: suggestion.description || suggestion.snippet || '',
        start_time: '',
        end_time: '',
        duration_minutes: '60',
        location: suggestion.location || '',
        attendees: suggestion.attendees || '',
      });
      setMode('create');
      Alert.alert('Cần bổ sung thời gian', 'Gợi ý này chưa có giờ bắt đầu, hãy nhập thời gian để tạo lịch.');
      return;
    }

    setLoading(true);
    try {
      const data = await apiPost('/schedule/create', {
        title: suggestion.title || suggestion.subject || 'Lịch hẹn từ email',
        description: suggestion.description || suggestion.snippet || '',
        start_time: normalizeDateTime(suggestion.start_time),
        end_time: normalizeDateTime(suggestion.end_time) || addMinutesIso(suggestion.start_time, 60),
        duration_minutes: durationMinutes(suggestion.start_time, suggestion.end_time) || 60,
        location: suggestion.location || '',
        attendees: splitAttendees(suggestion.attendees || ''),
      });
      await updateMeetingSuggestionStatus(suggestion.id, 'created', data.schedule_id);
      await loadSchedules();
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history']);
      Alert.alert('Đã tạo lịch từ email');
    } catch (error) {
      Alert.alert('Không tạo được lịch', error.message);
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
      Alert.alert('Thiếu thông tin', 'Vui lòng nhập tiêu đề và thời gian bắt đầu.');
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
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history']);
      Alert.alert('Đã cập nhật lịch');
    } catch (error) {
      Alert.alert('Không cập nhật được lịch', error.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteSchedule = async (schedule) => {
    try {
      await apiDelete(`/schedule/${schedule.local_id}`);
      await loadSchedules();
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history']);
      return true;
    } catch (error) {
      Alert.alert('Không xóa được lịch', error.message);
    }
    return false;
  };

  const deleteEditingSchedule = async () => {
    if (!editingSchedule) return;
    const deleted = await deleteSchedule(editingSchedule);
    if (deleted) {
      setEditingSchedule(null);
      setEditForm(initialForm);
    }
  };

  const deleteEvent = async (event) => {
    try {
      await apiDelete(`/calendar/delete/${event.google_event_id}`);
      await loadSchedules();
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history']);
    } catch (error) {
      Alert.alert('Không xóa được sự kiện', error.message);
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
            <Text style={styles.summaryKicker}>Tổng hợp lịch hẹn</Text>
            <Text style={styles.summaryTitle}>{formatWeekRange(currentWeekStart)}</Text>
          </View>
          <Text style={styles.summaryTotal}>{weekSummary.current.length + weekSummary.next.length}</Text>
        </View>
        <View style={styles.weekNav}>
          <Button title="Tuần trước" variant="secondary" onPress={() => shiftWeek(-1)} />
          <Button title="Tuần này" variant="secondary" onPress={() => setCurrentWeekStart(getMonday(new Date()))} />
          <Button title="Tuần sau" variant="secondary" onPress={() => shiftWeek(1)} />
        </View>
        <View style={styles.weekGrid}>
          {renderWeekSummary('Tuần đang xem', weekSummary.current)}
          {renderWeekSummary('Tuần kế tiếp', weekSummary.next)}
        </View>
      </Card>

      <Card style={styles.suggestionCard}>
        <View style={styles.summaryHeader}>
          <View>
            <Text style={styles.summaryKicker}>Gợi ý từ email</Text>
            <Text style={styles.summaryTitle}>Cuộc họp và lịch hẹn phát hiện</Text>
          </View>
          <Text style={styles.summaryTotal}>{meetingSuggestions.length}</Text>
        </View>
        <View style={styles.weekNav}>
          <Button title="Quét email" variant="secondary" onPress={scanMeetingSuggestions} loading={suggestionsLoading} />
          <Button title="Làm mới" variant="secondary" onPress={loadMeetingSuggestions} loading={suggestionsLoading} />
        </View>
        {meetingSuggestions.length === 0 ? (
          <Text style={styles.weekEmpty}>Chưa có gợi ý lịch mới.</Text>
        ) : (
          meetingSuggestions.map((suggestion) => (
            <View key={suggestion.id} style={styles.suggestionItem}>
              <Text style={styles.weekItemTitle}>{suggestion.title || suggestion.subject || 'Lịch hẹn từ email'}</Text>
              <Text style={styles.weekItemTime}>Từ: {suggestion.sender || 'Không xác định'}</Text>
              <Text style={styles.previewText} numberOfLines={3}>{suggestion.snippet || suggestion.description || ''}</Text>
              <Text style={styles.weekItemTime}>{suggestion.start_time ? formatShortDate(suggestion.start_time) : 'Chưa xác định thời gian'}</Text>
              <View style={styles.actions}>
                <Button title="Tạo lịch" onPress={() => createScheduleFromSuggestion(suggestion)} />
                <Button title="Bỏ qua" variant="secondary" onPress={() => updateMeetingSuggestionStatus(suggestion.id, 'dismissed')} />
              </View>
            </View>
          ))
        )}
      </Card>

      {schedules.length === 0 ? (
        <EmptyState title="Chưa có lịch sắp tới" detail="Tạo lịch mới hoặc kết nối Google/Outlook để đồng bộ lịch." />
      ) : (
        schedules.map((schedule) => (
          <Card key={schedule.id}>
            <View style={styles.cardHeader}>
              <Text style={styles.title}>{schedule.title}</Text>
              <Text style={[
                styles.source,
                sourceStyle(schedule, styles),
              ]}>
                {sourceLabel(schedule)}
              </Text>
            </View>
            <Text style={styles.time}>
              {formatDate(schedule.start_time)}
              {schedule.end_time ? ` - ${formatDate(schedule.end_time)}` : ''}
            </Text>
            {schedule.description ? <Text style={styles.description}>{schedule.description}</Text> : null}
            {schedule.location   ? <Text style={styles.meta}>Địa điểm: {schedule.location}</Text>  : null}
            {schedule.attendees  ? <Text style={styles.meta}>Tham dự: {schedule.attendees}</Text>   : null}
            <View style={styles.actions}>
              {schedule.local_id ? (
                <>
                  <Button title="Hoàn tất" variant="secondary" onPress={() => updateStatus(schedule, 'completed')} />
                  <Button title="Sửa" variant="secondary" onPress={() => openEditSchedule(schedule)} />
                  <Button title="Hủy" variant="secondary" onPress={() => updateStatus(schedule, 'cancelled')} />
                  <Button title="Xóa" variant="danger" onPress={() => deleteSchedule(schedule)} />
                </>
              ) : schedule.google_event_id ? (
                <Button title="Xóa khỏi Google" variant="danger" onPress={() => deleteEvent(schedule)} />
              ) : schedule.html_link || schedule.web_link ? (
                <Button title="Mở lịch" variant="secondary" onPress={() => Linking.openURL(schedule.html_link || schedule.web_link)} />
              ) : null}
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
        <Text style={styles.weekCount}>{items.length} lịch</Text>
      </View>
      {items.length === 0 ? (
        <Text style={styles.weekEmpty}>Chưa có lịch hẹn.</Text>
      ) : (
        items.slice(0, 3).map((item) => (
          <View key={`${item.id}-${item.start_time}`} style={styles.weekItem}>
            <Text style={styles.weekItemTime}>{formatShortDate(item.start_time)}</Text>
            <Text style={styles.weekItemTitle} numberOfLines={2}>{item.title || 'Sự kiện'}</Text>
          </View>
        ))
      )}
      {items.length > 3 ? (
        <Text style={styles.weekMore}>+{items.length - 3} lịch khác</Text>
      ) : null}
    </View>
  );

  const renderCreate = () => (
    <Card>
      <Field label="Tiêu đề"         value={form.title}            onChangeText={(v) => setField('title', v)}            placeholder="Họp phụ huynh" />
      <Field label="Mô tả"            value={form.description}      onChangeText={(v) => setField('description', v)}      placeholder="Nội dung lịch hẹn" multiline />
      <DateTimeField label="Bắt đầu" value={form.start_time} onChange={(v) => setField('start_time', v)} placeholder="2026-06-05T09:00:00" />
      <DateTimeField label="Kết thúc" value={form.end_time} onChange={(v) => setField('end_time', v)} placeholder="2026-06-05T10:00:00" />
      <Field label="Thời lượng (phút)" value={form.duration_minutes} onChangeText={(v) => setField('duration_minutes', v)} placeholder="60" keyboardType="number-pad" />
      <Field label="Địa điểm"         value={form.location}         onChangeText={(v) => setField('location', v)}         placeholder="Phòng họp / online" />
      <Field label="Người tham dự"    value={form.attendees}        onChangeText={(v) => setField('attendees', v)}        placeholder="a@example.com, b@example.com" />
      <Button title="Tạo lịch hẹn" onPress={createSchedule} loading={loading} />
    </Card>
  );

  return (
    <>
      <Screen
        title="Lịch"
        refreshing={loading}
        onRefresh={() => loadSchedules({ syncGoogle: true })}
        actions={
          <>
            <Button title="Cập nhật" variant="secondary" onPress={() => loadSchedules({ syncGoogle: true })} loading={loading} />
            <Button
              title={calendarConnected ? `Đã kết nối ${connectedCalendars.join(' + ')}` : 'Kết nối lịch'}
              variant="secondary"
              onPress={() => Linking.openURL('https://calendar.google.com')}
            />
          </>
        }
      >
        <SegmentedControl options={modes} value={mode} onChange={setMode} />
        {mode === 'create' ? renderCreate() : renderList()}
      </Screen>
      <Modal visible={!!editingSchedule} animationType="slide" onRequestClose={() => setEditingSchedule(null)}>
        <Screen title="Sửa lịch hẹn" actions={<Button title="Đóng" variant="secondary" onPress={() => setEditingSchedule(null)} />}>
          <Card>
            <Field label="Tiêu đề"         value={editForm.title}            onChangeText={(v) => setEditField('title', v)}            placeholder="Họp phụ huynh" />
            <Field label="Mô tả"            value={editForm.description}      onChangeText={(v) => setEditField('description', v)}      placeholder="Nội dung lịch hẹn" multiline />
            <DateTimeField label="Bắt đầu" value={editForm.start_time} onChange={(v) => setEditField('start_time', v)} placeholder="2026-06-05T09:00:00" />
            <DateTimeField label="Kết thúc" value={editForm.end_time} onChange={(v) => setEditField('end_time', v)} placeholder="2026-06-05T10:00:00" />
            <Field label="Thời lượng (phút)" value={editForm.duration_minutes} onChangeText={(v) => setEditField('duration_minutes', v)} placeholder="60" keyboardType="number-pad" />
            <Field label="Địa điểm"         value={editForm.location}         onChangeText={(v) => setEditField('location', v)}         placeholder="Phòng họp / online" />
            <Field label="Người tham dự"    value={editForm.attendees}        onChangeText={(v) => setEditField('attendees', v)}        placeholder="a@example.com, b@example.com" />
            <View style={styles.editActions}>
              <Button title="Xóa lịch hẹn" variant="danger" onPress={deleteEditingSchedule} loading={loading} />
              <Button title="Lưu thay đổi" onPress={updateSchedule} loading={loading} />
            </View>
          </Card>
        </Screen>
      </Modal>
    </>
  );
}

function notifyNewMeetingSuggestions(suggestions) {
  const fresh = filterNewMeetingSuggestions(suggestions);
  if (!fresh.length) return;
  const first = fresh[0] || {};
  const title = first.title || first.subject || 'một email liên quan đến cuộc họp';
  const extra = fresh.length > 1 ? ` và ${fresh.length - 1} email khác` : '';
  setPendingAgentNotice(
    `AI Agent phát hiện ${fresh.length} email có thể liên quan đến lịch họp: "${title}"${extra}. Mở tab Lịch để tạo lịch hoặc bỏ qua.`
  );
}

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
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
  return dedupeSchedules((days || [])
    .flatMap((dayEvents) => Array.isArray(dayEvents) ? dayEvents : [])
    .filter((schedule) => schedule && schedule.start_time))
    .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
}

function scheduleFingerprint(schedule) {
  const title = String(schedule?.title || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const start = new Date(schedule?.start_time || '');
  const startKey = Number.isNaN(start.getTime())
    ? String(schedule?.start_time || '')
    : start.toISOString().slice(0, 16);
  return `${title}|${startKey}`;
}

function dedupeSchedules(schedules = []) {
  const byGoogleId = new Map();
  const byFingerprint = new Map();
  const result = [];
  const priority = (schedule) => (
    schedule?.calendar_event_id || schedule?.google_event_id || schedule?.source === 'synced'
      ? 2
      : schedule?.source === 'google' ? 1 : 0
  );

  schedules.forEach((schedule) => {
    if (!schedule) return;
    const googleId = schedule.calendar_event_id || schedule.google_event_id || '';
    const fingerprint = scheduleFingerprint(schedule);
    const existing = (googleId && byGoogleId.get(googleId)) || byFingerprint.get(fingerprint);
    if (!existing) {
      result.push(schedule);
      if (googleId) byGoogleId.set(googleId, schedule);
      byFingerprint.set(fingerprint, schedule);
      return;
    }

    if (priority(schedule) > priority(existing)) {
      const index = result.indexOf(existing);
      if (index >= 0) result[index] = schedule;
      if (googleId) byGoogleId.set(googleId, schedule);
      byFingerprint.set(fingerprint, schedule);
    }
  });

  return result;
}

function scheduleProvider(schedule) {
  return schedule?.provider || schedule?.source || '';
}

function sourceLabel(schedule) {
  const provider = scheduleProvider(schedule);
  if (provider === 'outlook' || provider === 'microsoft') return 'Outlook';
  if (schedule?.source === 'synced') return 'Đã đồng bộ';
  if (schedule?.source === 'google' || provider === 'google') return 'Google';
  return 'FlowMate';
}

function sourceStyle(schedule, styles) {
  const provider = scheduleProvider(schedule);
  if (provider === 'outlook' || provider === 'microsoft') return styles.sourceOutlook;
  if (schedule?.source === 'synced') return styles.sourceSynced;
  return styles.sourceDefault;
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
    sourceOutlook: { color: '#0369a1', backgroundColor: 'rgba(14,165,233,0.16)' },
    time:  { marginTop: 6, color: colors.primary, fontWeight: '700' },
    description: { marginTop: 8,  color: colors.textMuted, lineHeight: 20 },
    meta:        { marginTop: 6,  color: colors.textMuted },
    actions:     { marginTop: 12, flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
    editActions: { marginTop: 14, flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
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
