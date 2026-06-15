import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Linking, StyleSheet, Text, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import SegmentedControl from '../components/SegmentedControl';
import { apiDelete, apiGet, apiPatch, apiPost } from '../api/client';
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
  const [schedules, setSchedules] = useState([]);
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(false);

  const loadSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet('/schedule/unified?max_results=50');
      setSchedules(data.items || []);
      setCalendarConnected(Boolean(data.calendar_connected));
    } catch (error) {
      Alert.alert('Loi tai lich', error.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSchedules(); }, [loadSchedules]);

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));

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

  const renderList = () => (
    schedules.length === 0 ? (
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
                <Button title="Huy" variant="secondary" onPress={() => updateStatus(schedule, 'cancelled')} />
                <Button title="Xoa" variant="danger" onPress={() => deleteSchedule(schedule)} />
              </>
            ) : (
              <Button title="Xoa khoi Google" variant="danger" onPress={() => deleteEvent(schedule)} />
            )}
          </View>
        </Card>
      ))
    )
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
    <Screen
      title="Lich"
      refreshing={loading}
      onRefresh={loadSchedules}
      actions={<Button title={calendarConnected ? 'Da ket noi Google' : 'Ket noi Google'} variant="secondary" onPress={() => Linking.openURL('https://calendar.google.com')} />}
    >
      <SegmentedControl options={modes} value={mode} onChange={setMode} />
      {mode === 'create' ? renderCreate() : renderList()}
    </Screen>
  );
}

function splitAttendees(value) {
  return (value || '').split(',').map((item) => item.trim()).filter(Boolean);
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
  });
}
