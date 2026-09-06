import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Modal, SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { apiDelete, apiGet } from '../api/client';

const SOURCE_TYPE_LABELS = {
  email_summary: 'Email',
  calendar_event: 'Lịch',
  note: 'Ghi chú',
  document_reference: 'Tài liệu',
};

// "Trung tam chia se" (Sharing Center, Phase 4): everything the caller has
// personally shared into any Business workspace, with a revoke action.
// Reached from Settings. Not workspace-scoped -- GET /api/user/sharing
// spans every workspace the caller belongs to.
export default function SharingCenterScreen({ visible, onClose }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [artifacts, setArtifacts] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet('/user/sharing');
      if (data?.success) setArtifacts(data.artifacts || []);
    } catch { /* keep whatever was already shown */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  const revoke = (artifact) => {
    Alert.alert(
      t('Thu hồi chia sẻ này?', 'Revoke this share?'),
      t(
        'Không gian sẽ không còn thấy nội dung này nữa.',
        'The workspace will no longer see this content.'
      ),
      [
        { text: t('Hủy', 'Cancel'), style: 'cancel' },
        {
          text: t('Thu hồi', 'Revoke'),
          style: 'destructive',
          onPress: async () => {
            try {
              await apiDelete(`/workspaces/${artifact.workspace_id}/shared-artifacts/${artifact.id}`);
              await load();
            } catch (error) {
              Alert.alert(t('Không thu hồi được', 'Could not revoke'), error.message);
            }
          },
        },
      ]
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.root}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={22} color={colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>{t('Trung tâm chia sẻ', 'Sharing Center')}</Text>
        </View>

        <ScrollView contentContainerStyle={styles.body}>
          {loading ? (
            <ActivityIndicator style={{ marginVertical: 40 }} color={colors.primary} />
          ) : artifacts.length ? (
            artifacts.map((artifact) => (
              <View key={artifact.id} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.title}>{artifact.title}</Text>
                  <Text style={styles.meta}>
                    {artifact.workspace_name} · {SOURCE_TYPE_LABELS[artifact.source_type] || artifact.source_type}
                  </Text>
                </View>
                <TouchableOpacity onPress={() => revoke(artifact)}>
                  <Text style={styles.revokeText}>{t('Thu hồi', 'Revoke')}</Text>
                </TouchableOpacity>
              </View>
            ))
          ) : (
            <Text style={styles.emptyText}>{t('Bạn chưa chia sẻ nội dung nào.', "You haven't shared anything yet.")}</Text>
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
    body: { paddingHorizontal: 16, paddingBottom: 32, gap: 10 },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      padding: 12,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      borderWidth: 1,
      borderColor: colors.border,
    },
    title: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    meta: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11.5, marginTop: 2 },
    revokeText: { color: colors.danger, fontFamily: 'Poppins_600SemiBold', fontSize: 12.5 },
    emptyText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13, textAlign: 'center', marginTop: 40 },
  });
}
