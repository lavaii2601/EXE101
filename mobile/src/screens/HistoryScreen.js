import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Screen from '../components/Screen';
import { apiGet, apiPost } from '../api/client';
import { useLanguage } from '../i18n/LanguageContext';
import { useTheme } from '../theme/ThemeContext';

const actionMeta = {
  chat: {
    label: ['Trao đổi với AI', 'AI conversation'],
    icon: 'sparkles-outline',
    category: 'ai',
    source: ['Bob AI', 'Bob AI'],
  },
  email_summary: {
    label: ['AI tóm tắt email', 'AI summarized email'],
    icon: 'document-text-outline',
    category: 'email',
    source: ['Email · Bob AI', 'Email · Bob AI'],
  },
  email_reply: {
    label: ['AI soạn trả lời', 'AI drafted a reply'],
    icon: 'create-outline',
    category: 'email',
    source: ['Email · Bob AI', 'Email · Bob AI'],
  },
  email_sent: {
    label: ['Đã gửi email', 'Email sent'],
    icon: 'paper-plane-outline',
    category: 'email',
    source: ['Email', 'Email'],
  },
  email_daily_summary: {
    label: ['AI tạo báo cáo email', 'AI created email report'],
    icon: 'analytics-outline',
    category: 'email',
    source: ['Email · Bob AI', 'Email · Bob AI'],
  },
  schedule_created: {
    label: ['Đã tạo lịch', 'Schedule created'],
    icon: 'calendar-outline',
    category: 'calendar',
    source: ['Lịch', 'Calendar'],
  },
  schedule_updated: {
    label: ['Đã cập nhật lịch', 'Schedule updated'],
    icon: 'calendar-clear-outline',
    category: 'calendar',
    source: ['Lịch', 'Calendar'],
  },
  schedule_deleted: {
    label: ['Đã xóa lịch', 'Schedule deleted'],
    icon: 'calendar-number-outline',
    category: 'calendar',
    source: ['Lịch', 'Calendar'],
  },
  calendar_event_created: {
    label: ['Đã tạo sự kiện Google', 'Google event created'],
    icon: 'calendar-outline',
    category: 'calendar',
    source: ['Google Calendar', 'Google Calendar'],
  },
  calendar_event_updated: {
    label: ['Đã cập nhật sự kiện Google', 'Google event updated'],
    icon: 'calendar-clear-outline',
    category: 'calendar',
    source: ['Google Calendar', 'Google Calendar'],
  },
  calendar_event_deleted: {
    label: ['Đã xóa sự kiện Google', 'Google event deleted'],
    icon: 'calendar-number-outline',
    category: 'calendar',
    source: ['Google Calendar', 'Google Calendar'],
  },
  settings_updated: {
    label: ['AI cập nhật tùy chọn', 'AI updated preferences'],
    icon: 'options-outline',
    category: 'ai',
    source: ['Cài đặt · Bob AI', 'Settings · Bob AI'],
  },
  system: {
    label: ['Sự kiện hệ thống', 'System event'],
    icon: 'hardware-chip-outline',
    category: 'ai',
    source: ['Hệ thống', 'System'],
  },
};

const filterOptions = [
  { key: 'all', label: ['Tất cả', 'All'] },
  { key: 'ai', label: ['AI', 'AI'] },
  { key: 'email', label: ['Email', 'Email'] },
  { key: 'calendar', label: ['Lịch', 'Calendar'] },
];

export default function HistoryScreen({ syncEvent }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [history, setHistory] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState('all');
  const [expandedId, setExpandedId] = useState(null);

  const loadHistory = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await apiGet('/chat/history?limit=50');
      setHistory(data.history || []);
    } catch (error) {
      Alert.alert(t('Lỗi tải nhật ký', 'Could not load audit log'), error.message);
    } finally {
      setRefreshing(false);
    }
  }, [t]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['history', 'chat', 'email', 'schedule', 'calendar', 'settings'])) {
      loadHistory();
    }
  }, [loadHistory, syncEvent]);

  const clearAll = useCallback(() => {
    Alert.alert(
      t('Xóa toàn bộ audit log?', 'Clear the entire audit log?'),
      t(
        'Hành động này sẽ xóa lịch sử chat, email và lịch đã ghi nhận.',
        'This removes recorded chat, email, and calendar activity.'
      ),
      [
        { text: t('Hủy', 'Cancel'), style: 'cancel' },
        {
          text: t('Xóa', 'Clear'),
          style: 'destructive',
          onPress: async () => {
            try {
              await apiPost('/chat/clear-all');
              setHistory([]);
              setExpandedId(null);
            } catch (error) {
              Alert.alert(t('Không xóa được nhật ký', 'Could not clear audit log'), error.message);
            }
          },
        },
      ]
    );
  }, [t]);

  const visibleHistory = useMemo(() => history.filter((item) => {
    if (filter === 'all') return true;
    const category = getMeta(item.action_type).category;
    if (filter === 'ai') {
      return category === 'ai'
        || ['email_summary', 'email_reply', 'email_daily_summary'].includes(item.action_type);
    }
    return category === filter;
  }), [filter, history]);

  const groups = useMemo(() => groupByDay(visibleHistory, t), [t, visibleHistory]);

  const auditAction = history.length ? (
    <TouchableOpacity
      style={styles.clearButton}
      onPress={clearAll}
      accessibilityRole="button"
      accessibilityLabel={t('Xóa audit log', 'Clear audit log')}
      activeOpacity={0.8}
    >
      <Ionicons name="trash-outline" size={18} color={colors.danger} />
    </TouchableOpacity>
  ) : null;

  return (
    <Screen
      title="AI Audit Log"
      refreshing={refreshing}
      onRefresh={loadHistory}
      actions={auditAction}
    >
      <Card style={styles.overviewCard}>
        <View style={styles.overviewIcon}>
          <Ionicons name="shield-checkmark-outline" size={23} color={colors.primary} />
        </View>
        <View style={styles.overviewBody}>
          <Text style={styles.overviewTitle}>
            {t('Nhật ký quyết định & hành động', 'Decisions & actions log')}
          </Text>
          <Text style={styles.overviewText}>
            {t(
              `${history.length} sự kiện gần nhất của Bob và các kết nối`,
              `${history.length} recent events from Bob and connected services`
            )}
          </Text>
        </View>
        <View style={styles.livePill}>
          <View style={styles.liveDot} />
          <Text style={styles.liveText}>{t('Đang ghi', 'Live')}</Text>
        </View>
      </Card>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filters}
      >
        {filterOptions.map((option) => {
          const active = option.key === filter;
          const count = countForFilter(history, option.key);
          return (
            <TouchableOpacity
              key={option.key}
              style={[styles.filterChip, active && styles.filterChipActive]}
              onPress={() => setFilter(option.key)}
              activeOpacity={0.82}
            >
              <Text style={[styles.filterText, active && styles.filterTextActive]}>
                {t(...option.label)}
              </Text>
              <View style={[styles.countBadge, active && styles.countBadgeActive]}>
                <Text style={[styles.countText, active && styles.countTextActive]}>{count}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {visibleHistory.length === 0 ? (
        <EmptyState
          title={t('Chưa có sự kiện', 'No events yet')}
          detail={filter === 'all'
            ? t(
              'Các quyết định và hành động của Bob sẽ được ghi nhận tại đây.',
              'Bob’s decisions and actions will be recorded here.'
            )
            : t('Không có sự kiện phù hợp với bộ lọc này.', 'No events match this filter.')}
        />
      ) : (
        groups.map((group) => (
          <View key={group.key} style={styles.dayGroup}>
            <View style={styles.dayHeader}>
              <Text style={styles.dayLabel}>{group.label}</Text>
              <View style={styles.dayLine} />
              <Text style={styles.dayCount}>
                {t(`${group.items.length} sự kiện`, `${group.items.length} events`)}
              </Text>
            </View>
            {group.items.map((item) => (
              <AuditEvent
                key={item.id}
                item={item}
                expanded={expandedId === item.id}
                onToggle={() => setExpandedId((current) => current === item.id ? null : item.id)}
                colors={colors}
                styles={styles}
                t={t}
              />
            ))}
          </View>
        ))
      )}
    </Screen>
  );
}

function AuditEvent({ item, expanded, onToggle, colors, styles, t }) {
  const meta = getMeta(item.action_type);
  const title = t(...meta.label);
  const input = cleanText(item.user_message);
  const output = cleanText(item.assistant_response);

  return (
    <TouchableOpacity
      style={styles.eventRow}
      onPress={onToggle}
      activeOpacity={0.86}
      accessibilityRole="button"
      accessibilityState={{ expanded }}
    >
      <View style={styles.eventRail}>
        <View style={styles.eventIcon}>
          <Ionicons name={meta.icon} size={17} color={colors.primary} />
        </View>
        <View style={styles.railLine} />
      </View>
      <Card style={styles.eventCard}>
        <View style={styles.eventTop}>
          <View style={styles.eventHeading}>
            <Text style={styles.eventTitle}>{title}</Text>
            <Text style={styles.eventSource}>{t(...meta.source)}</Text>
          </View>
          <View style={styles.eventTimeWrap}>
            <Text style={styles.eventTime}>
              {formatTime(item.created_at, t('vi-VN', 'en-US'))}
            </Text>
            <Ionicons
              name={expanded ? 'chevron-up' : 'chevron-down'}
              size={15}
              color={colors.textMuted}
            />
          </View>
        </View>

        <Text style={styles.eventPreview} numberOfLines={expanded ? undefined : 2}>
          {input || output || t('Sự kiện đã được ghi nhận.', 'Event recorded.')}
        </Text>

        <View style={styles.eventFooter}>
          <View style={styles.recordedPill}>
            <Ionicons name="checkmark-circle" size={13} color={colors.success} />
            <Text style={styles.recordedText}>{t('Đã ghi nhận', 'Recorded')}</Text>
          </View>
          <Text style={styles.eventId}>ID #{String(item.id).padStart(4, '0')}</Text>
        </View>

        {expanded ? (
          <View style={styles.detailBox}>
            {input ? (
              <AuditDetail
                label={t('Yêu cầu / Ngữ cảnh', 'Request / Context')}
                value={input}
                styles={styles}
              />
            ) : null}
            {output ? (
              <AuditDetail
                label={t('Kết quả của AI', 'AI output')}
                value={output}
                styles={styles}
              />
            ) : null}
            {item.related_id ? (
              <AuditDetail
                label={t('Tham chiếu', 'Reference')}
                value={String(item.related_id)}
                styles={styles}
              />
            ) : null}
            <AuditDetail
              label={t('Dấu thời gian', 'Timestamp')}
              value={formatDateTime(item.created_at, t('vi-VN', 'en-US'))}
              styles={styles}
              last
            />
          </View>
        ) : null}
      </Card>
    </TouchableOpacity>
  );
}

function AuditDetail({ label, value, styles, last }) {
  return (
    <View style={[styles.detailRow, last && styles.detailRowLast]}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

function getMeta(actionType) {
  return actionMeta[actionType] || {
    label: [humanize(actionType), humanize(actionType)],
    icon: 'pulse-outline',
    category: 'ai',
    source: ['Bob AI', 'Bob AI'],
  };
}

function countForFilter(history, filter) {
  if (filter === 'all') return history.length;
  return history.filter((item) => {
    const category = getMeta(item.action_type).category;
    if (filter === 'ai') {
      return category === 'ai'
        || ['email_summary', 'email_reply', 'email_daily_summary'].includes(item.action_type);
    }
    return category === filter;
  }).length;
}

function groupByDay(items, t) {
  const today = dayKey(new Date());
  const yesterdayDate = new Date();
  yesterdayDate.setDate(yesterdayDate.getDate() - 1);
  const yesterday = dayKey(yesterdayDate);
  const groups = [];

  items.forEach((item) => {
    const date = new Date(item.created_at);
    const key = Number.isNaN(date.getTime()) ? 'unknown' : dayKey(date);
    let group = groups.find((entry) => entry.key === key);
    if (!group) {
      let label;
      if (key === today) label = t('Hôm nay', 'Today');
      else if (key === yesterday) label = t('Hôm qua', 'Yesterday');
      else if (key === 'unknown') label = t('Không rõ ngày', 'Unknown date');
      else label = date.toLocaleDateString(t('vi-VN', 'en-US'), {
        weekday: 'short',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      });
      group = { key, label, items: [] };
      groups.push(group);
    }
    group.items.push(item);
  });
  return groups;
}

function dayKey(date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function cleanText(value) {
  return String(value || '').trim();
}

function humanize(value) {
  const text = String(value || 'activity').replace(/_/g, ' ').trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatTime(value, locale) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
}

function formatDateTime(value, locale) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || '');
  return date.toLocaleString(locale);
}

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
}

function makeStyles(colors) {
  return StyleSheet.create({
    clearButton: {
      width: 42,
      height: 42,
      borderRadius: 13,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: `${colors.danger}12`,
      borderWidth: 1,
      borderColor: `${colors.danger}24`,
    },
    overviewCard: {
      flexDirection: 'row',
      alignItems: 'center',
      padding: 14,
      borderRadius: 18,
    },
    overviewIcon: {
      width: 44,
      height: 44,
      borderRadius: 14,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.primarySoft,
      marginRight: 11,
    },
    overviewBody: { flex: 1, paddingRight: 8 },
    overviewTitle: {
      color: colors.text,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 13,
    },
    overviewText: {
      color: colors.textMuted,
      fontFamily: 'Poppins_400Regular',
      fontSize: 10.5,
      lineHeight: 16,
      marginTop: 1,
    },
    livePill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 5,
      paddingHorizontal: 8,
      paddingVertical: 5,
      borderRadius: 999,
      backgroundColor: `${colors.success}12`,
    },
    liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success },
    liveText: {
      color: colors.success,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 9.5,
    },
    filters: { gap: 8, paddingRight: 16 },
    filterChip: {
      minHeight: 38,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 7,
      paddingHorizontal: 13,
      borderRadius: 12,
      backgroundColor: colors.panel,
      borderWidth: 1,
      borderColor: colors.border,
    },
    filterChipActive: {
      backgroundColor: colors.primary,
      borderColor: colors.primary,
    },
    filterText: {
      color: colors.textMuted,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 11.5,
    },
    filterTextActive: { color: '#FFFFFF' },
    countBadge: {
      minWidth: 20,
      height: 20,
      paddingHorizontal: 5,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 10,
      backgroundColor: colors.panelSoft,
    },
    countBadgeActive: { backgroundColor: 'rgba(255,255,255,0.18)' },
    countText: {
      color: colors.textMuted,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 9,
    },
    countTextActive: { color: '#FFFFFF' },
    dayGroup: { gap: 9 },
    dayHeader: { flexDirection: 'row', alignItems: 'center', gap: 9, marginTop: 2 },
    dayLabel: {
      color: colors.text,
      fontFamily: 'Poppins_700Bold',
      fontSize: 12,
    },
    dayLine: { height: 1, flex: 1, backgroundColor: colors.border },
    dayCount: {
      color: colors.textMuted,
      fontFamily: 'Poppins_500Medium',
      fontSize: 9.5,
    },
    eventRow: { flexDirection: 'row', alignItems: 'stretch' },
    eventRail: { width: 38, alignItems: 'center' },
    eventIcon: {
      width: 32,
      height: 32,
      borderRadius: 11,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.primarySoft,
      borderWidth: 1,
      borderColor: `${colors.primary}22`,
      zIndex: 1,
    },
    railLine: { width: 1, flex: 1, minHeight: 16, backgroundColor: colors.border },
    eventCard: {
      flex: 1,
      padding: 13,
      borderRadius: 16,
      marginBottom: 2,
    },
    eventTop: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
    eventHeading: { flex: 1 },
    eventTitle: {
      color: colors.text,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 12.5,
    },
    eventSource: {
      color: colors.textMuted,
      fontFamily: 'Poppins_400Regular',
      fontSize: 9.5,
      marginTop: 1,
    },
    eventTimeWrap: { flexDirection: 'row', alignItems: 'center', gap: 4 },
    eventTime: {
      color: colors.textMuted,
      fontFamily: 'Poppins_500Medium',
      fontSize: 10.5,
    },
    eventPreview: {
      marginTop: 9,
      color: colors.textMuted,
      fontFamily: 'Poppins_400Regular',
      fontSize: 11,
      lineHeight: 18,
    },
    eventFooter: {
      marginTop: 10,
      paddingTop: 9,
      borderTopWidth: 1,
      borderTopColor: colors.border,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    recordedPill: { flexDirection: 'row', alignItems: 'center', gap: 4 },
    recordedText: {
      color: colors.success,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 9.5,
    },
    eventId: {
      color: colors.textMuted,
      fontFamily: 'Poppins_500Medium',
      fontSize: 9,
    },
    detailBox: {
      marginTop: 11,
      padding: 11,
      borderRadius: 12,
      backgroundColor: colors.panelSoft,
    },
    detailRow: {
      paddingBottom: 9,
      marginBottom: 9,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    detailRowLast: { paddingBottom: 0, marginBottom: 0, borderBottomWidth: 0 },
    detailLabel: {
      color: colors.textMuted,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 9,
      textTransform: 'uppercase',
      letterSpacing: 0.45,
      marginBottom: 3,
    },
    detailValue: {
      color: colors.text,
      fontFamily: 'Poppins_400Regular',
      fontSize: 10.5,
      lineHeight: 17,
    },
  });
}
