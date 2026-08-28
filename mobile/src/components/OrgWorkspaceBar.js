import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { useOrgWorkspace } from '../state/OrgWorkspaceContext';
import Button from './Button';

function roleLabel(role, t) {
  if (role === 'owner') return t('Chủ sở hữu', 'Owner');
  if (role === 'admin') return t('Quản trị', 'Admin');
  return t('Thành viên', 'Worker');
}

// Compact bar placed just below ProfileHeader in App.js. Tapping it opens a
// bottom sheet to switch workspaces, create a Business workspace, or accept
// an invitation by pasting its token (no email delivery exists yet -- see
// design doc section 1.1 -- so this is the real acceptance path for now,
// matching the web client's `?invite=<token>` link that a user pastes/opens
// manually).
export default function OrgWorkspaceBar() {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const workspace = useOrgWorkspace();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [sheetVisible, setSheetVisible] = useState(false);
  const [dialog, setDialog] = useState(null); // 'create' | 'join' | null

  const active = workspace?.current;
  const isBusiness = active?.type === 'business';

  return (
    <>
      <TouchableOpacity style={styles.bar} onPress={() => setSheetVisible(true)} activeOpacity={0.8}>
        <Text style={styles.icon}>{isBusiness ? '🏢' : '👤'}</Text>
        <Text style={styles.name} numberOfLines={1}>
          {active ? active.name : t('Cá nhân', 'Personal')}
        </Text>
        <Ionicons name="swap-vertical-outline" size={15} color={colors.textMuted} />
      </TouchableOpacity>

      <Modal visible={sheetVisible} animationType="slide" transparent onRequestClose={() => setSheetVisible(false)}>
        <Pressable style={styles.overlay} onPress={() => setSheetVisible(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t('Không gian làm việc', 'Workspaces')}</Text>

            {workspace?.loading ? (
              <ActivityIndicator style={{ marginVertical: 16 }} color={colors.primary} />
            ) : (
              <ScrollView style={{ maxHeight: 260 }}>
                {(workspace?.workspaces || []).map((w) => {
                  const isActive = w.id === workspace.currentWorkspaceId;
                  return (
                    <TouchableOpacity
                      key={w.id}
                      style={styles.workspaceRow}
                      activeOpacity={0.75}
                      onPress={() => {
                        workspace.switchWorkspace(w.id);
                        setSheetVisible(false);
                      }}
                    >
                      <Text style={styles.workspaceIcon}>{w.type === 'business' ? '🏢' : '👤'}</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.workspaceName}>{w.name}</Text>
                        {w.member_role ? (
                          <Text style={styles.workspaceRole}>{roleLabel(w.member_role, t)}</Text>
                        ) : null}
                      </View>
                      {isActive ? <Ionicons name="checkmark-circle" size={20} color={colors.primary} /> : null}
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            )}

            <View style={{ height: 10 }} />
            <Button
              title={t('+ Tạo không gian doanh nghiệp', '+ Create Business workspace')}
              variant="secondary"
              onPress={() => { setSheetVisible(false); setDialog('create'); }}
            />
            <View style={{ height: 8 }} />
            <Button
              title={t('Nhập mã lời mời', 'Enter invite code')}
              variant="secondary"
              onPress={() => { setSheetVisible(false); setDialog('join'); }}
            />
          </Pressable>
        </Pressable>
      </Modal>

      <NamedActionDialog
        visible={dialog === 'create'}
        title={t('Tạo không gian doanh nghiệp', 'Create Business workspace')}
        placeholder={t('Tên công ty / nhóm', 'Company / team name')}
        submitLabel={t('Tạo', 'Create')}
        onCancel={() => setDialog(null)}
        onSubmit={(value) => workspace.createBusinessWorkspace(value)}
        successMessage={t('Đã tạo không gian doanh nghiệp', 'Business workspace created')}
      />
      <NamedActionDialog
        visible={dialog === 'join'}
        title={t('Nhập mã lời mời', 'Enter invite code')}
        placeholder={t('Dán mã lời mời tại đây', 'Paste the invite code here')}
        submitLabel={t('Tham gia', 'Join')}
        onCancel={() => setDialog(null)}
        onSubmit={(value) => workspace.acceptInvitation(extractToken(value))}
        successMessage={t('Đã tham gia không gian doanh nghiệp', 'Joined the Business workspace')}
      />
    </>
  );
}

// Accepts either a raw token or a full web invite link
// (".../app?invite=<token>") so users can paste whichever they were sent.
function extractToken(input) {
  const trimmed = (input || '').trim();
  const queryIndex = trimmed.indexOf('invite=');
  if (queryIndex === -1) return trimmed;
  return decodeURIComponent(trimmed.slice(queryIndex + 'invite='.length).split('&')[0]);
}

function NamedActionDialog({ visible, title, placeholder, submitLabel, onCancel, onSubmit, successMessage }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const close = () => {
    setValue('');
    setSubmitting(false);
    onCancel();
  };

  const submit = async () => {
    if (!value.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(value.trim());
      setValue('');
      setSubmitting(false);
      onCancel();
      Alert.alert(successMessage);
    } catch (error) {
      setSubmitting(false);
      Alert.alert(t('Không thực hiện được', 'Could not complete'), error.message);
    }
  };

  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={close}>
      <Pressable style={styles.dialogOverlay} onPress={close}>
        <Pressable style={styles.dialogBox} onPress={() => {}}>
          <Text style={styles.dialogTitle}>{title}</Text>
          <TextInput
            style={styles.dialogInput}
            value={value}
            onChangeText={setValue}
            placeholder={placeholder}
            placeholderTextColor={colors.inputPlaceholder}
            autoFocus
          />
          <View style={styles.dialogActions}>
            <TouchableOpacity onPress={close} disabled={submitting} style={styles.dialogButton}>
              <Text style={styles.dialogCancelText}>{t('Hủy', 'Cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={submit} disabled={submitting} style={styles.dialogButton}>
              {submitting ? <ActivityIndicator size="small" color={colors.primary} /> : (
                <Text style={styles.dialogSubmitText}>{submitLabel}</Text>
              )}
            </TouchableOpacity>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    bar: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingHorizontal: 18,
      paddingVertical: 10,
      backgroundColor: colors.panelSoft,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    icon: { fontSize: 15 },
    name: { flex: 1, color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },

    overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' },
    sheet: {
      maxHeight: '80%',
      backgroundColor: colors.panel,
      borderTopLeftRadius: 24,
      borderTopRightRadius: 24,
      padding: 20,
      paddingBottom: 28,
    },
    sheetTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 17, marginBottom: 12 },
    workspaceRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      paddingVertical: 10,
    },
    workspaceIcon: { fontSize: 18 },
    workspaceName: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 14 },
    workspaceRole: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11.5, marginTop: 1 },

    dialogOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center', padding: 24 },
    dialogBox: {
      width: '100%',
      backgroundColor: colors.panel,
      borderRadius: radius.card,
      padding: 20,
    },
    dialogTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 16, marginBottom: 12 },
    dialogInput: {
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
    dialogActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 18, marginTop: 16 },
    dialogButton: { minWidth: 56, alignItems: 'flex-end', paddingVertical: 4 },
    dialogCancelText: { color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 14 },
    dialogSubmitText: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 14 },
  });
}
