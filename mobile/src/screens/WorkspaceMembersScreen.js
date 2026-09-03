import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Modal, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { useOrgWorkspace } from '../state/OrgWorkspaceContext';
import { apiDelete, apiGet, apiPatch, apiPost } from '../api/client';
import Button from '../components/Button';

function roleLabel(role, t) {
  if (role === 'owner') return t('Chủ sở hữu', 'Owner');
  if (role === 'admin') return t('Quản trị', 'Admin');
  return t('Thành viên', 'Worker');
}

function accessStateLabel(state, t) {
  if (state === 'active') return t('Đang hoạt động', 'Active');
  if (state === 'grace') return t('Sắp hết hạn', 'Expiring soon');
  if (state === 'read_only') return t('Chỉ đọc (đã hết hạn)', 'Read-only (expired)');
  return t('Chưa có gói', 'No subscription yet');
}

function accessStateColor(state, colors) {
  if (state === 'active') return colors.success;
  if (state === 'grace') return colors.warning;
  if (state === 'read_only') return colors.danger;
  return colors.textMuted;
}

// Member/invitation management for the active Business workspace, reached
// from Settings. Mirrors the web client's "Thành viên" page and the Flutter
// client's WorkspaceMembersScreen.
export default function WorkspaceMembersScreen({ visible, onClose }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const workspace = useOrgWorkspace();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const canManage = workspace?.canManage;

  const [members, setMembers] = useState([]);
  const [pendingInvitations, setPendingInvitations] = useState([]);
  const [subscriptionInfo, setSubscriptionInfo] = useState(null);
  const [seatRequests, setSeatRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [inviteResultToken, setInviteResultToken] = useState(null);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('worker');

  const load = useCallback(async () => {
    const workspaceId = workspace?.currentWorkspaceId;
    if (!workspaceId) return;
    setLoading(true);
    try {
      const data = await apiGet(`/workspaces/${workspaceId}/members`);
      if (data?.success) setMembers(data.members || []);
    } catch { /* keep whatever was already shown */ }

    try {
      const data = await apiGet(`/workspaces/${workspaceId}/subscription`);
      if (data?.success) setSubscriptionInfo(data);
    } catch { /* keep whatever was already shown */ }

    if (workspace?.canManage) {
      try {
        const data = await apiGet(`/workspaces/${workspaceId}/invitations`);
        if (data?.success) {
          setPendingInvitations((data.invitations || []).filter((i) => i.status === 'pending'));
        }
      } catch { /* keep whatever was already shown */ }

      try {
        const data = await apiGet(`/workspaces/${workspaceId}/seat-requests`);
        if (data?.success) {
          setSeatRequests((data.seat_requests || []).filter((r) => r.status === 'pending_owner'));
        }
      } catch { /* keep whatever was already shown */ }
    }
    setLoading(false);
  }, [workspace?.currentWorkspaceId, workspace?.canManage]);

  const resolveSeatRequest = async (requestId, action) => {
    const workspaceId = workspace?.currentWorkspaceId;
    if (!workspaceId) return;
    try {
      await apiPost(`/workspaces/${workspaceId}/seat-requests/${requestId}/${action}`, {});
      load();
    } catch { /* no-op: list stays as-is, user can retry */ }
  };

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  const submitInvite = async () => {
    const workspaceId = workspace?.currentWorkspaceId;
    if (!workspaceId || !email.trim()) return;
    setInviting(true);
    setInviteResultToken(null);
    try {
      const data = await apiPost(`/workspaces/${workspaceId}/invitations`, { email: email.trim(), role });
      if (data?.success) {
        setInviteResultToken(data.invitation?.token || null);
        setEmail('');
        await load();
      }
    } catch (error) {
      Alert.alert(t('Không gửi được lời mời', 'Could not send invitation'), error.message);
    } finally {
      setInviting(false);
    }
  };

  const revokeInvitation = async (invitationId) => {
    const workspaceId = workspace?.currentWorkspaceId;
    if (!workspaceId) return;
    try {
      await apiDelete(`/workspaces/${workspaceId}/invitations/${invitationId}`);
      load();
    } catch { /* no-op: list stays as-is, user can retry */ }
  };

  const changeRole = async (userId, currentRole) => {
    const workspaceId = workspace?.currentWorkspaceId;
    if (!workspaceId) return;
    try {
      await apiPatch(`/workspaces/${workspaceId}/members/${userId}/role`, {
        role: currentRole === 'admin' ? 'worker' : 'admin',
      });
      load();
    } catch { /* no-op: list stays as-is, user can retry */ }
  };

  const removeMember = (userId) => {
    Alert.alert(
      t('Xóa thành viên', 'Remove member'),
      t('Xóa thành viên này khỏi không gian làm việc?', 'Remove this member from the workspace?'),
      [
        { text: t('Hủy', 'Cancel'), style: 'cancel' },
        {
          text: t('Xóa', 'Remove'),
          style: 'destructive',
          onPress: async () => {
            const workspaceId = workspace?.currentWorkspaceId;
            if (!workspaceId) return;
            try {
              await apiPost(`/workspaces/${workspaceId}/members/${userId}/disable`, {});
              load();
            } catch { /* no-op: list stays as-is, user can retry */ }
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
          <Text style={styles.headerTitle}>{t('Thành viên', 'Members')}</Text>
        </View>

        <ScrollView contentContainerStyle={styles.body}>
          {loading ? (
            <ActivityIndicator style={{ marginVertical: 40 }} color={colors.primary} />
          ) : (
            <>
              {subscriptionInfo ? (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>{t('GÓI DOANH NGHIỆP', 'BUSINESS PLAN')}</Text>
                  <View style={styles.subscriptionHeading}>
                    <Text style={styles.subscriptionPlanName}>
                      {subscriptionInfo.subscription?.plan_name || t('Chưa có gói doanh nghiệp', 'No Business plan yet')}
                    </Text>
                    <View style={[styles.subscriptionBadge, { backgroundColor: `${accessStateColor(subscriptionInfo.access_state, colors)}24` }]}>
                      <Text style={[styles.subscriptionBadgeText, { color: accessStateColor(subscriptionInfo.access_state, colors) }]}>
                        {accessStateLabel(subscriptionInfo.access_state, t)}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.subscriptionSeats}>
                    {t('Chỗ đang dùng', 'Seats used')}: {subscriptionInfo.active_seats} / {subscriptionInfo.seat_capacity}
                  </Text>
                  {subscriptionInfo.access_state === 'grace' ? (
                    <Text style={[styles.subscriptionNotice, { color: colors.warning }]}>
                      {t(
                        'Gói đã hết hạn, đang trong 7 ngày gia hạn. Sau đó không gian sẽ chuyển sang chỉ đọc.',
                        'Your plan has expired and is in the 7-day grace period. After that, this workspace becomes read-only.'
                      )}
                    </Text>
                  ) : null}
                  {subscriptionInfo.access_state === 'read_only' ? (
                    <Text style={[styles.subscriptionNotice, { color: colors.danger }]}>
                      {t(
                        'Không gian đang ở chế độ chỉ đọc do gói đã hết hạn. Gia hạn để tiếp tục chỉnh sửa.',
                        'This workspace is read-only because its plan expired. Renew to resume editing.'
                      )}
                    </Text>
                  ) : null}
                </View>
              ) : null}

              <View style={styles.section}>
                <Text style={styles.sectionLabel}>{t('DANH SÁCH THÀNH VIÊN', 'MEMBER LIST')}</Text>
                {members.map((m) => (
                  <View key={m.user_id} style={styles.memberRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.memberName}>{m.name || m.email || m.user_id}</Text>
                      <Text style={styles.memberEmail}>{m.email || ''}</Text>
                    </View>
                    <View style={styles.roleBadge}>
                      <Text style={styles.roleBadgeText}>{roleLabel(m.role, t)}</Text>
                    </View>
                    {canManage && m.role !== 'owner' ? (
                      <>
                        <TouchableOpacity
                          onPress={() => changeRole(m.user_id, m.role)}
                          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                          style={{ marginLeft: 6 }}
                        >
                          <Ionicons name="swap-horizontal-outline" size={18} color={colors.textMuted} />
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => removeMember(m.user_id)}
                          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                          style={{ marginLeft: 10 }}
                        >
                          <Ionicons name="person-remove-outline" size={18} color={colors.danger} />
                        </TouchableOpacity>
                      </>
                    ) : null}
                  </View>
                ))}
                {!members.length ? (
                  <Text style={styles.emptyText}>{t('Chưa có thành viên nào.', 'No members yet.')}</Text>
                ) : null}
              </View>

              {canManage ? (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>{t('MỜI THÀNH VIÊN', 'INVITE MEMBER')}</Text>
                  <Text style={styles.fieldLabel}>{t('Email', 'Email')}</Text>
                  <TextInput
                    style={styles.input}
                    value={email}
                    onChangeText={setEmail}
                    placeholder="email@congty.com"
                    placeholderTextColor={colors.inputPlaceholder}
                    keyboardType="email-address"
                    autoCapitalize="none"
                  />
                  <View style={styles.roleChoiceRow}>
                    {['worker', 'admin'].map((opt) => (
                      <TouchableOpacity
                        key={opt}
                        style={[styles.roleChip, role === opt && styles.roleChipActive]}
                        onPress={() => setRole(opt)}
                      >
                        {role === opt ? <Ionicons name="checkmark" size={14} color={colors.text} style={{ marginRight: 4 }} /> : null}
                        <Text style={styles.roleChipText}>{opt === 'worker' ? 'Worker' : 'Admin'}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <Button title={t('Gửi lời mời', 'Send invitation')} onPress={submitInvite} loading={inviting} />

                  {inviteResultToken ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={styles.hintText}>
                        {t('Đã tạo lời mời. Gửi mã này cho người được mời:', 'Invitation created. Send this code to the invitee:')}
                      </Text>
                      <Text selectable style={styles.tokenText}>{inviteResultToken}</Text>
                    </View>
                  ) : null}

                  {pendingInvitations.length ? (
                    <View style={{ marginTop: 14 }}>
                      <Text style={styles.sectionLabel}>{t('LỜI MỜI ĐANG CHỜ', 'PENDING INVITATIONS')}</Text>
                      {pendingInvitations.map((inv) => (
                        <View key={inv.id} style={styles.inviteRow}>
                          <Text style={styles.inviteEmail}>{inv.email_normalized}</Text>
                          <TouchableOpacity onPress={() => revokeInvitation(inv.id)}>
                            <Text style={styles.revokeText}>{t('Thu hồi', 'Revoke')}</Text>
                          </TouchableOpacity>
                        </View>
                      ))}
                    </View>
                  ) : null}
                </View>
              ) : null}

              {canManage && seatRequests.length ? (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>{t('YÊU CẦU THÊM CHỖ', 'SEAT REQUESTS')}</Text>
                  {seatRequests.map((r) => (
                    <View key={r.id} style={styles.seatRequestRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.seatRequestText}>
                          {t('Cần thêm', 'Needs')} {r.requested_seats} {t('chỗ', 'seat(s)')}
                        </Text>
                        <Text style={styles.memberEmail}>{r.requested_by_user_id || ''}</Text>
                      </View>
                      <TouchableOpacity onPress={() => resolveSeatRequest(r.id, 'approve')}>
                        <Text style={[styles.seatRequestAction, { color: colors.success }]}>{t('Duyệt', 'Approve')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => resolveSeatRequest(r.id, 'reject')} style={{ marginLeft: 14 }}>
                        <Text style={[styles.seatRequestAction, { color: colors.danger }]}>{t('Từ chối', 'Reject')}</Text>
                      </TouchableOpacity>
                    </View>
                  ))}
                </View>
              ) : null}
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
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 14,
      paddingHorizontal: 16,
      paddingVertical: 12,
    },
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
    subscriptionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
    subscriptionPlanName: { flex: 1, color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 14 },
    subscriptionBadge: { borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 4 },
    subscriptionBadgeText: { fontFamily: 'Poppins_700Bold', fontSize: 10.5 },
    subscriptionSeats: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12.5, marginTop: 6 },
    subscriptionNotice: { fontFamily: 'Poppins_400Regular', fontSize: 12, marginTop: 10, lineHeight: 17 },

    seatRequestRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4, marginBottom: 6 },
    seatRequestText: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    seatRequestAction: { fontFamily: 'Poppins_700Bold', fontSize: 12.5 },

    memberRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
    memberName: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    memberEmail: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11.5, marginTop: 1 },
    roleBadge: { backgroundColor: colors.primarySoft, borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 4 },
    roleBadgeText: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 10.5 },
    emptyText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13 },

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
      marginBottom: 12,
    },
    roleChoiceRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
    roleChip: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: radius.pill,
      backgroundColor: colors.panelSoft,
      borderWidth: 1,
      borderColor: colors.border,
    },
    roleChipActive: { backgroundColor: colors.secondaryBg, borderColor: colors.primary },
    roleChipText: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },

    hintText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12 },
    tokenText: { color: colors.primary, fontFamily: 'Poppins_600SemiBold', fontSize: 12, marginTop: 4 },

    inviteRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
    inviteEmail: { flex: 1, color: colors.text, fontFamily: 'Poppins_500Medium', fontSize: 12.5 },
    revokeText: { color: colors.danger, fontFamily: 'Poppins_600SemiBold', fontSize: 12 },
  });
}
