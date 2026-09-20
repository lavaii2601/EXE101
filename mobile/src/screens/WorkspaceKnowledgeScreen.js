import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  StatusBar,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { apiDelete, apiGet, apiPost } from '../api/client';
import Button from '../components/Button';
import { useLanguage } from '../i18n/LanguageContext';
import { useOrgWorkspace } from '../state/OrgWorkspaceContext';
import { radius, useTheme } from '../theme/ThemeContext';

export default function WorkspaceKnowledgeScreen({ visible, onClose, syncEvent }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const workspace = useOrgWorkspace();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');

  const load = useCallback(async () => {
    if (!workspace?.isBusiness) {
      setDocuments([]);
      return;
    }
    setLoading(true);
    try {
      const data = await apiGet('/workspace-knowledge');
      if (data?.success) setDocuments(data.documents || []);
    } catch (error) {
      Alert.alert(
        t('Không tải được kiến thức doanh nghiệp', 'Could not load workspace knowledge'),
        error.message,
      );
    } finally {
      setLoading(false);
    }
  }, [t, workspace?.isBusiness, workspace?.currentWorkspaceId]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  useEffect(() => {
    if (!visible || !syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['workspace_knowledge'])) load();
  }, [visible, syncEvent, load]);

  const createDocument = async () => {
    if (!title.trim() || !content.trim()) {
      Alert.alert(
        t('Thiếu thông tin', 'Missing information'),
        t('Vui lòng nhập tiêu đề và nội dung.', 'Please enter a title and content.'),
      );
      return;
    }
    setSaving(true);
    try {
      await apiPost('/workspace-knowledge', {
        title: title.trim(),
        content: content.trim(),
        tags: tags.trim() || undefined,
      });
      setTitle('');
      setContent('');
      setTags('');
      await load();
    } catch (error) {
      Alert.alert(
        t('Không lưu được tài liệu', 'Could not save document'),
        error.message,
      );
    } finally {
      setSaving(false);
    }
  };

  const deleteDocument = (document) => {
    Alert.alert(
      t('Xóa tài liệu?', 'Delete document?'),
      document.title || '',
      [
        { text: t('Hủy', 'Cancel'), style: 'cancel' },
        {
          text: t('Xóa', 'Delete'),
          style: 'destructive',
          onPress: async () => {
            try {
              await apiDelete(`/workspace-knowledge/${document.id}`);
              setDocuments((current) => current.filter((item) => item.id !== document.id));
            } catch (error) {
              Alert.alert(
                t('Không xóa được tài liệu', 'Could not delete document'),
                error.message,
              );
            }
          },
        },
      ],
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.root}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={22} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCopy}>
            <Text style={styles.headerTitle}>{t('Kiến thức doanh nghiệp', 'Workspace Knowledge')}</Text>
            <Text style={styles.headerSubtitle} numberOfLines={1}>{workspace?.current?.name || ''}</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          {!workspace?.isBusiness ? (
            <View style={styles.section}>
              <Text style={styles.emptyText}>
                {t(
                  'Hãy chọn một không gian doanh nghiệp để xem tài liệu dùng chung.',
                  'Choose a business workspace to view shared documents.',
                )}
              </Text>
            </View>
          ) : (
            <>
              {workspace.canManage ? (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>{t('THÊM TÀI LIỆU', 'ADD DOCUMENT')}</Text>
                  <TextInput
                    style={styles.input}
                    value={title}
                    onChangeText={setTitle}
                    placeholder={t('Tiêu đề', 'Title')}
                    placeholderTextColor={colors.inputPlaceholder}
                  />
                  <TextInput
                    style={[styles.input, styles.multiline]}
                    value={content}
                    onChangeText={setContent}
                    placeholder={t('Nội dung policy, quy trình, FAQ...', 'Policy, process, or FAQ content...')}
                    placeholderTextColor={colors.inputPlaceholder}
                    multiline
                  />
                  <TextInput
                    style={styles.input}
                    value={tags}
                    onChangeText={setTags}
                    placeholder={t('Nhãn, phân tách bằng dấu phẩy', 'Tags, separated by commas')}
                    placeholderTextColor={colors.inputPlaceholder}
                  />
                  <Button title={t('Lưu tài liệu', 'Save document')} onPress={createDocument} loading={saving} />
                </View>
              ) : null}

              <View style={styles.section}>
                <View style={styles.sectionHeading}>
                  <Text style={styles.sectionLabel}>{t('TÀI LIỆU DOANH NGHIỆP', 'WORKSPACE DOCUMENTS')}</Text>
                  <Text style={styles.count}>{documents.length}</Text>
                </View>
                {loading ? (
                  <ActivityIndicator style={styles.loader} color={colors.primary} />
                ) : documents.length ? (
                  documents.map((document) => (
                    <View key={document.id} style={styles.documentCard}>
                      <View style={styles.documentHeading}>
                        <View style={styles.documentTitleWrap}>
                          <Ionicons name="document-text-outline" size={18} color={colors.secondaryText} />
                          <Text style={styles.documentTitle}>{document.title}</Text>
                        </View>
                        {workspace.canManage ? (
                          <TouchableOpacity
                            onPress={() => deleteDocument(document)}
                            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                          >
                            <Ionicons name="trash-outline" size={18} color={colors.danger} />
                          </TouchableOpacity>
                        ) : null}
                      </View>
                      <Text style={styles.documentContent}>{document.content}</Text>
                      {document.tags ? (
                        <View style={styles.tagsRow}>
                          {String(document.tags).split(',').map((tag) => tag.trim()).filter(Boolean).map((tag) => (
                            <Text key={tag} style={styles.tag}>{tag}</Text>
                          ))}
                        </View>
                      ) : null}
                    </View>
                  ))
                ) : (
                  <Text style={styles.emptyText}>
                    {t('Chưa có tài liệu doanh nghiệp.', 'No workspace documents yet.')}
                  </Text>
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
    root: {
      flex: 1,
      backgroundColor: colors.background,
      paddingTop: Platform.OS === 'android' ? (StatusBar.currentHeight || 0) : 0,
    },
    header: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 16, paddingVertical: 12 },
    headerCopy: { flex: 1 },
    headerTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 17 },
    headerSubtitle: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11 },
    body: { paddingHorizontal: 16, paddingBottom: 32, gap: 14 },
    section: {
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: radius.card,
      padding: 16,
      ...colors.shadow,
    },
    sectionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    sectionLabel: {
      color: colors.primary,
      fontFamily: 'Poppins_700Bold',
      fontSize: 10,
      letterSpacing: 1.2,
      marginBottom: 10,
    },
    count: { color: colors.textMuted, fontFamily: 'Poppins_700Bold', fontSize: 12, marginBottom: 10 },
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
      marginBottom: 12,
    },
    multiline: { minHeight: 110, paddingTop: 12, textAlignVertical: 'top' },
    loader: { marginVertical: 30 },
    documentCard: {
      padding: 13,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      borderColor: colors.border,
      borderWidth: 1,
      marginBottom: 10,
    },
    documentHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
    documentTitleWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
    documentTitle: { flex: 1, color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13.5 },
    documentContent: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12, lineHeight: 18, marginTop: 9 },
    tagsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
    tag: {
      color: colors.secondaryText,
      backgroundColor: colors.secondaryBg,
      borderRadius: radius.pill,
      paddingHorizontal: 8,
      paddingVertical: 3,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 10,
    },
    emptyText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13, lineHeight: 20 },
  });
}

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
}
