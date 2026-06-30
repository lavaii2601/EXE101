import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import Button from '../components/Button';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Screen from '../components/Screen';
import { apiGet, apiPost } from '../api/client';
import { useTheme } from '../theme/ThemeContext';

const labels = {
  chat:                   'Chat',
  email_summary:          'Tóm tắt email',
  email_reply:            'Tạo trả lời email',
  email_sent:             'Gửi email',
  email_daily_summary:    'Báo cáo email',
  schedule_created:       'Tạo lịch',
  schedule_updated:       'Sửa lịch',
  schedule_deleted:       'Xóa lịch',
  calendar_event_created: 'Tạo Google Calendar',
  calendar_event_deleted: 'Xóa Google Calendar',
};

export default function HistoryScreen({ syncEvent }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [history, setHistory] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadHistory = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await apiGet('/chat/history?limit=50');
      setHistory(data.history || []);
    } catch (error) {
      Alert.alert('Lỗi tải lịch sử', error.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);
  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['history', 'chat', 'email', 'schedule', 'calendar', 'settings'])) {
      loadHistory();
    }
  }, [loadHistory, syncEvent]);

  const clearAll = async () => {
    try {
      await apiPost('/chat/clear-all');
      setHistory([]);
    } catch (error) {
      Alert.alert('Không xóa được lịch sử', error.message);
    }
  };

  return (
    <Screen
      title="Lịch sử"
      refreshing={refreshing}
      onRefresh={loadHistory}
      actions={<Button title="Xóa hết" variant="secondary" onPress={clearAll} />}
    >
      {history.length === 0 ? (
        <EmptyState title="Chưa có hoạt động" detail="Các lần chat, gửi email và tạo lịch sẽ hiện ở đây." />
      ) : (
        history.map((item) => (
          <View key={item.id} style={styles.timelineRow}>
            <View style={styles.timelineRail}>
              <View style={styles.dot} />
              <View style={styles.line} />
            </View>
            <Card style={styles.card}>
              <View style={styles.row}>
                <Text style={styles.type}>{labels[item.action_type] || item.action_type}</Text>
                <Text style={styles.date}>{formatDate(item.created_at)}</Text>
              </View>
              <Text style={styles.message} numberOfLines={3}>
                {item.user_message || item.assistant_response}
              </Text>
            </Card>
          </View>
        ))
      )}
    </Screen>
  );
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('vi-VN');
}

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
}

function makeStyles(colors) {
  return StyleSheet.create({
    timelineRow: { flexDirection: 'row', gap: 12 },
    timelineRail: { width: 8, alignItems: 'center' },
    dot: { width: 8, height: 8, borderRadius: 4, marginTop: 6, backgroundColor: colors.primary },
    line: { flex: 1, width: 1, marginTop: 4, backgroundColor: colors.border },
    card: { flex: 1, marginBottom: 4 },
    row:     { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
    type: {
      color: colors.primary,
      fontFamily: 'Poppins_700Bold',
      fontSize: 11,
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 999,
      backgroundColor: colors.primarySoft,
      overflow: 'hidden',
    },
    date:    { color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 12 },
    message: { marginTop: 8, color: colors.textMuted, fontFamily: 'Poppins_400Regular', lineHeight: 20 },
  });
}
