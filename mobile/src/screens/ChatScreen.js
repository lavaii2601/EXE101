import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, FlatList, KeyboardAvoidingView, Modal, Platform, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Field from '../components/Field';
import { apiDelete, apiGet, apiPost } from '../api/client';
import { useTheme } from '../theme/ThemeContext';
import { getUserMode } from '../config/userModes';
import { takePendingAgentNotice } from '../state/agentNotices';

function normalizePlanSuggestion(value) {
  return {
    ...value,
    items: Array.isArray(value?.items)
      ? value.items.map((item) => ({ ...item, selected: true }))
      : [],
  };
}

function toEditableDateTime(value) {
  if (!value) return '';
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(text)) return text.slice(0, 16);
  return text;
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

function mapHistoryItem(item) {
  return [
    { id: `${item.id}-u`, role: 'user',      text: item.user_message },
    { id: `${item.id}-a`, role: 'assistant', text: item.assistant_response },
  ];
}

function createSessionId() {
  if (global.crypto && typeof global.crypto.randomUUID === 'function') {
    return global.crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const value = Math.random() * 16 | 0;
    const next = char === 'x' ? value : (value & 0x3 | 0x8);
    return next.toString(16);
  });
}

function formatAgentMeta(data) {
  const trace = data?.agent_trace || {};
  const sources = Array.isArray(trace.workspace_sources) && trace.workspace_sources.length
    ? trace.workspace_sources
    : (Array.isArray(data?.workspace_sources) ? data.workspace_sources : []);
  const sourceLabels = {
    email: 'Email',
    calendar: 'Lịch',
    history: 'Lịch sử',
    profile: 'Hồ sơ',
    knowledge: 'Kiến thức',
    internet: 'Internet',
    time: 'Thời gian hệ thống',
  };
  const parts = [];
  // Intent names and trace steps are internal diagnostics. Keep only useful
  // user-facing provenance and confirmation state.
  const visibleSources = sources.filter((source) => ['email', 'calendar', 'internet'].includes(source));
  if (visibleSources.length) {
    parts.push(`Nguồn: ${visibleSources.map((source) => sourceLabels[source] || source).join(' + ')}`);
  }
  if (trace.requires_confirmation || data?.schedule_suggestion) {
    parts.push('Cần xác nhận');
  }
  if (data?.pending_action) {
    parts.push('Cần xác nhận hành động');
  }
  return parts.join(' · ');
}

export default function ChatScreen({ userMode = 'worker', agentProfile = null, onAgentSync }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(() => createSessionId());
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [planSuggestion, setPlanSuggestion] = useState(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [sessions, setSessions] = useState([]);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const listRef = useRef(null);
  const mode = getUserMode(userMode);

  const loadHistory = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await apiGet('/chat/history?limit=20');
      const nextMessages = (data.history || []).reverse().flatMap(mapHistoryItem).filter((m) => m.text);
      setMessages(nextMessages);
    } catch (error) {
      Alert.alert('Lỗi tải lịch sử chat', error.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await loadHistory();
      const notice = takePendingAgentNotice();
      if (notice) {
        setMessages((current) => [
          ...current,
          { id: `agent-${Date.now()}`, role: 'assistant', text: notice, badge: 'AI Agent' },
        ]);
      }
      // Always open the chat already scrolled to the newest message --
      // loadHistory leaves the FlatList at its default top position
      // otherwise, forcing users to manually scroll down every time.
      requestAnimationFrame(() => listRef.current?.scrollToEnd?.({ animated: false }));
    })();
  }, [loadHistory]);

  const handleMessagesScroll = useCallback((event) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const distanceFromBottom = contentSize.height - layoutMeasurement.height - contentOffset.y;
    setIsAtBottom(distanceFromBottom < 80);
  }, []);

  const scrollToLatest = useCallback(() => {
    listRef.current?.scrollToEnd?.({ animated: true });
  }, []);

  const startNewChat = () => {
    setSessionId(createSessionId());
    setMessages([]);
    setSuggestion(null);
    setPendingAction(null);
    setPlanSuggestion(null);
    setInput('');
  };

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const data = await apiGet('/chat/sessions?limit=40');
      setSessions(Array.isArray(data.sessions) ? data.sessions : []);
    } catch (error) {
      Alert.alert('Không tải được đoạn chat', error.message);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const showSessions = useCallback(async () => {
    setSessionsOpen(true);
    await loadSessions();
  }, [loadSessions]);

  const openSession = useCallback(async (session) => {
    if (!session?.id) return;
    setRefreshing(true);
    try {
      const data = await apiGet(`/chat/history?limit=100&session_id=${encodeURIComponent(session.id)}`);
      setSessionId(session.id);
      setMessages((data.history || []).reverse().flatMap(mapHistoryItem).filter((item) => item.text));
      setSuggestion(null);
      setPendingAction(null);
      setPlanSuggestion(null);
      setSessionsOpen(false);
      requestAnimationFrame(() => listRef.current?.scrollToEnd?.({ animated: false }));
    } catch (error) {
      Alert.alert('Không mở được đoạn chat', error.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  const deleteSession = useCallback((session) => {
    Alert.alert('Xóa đoạn chat?', session?.title || 'Đoạn chat này sẽ bị xóa ngay.', [
      { text: 'Hủy', style: 'cancel' },
      {
        text: 'Xóa',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiDelete(`/chat/sessions/${encodeURIComponent(session.id)}`);
            setSessions((current) => current.filter((item) => item.id !== session.id));
            if (session.id === sessionId) startNewChat();
            onAgentSync?.(['chat', 'history']);
          } catch (error) {
            Alert.alert('Không xóa được đoạn chat', error.message);
          }
        },
      },
    ]);
  }, [onAgentSync, sessionId]);

  const submitChatMessage = useCallback(async (text, options = {}) => {
    const trimmed = String(text || '').trim();
    if (!trimmed || loading) return;

    const {
      addUserMessage = true,
      confirmedAction = false,
      actionOverride = null,
      confirmedSchedule = false,
      scheduleOverride = null,
    } = options;

    if (addUserMessage) {
      const userMessage = { id: `u-${Date.now()}`, role: 'user', text: trimmed };
      setMessages((current) => [...current, userMessage]);
      setInput('');
    }

    setLoading(true);
    setSuggestion(null);
    setPendingAction(null);
    setPlanSuggestion(null);

    try {
      const data = await apiPost('/chat/message', {
        message: trimmed,
        mode: userMode,
        session_id: sessionId,
        confirmed_schedule: confirmedSchedule,
        schedule_override: scheduleOverride,
        confirmed_action: confirmedAction,
        action_override: actionOverride,
      });
      const assistantMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: data.response || 'Không có phản hồi.',
        badge: 'AI Agent',
        meta: formatAgentMeta(data),
      };
      setMessages((current) => [...current, assistantMessage]);
      onAgentSync?.(data.refresh_targets || [], data);
      if (data.schedule_suggestion) {
        setSuggestion({
          ...data.schedule_suggestion,
          message: trimmed,
        });
      }
      if (data.pending_action) {
        setPendingAction({
          ...data.pending_action,
          message: trimmed,
        });
      }
      if (data.day_plan_suggestion) setPlanSuggestion(normalizePlanSuggestion(data.day_plan_suggestion));
      if (data.schedule_created) Alert.alert('Đã tạo lịch', data.schedule_created.title || 'Lịch hẹn mới');
      if (data.action_applied) Alert.alert('Đã thực hiện', data.response || 'Hành động đã được áp dụng.');
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: `e-${Date.now()}`, role: 'assistant', text: `Lỗi kết nối: ${error.message}` },
      ]);
    } finally {
      setLoading(false);
      setIsAtBottom(true);
      requestAnimationFrame(() => listRef.current?.scrollToEnd?.({ animated: true }));
    }
  }, [loading, onAgentSync, sessionId, userMode]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;
    submitChatMessage(text);
  };

  const createSuggestedSchedule = async () => {
    if (!suggestion) return;
    if (suggestion.action === 'update' || suggestion.action === 'delete') {
      submitChatMessage(suggestion.message || 'Xác nhận lịch', {
        addUserMessage: false,
        confirmedSchedule: true,
        scheduleOverride: suggestion,
      });
      return;
    }
    setLoading(true);
    try {
      const data = await apiPost('/schedule/create', {
        title: suggestion.title || 'Lich hen',
        description: suggestion.description || '',
        start_time: suggestion.start_time,
        attendees: suggestion.attendees || [],
      });
      if (data.success) {
        Alert.alert('Đã tạo lịch', data.message || 'Lịch hẹn đã được tạo.');
        setSuggestion(null);
        onAgentSync?.(['schedule', 'calendar', 'overview', 'history'], data);
      }
    } catch (error) {
      Alert.alert('Không tạo được lịch', error.message);
    } finally {
      setLoading(false);
    }
  };

  const confirmPendingAction = useCallback(() => {
    if (!pendingAction) return;
    submitChatMessage(pendingAction.message || 'Xác nhận', {
      addUserMessage: false,
      confirmedAction: true,
      actionOverride: { ...(pendingAction.arguments || {}), tool: pendingAction.tool },
    });
  }, [pendingAction, submitChatMessage]);

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

  const applyDayPlanSuggestion = useCallback(async () => {
    const selectedItems = (planSuggestion?.items || []).filter((item) => item.selected !== false);
    if (!selectedItems.length) {
      Alert.alert('Chưa chọn hoạt động', 'Chọn ít nhất một hoạt động để tạo lịch.');
      return;
    }
    setPlanLoading(true);
    try {
      const data = await apiPost('/schedule/plan-day/apply', {
        date: planSuggestion?.date,
        items: selectedItems.map(toPlanPayload),
      });
      setPlanSuggestion(null);
      Alert.alert('Đã tạo lịch', data.message || `FlowMate đã tạo ${data.created_count || selectedItems.length} hoạt động.`);
      onAgentSync?.(['schedule', 'calendar', 'overview', 'history'], data);
    } catch (error) {
      Alert.alert('Không áp dụng được lịch', error.message);
    } finally {
      setPlanLoading(false);
    }
  }, [onAgentSync, planSuggestion]);

  const clearChat = async () => {
    try {
      await apiPost('/chat/clear');
      setMessages([]);
      setSuggestion(null);
      setPendingAction(null);
      setPlanSuggestion(null);
      setSessionId(createSessionId());
      onAgentSync?.(['chat', 'history']);
    } catch (error) {
      Alert.alert('Không xóa được lịch sử', error.message);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 92 : 0}
    >
      <View style={styles.header}>
        <View>
          <Text style={styles.kicker}>{mode.shortLabel.toUpperCase()} MODE</Text>
          <Text style={styles.title}>FlowMate Agent</Text>
        </View>
        <View style={styles.headerActions}>
          <Button title="Lịch sử" variant="secondary" onPress={showSessions} />
          <Button title="Chat mới" variant="secondary" onPress={startNewChat} />
        </View>
      </View>
      <View style={styles.listWrap}>
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          refreshing={refreshing}
          onRefresh={loadHistory}
          onScroll={handleMessagesScroll}
          scrollEventThrottle={100}
          onContentSizeChange={() => {
            if (isAtBottom) listRef.current?.scrollToEnd?.({ animated: false });
          }}
          ListEmptyComponent={
            <EmptyState title="Bắt đầu với FlowMate Agent" detail="Giao việc để agent đọc email, kiểm tra lịch, tóm tắt công việc hoặc chuẩn bị lịch hẹn." />
          }
          renderItem={({ item }) => (
            <View style={[styles.messageRow, item.role === 'user' && styles.messageRowUser]}>
              {item.badge ? <Text style={styles.agentBadge}>{item.badge}</Text> : null}
              <View style={[styles.bubble, item.role === 'user' && styles.bubbleUser]}>
                <Text style={[styles.messageText, item.role === 'user' && styles.messageTextUser]}>
                  {item.text}
                </Text>
                {item.meta ? <Text style={styles.agentMeta}>{item.meta}</Text> : null}
              </View>
            </View>
          )}
        />
        {!isAtBottom && messages.length > 0 ? (
          <TouchableOpacity style={styles.jumpToLatest} onPress={scrollToLatest} activeOpacity={0.85}>
            <Text style={styles.jumpToLatestText}>↓ Mới nhất</Text>
          </TouchableOpacity>
        ) : null}
      </View>

      <View style={styles.quickPrompts}>
        {mode.prompts.map((prompt) => (
          <Text key={prompt} style={styles.quickPrompt} onPress={() => setInput(prompt)}>
            {prompt}
          </Text>
        ))}
      </View>

      {suggestion ? (
        <Card style={styles.suggestion}>
          <Text style={styles.suggestionTitle}>
            {suggestion.action === 'delete'
              ? 'Gợi ý xóa lịch'
              : suggestion.action === 'update'
                ? 'Gợi ý sửa lịch'
                : 'Gợi ý tạo lịch'}
          </Text>
          <Text style={styles.suggestionText}>{suggestion.title || 'Lịch hẹn'}</Text>
          <Text style={styles.suggestionMeta}>
            {suggestion.new_start_time
              ? `${suggestion.start_time || ''} → ${suggestion.new_start_time}`
              : suggestion.start_time || 'Chưa có thời gian'}
          </Text>
          <View style={styles.suggestionActions}>
            <Button
              title={suggestion.action === 'delete' ? 'Xóa lịch' : suggestion.action === 'update' ? 'Cập nhật' : 'Tạo lịch'}
              onPress={createSuggestedSchedule}
              loading={loading}
            />
            <Button title="Bỏ qua" variant="secondary" onPress={() => setSuggestion(null)} />
          </View>
        </Card>
      ) : null}

      {pendingAction ? (
        <Card style={styles.suggestion}>
          <Text style={styles.suggestionTitle}>Xác nhận hành động</Text>
          <Text style={styles.suggestionMeta}>{pendingAction.tool || 'Hành động từ Bob'}</Text>
          <View style={styles.suggestionActions}>
            <Button title="Xác nhận" onPress={confirmPendingAction} loading={loading} />
            <Button title="Bỏ qua" variant="secondary" onPress={() => setPendingAction(null)} disabled={loading} />
          </View>
        </Card>
      ) : null}

      {planSuggestion ? (
        <Card style={styles.suggestion}>
          <Text style={styles.suggestionTitle}>
            Gợi ý lịch cho {planSuggestion.items?.length || 0} hoạt động
          </Text>
          {(planSuggestion.items || []).map((item, index) => (
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
                {item.reason ? <Text style={styles.suggestionMeta}>{item.reason}</Text> : null}
              </View>
            </View>
          ))}
          <View style={styles.suggestionActions}>
            <Button title="Áp dụng lịch đã chọn" onPress={applyDayPlanSuggestion} loading={planLoading} />
            <Button title="Bỏ qua" variant="secondary" onPress={() => setPlanSuggestion(null)} disabled={planLoading} />
          </View>
        </Card>
      ) : null}

      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Nhập tin nhắn..."
          placeholderTextColor={colors.inputPlaceholder}
          multiline
        />
        <Button
          title={loading ? '' : 'Gửi'}
          onPress={sendMessage}
          loading={loading}
          disabled={!input.trim()}
          style={styles.send}
        />
      </View>
      {loading ? <ActivityIndicator style={styles.loading} color={colors.primary} /> : null}
      <Modal visible={sessionsOpen} transparent animationType="slide" onRequestClose={() => setSessionsOpen(false)}>
        <TouchableOpacity style={styles.sessionBackdrop} activeOpacity={1} onPress={() => setSessionsOpen(false)} />
        <View style={styles.sessionSheet}>
          <View style={styles.sessionSheetHeader}>
            <View>
              <Text style={styles.kicker}>ĐỒNG BỘ WEB + APK</Text>
              <Text style={styles.sessionSheetTitle}>Đoạn chat gần đây</Text>
            </View>
            <TouchableOpacity style={styles.sessionClose} onPress={() => setSessionsOpen(false)}>
              <Text style={styles.sessionCloseText}>×</Text>
            </TouchableOpacity>
          </View>
          {sessionsLoading ? <ActivityIndicator color={colors.primary} /> : (
            <FlatList
              data={sessions}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.sessionList}
              ListEmptyComponent={<EmptyState title="Chưa có đoạn chat" detail="Các cuộc trò chuyện mới sẽ xuất hiện ở đây và trên web." />}
              renderItem={({ item }) => (
                <View style={[styles.sessionItem, item.id === sessionId && styles.sessionItemActive]}>
                  <TouchableOpacity style={styles.sessionMain} onPress={() => openSession(item)}>
                    <Text style={styles.sessionTitle} numberOfLines={1}>{item.title || 'Đoạn chat'}</Text>
                    <Text style={styles.sessionMeta} numberOfLines={1}>
                      {item.updated_at || item.created_at || `${item.retention_days || 90} ngày lưu`}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.sessionDelete} onPress={() => deleteSession(item)}>
                    <Text style={styles.sessionDeleteText}>Xóa</Text>
                  </TouchableOpacity>
                </View>
              )}
            />
          )}
          <Button title="Bắt đầu chat mới" onPress={() => { startNewChat(); setSessionsOpen(false); }} />
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1 },
    header: {
      paddingHorizontal: 16,
      paddingVertical: 14,
      backgroundColor: colors.panel,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 10,
    },
    headerActions: { flexDirection: 'row', gap: 8, flexShrink: 1 },
    kicker: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 10, letterSpacing: 1, textTransform: 'uppercase' },
    title: { marginTop: 3, fontSize: 22, fontFamily: 'Poppins_800ExtraBold', color: colors.text },
    listWrap: { flex: 1, position: 'relative' },
    list:  { padding: 16, gap: 10 },
    jumpToLatest: {
      position: 'absolute',
      bottom: 12,
      alignSelf: 'center',
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: 999,
      backgroundColor: colors.primary,
      ...colors.shadow,
    },
    jumpToLatestText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 12 },
    messageRow:     { alignItems: 'flex-start' },
    messageRowUser: { alignItems: 'flex-end' },
    agentBadge: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 10, letterSpacing: 0.5, marginBottom: 4, textTransform: 'uppercase' },
    agentMeta: { marginTop: 8, color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 10 },
    bubble: {
      maxWidth: '86%',
      paddingHorizontal: 14,
      paddingVertical: 11,
      borderRadius: 12,
      borderBottomLeftRadius: 4,
      backgroundColor: colors.panelSoft,
      borderColor: colors.border,
      borderWidth: 1,
    },
    bubbleUser: {
      backgroundColor: colors.primary,
      borderColor: colors.primary,
      borderBottomLeftRadius: 12,
      borderBottomRightRadius: 4,
    },
    messageText:     { color: colors.text, fontFamily: 'Poppins_400Regular', fontSize: 13, lineHeight: 19 },
    messageTextUser: { color: '#ffffff' },
    suggestion: { marginHorizontal: 16, marginBottom: 8 },
    suggestionTitle: { color: colors.text, fontFamily: 'Poppins_700Bold' },
    suggestionText:  { marginTop: 5, color: colors.text, fontFamily: 'Poppins_500Medium' },
    suggestionMeta:  { marginTop: 4, color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 12 },
    suggestionActions: { flexDirection: 'row', gap: 8, marginTop: 10 },
    planItem: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 8,
      paddingTop: 10,
      marginTop: 10,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    planItemMuted: { opacity: 0.52 },
    planItemBody: { flex: 1, minWidth: 0 },
    planTimeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    planTimeField: { flexGrow: 1, flexBasis: '46%', minWidth: 128 },
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
      fontWeight: '600',
      lineHeight: 16,
    },
    checkboxTextChecked: { color: '#ffffff' },
    quickPrompts: { flexDirection: 'row', gap: 8, paddingHorizontal: 12, paddingBottom: 8 },
    quickPrompt: {
      flex: 1,
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.panelSoft,
      color: colors.textMuted,
      fontFamily: 'Poppins_500Medium',
      fontSize: 11,
      textAlign: 'center',
    },
    composer: {
      flexDirection: 'row',
      gap: 10,
      padding: 12,
      backgroundColor: colors.panel,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    input: {
      flex: 1,
      minHeight: 44,
      maxHeight: 110,
      borderRadius: 8,
      borderColor: colors.border,
      borderWidth: 1,
      paddingHorizontal: 12,
      paddingVertical: 10,
      color: colors.text,
      fontFamily: 'Poppins_400Regular',
      fontSize: 13,
      backgroundColor: colors.panelSoft,
    },
    send:    { alignSelf: 'flex-end', minWidth: 64 },
    loading: { position: 'absolute', right: 24, top: 18 },
    sessionBackdrop: { flex: 1, backgroundColor: 'rgba(10,15,30,0.42)' },
    sessionSheet: {
      maxHeight: '76%',
      padding: 18,
      paddingBottom: 24,
      borderTopLeftRadius: 26,
      borderTopRightRadius: 26,
      backgroundColor: colors.panel,
      gap: 14,
    },
    sessionSheetHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    sessionSheetTitle: { color: colors.text, fontFamily: 'Poppins_800ExtraBold', fontSize: 22 },
    sessionClose: { width: 38, height: 38, borderRadius: 12, backgroundColor: colors.panelSoft, alignItems: 'center', justifyContent: 'center' },
    sessionCloseText: { color: colors.text, fontSize: 25, lineHeight: 28 },
    sessionList: { gap: 8, paddingVertical: 2 },
    sessionItem: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: 16, backgroundColor: colors.panelSoft, padding: 12 },
    sessionItemActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
    sessionMain: { flex: 1, minWidth: 0 },
    sessionTitle: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    sessionMeta: { marginTop: 3, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 10 },
    sessionDelete: { paddingHorizontal: 10, paddingVertical: 7 },
    sessionDeleteText: { color: colors.danger, fontFamily: 'Poppins_600SemiBold', fontSize: 11 },
  });
}
