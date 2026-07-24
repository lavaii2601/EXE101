import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Animated, Linking as RNLinking, Modal, PanResponder, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import Screen from '../components/Screen';
import SegmentedControl from '../components/SegmentedControl';
import * as FileSystem from 'expo-file-system/legacy';
import { apiGet, apiPost } from '../api/client';
import { API_BASE } from '../api/config';
import { getMobileAccessToken } from '../api/session';
import { connectGoogleAccount } from '../api/googleAuth';
import { useTheme } from '../theme/ThemeContext';

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

export default function EmailScreen({ onAuthChanged, onAgentSync, onNavigate, syncEvent }) {
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
  const [summarizingId, setSummarizingId] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [cacheMiss, setCacheMiss] = useState(false);
  const [authExpired, setAuthExpired] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [downloadingAttachmentId, setDownloadingAttachmentId] = useState('');
  const [pageInfo, setPageInfo] = useState({ current_page: 1, total_pages: 1 });
  const [loadingMore, setLoadingMore] = useState(false);
  const [scanningGmail, setScanningGmail] = useState(false);
  const [calendarPermissionAttempted, setCalendarPermissionAttempted] = useState(false);
  const [meetingSuggestions, setMeetingSuggestions] = useState([]);
  const [filterModalVisible, setFilterModalVisible] = useState(false);

  const isDefaultFilters = filter === 'all' && source === 'all';
  const activeFilterLabel = filters.find((item) => item.value === filter)?.label || 'Tất cả';
  const activeSourceLabel = sourceFilters.find((item) => item.value === source)?.label || 'Tất cả';

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
    // Outlook has no backend implementation at all yet (no /outlook routes
    // anywhere in web/backend) -- don't hit the network, just say so.
    if (source === 'outlook') {
      setEmails([]);
      setCacheMiss(false);
      setAuthExpired(false);
      setPageInfo({ current_page: 1, total_pages: 1 });
      return;
    }

    const targetPage = options.page || 1;
    if (options.append) setLoadingMore(true); else setLoading(true);
    try {
      const params = new URLSearchParams({
        max_results: '20',
        page: String(targetPage),
        filter,
        include_read: String(includeRead),
        search: searchKeyword,
      });
      params.set(options.fresh ? 'fresh' : 'cache_only', 'true');

      const authPromise = loadAuth();
      const data = await apiGet(`/email/get-unread?${params.toString()}`);
      await authPromise;
      setAuthExpired(false);
      setCacheMiss(Boolean(data.cache_miss));
      const nextEmails = (data.emails || data.items || []).map(normalizeEmailProvider);
      if ((data.needs_refresh || data.cache_miss) && nextEmails.length === 0 && !options.fresh && !options.autoRefreshAttempted) {
        setCacheMiss(true);
        await loadEmails({ fresh: true, autoRefreshAttempted: true });
        apiPost('/email/meeting-suggestions/scan').catch(() => {});
        return;
      }
      setEmails((current) => (options.append ? [...current, ...nextEmails] : nextEmails));
      if (data.pagination) setPageInfo(data.pagination);
    } catch (error) {
      if (error.status === 401) {
        // The mobile bearer token expired (or Gmail was never connected).
        // Showing a plain empty inbox here is misleading when auth-status
        // still claims "connected" (it only checks whether a token file
        // exists, not whether the current session can use it) -- surface a
        // clear re-auth prompt instead of silently rendering "no email".
        setEmails([]);
        setAuthExpired(true);
      } else {
        Alert.alert('Lỗi tải email', error.message);
      }
    } finally {
      if (options.append) setLoadingMore(false); else setLoading(false);
    }
  }, [filter, includeRead, loadAuth, searchKeyword, source]);

  const loadMoreEmails = useCallback(() => {
    if (loading || loadingMore) return;
    const nextPage = (pageInfo.current_page || 1) + 1;
    if (nextPage > (pageInfo.total_pages || 1)) return;
    loadEmails({ append: true, page: nextPage });
  }, [loadEmails, loading, loadingMore, pageInfo]);

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
    apiPost('/email/meeting-suggestions/scan')
      .then((data) => setMeetingSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []))
      .catch(() => {});
  }, [loadEmails]);

  const loadMeetingSuggestions = useCallback(async () => {
    try {
      const data = await apiGet('/email/meeting-suggestions');
      setMeetingSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []);
    } catch (error) {
      if (error.status !== 401) console.warn('Meeting suggestions failed:', error);
    }
  }, []);

  useEffect(() => { loadEmails(); loadMeetingSuggestions(); }, [loadEmails, loadMeetingSuggestions]);
  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['email', 'profile', 'settings'])) {
      loadEmails({ fresh: hasSyncTarget(syncEvent, ['email']) });
      loadMeetingSuggestions();
    }
  }, [loadEmails, loadMeetingSuggestions, syncEvent]);
  useEffect(() => {
    const timer = setTimeout(() => setSearchKeyword(searchInput.trim()), 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const login = async () => {
    try {
      const result = await connectGoogleAccount();
      if (!result.connected) return;
      await loadAuth();
      setScanningGmail(true);
      try {
        await loadEmails();
      } finally {
        setScanningGmail(false);
      }
      onAuthChanged?.();
      onAgentSync?.(['profile', 'settings', 'email']);
    } catch (error) {
      Alert.alert('Không mở được Gmail OAuth', error.message);
    }
  };

  useEffect(() => {
    if (
      auth?.authenticated
      && auth.calendar_write_connected === false
      && !calendarPermissionAttempted
    ) {
      setCalendarPermissionAttempted(true);
      login();
    }
  }, [auth, calendarPermissionAttempted]);

  const openEmail = async (email) => {
    setSelectedEmail(email);
    setEmailBody('');
    setSummary(email.summary || '');
    setAttachments([]);
    try {
      const data = await apiGet(`/email/get-email-body/${email.id}`);
      setEmailBody(data.body || '');
      setAttachments(Array.isArray(data.email?.attachments) ? data.email.attachments : []);
    } catch (error) {
      setEmailBody(error.message);
    }
  };

  const downloadAttachment = async (attachment) => {
    if (!selectedEmail) return;
    setDownloadingAttachmentId(attachment.id);
    try {
      const token = getMobileAccessToken();
      const url = `${API_BASE}/email/attachment/${encodeURIComponent(selectedEmail.id)}/${encodeURIComponent(attachment.id)}`;
      const safeFilename = String(attachment.filename || 'attachment')
        .replace(/[^\p{L}\p{N}._() -]+/gu, '_')
        .replace(/^\.+/, '') || 'attachment';
      const fileUri = `${FileSystem.documentDirectory}${safeFilename}`;
      await FileSystem.downloadAsync(url, fileUri, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      Alert.alert('Đã tải file đính kèm', `Đã lưu "${attachment.filename}" vào bộ nhớ ứng dụng.`);
    } catch (error) {
      Alert.alert('Không tải được file đính kèm', error.message);
    } finally {
      setDownloadingAttachmentId('');
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

  const archiveEmail = async (email) => {
    try {
      await apiPost(`/email/archive/${email.id}`);
      setEmails((current) => current.filter((item) => item.id !== email.id));
      onAgentSync?.(['email', 'overview', 'history']);
    } catch (error) {
      Alert.alert('Không lưu trữ được email', error.message);
    }
  };

  const trashEmail = async (email) => {
    try {
      await apiPost(`/email/trash/${email.id}`);
      setEmails((current) => current.filter((item) => item.id !== email.id));
      onAgentSync?.(['email', 'overview', 'history']);
    } catch (error) {
      Alert.alert('Không xóa được email', error.message);
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
      <TouchableOpacity style={styles.filterTrigger} onPress={() => setFilterModalVisible(true)} activeOpacity={0.85}>
        <Ionicons name="options-outline" size={18} color={colors.primary} />
        <Text style={styles.filterTriggerText}>
          {isDefaultFilters ? 'Bộ lọc' : `${activeFilterLabel} · ${activeSourceLabel}`}
        </Text>
        {isDefaultFilters ? null : <View style={styles.filterDot} />}
      </TouchableOpacity>
      <Card>
        <View style={styles.switchRow}>
          <Text style={styles.cardTitle}>Giữ email đã đọc trong hộp thư</Text>
          <Switch value={includeRead} onValueChange={setIncludeRead} trackColor={{ false: colors.border, true: colors.primary }} thumbColor="#ffffff" />
        </View>
      </Card>
      {scanningGmail ? (
        <View style={styles.scanningBanner}>
          <Text style={styles.scanningText}>⏳ Đang quét Gmail của bạn lần đầu...</Text>
        </View>
      ) : null}
      {emails.length === 0 ? (
        source === 'outlook' ? (
          <EmptyState title="Outlook chưa được hỗ trợ" detail="FlowMate hiện chỉ đọc được Gmail. Chọn nguồn Gmail hoặc Tất cả." />
        ) : authExpired ? (
          <EmptyState
            title="Phiên đăng nhập Gmail đã hết hạn"
            detail="Vào tab Cài đặt để đăng nhập lại Google."
          />
        ) : cacheMiss ? (
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
          <SwipeableEmailRow
            key={email.id}
            styles={styles}
            isUnread={!!email.is_unread}
            onArchive={() => archiveEmail(email)}
            onTrash={() => trashEmail(email)}
            onToggleRead={() => toggleReadStatus(email)}
          >
            <Card style={[styles.emailCard, email.is_unread ? styles.emailUnread : styles.emailRead]}>
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
          </SwipeableEmailRow>
        ))
      )}
      {emails.length > 0 && pageInfo.current_page < pageInfo.total_pages ? (
        <Button
          title="Tải thêm email"
          variant="secondary"
          onPress={loadMoreEmails}
          loading={loadingMore}
          style={styles.loadMoreButton}
        />
      ) : null}
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
        {meetingSuggestions.length > 0 ? (
          <TouchableOpacity
            style={styles.meetingBanner}
            activeOpacity={0.86}
            onPress={() => {
              onAgentSync?.(['email', 'schedule', 'overview']);
              onNavigate?.('schedule');
            }}
          >
            <Text style={styles.meetingBannerIcon}>📅</Text>
            <View style={styles.meetingBannerBody}>
              <Text style={styles.meetingBannerTitle}>Bob phát hiện lịch hẹn trong email</Text>
              <Text style={styles.meetingBannerText} numberOfLines={2}>
                {meetingSuggestions.length} gợi ý đang chờ · Chạm để kiểm tra và tạo lịch
              </Text>
            </View>
            <Text style={styles.meetingBannerArrow}>›</Text>
          </TouchableOpacity>
        ) : null}
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
              {attachments.length > 0 ? (
                <View style={styles.attachmentList}>
                  <Text style={styles.attachmentHeader}>{`ĐÍNH KÈM (${attachments.length})`}</Text>
                  {attachments.map((attachment) => (
                    <View key={attachment.id} style={styles.attachmentRow}>
                      <View style={styles.attachmentInfo}>
                        <Text style={styles.attachmentName} numberOfLines={1}>{attachment.filename}</Text>
                        <Text style={styles.attachmentMeta}>{formatFileSize(attachment.size)}</Text>
                      </View>
                      <Button
                        title="Tải"
                        variant="secondary"
                        onPress={() => downloadAttachment(attachment)}
                        loading={downloadingAttachmentId === attachment.id}
                      />
                    </View>
                  ))}
                </View>
              ) : null}
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
      <Modal
        visible={filterModalVisible}
        animationType="slide"
        transparent
        onRequestClose={() => setFilterModalVisible(false)}
      >
        <TouchableOpacity
          style={styles.filterModalOverlay}
          activeOpacity={1}
          onPress={() => setFilterModalVisible(false)}
        >
          <TouchableOpacity style={styles.filterModalSheet} activeOpacity={1} onPress={() => {}}>
            <View style={styles.filterModalHeader}>
              <Text style={styles.filterModalTitle}>Bộ lọc email</Text>
              <TouchableOpacity onPress={() => setFilterModalVisible(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Ionicons name="close" size={22} color={colors.textMuted} />
              </TouchableOpacity>
            </View>
            <Text style={styles.filterSectionLabel}>Danh mục</Text>
            <SegmentedControl options={filters} value={filter} onChange={setFilter} />
            <Text style={styles.filterSectionLabel}>Nguồn email</Text>
            <SegmentedControl options={sourceFilters} value={source} onChange={setSource} />
            <Button title="Xong" onPress={() => setFilterModalVisible(false)} style={styles.filterModalDone} />
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
    </>
  );
}

const SWIPE_RIGHT_ACTIONS_WIDTH = 152; // Archive + Trash, revealed on swipe-left
const SWIPE_LEFT_ACTION_WIDTH = 108;   // Toggle read/unread, revealed on swipe-right
const SWIPE_OPEN_THRESHOLD = 40;

function SwipeableEmailRow({ children, styles, isUnread, onArchive, onTrash, onToggleRead }) {
  const translateX = useRef(new Animated.Value(0)).current;
  const openX = useRef(0);

  const closeRow = useCallback(() => {
    openX.current = 0;
    Animated.spring(translateX, { toValue: 0, useNativeDriver: true, bounciness: 0 }).start();
  }, [translateX]);

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponderCapture: (_, gesture) => (
        Math.abs(gesture.dx) > 10 && Math.abs(gesture.dx) > Math.abs(gesture.dy) * 1.5
      ),
      onPanResponderMove: (_, gesture) => {
        const next = Math.max(
          -SWIPE_RIGHT_ACTIONS_WIDTH,
          Math.min(SWIPE_LEFT_ACTION_WIDTH, openX.current + gesture.dx)
        );
        translateX.setValue(next);
      },
      onPanResponderRelease: (_, gesture) => {
        const next = openX.current + gesture.dx;
        let target = 0;
        if (next <= -SWIPE_OPEN_THRESHOLD) target = -SWIPE_RIGHT_ACTIONS_WIDTH;
        else if (next >= SWIPE_OPEN_THRESHOLD) target = SWIPE_LEFT_ACTION_WIDTH;
        openX.current = target;
        Animated.spring(translateX, { toValue: target, useNativeDriver: true, bounciness: 0 }).start();
      },
    })
  ).current;

  return (
    <View style={styles.swipeWrap}>
      <View style={styles.swipeActionsRight} pointerEvents="box-none">
        <TouchableOpacity
          style={[styles.swipeActionBtn, styles.swipeArchiveBtn]}
          onPress={() => { closeRow(); onArchive(); }}
        >
          <Ionicons name="archive-outline" size={18} color="#FFFFFF" />
          <Text style={styles.swipeActionText}>Lưu trữ</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.swipeActionBtn, styles.swipeTrashBtn]}
          onPress={() => { closeRow(); onTrash(); }}
        >
          <Ionicons name="trash-outline" size={18} color="#FFFFFF" />
          <Text style={styles.swipeActionText}>Xóa</Text>
        </TouchableOpacity>
      </View>
      <View style={styles.swipeActionsLeft} pointerEvents="box-none">
        <TouchableOpacity
          style={[styles.swipeActionBtn, styles.swipeReadBtn]}
          onPress={() => { closeRow(); onToggleRead(); }}
        >
          <Ionicons name={isUnread ? 'mail-open-outline' : 'mail-unread-outline'} size={18} color="#FFFFFF" />
          <Text style={styles.swipeActionText}>{isUnread ? 'Đã đọc' : 'Chưa đọc'}</Text>
        </TouchableOpacity>
      </View>
      <Animated.View style={[styles.swipeContent, { transform: [{ translateX }] }]} {...panResponder.panHandlers}>
        {children}
      </Animated.View>
    </View>
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

function formatFileSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
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
    cardTitle:{ color: colors.text, fontFamily: 'Poppins_700Bold' },
    muted:    { marginTop: 4, color: colors.textMuted, fontFamily: 'Poppins_400Regular' },
    filterTrigger: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      alignSelf: 'flex-start',
      paddingHorizontal: 14,
      paddingVertical: 10,
      borderRadius: 12,
      backgroundColor: colors.panel,
      borderWidth: 1,
      borderColor: colors.border,
    },
    filterTriggerText: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    filterDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.primary },
    filterModalOverlay: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.4)',
      justifyContent: 'flex-end',
    },
    filterModalSheet: {
      backgroundColor: colors.panel,
      borderTopLeftRadius: 24,
      borderTopRightRadius: 24,
      padding: 20,
      paddingBottom: 32,
      gap: 4,
    },
    filterModalHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 6,
    },
    filterModalTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 17 },
    filterSectionLabel: {
      marginTop: 12,
      marginBottom: 6,
      color: colors.primary,
      fontFamily: 'Poppins_700Bold',
      fontSize: 10,
      letterSpacing: 1,
      textTransform: 'uppercase',
    },
    filterModalDone: { marginTop: 18 },
    switchRow:{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    swipeWrap: { position: 'relative', overflow: 'hidden', borderRadius: 20 },
    swipeContent: { width: '100%', backgroundColor: colors.background },
    swipeActionsRight: {
      position: 'absolute',
      top: 0,
      bottom: 0,
      right: 0,
      width: 152,
      flexDirection: 'row',
    },
    swipeActionsLeft: {
      position: 'absolute',
      top: 0,
      bottom: 0,
      left: 0,
      width: 108,
      flexDirection: 'row',
    },
    swipeActionBtn: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: 3,
    },
    swipeArchiveBtn: { backgroundColor: '#2563eb' },
    swipeTrashBtn: { backgroundColor: '#dc2626' },
    swipeReadBtn: { backgroundColor: colors.primary },
    swipeActionText: { color: '#FFFFFF', fontFamily: 'Poppins_600SemiBold', fontSize: 10 },
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
      fontFamily: 'Poppins_700Bold',
    },
    unreadBadge: { color: colors.accentText, backgroundColor: colors.primarySoft },
    readBadgeDone: { color: '#5eead4', backgroundColor: 'rgba(13,148,136,0.22)' },
    providerBadge: {
      paddingHorizontal: 7,
      paddingVertical: 3,
      borderRadius: 999,
      fontSize: 9,
      fontFamily: 'Poppins_700Bold',
      overflow: 'hidden',
    },
    gmailBadge: { color: colors.primary, backgroundColor: `${colors.primary}18` },
    outlookBadge: { color: '#0369a1', backgroundColor: 'rgba(14,165,233,0.16)' },
    subject:  { flex: 1, color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 15, lineHeight: 21 },
    tag:      { color: colors.primary, fontSize: 12, fontFamily: 'Poppins_700Bold' },
    sender:   { marginTop: 6, color: colors.textMuted, fontFamily: 'Poppins_500Medium' },
    preview:  { marginTop: 8, color: colors.textMuted, fontFamily: 'Poppins_400Regular', lineHeight: 20 },
    aiSummary: {
      marginTop: 10,
      padding: 11,
      borderRadius: 12,
      borderLeftWidth: 3,
      borderLeftColor: colors.primary,
      backgroundColor: colors.panelSoft,
    },
    aiSummaryLabel: { color: colors.primary, fontSize: 9, fontFamily: 'Poppins_700Bold', letterSpacing: 1 },
    inlineActions: { flexDirection: 'row', gap: 8, marginTop: 12 },
    reportRow: {
      marginTop: 14,
      paddingTop: 14,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    reportButton: { marginTop: 10, alignSelf: 'flex-start' },
    body:    { marginTop: 14, color: colors.text, fontFamily: 'Poppins_400Regular', lineHeight: 21 },
    summary: {
      marginTop: 14,
      padding: 12,
      borderRadius: 8,
      backgroundColor: colors.panelSoft,
      color: colors.text,
      fontFamily: 'Poppins_400Regular',
    },
    detailButton: { marginTop: 14 },
    attachmentList: {
      marginTop: 14,
      paddingTop: 12,
      borderTopColor: colors.border,
      borderTopWidth: 1,
      gap: 8,
    },
    attachmentHeader: { color: colors.primary, fontSize: 10, fontFamily: 'Poppins_700Bold', letterSpacing: 1 },
    attachmentRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      padding: 10,
      borderRadius: 10,
      backgroundColor: colors.panelSoft,
    },
    attachmentInfo: { flex: 1, minWidth: 0 },
    attachmentName: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 12 },
    attachmentMeta: { marginTop: 2, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11 },
    applyButton:  { marginBottom: 12 },
    loadMoreButton: { marginTop: 4 },
    scanningBanner: {
      padding: 14,
      borderRadius: 10,
      backgroundColor: colors.primarySoft,
      borderLeftWidth: 3,
      borderLeftColor: colors.primary,
    },
    scanningText: {
      color: colors.primary,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 13,
    },
    meetingBanner: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      padding: 14,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: `${colors.primary}55`,
      backgroundColor: colors.primarySoft,
      ...colors.shadow,
    },
    meetingBannerIcon: { fontSize: 28 },
    meetingBannerBody: { flex: 1, minWidth: 0 },
    meetingBannerTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 13 },
    meetingBannerText: { marginTop: 2, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11 },
    meetingBannerArrow: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 28 },
  });
}
