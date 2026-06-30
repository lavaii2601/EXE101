import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Linking as RNLinking, Modal, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import SegmentedControl from '../components/SegmentedControl';
import { apiGet, apiPost } from '../api/client';
import { clearPersistedSession, setMobileUserId } from '../api/session';
import { connectGoogleAccount } from '../api/googleAuth';
import { useTheme } from '../theme/ThemeContext';
import ModeBrief from '../components/ModeBrief';

const filters = [
  { label: 'Tất cả',     value: 'all' },
  { label: 'Giáo dục',   value: 'education' },
  { label: 'Công việc',  value: 'work' },
  { label: 'Họp',        value: 'meeting' },
  { label: 'Khuyến mãi', value: 'promotion' },
  { label: 'Tài chính',  value: 'finance' },
  { label: 'Cá nhân',    value: 'personal' },
  { label: 'Khác',       value: 'other' },
];

const sourceFilters = [
  { label: 'Tất cả', value: 'all' },
  { label: 'Gmail', value: 'gmail' },
  { label: 'Outlook', value: 'outlook' },
];

const modes = [
  { label: 'Hộp thư',  value: 'inbox' },
  { label: 'Báo cáo',  value: 'report' },
  { label: 'Soạn thư', value: 'compose' },
];

export default function EmailScreen({ onAuthChanged, onAgentSync, syncEvent, userMode = 'worker' }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [mode, setMode] = useState('inbox');
  const [source, setSource] = useState('all');
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
  const [cacheMiss, setCacheMiss] = useState(false);

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

  const loadEmails = useCallback(async (options = {}) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        max_results: '20',
        page: '1',
        filter,
        include_read: String(includeRead),
        search: searchKeyword,
      });
      params.set(options.fresh ? 'fresh' : 'cache_only', 'true');

      let data;
      const authPromise = loadAuth();
      try {
        const unifiedParams = new URLSearchParams(params);
        unifiedParams.set('source', source);
        data = await apiGet(`/email/unified?${unifiedParams.toString()}`);
      } catch (error) {
        if (source === 'outlook') {
          setEmails([]);
          setCacheMiss(false);
          await authPromise;
          return;
        }
        data = await apiGet(`/email/get-unread?${params.toString()}`);
      }
      await authPromise;
      setCacheMiss(Boolean(data.cache_miss));
      const nextEmails = (data.emails || data.items || []).map(normalizeEmailProvider);
      if ((data.needs_refresh || data.cache_miss) && nextEmails.length === 0 && !options.fresh && !options.autoRefreshAttempted && source !== 'outlook') {
        setCacheMiss(true);
        await loadEmails({ fresh: true, autoRefreshAttempted: true });
        apiPost('/email/meeting-suggestions/scan').catch(() => {});
        return;
      }
      setEmails(nextEmails);
    } catch (error) {
      if (error.status === 401) setEmails([]);
      else Alert.alert('Lỗi tải email', error.message);
    } finally {
      setLoading(false);
    }
  }, [filter, includeRead, loadAuth, searchKeyword, source]);

  const refreshEmailsFromGmail = useCallback(async () => {
    setLoading(true);
    try {
      await apiPost('/email/cache/clear');
    } catch (error) {
      setLoading(false);
      Alert.alert('Không làm mới được email', error.message);
      return;
    }
    await loadEmails({ fresh: true });
    apiPost('/email/meeting-suggestions/scan').catch(() => {});
  }, [loadEmails]);

  useEffect(() => { loadEmails(); }, [loadEmails]);
  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['email', 'profile', 'settings'])) {
      loadEmails({ fresh: hasSyncTarget(syncEvent, ['email']) });
    }
  }, [loadEmails, syncEvent]);
  useEffect(() => {
    const timer = setTimeout(() => setSearchKeyword(searchInput.trim()), 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const login = async () => {
    try {
      const result = await connectGoogleAccount();
      if (!result.connected) return; // user closed the browser without finishing
      await loadEmails();
      onAuthChanged?.();
      onAgentSync?.(['profile', 'settings', 'email']);
    } catch (error) {
      Alert.alert('Không mở được Gmail OAuth', error.message);
    }
  };

  const applyMobileUser = async () => {
    setMobileUserId(userIdInput);
    await loadEmails();
    onAuthChanged?.();
    onAgentSync?.(['profile', 'email']);
  };

  const logout = async () => {
    try {
      await apiPost('/email/logout');
      await clearPersistedSession();
      setAuth({ authenticated: false });
      setEmails([]);
      onAuthChanged?.();
      onAgentSync?.(['profile', 'settings', 'email']);
    } catch (error) {
      Alert.alert('Không đăng xuất được', error.message);
    }
  };

  const openEmail = async (email) => {
    setSelectedEmail(email);
    setEmailBody('');
    setSummary(email.summary || '');
    try {
      const data = email.provider && email.provider !== 'gmail'
        ? await apiGet(`/email/unified/${email.provider}/${encodeURIComponent(email.external_id || email.id)}`)
        : await apiGet(`/email/get-email-body/${email.id}`);
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
      const data = email.provider && email.provider !== 'gmail'
        ? await apiPost(`/email/unified/${email.provider}/${encodeURIComponent(email.external_id || email.id)}/summary`)
        : await apiPost(`/email/summary/${email.id}`);
      email.summary = data.summary || '';
      setSummary(data.summary || '');
      setEmails((current) => current.map((item) => (
        item.id === email.id ? { ...item, summary: data.summary || '' } : item
      )));
      onAgentSync?.(['email', 'overview', 'history'], data);
    } catch (error) {
      Alert.alert('Không tóm tắt được', error.message);
    } finally {
      setSummarizingId('');
    }
  };

  const draftReply = async (email = selectedEmail) => {
    if (!email) return;
    setLoading(true);
    try {
      const context = `Tiêu đề: ${email.subject || ''}\nTừ: ${email.sender || email.from || ''}\nNội dung: ${emailBody || email.body || email.summary || email.snippet || ''}`;
      const data = await apiPost('/chat/generate-reply', {
        context,
        choice: 'Xác nhận đã nhận được email và sẽ phản hồi/xử lý sớm, văn phong lịch sự',
      });
      const senderEmail = extractEmailAddress(email.sender || email.from || '');
      setCompose({
        to: senderEmail,
        subject: String(email.subject || '').startsWith('Re:') ? email.subject : `Re: ${email.subject || ''}`,
        body: data.reply || '',
      });
      setSelectedEmail(null);
      setMode('compose');
      Alert.alert('Đã tạo bản nháp', 'Vui lòng kiểm tra nội dung trước khi gửi.');
      onAgentSync?.(['history'], data);
    } catch (error) {
      Alert.alert('Không tạo được trả lời', error.message);
    } finally {
      setLoading(false);
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
      onAgentSync?.(['email', 'overview', 'history']);
    } catch (error) {
      Alert.alert('Không cập nhật được email', error.message);
    }
  };

  const sendEmail = async () => {
    if (!compose.to || !compose.subject || !compose.body) {
      Alert.alert('Thiếu thông tin', 'Vui lòng điền người nhận, tiêu đề và nội dung.');
      return;
    }
    setLoading(true);
    try {
      await apiPost('/email/send-reply', compose);
      setCompose({ to: '', subject: '', body: '' });
      Alert.alert('Đã gửi email');
      onAgentSync?.(['email', 'overview', 'history']);
    } catch (error) {
      Alert.alert('Không gửi được email', error.message);
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async () => {
    if (!reportDate) {
      Alert.alert('Chọn ngày', 'Nhập ngày theo định dạng DD/MM/YYYY.');
      return;
    }
    setLoading(true);
    try {
      const data = await apiPost('/email/summarize-by-date', { date: reportDate, max_results: 50 });
      setReport(data);
      onAgentSync?.(['email', 'overview', 'history'], data);
    } catch (error) {
      Alert.alert('Không tạo được báo cáo', error.message);
    } finally {
      setLoading(false);
    }
  };

  const createScheduleFromReport = async (row) => {
    try {
      const start = row.suggested_start_time || buildReportStart(reportDate);
      await apiPost('/schedule/create', {
        title: row.schedule_title || row.subject || 'Lịch hẹn từ email',
        description: row.suggested_description || row.summary || '',
        start_time: start,
        end_time: row.suggested_end_time || buildReportEnd(start),
        attendees: [],
      });
      Alert.alert('Đã tạo lịch');
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history']);
    } catch (error) {
      Alert.alert('Không tạo được lịch', error.message);
    }
  };

  const renderInbox = () => (
    <>
      <Card>
        <Field
          label="Gmail đã kết nối trên backend"
          value={userIdInput}
          onChangeText={setUserIdInput}
          placeholder="ten@gmail.com"
          keyboardType="email-address"
        />
        <Button title="Dùng tài khoản này" variant="secondary" onPress={applyMobileUser} style={styles.applyButton} />
        <View style={styles.authRow}>
          <View style={styles.authText}>
            <Text style={styles.cardTitle}>{auth?.authenticated ? 'Gmail đã kết nối' : 'Chưa kết nối Gmail'}</Text>
            <Text style={styles.muted} numberOfLines={1}>{auth?.gmail_email || 'Đăng nhập để đọc và gửi email.'}</Text>
          </View>
          <Button
            title={auth?.authenticated ? 'Đăng xuất' : 'Đăng nhập'}
            variant={auth?.authenticated ? 'secondary' : 'primary'}
            onPress={auth?.authenticated ? logout : login}
          />
        </View>
      </Card>
      <Card style={styles.searchCard}>
        <Field
          label="Tìm kiếm email"
          value={searchInput}
          onChangeText={setSearchInput}
          placeholder="Người gửi, tiêu đề, nội dung..."
        />
        {searchInput ? (
          <Button
            title="Xóa từ khóa"
            variant="secondary"
            onPress={() => {
              setSearchInput('');
              setSearchKeyword('');
            }}
          />
        ) : null}
      </Card>
      <SegmentedControl options={filters} value={filter} onChange={setFilter} />
      <Text style={styles.filterLabel}>Nguồn email</Text>
      <SegmentedControl options={sourceFilters} value={source} onChange={setSource} />
      <Card>
        <View style={styles.switchRow}>
          <Text style={styles.cardTitle}>Giữ email đã đọc trong hộp thư</Text>
          <Switch value={includeRead} onValueChange={setIncludeRead} trackColor={{ false: colors.border, true: colors.primary }} thumbColor="#ffffff" />
        </View>
      </Card>
      {emails.length === 0 ? (
        cacheMiss ? (
          <Card style={styles.cacheMissCard}>
            <Text style={styles.cardTitle}>Chưa có email trong bộ nhớ đệm</Text>
            <Text style={styles.muted}>
              FlowMate sẽ tự quét Gmail khi cache trống. Nếu vẫn chưa thấy dữ liệu, bạn có thể làm mới lại.
            </Text>
            <Button title="Làm mới Gmail" onPress={refreshEmailsFromGmail} loading={loading} style={styles.applyButton} />
          </Card>
        ) : (
          <EmptyState
            title={auth?.authenticated ? 'Không tìm thấy email' : 'Cần đăng nhập Gmail'}
            detail={searchKeyword ? `Không có kết quả cho "${searchKeyword}".` : 'Kéo xuống để làm mới hoặc đổi bộ lọc email.'}
          />
        )
      ) : (
        emails.map((email) => (
          <Card
            key={email.id}
            style={[styles.emailCard, email.is_unread ? styles.emailUnread : styles.emailRead]}
          >
            <TouchableOpacity onPress={() => openEmail(email)} activeOpacity={0.86}>
              <View style={styles.rowBetween}>
                <Text style={styles.subject} numberOfLines={2}>{email.subject || '(Không tiêu đề)'}</Text>
                <View style={styles.badges}>
                  <Text style={[styles.providerBadge, email.provider === 'outlook' ? styles.outlookBadge : styles.gmailBadge]}>
                    {email.provider_label || providerLabel(email.provider)}
                  </Text>
                  <Text style={[styles.readBadge, email.is_unread ? styles.unreadBadge : styles.readBadgeDone]}>
                    {email.is_unread ? 'CHƯA ĐỌC' : 'ĐÃ ĐỌC'}
                  </Text>
                  <Text style={styles.tag}>{email.tag || 'email'}</Text>
                </View>
              </View>
              <Text style={styles.sender} numberOfLines={1}>{email.sender || email.from || 'Người gửi'}</Text>
              {email.summary ? (
                <View style={styles.aiSummary}>
                  <Text style={styles.aiSummaryLabel}>AI TÓM TẮT</Text>
                  <Text style={styles.preview} numberOfLines={4}>{email.summary}</Text>
                </View>
              ) : (
                <Text style={styles.preview} numberOfLines={3}>{email.snippet || ''}</Text>
              )}
            </TouchableOpacity>
            <View style={styles.inlineActions}>
              <Button title="Xem" variant="secondary" onPress={() => openEmail(email)} />
              <Button
                title={email.summary ? 'Xem tóm tắt AI' : 'Tóm tắt AI'}
                onPress={() => email.summary ? openEmail(email) : summarizeEmail(email)}
                loading={summarizingId === email.id}
              />
              <Button
                title={email.is_unread ? 'Đánh dấu đã đọc' : 'Đánh dấu chưa đọc'}
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
      <Field label="Người nhận" value={compose.to}      onChangeText={(to)      => setCompose((c) => ({ ...c, to }))}      placeholder="email@example.com" keyboardType="email-address" />
      <Field label="Tiêu đề"    value={compose.subject} onChangeText={(subject) => setCompose((c) => ({ ...c, subject }))} placeholder="Tiêu đề email" />
      <Field label="Nội dung"   value={compose.body}    onChangeText={(body)    => setCompose((c) => ({ ...c, body }))}    placeholder="Nội dung email" multiline />
      <Button title="Gửi email" onPress={sendEmail} loading={loading} />
    </Card>
  );

  const renderReport = () => (
    <>
      <Card>
        <Field label="Ngày báo cáo" value={reportDate} onChangeText={setReportDate} placeholder="05/06/2026" />
        <Button title="Tạo báo cáo" onPress={generateReport} loading={loading} />
      </Card>
      {report ? (
        <Card>
          <Text style={styles.cardTitle}>Báo cáo ngày {report.date}</Text>
          <Text style={styles.muted}>Tổng {report.total_emails || 0} email</Text>
          {(report.rows || []).map((row, index) => (
            <View key={`${row.subject}-${index}`} style={styles.reportRow}>
              <Text style={styles.subject}>{index + 1}. {row.subject || 'Email'}</Text>
              <Text style={styles.preview}>{row.summary || 'Không có tóm tắt'}</Text>
              {row.is_meeting
                ? <Button title="Tạo lịch" variant="secondary" onPress={() => createScheduleFromReport(row)} style={styles.reportButton} />
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
        onRefresh={refreshEmailsFromGmail}
        actions={<Button title="Gmail" variant="secondary" onPress={() => RNLinking.openURL('https://mail.google.com')} />}
      >
        <ModeBrief
          userMode={userMode}
          stats={[
            { value: emails.length, label: 'Email hiển thị' },
            { value: emails.filter((email) => email.is_unread).length, label: 'Chưa đọc' },
            { value: emails.filter((email) => email.provider === 'outlook').length, label: 'Outlook' },
          ]}
        />
        <SegmentedControl options={modes} value={mode} onChange={setMode} />
        {mode === 'compose' ? renderCompose() : mode === 'report' ? renderReport() : renderInbox()}
      </Screen>
      <Modal visible={!!selectedEmail} animationType="slide" onRequestClose={() => setSelectedEmail(null)}>
        <Screen title="Chi tiết email" actions={<Button title="Đóng" variant="secondary" onPress={() => setSelectedEmail(null)} />}>
          {selectedEmail ? (
            <Card>
              <Text style={styles.subject}>{selectedEmail.subject || '(Không tiêu đề)'}</Text>
              <Text style={styles.sender}>{selectedEmail.sender || selectedEmail.from || ''}</Text>
              <Text style={styles.body}>{emailBody || selectedEmail.snippet || 'Đang tải...'}</Text>
              {summary ? <Text style={styles.summary}>{summary}</Text> : null}
              <Button
                title={summary ? 'Tóm tắt lại bằng AI' : 'Tóm tắt bằng AI'}
                onPress={() => summarizeEmail(selectedEmail)}
                loading={summarizingId === selectedEmail.id}
                style={styles.detailButton}
              />
              <Button
                title="Soạn trả lời AI"
                variant="secondary"
                onPress={() => draftReply(selectedEmail)}
                loading={loading}
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

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
}

function buildReportEnd(startValue) {
  const start = new Date(startValue);
  if (Number.isNaN(start.getTime())) return '';
  start.setMinutes(start.getMinutes() + 60);
  const yyyy = start.getFullYear();
  const mm = String(start.getMonth() + 1).padStart(2, '0');
  const dd = String(start.getDate()).padStart(2, '0');
  const hh = String(start.getHours()).padStart(2, '0');
  const min = String(start.getMinutes()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}T${hh}:${min}:00`;
}

function extractEmailAddress(value) {
  const match = String(value || '').match(/<(.+?)>/);
  return match ? match[1] : String(value || '').trim();
}

function providerLabel(provider) {
  if (provider === 'outlook' || provider === 'microsoft') return 'Outlook';
  return 'Gmail';
}

function normalizeEmailProvider(email) {
  const provider = email.provider === 'microsoft' ? 'outlook' : (email.provider || 'gmail');
  return {
    ...email,
    provider,
    provider_label: email.provider_label || providerLabel(provider),
    external_id: email.external_id || email.gmail_message_id || email.outlook_message_id || email.id,
  };
}

function makeStyles(colors) {
  return StyleSheet.create({
    authRow:  { flexDirection: 'row', alignItems: 'center', gap: 10 },
    authText: { flex: 1, minWidth: 0 },
    searchCard: { gap: 2 },
    cacheMissCard: { gap: 8 },
    cardTitle:{ color: colors.text, fontWeight: '800' },
    muted:    { marginTop: 4, color: colors.textMuted },
    filterLabel: { color: colors.textMuted, fontSize: 11, fontWeight: '900', textTransform: 'uppercase' },
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
    providerBadge: {
      paddingHorizontal: 7,
      paddingVertical: 3,
      borderRadius: 999,
      fontSize: 9,
      fontWeight: '900',
      overflow: 'hidden',
    },
    gmailBadge: { color: colors.primary, backgroundColor: `${colors.primary}18` },
    outlookBadge: { color: '#0369a1', backgroundColor: 'rgba(14,165,233,0.16)' },
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
