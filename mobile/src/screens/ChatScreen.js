import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, FlatList, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import { apiGet, apiPost } from '../api/client';
import { useTheme } from '../theme/ThemeContext';
import { getUserMode } from '../config/userModes';
import ModeBrief from '../components/ModeBrief';

function mapHistoryItem(item) {
  return [
    { id: `${item.id}-u`, role: 'user',      text: item.user_message },
    { id: `${item.id}-a`, role: 'assistant', text: item.assistant_response },
  ];
}

export default function ChatScreen({ userMode = 'worker' }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [messages, setMessages] = useState([]);
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
      Alert.alert('Loi tai lich su chat', error.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMessage = { id: `u-${Date.now()}`, role: 'user', text };
    setMessages((current) => [...current, userMessage]);
    setInput('');
    setLoading(true);
    setSuggestion(null);

    try {
      const data = await apiPost('/chat/message', { message: text, mode: userMode });
      const assistantMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: data.response || 'Khong co phan hoi.',
      };
      setMessages((current) => [...current, assistantMessage]);
      if (data.schedule_suggestion) setSuggestion(data.schedule_suggestion);
      if (data.schedule_created) Alert.alert('Da tao lich', data.schedule_created.title || 'Lich hen moi');
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: `e-${Date.now()}`, role: 'assistant', text: `Loi ket noi: ${error.message}` },
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
        Alert.alert('Da tao lich', data.message || 'Lich hen da duoc tao.');
        setSuggestion(null);
      }
    } catch (error) {
      Alert.alert('Khong tao duoc lich', error.message);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = async () => {
    try {
      await apiPost('/chat/clear');
      setMessages([]);
      setSuggestion(null);
    } catch (error) {
      Alert.alert('Khong xoa duoc lich su', error.message);
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
          <Text style={styles.title}>FlowMate AI</Text>
        </View>
        <Button title="Xoa" variant="secondary" onPress={clearChat} />
      </View>
      <ModeBrief
        userMode={userMode}
        stats={[
          { value: messages.filter((item) => item.role === 'assistant').length, label: 'AI phan hoi' },
          { value: suggestion ? 1 : 0, label: 'Goi y lich' },
          { value: mode.prompts.length, label: 'Prompt nhanh' },
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
          <EmptyState title="Bat dau voi FlowMate AI" detail="Hoi ve email, lich hen, cong viec hoac ke hoach cua ban." />
        }
        renderItem={({ item }) => (
          <View style={[styles.messageRow, item.role === 'user' && styles.messageRowUser]}>
            <View style={[styles.bubble, item.role === 'user' && styles.bubbleUser]}>
              <Text style={[styles.messageText, item.role === 'user' && styles.messageTextUser]}>
                {item.text}
              </Text>
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
          <Text style={styles.suggestionTitle}>Goi y tao lich</Text>
          <Text style={styles.suggestionText}>{suggestion.title || 'Lich hen'}</Text>
          <Text style={styles.suggestionMeta}>{suggestion.start_time || 'Chua co thoi gian'}</Text>
          <View style={styles.suggestionActions}>
            <Button title="Tao lich" onPress={createSuggestedSchedule} loading={loading} />
            <Button title="Bo qua" variant="secondary" onPress={() => setSuggestion(null)} />
          </View>
        </Card>
      ) : null}

      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Nhap tin nhan..."
          placeholderTextColor={colors.inputPlaceholder}
          multiline
        />
        <Button
          title={loading ? '' : 'Gui'}
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
    },
    kicker: { color: colors.accentText, fontSize: 10, fontWeight: '900', letterSpacing: 1 },
    title: { marginTop: 3, fontSize: 22, fontWeight: '800', color: colors.text },
    list:  { padding: 16, gap: 10 },
    messageRow:     { alignItems: 'flex-start' },
    messageRowUser: { alignItems: 'flex-end' },
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
