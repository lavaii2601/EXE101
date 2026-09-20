import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { apiGet } from '../api/client';
import { useLanguage } from '../i18n/LanguageContext';
import { useOrgWorkspace } from '../state/OrgWorkspaceContext';
import { radius, useTheme } from '../theme/ThemeContext';
import SharingCenterScreen from './SharingCenterScreen';
import StatusReportsScreen from './StatusReportsScreen';
import WorkHubScreen from './WorkHubScreen';
import WorkspaceKnowledgeScreen from './WorkspaceKnowledgeScreen';
import WorkspaceMembersScreen from './WorkspaceMembersScreen';

const EMPTY_DASHBOARD = {
  total_projects: 0,
  total_tasks: 0,
  overdue_tasks: 0,
  active_members: 0,
  project_counts: {},
  task_counts: {},
  latest_reports: [],
};

export default function WorkerModeScreen({ syncEvent }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const workspace = useOrgWorkspace();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [dashboard, setDashboard] = useState(EMPTY_DASHBOARD);
  const [loading, setLoading] = useState(false);
  const [openScreen, setOpenScreen] = useState(null);

  const loadDashboard = useCallback(async () => {
    if (!workspace?.isBusiness) {
      setDashboard(EMPTY_DASHBOARD);
      return;
    }
    setLoading(true);
    try {
      const data = await apiGet('/work-hub/dashboard');
      if (data?.success) setDashboard({ ...EMPTY_DASHBOARD, ...(data.dashboard || {}) });
    } catch {
      setDashboard(EMPTY_DASHBOARD);
    } finally {
      setLoading(false);
    }
  }, [workspace?.isBusiness, workspace?.currentWorkspaceId]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['work_hub', 'status_reports', 'workspace_members'])) {
      loadDashboard();
    }
  }, [syncEvent, loadDashboard]);

  const openTasks = Number(dashboard.task_counts?.todo || 0)
    + Number(dashboard.task_counts?.in_progress || 0)
    + Number(dashboard.task_counts?.blocked || 0);
  const closeTool = useCallback(() => {
    setOpenScreen(null);
    loadDashboard();
  }, [loadDashboard]);
  const metrics = [
    { value: dashboard.total_projects || 0, label: t('Dự án', 'Projects'), color: colors.primary },
    { value: openTasks, label: t('Đang làm', 'Open tasks'), color: colors.secondaryText },
    { value: dashboard.overdue_tasks || 0, label: t('Quá hạn', 'Overdue'), color: colors.warning },
    { value: dashboard.active_members || 0, label: t('Thành viên', 'Members'), color: colors.success },
  ];

  const actions = [
    {
      key: 'work',
      icon: 'grid-outline',
      title: t('Dự án & nhiệm vụ', 'Projects & tasks'),
      detail: t('Theo dõi công việc dùng chung', 'Track shared work'),
      color: colors.primary,
    },
    {
      key: 'reports',
      icon: 'document-text-outline',
      title: t('Báo cáo trạng thái', 'Status reports'),
      detail: 'Done / Doing / Blocked / Next / Risks',
      color: colors.success,
    },
    {
      key: 'knowledge',
      icon: 'library-outline',
      title: t('Kiến thức doanh nghiệp', 'Workspace knowledge'),
      detail: t('Policy, quy trình, template và FAQ', 'Policies, processes, templates, and FAQs'),
      color: colors.secondaryText,
    },
    {
      key: 'members',
      icon: 'people-outline',
      title: t('Thành viên', 'Members'),
      detail: t('Vai trò, lời mời và chỗ ngồi', 'Roles, invitations, and seats'),
      color: colors.warning,
    },
  ];

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={styles.body}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={loadDashboard} tintColor={colors.primary} />}
      >
        <View style={styles.hero}>
          <View style={styles.heroIcon}>
            <Ionicons name="briefcase-outline" size={24} color={colors.primary} />
          </View>
          <View style={styles.heroCopy}>
            <Text style={styles.kicker}>WORKER MODE</Text>
            <Text style={styles.title}>{t('Không gian công việc', 'Work Hub')}</Text>
            <Text style={styles.subtitle} numberOfLines={2}>
              {workspace?.current?.name || t('Không gian cá nhân', 'Personal workspace')}
            </Text>
          </View>
          {loading ? <ActivityIndicator color={colors.primary} /> : null}
        </View>

        {!workspace?.isBusiness ? (
          <View style={styles.notice}>
            <Ionicons name="business-outline" size={22} color={colors.secondaryText} />
            <View style={styles.noticeCopy}>
              <Text style={styles.noticeTitle}>{t('Chọn không gian doanh nghiệp', 'Choose a business workspace')}</Text>
              <Text style={styles.noticeText}>
                {t(
                  'Dùng thanh không gian phía trên để mở dự án, báo cáo và kiến thức dùng chung.',
                  'Use the workspace bar above to open shared projects, reports, and knowledge.',
                )}
              </Text>
            </View>
          </View>
        ) : (
          <>
            <View style={styles.metricsGrid}>
              {metrics.map((metric) => (
                <View key={metric.label} style={styles.metricCard}>
                  <View style={[styles.metricDot, { backgroundColor: metric.color }]} />
                  <Text style={styles.metricValue}>{metric.value}</Text>
                  <Text style={styles.metricLabel}>{metric.label}</Text>
                </View>
              ))}
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionLabel}>{t('CÔNG CỤ NHÓM', 'TEAM TOOLS')}</Text>
              {actions.map((action) => (
                <TouchableOpacity
                  key={action.key}
                  style={styles.actionRow}
                  onPress={() => setOpenScreen(action.key)}
                  activeOpacity={0.75}
                >
                  <View style={[styles.actionIcon, { backgroundColor: `${action.color}18` }]}>
                    <Ionicons name={action.icon} size={20} color={action.color} />
                  </View>
                  <View style={styles.actionCopy}>
                    <Text style={styles.actionTitle}>{action.title}</Text>
                    <Text style={styles.actionDetail} numberOfLines={2}>{action.detail}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              ))}
            </View>

            <View style={styles.section}>
              <View style={styles.sectionHeading}>
                <Text style={styles.sectionLabel}>{t('BÁO CÁO GẦN ĐÂY', 'LATEST REPORTS')}</Text>
                <TouchableOpacity onPress={() => setOpenScreen('reports')}>
                  <Text style={styles.seeAll}>{t('Xem tất cả', 'See all')}</Text>
                </TouchableOpacity>
              </View>
              {Array.isArray(dashboard.latest_reports) && dashboard.latest_reports.length ? (
                dashboard.latest_reports.slice(0, 3).map((report) => {
                  const published = report.status === 'published';
                  const statusColor = published ? colors.success : colors.warning;
                  return (
                    <TouchableOpacity key={report.id} style={styles.reportRow} onPress={() => setOpenScreen('reports')}>
                      <View style={[styles.reportIcon, { backgroundColor: `${statusColor}18` }]}>
                        <Ionicons name={published ? 'checkmark-done-outline' : 'create-outline'} size={18} color={statusColor} />
                      </View>
                      <View style={styles.actionCopy}>
                        <Text style={styles.actionTitle}>{report.author_name || report.author_user_id || t('Thành viên', 'Member')}</Text>
                        <Text style={styles.actionDetail}>{report.report_date || ''}</Text>
                      </View>
                      <Text style={[styles.reportStatus, { color: statusColor }]}>
                        {published ? t('Đã công bố', 'Published') : t('Bản nháp', 'Draft')}
                      </Text>
                    </TouchableOpacity>
                  );
                })
              ) : (
                <Text style={styles.emptyText}>{t('Chưa có báo cáo được công bố.', 'No published reports yet.')}</Text>
              )}
            </View>
          </>
        )}

        {workspace?.workspaces?.some((item) => item.type === 'business') ? (
          <TouchableOpacity style={styles.privacyCard} onPress={() => setOpenScreen('sharing')} activeOpacity={0.8}>
            <View style={styles.actionIcon}>
              <Ionicons name="share-social-outline" size={20} color={colors.secondaryText} />
            </View>
            <View style={styles.actionCopy}>
              <Text style={styles.actionTitle}>{t('Trung tâm chia sẻ', 'Sharing Center')}</Text>
              <Text style={styles.actionDetail}>{t('Kiểm soát nội dung cá nhân đã chia sẻ', 'Control personal content you shared')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        ) : null}
      </ScrollView>

      <WorkHubScreen visible={openScreen === 'work'} onClose={closeTool} syncEvent={syncEvent} />
      <StatusReportsScreen visible={openScreen === 'reports'} onClose={closeTool} syncEvent={syncEvent} />
      <WorkspaceKnowledgeScreen visible={openScreen === 'knowledge'} onClose={closeTool} syncEvent={syncEvent} />
      <WorkspaceMembersScreen visible={openScreen === 'members'} onClose={closeTool} syncEvent={syncEvent} />
      <SharingCenterScreen visible={openScreen === 'sharing'} onClose={closeTool} syncEvent={syncEvent} />
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    body: { padding: 16, paddingBottom: 30, gap: 14 },
    hero: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      padding: 16,
      borderRadius: radius.card,
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
      ...colors.shadow,
    },
    heroIcon: { width: 48, height: 48, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft },
    heroCopy: { flex: 1 },
    kicker: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 9.5, letterSpacing: 1.2 },
    title: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 20, marginTop: 2 },
    subtitle: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12, marginTop: 1 },
    notice: {
      flexDirection: 'row',
      gap: 12,
      padding: 16,
      borderRadius: radius.card,
      backgroundColor: colors.secondaryBg,
      borderColor: colors.border,
      borderWidth: 1,
    },
    noticeCopy: { flex: 1 },
    noticeTitle: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 14 },
    noticeText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12, lineHeight: 18, marginTop: 3 },
    metricsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
    metricCard: {
      width: '48.5%',
      minHeight: 102,
      padding: 14,
      borderRadius: radius.control,
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
    },
    metricDot: { width: 9, height: 9, borderRadius: 5, marginBottom: 8 },
    metricValue: { color: colors.text, fontFamily: 'Poppins_800ExtraBold', fontSize: 23 },
    metricLabel: { color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 11 },
    section: {
      padding: 16,
      borderRadius: radius.card,
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
      ...colors.shadow,
    },
    sectionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
    sectionLabel: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 10, letterSpacing: 1.1, marginBottom: 8 },
    seeAll: { color: colors.primary, fontFamily: 'Poppins_600SemiBold', fontSize: 11, marginBottom: 8 },
    actionRow: { flexDirection: 'row', alignItems: 'center', gap: 11, paddingVertical: 11, borderBottomColor: colors.border, borderBottomWidth: StyleSheet.hairlineWidth },
    actionIcon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.secondaryBg },
    actionCopy: { flex: 1 },
    actionTitle: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13.5 },
    actionDetail: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11, lineHeight: 16, marginTop: 2 },
    reportRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9 },
    reportIcon: { width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
    reportStatus: { fontFamily: 'Poppins_600SemiBold', fontSize: 10 },
    emptyText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12, lineHeight: 18 },
    privacyCard: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 11,
      padding: 16,
      borderRadius: radius.card,
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
    },
  });
}

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
}
