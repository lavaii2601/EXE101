import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import { apiGet, apiPost } from '../api/client';
import { useTheme } from '../theme/ThemeContext';

export default function OverviewScreen() {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [date, setDate] = useState(() => formatDateForApi(new Date()));
  const [emails, setEmails] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [emailError, setEmailError] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setEmailError('');
    try {
      const reportDate = formatReportDate(date);
      const [scheduleResult, emailResult] = await Promise.allSettled([
        apiGet('/schedule/unified?max_results=100&live=0'),
        apiPost('/email/summarize-by-date', { date: reportDate, max_results: 50 }),
      ]);

      if (scheduleResult.status === 'fulfilled') {
        setSchedules(dedupeSchedules(scheduleResult.value.items || [])
          .filter((item) => isSameDay(item.start_time, date))
          .sort((a, b) => new Date(a.start_time) - new Date(b.start_time)));
      } else {
        setSchedules([]);
      }

      if (emailResult.status === 'fulfilled') {
        setEmails(emailResult.value.rows || []);
      } else {
        setEmails([]);
        setEmailError(emailResult.reason?.status === 401
          ? 'Cần đăng nhập Gmail để tổng hợp email.'
          : (emailResult.reason?.message || 'Không tải được email trong ngày.'));
      }
    } catch (error) {
      Alert.alert('Không tổng hợp được dữ liệu', error.message);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const deadlines = schedules.filter((item) => priorityLabel(item) === 'Deadline');
  const openTasks = schedules.filter((item) => item.status !== 'completed');
  const meetingEmails = emails.filter((item) => item.is_meeting);
  const insight = buildInsight({ emails, schedules, date });
  const sourceText = buildSourceText({ emails, schedules });

  return (
    <Screen
      title="Tổng hợp"
      refreshing={loading}
      onRefresh={loadOverview}
      actions={<Button title="Tổng hợp lại" variant="secondary" onPress={loadOverview} loading={loading} />}
    >
      <Card style={styles.heroCard}>
        <Text style={styles.kicker}>FLOWMATE AI</Text>
        <Text style={styles.heroTitle}>{formatReportDate(date)}</Text>
        <Text style={styles.heroText}>{insight}</Text>
        <Text style={styles.sourceText}>{sourceText}</Text>
      </Card>

      <Card style={styles.dateCard}>
        <Field
          label="Ngày cần tổng hợp"
          value={date}
          onChangeText={setDate}
          placeholder="2026-06-26"
        />
        <Button title="Xem ngày này" onPress={loadOverview} loading={loading} />
      </Card>

      <View style={styles.statsGrid}>
        <StatCard label="Deadline" value={deadlines.length} styles={styles} />
        <StatCard label="Email" value={emails.length} styles={styles} />
        <StatCard label="Task mở" value={openTasks.length} styles={styles} />
        <StatCard label="Mail họp" value={meetingEmails.length} styles={styles} />
      </View>

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
  return StyleSheet.create({
    heroCard: {
      gap: 6,
      backgroundColor: colors.primarySoft,
      borderColor: `${colors.primary}33`,
    },
    kicker: {
      color: colors.primary,
      fontSize: 10,
      fontWeight: '900',
      letterSpacing: 1,
      textTransform: 'uppercase',
    },
    heroTitle: { color: colors.text, fontSize: 22, fontWeight: '900' },
    heroText: { color: colors.textMuted, lineHeight: 21 },
    sourceText: { marginTop: 4, color: colors.textMuted, fontSize: 12, fontWeight: '800' },
    dateCard: { gap: 10 },
    statsGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 10,
    },
    statCard: {
      flexGrow: 1,
      flexBasis: '46%',
      minHeight: 76,
      justifyContent: 'center',
    },
    statValue: { color: colors.text, fontSize: 24, fontWeight: '900' },
    statLabel: { marginTop: 3, color: colors.textMuted, fontWeight: '800' },
    sectionHeader: { marginBottom: 4 },
    sectionTitle: { marginTop: 2, color: colors.text, fontSize: 16, fontWeight: '900' },
    item: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 10,
      paddingVertical: 12,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    itemIndex: {
      width: 28,
      height: 28,
      overflow: 'hidden',
      borderRadius: 8,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: `${colors.primary}18`,
    },
    itemIndexText: { color: colors.primary, fontSize: 12, fontWeight: '900' },
    itemBody: { flex: 1, minWidth: 0 },
    itemTitle: { color: colors.text, fontWeight: '900', lineHeight: 20 },
    itemMeta: { marginTop: 3, color: colors.textMuted, fontSize: 12, fontWeight: '700' },
    itemPreview: { marginTop: 6, color: colors.textMuted, lineHeight: 19 },
    chip: {
      overflow: 'hidden',
      borderRadius: 999,
      paddingHorizontal: 8,
      paddingVertical: 4,
      backgroundColor: 'rgba(13,148,136,0.13)',
      color: '#0f766e',
      fontSize: 10,
      fontWeight: '900',
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
      fontWeight: '700',
    },
  });
}
