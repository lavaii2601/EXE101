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
          <Card key={item.id}>
            <View style={styles.row}>
              <Text style={styles.type}>{labels[item.action_type] || item.action_type}</Text>
              <Text style={styles.date}>{formatDate(item.created_at)}</Text>
            </View>
            <Text style={styles.message} numberOfLines={3}>
              {item.user_message || item.assistant_response}
            </Text>
          </Card>
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
    row:     { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
    type:    { flex: 1, color: colors.text, fontWeight: '800' },
    date:    { color: colors.textMuted, fontSize: 12 },
    message: { marginTop: 8, color: colors.textMuted, lineHeight: 20 },
  });
}
