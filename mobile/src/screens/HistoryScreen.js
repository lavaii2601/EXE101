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
  email_summary:          'Tom tat email',
  email_reply:            'Tao tra loi email',
  email_sent:             'Gui email',
  email_daily_summary:    'Bao cao email',
  schedule_created:       'Tao lich',
  schedule_updated:       'Sua lich',
  schedule_deleted:       'Xoa lich',
  calendar_event_created: 'Tao Google Calendar',
  calendar_event_deleted: 'Xoa Google Calendar',
};

export default function HistoryScreen() {
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
      Alert.alert('Loi tai lich su', error.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const clearAll = async () => {
    try {
      await apiPost('/chat/clear-all');
      setHistory([]);
    } catch (error) {
      Alert.alert('Khong xoa duoc lich su', error.message);
    }
  };

  return (
    <Screen
      title="Lich su"
      refreshing={refreshing}
      onRefresh={loadHistory}
      actions={<Button title="Xoa het" variant="secondary" onPress={clearAll} />}
    >
      {history.length === 0 ? (
        <EmptyState title="Chua co hoat dong" detail="Cac lan chat, gui email va tao lich se hien o day." />
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

function makeStyles(colors) {
  return StyleSheet.create({
    row:     { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
    type:    { flex: 1, color: colors.text, fontWeight: '800' },
    date:    { color: colors.textMuted, fontSize: 12 },
    message: { marginTop: 8, color: colors.textMuted, lineHeight: 20 },
  });
}
