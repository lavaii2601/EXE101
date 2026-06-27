import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, FlatList, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import { apiGet, apiPost } from '../api/client';
import { useTheme } from '../theme/ThemeContext';
import { getUserMode } from '../config/userModes';
import ModeBrief from '../components/ModeBrief';
import { takePendingAgentNotice } from '../state/agentNotices';

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
  };
  const parts = [];
  if (trace.intent || data?.intent?.intent) {
    parts.push(trace.intent || data.intent.intent);
  }
  if (sources.length) {
    parts.push(`Nguồn: ${sources.map((source) => sourceLabels[source] || source).join(' + ')}`);
  }
  if (trace.requires_confirmation || data?.schedule_suggestion) {
    parts.push('Cần xác nhận');
  }
  return parts.join(' · ');
}

export default function ChatScreen({ userMode = 'worker' }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(() => createSessionId());
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
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
    })();
  }, [loadHistory]);

  const startNewChat = () => {
    setSessionId(createSessionId());
    setMessages([]);
    setSuggestion(null);
    setInput('');
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMessage = { id: `u-${Date.now()}`, role: 'user', text };
    setMessages((current) => [...current, userMessage]);
    setInput('');
    setLoading(true);
    setSuggestion(null);

    try {
      const data = await apiPost('/chat/message', {
        message: text,
        mode: userMode,
        session_id: sessionId,
      });
      const assistantMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: data.response || 'Không có phản hồi.',
        badge: 'AI Agent',
        meta: formatAgentMeta(data),
      };
      setMessages((current) => [...current, assistantMessage]);
      if (data.schedule_suggestion) setSuggestion(data.schedule_suggestion);
      if (data.schedule_created) Alert.alert('Đã tạo lịch', data.schedule_created.title || 'Lịch hẹn mới');
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: `e-${Date.now()}`, role: 'assistant', text: `Lỗi kết nối: ${error.message}` },
      ]);
    } finally {
      setLoading(false);
      requestAnimationFrame(() => listRef.current?.scrollToEnd?.({ animated: true }));
    }
  };

  const createSuggestedSchedule = async () => {
    if (!suggestion) return;
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
      }
    } catch (error) {
      Alert.alert('Không tạo được lịch', error.message);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = async () => {
    try {
      await apiPost('/chat/clear');
      setMessages([]);
      setSuggestion(null);
      setSessionId(createSessionId());
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
          <Button title="Chat mới" variant="secondary" onPress={startNewChat} />
          <Button title="Xóa" variant="secondary" onPress={clearChat} />
        </View>
      </View>
      <ModeBrief
        userMode={userMode}
        stats={[
          { value: messages.filter((item) => item.role === 'assistant').length, label: 'AI phản hồi' },
          { value: suggestion ? 1 : 0, label: 'Gợi ý lịch' },
          { value: mode.prompts.length, label: 'Lệnh agent' },
        ]}
      />

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshing={refreshing}
        onRefresh={loadHistory}
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

      <View style={styles.quickPrompts}>
        {mode.prompts.map((prompt) => (
          <Text key={prompt} style={styles.quickPrompt} onPress={() => setInput(prompt)}>
            {prompt}
          </Text>
        ))}
      </View>

      {suggestion ? (
        <Card style={styles.suggestion}>
          <Text style={styles.suggestionTitle}>Gợi ý tạo lịch</Text>
          <Text style={styles.suggestionText}>{suggestion.title || 'Lịch hẹn'}</Text>
          <Text style={styles.suggestionMeta}>{suggestion.start_time || 'Chưa có thời gian'}</Text>
          <View style={styles.suggestionActions}>
            <Button title="Tạo lịch" onPress={createSuggestedSchedule} loading={loading} />
            <Button title="Bỏ qua" variant="secondary" onPress={() => setSuggestion(null)} />
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
    </KeyboardAvoidingView>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1 },
    header: {
      paddingHorizontal: 16,
      paddingVertical: 12,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 10,
    },
    headerActions: { flexDirection: 'row', gap: 8 },
    kicker: { color: colors.accentText, fontSize: 10, fontWeight: '900', letterSpacing: 1 },
    title: { marginTop: 3, fontSize: 22, fontWeight: '800', color: colors.text },
    list:  { padding: 16, gap: 10 },
    messageRow:     { alignItems: 'flex-start' },
    messageRowUser: { alignItems: 'flex-end' },
    agentBadge: { color: colors.accentText, fontSize: 10, fontWeight: '900', letterSpacing: 0.5, marginBottom: 4 },
    agentMeta: { marginTop: 8, color: colors.textMuted, fontSize: 10, fontWeight: '700' },
    bubble: {
      maxWidth: '86%',
      paddingHorizontal: 14,
      paddingVertical: 11,
      borderRadius: 16,
      borderBottomLeftRadius: 5,
      backgroundColor: colors.panelSoft,
      borderColor: colors.border,
      borderWidth: 1,
    },
    bubbleUser: {
      backgroundColor: colors.primary,
      borderColor: colors.primary,
      borderBottomLeftRadius: 16,
      borderBottomRightRadius: 5,
    },
    messageText:     { color: colors.text, lineHeight: 21 },
    messageTextUser: { color: '#ffffff' },
    suggestion: { marginHorizontal: 16, marginBottom: 8 },
    suggestionTitle: { color: colors.text, fontWeight: '800' },
    suggestionText:  { marginTop: 5, color: colors.text },
    suggestionMeta:  { marginTop: 4, color: colors.textMuted, fontSize: 12 },
    suggestionActions: { flexDirection: 'row', gap: 8, marginTop: 10 },
    quickPrompts: { flexDirection: 'row', gap: 8, paddingHorizontal: 12, paddingBottom: 8 },
    quickPrompt: {
      flex: 1,
      paddingHorizontal: 10,
      paddingVertical: 8,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.panelSoft,
      color: colors.textMuted,
      fontSize: 10,
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
      minHeight: 46,
      maxHeight: 110,
      borderRadius: 22,
      borderColor: colors.border,
      borderWidth: 1,
      paddingHorizontal: 12,
      paddingVertical: 10,
      color: colors.text,
      backgroundColor: colors.panel,
    },
    send:    { alignSelf: 'flex-end', minWidth: 64 },
    loading: { position: 'absolute', right: 24, top: 18 },
  });
}
