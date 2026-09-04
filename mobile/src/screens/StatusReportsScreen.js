import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Modal, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { apiDelete, apiGet, apiPost } from '../api/client';
import Button from '../components/Button';

const FIELDS = [
  ['done_text', 'Done'],
  ['doing_text', 'Doing'],
  ['blocked_text', 'Blocked'],
  ['next_text', 'Next'],
  ['risks_text', 'Risks'],
];

// Manual Done/Doing/Blocked/Next/Risks Status Reports for the active
// Business workspace (Phase 3, design doc section 8.5), reached from
// Settings. Mirrors the web client's "Báo cáo" page and the Flutter
// client's StatusReportsScreen, both on top of routes/work_hub.py's
// /api/status-reports endpoints. No Bob-AI-drafting in this slice --
// every report is filled in and reviewed by hand before publishing, and
// publishing is one-way (content becomes immutable).
export default function StatusReportsScreen({ visible, onClose }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [projects, setProjects] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [published, setPublished] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [fieldValues, setFieldValues] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet('/projects');
      if (data?.success) setProjects(data.projects || []);
    } catch { /* keep whatever was already shown */ }
    try {
      const data = await apiGet('/status-reports?status=draft');
      if (data?.success) setDrafts(data.reports || []);
    } catch { /* keep whatever was already shown */ }
    try {
      const data = await apiGet('/status-reports?status=published');
      if (data?.success) setPublished(data.reports || []);
    } catch { /* keep whatever was already shown */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  const projectName = (projectId) => projects.find((p) => p.id === projectId)?.name || null;

  const saveDraft = async () => {
    setSaving(true);
    try {
      await apiPost('/status-reports', {
        project_id: selectedProjectId || undefined,
        done_text: (fieldValues.done_text || '').trim(),
        doing_text: (fieldValues.doing_text || '').trim(),
        blocked_text: (fieldValues.blocked_text || '').trim(),
        next_text: (fieldValues.next_text || '').trim(),
        risks_text: (fieldValues.risks_text || '').trim(),
      });
      setFieldValues({});
      setSelectedProjectId(null);
      await load();
    } catch (error) {
      Alert.alert(t('Không lưu được báo cáo', 'Could not save report'), error.message);
    } finally {
      setSaving(false);
    }
  };

  const publish = (reportId) => {
    Alert.alert(
      t('Công bố báo cáo?', 'Publish report?'),
      t(
        'Công bố vào không gian doanh nghiệp. Sau khi công bố sẽ không thể chỉnh sửa nội dung nữa.',
        'This publishes it to the workspace. Once published, its content can no longer be edited.'
      ),
      [
        { text: t('Hủy', 'Cancel'), style: 'cancel' },
        {
          text: t('Công bố', 'Publish'),
          onPress: async () => {
            try {
              await apiPost(`/status-reports/${reportId}/publish`, {});
              await load();
            } catch (error) {
              const message = error.message === 'report_empty'
                ? t('Báo cáo trống, hãy điền ít nhất một mục trước khi công bố.', 'The report is empty -- fill in at least one field before publishing.')
                : t('Không công bố được báo cáo', 'Could not publish report');
              Alert.alert(t('Lỗi', 'Error'), message);
            }
          },
        },
      ]
    );
  };

  const deleteDraft = async (reportId) => {
    try {
      await apiDelete(`/status-reports/${reportId}`);
      await load();
    } catch { /* no-op: list stays as-is, user can retry */ }
  };

  const renderReportCard = (report, { draft }) => {
    const filled = FIELDS.filter(([key]) => (report[key] || '').trim());
    return (
      <View key={report.id} style={styles.reportCard}>
        <View style={styles.itemRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.itemTitle}>{report.report_date}</Text>
            <Text style={styles.itemMeta}>{projectName(report.project_id) || t('Không gắn dự án', 'No project')}</Text>
          </View>
          {draft ? (
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <TouchableOpacity onPress={() => publish(report.id)}>
                <Text style={styles.publishText}>{t('Công bố', 'Publish')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => deleteDraft(report.id)}>
                <Text style={styles.deleteText}>{t('Xoá', 'Delete')}</Text>
              </TouchableOpacity>
            </View>
          ) : null}
        </View>
        {filled.map(([key, label]) => (
          <Text key={key} style={styles.reportField}>
            <Text style={styles.reportFieldLabel}>{label}: </Text>
            {report[key]}
          </Text>
        ))}
      </View>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.root}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={22} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>{t('Báo cáo trạng thái', 'Status Reports')}</Text>
        </View>

        <ScrollView contentContainerStyle={styles.body}>
          {loading ? (
            <ActivityIndicator style={{ marginVertical: 40 }} color={colors.primary} />
          ) : (
            <>
              <View style={styles.section}>
                <Text style={styles.sectionLabel}>{t('BÁO CÁO MỚI', 'NEW REPORT')}</Text>
                {projects.length ? (
                  <View style={styles.chipRow}>
                    <TouchableOpacity
                      style={[styles.chip, !selectedProjectId && styles.chipActive]}
                      onPress={() => setSelectedProjectId(null)}
                    >
                      <Text style={styles.chipText}>{t('Không gắn dự án', 'No project')}</Text>
                    </TouchableOpacity>
                    {projects.map((p) => (
                      <TouchableOpacity
                        key={p.id}
                        style={[styles.chip, selectedProjectId === p.id && styles.chipActive]}
                        onPress={() => setSelectedProjectId(p.id)}
                      >
                        <Text style={styles.chipText}>{p.name}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                ) : null}
                {FIELDS.map(([key, label]) => (
                  <View key={key} style={{ marginBottom: 10 }}>
                    <Text style={styles.fieldLabel}>{label}</Text>
                    <TextInput
                      style={[styles.input, styles.multiline]}
                      value={fieldValues[key] || ''}
                      onChangeText={(text) => setFieldValues((current) => ({ ...current, [key]: text }))}
                      multiline
                      placeholderTextColor={colors.inputPlaceholder}
                    />
                  </View>
                ))}
                <Button title={t('Lưu nháp', 'Save draft')} onPress={saveDraft} loading={saving} />
              </View>

              <View style={styles.section}>
                <Text style={styles.sectionLabel}>{t('NHÁP CỦA TÔI', 'MY DRAFTS')}</Text>
                {drafts.length ? drafts.map((report) => renderReportCard(report, { draft: true })) : (
                  <Text style={styles.emptyText}>{t('Chưa có báo cáo nháp.', 'No drafts yet.')}</Text>
                )}
              </View>

              <View style={styles.section}>
                <Text style={styles.sectionLabel}>{t('ĐÃ CÔNG BỐ', 'PUBLISHED')}</Text>
                {published.length ? published.map((report) => renderReportCard(report, { draft: false })) : (
                  <Text style={styles.emptyText}>{t('Chưa có báo cáo nào được công bố.', 'No published reports yet.')}</Text>
                )}
              </View>
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    header: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 16, paddingVertical: 12 },
    headerTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 17 },
    body: { paddingHorizontal: 16, paddingBottom: 32, gap: 14 },

    section: {
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: radius.card,
      padding: 16,
      ...colors.shadow,
    },
    sectionLabel: {
      color: colors.primary,
      fontSize: 10,
      fontFamily: 'Poppins_700Bold',
      letterSpacing: 1.2,
      textTransform: 'uppercase',
      marginBottom: 10,
    },
    fieldLabel: { color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 12, marginBottom: 6 },
    input: {
      minHeight: 46,
      borderColor: colors.border,
      borderWidth: 1.5,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      color: colors.text,
      fontFamily: 'Poppins_400Regular',
      fontSize: 14,
      paddingHorizontal: 14,
    },
    multiline: { minHeight: 64, paddingTop: 12, textAlignVertical: 'top' },

    chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
    chip: {
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: radius.pill,
      backgroundColor: colors.panelSoft,
      borderWidth: 1,
      borderColor: colors.border,
    },
    chipActive: { backgroundColor: colors.secondaryBg, borderColor: colors.primary },
    chipText: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 12.5 },

    reportCard: {
      padding: 10,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      borderWidth: 1,
      borderColor: colors.border,
      marginBottom: 10,
    },
    itemRow: { flexDirection: 'row', alignItems: 'center' },
    itemTitle: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    itemMeta: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11, marginTop: 2 },
    publishText: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 12.5 },
    deleteText: { color: colors.danger, fontFamily: 'Poppins_600SemiBold', fontSize: 12.5 },
    reportField: { color: colors.text, fontFamily: 'Poppins_400Regular', fontSize: 12, marginTop: 6, lineHeight: 17 },
    reportFieldLabel: { color: colors.primary, fontFamily: 'Poppins_700Bold' },
    emptyText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13 },
  });
}
