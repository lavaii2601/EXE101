import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Linking, Modal, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import SegmentedControl from '../components/SegmentedControl';
import { apiGet, apiPost } from '../api/client';
import { setMobileUserId } from '../api/session';
import { useTheme } from '../theme/ThemeContext';
import ModeBrief from '../components/ModeBrief';

const filters = [
  { label: 'Tat ca',   value: 'all' },
  { label: 'Giao duc', value: 'education' },
  { label: 'Cong viec',value: 'work' },
  { label: 'Hop',      value: 'meeting' },
  { label: 'Ca nhan',  value: 'personal' },
];

const modes = [
  { label: 'Hop thu', value: 'inbox' },
  { label: 'Bao cao', value: 'report' },
  { label: 'Soan thu',value: 'compose' },
];

export default function EmailScreen({ onAuthChanged, userMode = 'worker' }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [mode, setMode] = useState('inbox');
  const [filter, setFilter] = useState('all');
  const [includeRead, setIncludeRead] = useState(true);
  const [emails, setEmails] = useState([]);
  const [auth, setAuth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [emailBody, setEmailBody] = useState('');
  const [summary, setSummary] = useState('');
  const [compose, setCompose] = useState({ to: '', subject: '', body: '' });
  const [reportDate, setReportDate] = useState('');
  const [report, setReport] = useState(null);
  const [userIdInput, setUserIdInput] = useState('');
  const [summarizingId, setSummarizingId] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');

  const loadAuth = useCallback(async () => {
    try {
      const data = await apiGet('/email/auth-status');
      setAuth(data);
      return data;
    } catch {
      setAuth({ authenticated: false });
      return { authenticated: false };
    }
  }, []);

  const loadEmails = useCallback(async () => {
    setLoading(true);
    try {
      await loadAuth();
      const data = await apiGet(
        `/email/get-unread?max_results=20&page=1&filter=${filter}&include_read=${includeRead}&search=${encodeURIComponent(searchKeyword)}`
      );
      setEmails(data.emails || []);
    } catch (error) {
      if (error.status === 401) setEmails([]);
      else Alert.alert('Loi tai email', error.message);
    } finally {
      setLoading(false);
    }
  }, [filter, includeRead, loadAuth, searchKeyword]);

  useEffect(() => { loadEmails(); }, [loadEmails]);
  useEffect(() => {
    const timer = setTimeout(() => setSearchKeyword(searchInput.trim()), 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const login = async () => {
    try {
      const data = await apiGet('/email/auth_url');
      if (data.auth_url) {
        await WebBrowser.openBrowserAsync(data.auth_url);
        await loadAuth();
        onAuthChanged?.();
      }
    } catch (error) {
      Alert.alert('Khong mo duoc Gmail OAuth', error.message);
    }
  };

  const applyMobileUser = async () => {
    setMobileUserId(userIdInput);
    await loadEmails();
    onAuthChanged?.();
  };

  const logout = async () => {
    try {
      await apiPost('/email/logout');
      setAuth({ authenticated: false });
      setEmails([]);
      onAuthChanged?.();
    } catch (error) {
      Alert.alert('Khong dang xuat duoc', error.message);
    }
  };

  const openEmail = async (email) => {
    setSelectedEmail(email);
    setEmailBody('');
    setSummary(email.summary || '');
    try {
      const data = await apiGet(`/email/get-email-body/${email.id}`);
      setEmailBody(data.body || '');
    } catch (error) {
      setEmailBody(error.message);
    }
  };

  const summarizeEmail = async (email) => {
    if (!email?.id) return;
    setSelectedEmail(email);
    setSummarizingId(email.id);
    try {
      const data = await apiPost(`/email/summary/${email.id}`);
      email.summary = data.summary || '';
      setSummary(data.summary || '');
      setEmails((current) => current.map((item) => (
        item.id === email.id ? { ...item, summary: data.summary || '' } : item
      )));
    } catch (error) {
      Alert.alert('Khong tom tat duoc', error.message);
    } finally {
      setSummarizingId('');
    }
  };

  const toggleReadStatus = async (email) => {
    const wasUnread = !!email.is_unread;
    try {
      await apiPost(`/email/${wasUnread ? 'mark-as-read' : 'mark-as-unread'}/${email.id}`);
      setEmails((current) => current.map((item) => (
        item.id === email.id ? { ...item, is_unread: !wasUnread } : item
      )));
      if (selectedEmail?.id === email.id) {
        setSelectedEmail((current) => ({ ...current, is_unread: !wasUnread }));
      }
    } catch (error) {
      Alert.alert('Khong cap nhat duoc email', error.message);
    }
  };

  const sendEmail = async () => {
    if (!compose.to || !compose.subject || !compose.body) {
      Alert.alert('Thieu thong tin', 'Vui long dien nguoi nhan, tieu de va noi dung.');
      return;
    }
    setLoading(true);
    try {
      await apiPost('/email/send-reply', compose);
      setCompose({ to: '', subject: '', body: '' });
      Alert.alert('Da gui email');
    } catch (error) {
      Alert.alert('Khong gui duoc email', error.message);
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async () => {
    if (!reportDate) {
      Alert.alert('Chon ngay', 'Nhap ngay theo dinh dang DD/MM/YYYY.');
      return;
    }
    setLoading(true);
    try {
      const data = await apiPost('/email/summarize-by-date', { date: reportDate, max_results: 50 });
      setReport(data);
    } catch (error) {
      Alert.alert('Khong tao duoc bao cao', error.message);
    } finally {
      setLoading(false);
    }
  };

  const createScheduleFromReport = async (row) => {
    try {
      const start = row.suggested_start_time || buildReportStart(reportDate);
      await apiPost('/schedule/create', {
        title: row.schedule_title || row.subject || 'Lich hen tu email',
        description: row.suggested_description || row.summary || '',
        start_time: start,
        end_time: row.suggested_end_time || '',
        attendees: [],
      });
      Alert.alert('Da tao lich');
    } catch (error) {
      Alert.alert('Khong tao duoc lich', error.message);
    }
  };

  const renderInbox = () => (
    <>
      <Card>
        <Field
          label="Gmail da ket noi tren backend"
          value={userIdInput}
          onChangeText={setUserIdInput}
          placeholder="ten@gmail.com"
          keyboardType="email-address"
        />
        <Button title="Dung tai khoan nay" variant="secondary" onPress={applyMobileUser} style={styles.applyButton} />
        <View style={styles.authRow}>
          <View style={styles.authText}>
            <Text style={styles.cardTitle}>{auth?.authenticated ? 'Gmail da ket noi' : 'Chua ket noi Gmail'}</Text>
            <Text style={styles.muted} numberOfLines={1}>{auth?.gmail_email || 'Dang nhap de doc va gui email.'}</Text>
          </View>
          <Button
            title={auth?.authenticated ? 'Dang xuat' : 'Dang nhap'}
            variant={auth?.authenticated ? 'secondary' : 'primary'}
            onPress={auth?.authenticated ? logout : login}
          />
        </View>
      </Card>
      <Card style={styles.searchCard}>
        <Field
          label="Tim kiem email"
          value={searchInput}
          onChangeText={setSearchInput}
          placeholder="Nguoi gui, tieu de, noi dung..."
        />
        {searchInput ? (
          <Button
            title="Xoa tu khoa"
            variant="secondary"
            onPress={() => {
              setSearchInput('');
              setSearchKeyword('');
            }}
          />
        ) : null}
      </Card>
      <SegmentedControl options={filters} value={filter} onChange={setFilter} />
      <Card>
        <View style={styles.switchRow}>
          <Text style={styles.cardTitle}>Giu email da doc trong hop thu</Text>
          <Switch value={includeRead} onValueChange={setIncludeRead} trackColor={{ false: colors.border, true: colors.primary }} thumbColor="#ffffff" />
        </View>
      </Card>
      {emails.length === 0 ? (
        <EmptyState
          title={auth?.authenticated ? 'Khong tim thay email' : 'Can dang nhap Gmail'}
          detail={searchKeyword ? `Khong co ket qua cho "${searchKeyword}".` : 'Keo xuong de lam moi hoac doi bo loc email.'}
        />
      ) : (
        emails.map((email) => (
          <Card
            key={email.id}
            style={[styles.emailCard, email.is_unread ? styles.emailUnread : styles.emailRead]}
          >
            <TouchableOpacity onPress={() => openEmail(email)} activeOpacity={0.86}>
              <View style={styles.rowBetween}>
                <Text style={styles.subject} numberOfLines={2}>{email.subject || '(Khong tieu de)'}</Text>
                <View style={styles.badges}>
                  <Text style={[styles.readBadge, email.is_unread ? styles.unreadBadge : styles.readBadgeDone]}>
                    {email.is_unread ? 'CHUA DOC' : 'DA DOC'}
                  </Text>
                  <Text style={styles.tag}>{email.tag || 'email'}</Text>
                </View>
              </View>
              <Text style={styles.sender} numberOfLines={1}>{email.sender || email.from || 'Nguoi gui'}</Text>
              {email.summary ? (
                <View style={styles.aiSummary}>
                  <Text style={styles.aiSummaryLabel}>AI TOM TAT</Text>
                  <Text style={styles.preview} numberOfLines={4}>{email.summary}</Text>
                </View>
              ) : (
                <Text style={styles.preview} numberOfLines={3}>{email.snippet || ''}</Text>
              )}
            </TouchableOpacity>
            <View style={styles.inlineActions}>
              <Button title="Xem" variant="secondary" onPress={() => openEmail(email)} />
              <Button
                title={email.summary ? 'Xem tom tat AI' : 'Tom tat AI'}
                onPress={() => email.summary ? openEmail(email) : summarizeEmail(email)}
                loading={summarizingId === email.id}
              />
              <Button
                title={email.is_unread ? 'Danh dau da doc' : 'Danh dau chua doc'}
                variant="secondary"
                onPress={() => toggleReadStatus(email)}
              />
            </View>
          </Card>
        ))
      )}
    </>
  );

  const renderCompose = () => (
    <Card>
      <Field label="Nguoi nhan" value={compose.to}      onChangeText={(to)      => setCompose((c) => ({ ...c, to }))}      placeholder="email@example.com" keyboardType="email-address" />
      <Field label="Tieu de"    value={compose.subject} onChangeText={(subject) => setCompose((c) => ({ ...c, subject }))} placeholder="Tieu de email" />
      <Field label="Noi dung"   value={compose.body}    onChangeText={(body)    => setCompose((c) => ({ ...c, body }))}    placeholder="Noi dung email" multiline />
      <Button title="Gui email" onPress={sendEmail} loading={loading} />
    </Card>
  );

  const renderReport = () => (
    <>
      <Card>
        <Field label="Ngay bao cao" value={reportDate} onChangeText={setReportDate} placeholder="05/06/2026" />
        <Button title="Tao bao cao" onPress={generateReport} loading={loading} />
      </Card>
      {report ? (
        <Card>
          <Text style={styles.cardTitle}>Bao cao ngay {report.date}</Text>
          <Text style={styles.muted}>Tong {report.total_emails || 0} email</Text>
          {(report.rows || []).map((row, index) => (
            <View key={`${row.subject}-${index}`} style={styles.reportRow}>
              <Text style={styles.subject}>{index + 1}. {row.subject || 'Email'}</Text>
              <Text style={styles.preview}>{row.summary || 'Khong co tom tat'}</Text>
              {row.is_meeting
                ? <Button title="Tao lich" variant="secondary" onPress={() => createScheduleFromReport(row)} style={styles.reportButton} />
                : null}
            </View>
          ))}
        </Card>
      ) : null}
    </>
  );

  return (
    <>
      <Screen
        title="Email"
        refreshing={loading}
        onRefresh={loadEmails}
        actions={<Button title="Gmail" variant="secondary" onPress={() => Linking.openURL('https://mail.google.com')} />}
      >
        <ModeBrief
          userMode={userMode}
          stats={[
            { value: emails.length, label: 'Email hien thi' },
            { value: emails.filter((email) => email.is_unread).length, label: 'Chua doc' },
            { value: emails.filter((email) => email.tag === 'meeting').length, label: 'Cuoc hop' },
          ]}
        />
        <SegmentedControl options={modes} value={mode} onChange={setMode} />
        {mode === 'compose' ? renderCompose() : mode === 'report' ? renderReport() : renderInbox()}
      </Screen>
      <Modal visible={!!selectedEmail} animationType="slide" onRequestClose={() => setSelectedEmail(null)}>
        <Screen title="Chi tiet email" actions={<Button title="Dong" variant="secondary" onPress={() => setSelectedEmail(null)} />}>
          {selectedEmail ? (
            <Card>
              <Text style={styles.subject}>{selectedEmail.subject || '(Khong tieu de)'}</Text>
              <Text style={styles.sender}>{selectedEmail.sender || selectedEmail.from || ''}</Text>
              <Text style={styles.body}>{emailBody || selectedEmail.snippet || 'Dang tai...'}</Text>
              {summary ? <Text style={styles.summary}>{summary}</Text> : null}
              <Button
                title={summary ? 'Tom tat lai bang AI' : 'Tom tat bang AI'}
                onPress={() => summarizeEmail(selectedEmail)}
                loading={summarizingId === selectedEmail.id}
                style={styles.detailButton}
              />
            </Card>
          ) : null}
        </Screen>
      </Modal>
    </>
  );
}

function buildReportStart(reportDate) {
  const [dd, mm, yyyy] = reportDate.split('/');
  if (!dd || !mm || !yyyy) return new Date().toISOString();
  return `${yyyy}-${mm}-${dd}T09:00:00`;
}

function makeStyles(colors) {
  return StyleSheet.create({
    authRow:  { flexDirection: 'row', alignItems: 'center', gap: 10 },
    authText: { flex: 1, minWidth: 0 },
    searchCard: { gap: 2 },
    cardTitle:{ color: colors.text, fontWeight: '800' },
    muted:    { marginTop: 4, color: colors.textMuted },
    switchRow:{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    emailCard: { borderLeftWidth: 4 },
    emailUnread: {
      borderLeftColor: colors.primary,
      backgroundColor: colors.primarySoft,
    },
    emailRead: {
      borderLeftColor: '#0d9488',
      borderColor: 'rgba(13,148,136,0.45)',
      backgroundColor: 'rgba(13,148,136,0.10)',
    },
    rowBetween:{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
    badges: { alignItems: 'flex-end', gap: 5 },
    readBadge: {
      paddingHorizontal: 7,
      paddingVertical: 3,
      borderRadius: 999,
      fontSize: 9,
      fontWeight: '900',
    },
    unreadBadge: { color: colors.accentText, backgroundColor: colors.primarySoft },
    readBadgeDone: { color: '#5eead4', backgroundColor: 'rgba(13,148,136,0.22)' },
    subject:  { flex: 1, color: colors.text, fontWeight: '800', lineHeight: 21 },
    tag:      { color: colors.primary, fontSize: 12, fontWeight: '800' },
    sender:   { marginTop: 6, color: colors.textMuted },
    preview:  { marginTop: 8, color: colors.textMuted, lineHeight: 20 },
    aiSummary: {
      marginTop: 10,
      padding: 11,
      borderRadius: 12,
      borderLeftWidth: 3,
      borderLeftColor: colors.primary,
      backgroundColor: colors.panelSoft,
    },
    aiSummaryLabel: { color: colors.accentText, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
    inlineActions: { flexDirection: 'row', gap: 8, marginTop: 12 },
    reportRow: {
      marginTop: 14,
      paddingTop: 14,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    reportButton: { marginTop: 10, alignSelf: 'flex-start' },
    body:    { marginTop: 14, color: colors.text, lineHeight: 21 },
    summary: {
      marginTop: 14,
      padding: 12,
      borderRadius: 8,
      backgroundColor: colors.panelSoft,
      color: colors.text,
    },
    detailButton: { marginTop: 14 },
    applyButton:  { marginBottom: 12 },
  });
}
