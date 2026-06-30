import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Image,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import Button from '../components/Button';
import SegmentedControl from '../components/SegmentedControl';
import { ACCENTS, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { getUserMode } from '../config/userModes';
import { apiGet, apiPost } from '../api/client';
import { PRIVACY_URL } from '../api/config';

const ACCENT_OPTIONS = [
  { key: 'charcoal', hex: '#242423' },
  { key: 'blue',     hex: '#2563eb' },
  { key: 'purple',   hex: '#7c3aed' },
  { key: 'green',    hex: '#059669' },
  { key: 'orange',   hex: '#ea580c' },
];

export default function SettingsScreen({ profile, status, userMode, onChangeMode, onRefresh, onLogout, onAgentSync, syncEvent }) {
  const { colors, isDark, accent, toggleTheme, setAccent } = useTheme();
  const { language, setLanguage, t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [pushNotif,     setPushNotif]     = useState(false);
  const [emailNotif,    setEmailNotif]    = useState(true);
  const [reminderNotif, setReminderNotif] = useState(true);
  const [biometric,     setBiometric]     = useState(false);
  const [twoFactor,     setTwoFactor]     = useState(false);
  const [outlook,       setOutlook]       = useState({ configured: false, connected: false });
  const [outlookLoading, setOutlookLoading] = useState(false);

  const name     = profile?.name || profile?.gmail_name || t('Người dùng', 'User');
  const email    = profile?.gmail_email || profile?.email || t('Chưa kết nối Gmail', 'Gmail not connected');
  const avatar   = profile?.avatar_url || profile?.gmail_picture;
  const gmailOk  = status?.gmail_configured;
  const initials = name.charAt(0).toUpperCase();
  const mode = getUserMode(userMode);

  const loadOutlookStatus = useCallback(async () => {
    try {
      const data = await apiGet('/outlook/auth-status');
      setOutlook({
        configured: Boolean(data.configured),
        connected: Boolean(data.connected || data.authenticated),
        email: data.email || data.account_email || '',
      });
    } catch {
      setOutlook({ configured: false, connected: false });
    }
  }, []);

  useEffect(() => { loadOutlookStatus(); }, [loadOutlookStatus]);
  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['settings', 'profile', 'providers'])) {
      loadOutlookStatus();
      onRefresh?.();
    }
  }, [loadOutlookStatus, onRefresh, syncEvent]);

  const confirmLogout = () => {
    Alert.alert(t('Đăng xuất', 'Sign out'), t('Bạn có chắc muốn đăng xuất?', 'Are you sure you want to sign out?'), [
      { text: t('Hủy', 'Cancel'), style: 'cancel' },
      { text: t('Đăng xuất', 'Sign out'), style: 'destructive', onPress: onLogout },
    ]);
  };

  const comingSoon = (featureVi, featureEn) =>
    Alert.alert(
      t('Sắp có', 'Coming soon'),
      t(`"${featureVi}" sẽ có trong phiên bản tiếp theo.`, `"${featureEn || featureVi}" will be available in a future update.`)
    );

  const openPrivacyPolicy = async () => {
    try {
      await WebBrowser.openBrowserAsync(PRIVACY_URL);
    } catch (error) {
      Alert.alert(t('Không mở được chính sách', 'Could not open policy'), error.message);
    }
  };

  const clearHistory = () => {
    Alert.alert(
      t('Xóa toàn bộ lịch sử', 'Clear all history'),
      t('Chat, email và hoạt động lịch đã ghi nhận sẽ bị xóa.', 'Saved chat, email activity, and calendar history will be deleted.'),
      [
        { text: t('Hủy', 'Cancel'), style: 'cancel' },
        {
          text: t('Xóa', 'Delete'),
          style: 'destructive',
          onPress: async () => {
            try {
              const data = await apiPost('/chat/clear-all');
              Alert.alert(t('Đã xóa dữ liệu', 'Data deleted'), t(`${data.deleted_count || 0} mục đã được xóa.`, `${data.deleted_count || 0} items deleted.`));
              onAgentSync?.(['history', 'chat', 'overview']);
            } catch (error) {
              Alert.alert(t('Không xóa được dữ liệu', 'Could not delete data'), error.message);
            }
          },
        },
      ]
    );
  };

  const connectOutlook = async () => {
    setOutlookLoading(true);
    try {
      const data = await apiGet('/outlook/auth-url');
      if (!data.auth_url) throw new Error(t('Server chưa trả về đường dẫn đăng nhập Outlook.', 'The server did not return an Outlook sign-in link.'));
      await WebBrowser.openBrowserAsync(data.auth_url);
      await loadOutlookStatus();
      onRefresh?.();
      onAgentSync?.(['settings', 'profile', 'email', 'schedule', 'overview']);
    } catch (error) {
      Alert.alert(
        outlook.configured ? t('Không mở được Outlook OAuth', 'Could not open Outlook OAuth') : t('Outlook chưa được cấu hình', 'Outlook is not configured'),
        outlook.configured
          ? error.message
          : t(
              'Thêm MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET và MICROSOFT_REDIRECT_URI trên Railway trước.',
              'Add MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and MICROSOFT_REDIRECT_URI on Railway first.'
            )
      );
    } finally {
      setOutlookLoading(false);
    }
  };

  const disconnectOutlook = () => {
    Alert.alert(t('Ngắt Outlook', 'Disconnect Outlook'), t('Bạn có chắc muốn ngắt kết nối Outlook khỏi FlowMate?', 'Are you sure you want to disconnect Outlook from FlowMate?'), [
      { text: t('Hủy', 'Cancel'), style: 'cancel' },
      {
        text: t('Ngắt kết nối', 'Disconnect'),
        style: 'destructive',
        onPress: async () => {
          setOutlookLoading(true);
          try {
            await apiPost('/outlook/logout');
            await loadOutlookStatus();
            onRefresh?.();
            onAgentSync?.(['settings', 'profile', 'email', 'schedule', 'overview']);
          } catch (error) {
            Alert.alert(t('Không ngắt được Outlook', 'Could not disconnect Outlook'), error.message);
          } finally {
            setOutlookLoading(false);
          }
        },
      },
    ]);
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.body}>

      <Text style={styles.pageTitle}>{t('Cài đặt', 'Settings')}</Text>

      {/* ── Profile ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('TÀI KHOẢN', 'ACCOUNT')}</Text>
        <View style={styles.profileRow}>
          <View style={styles.avatarWrap}>
            {avatar
              ? <Image source={{ uri: avatar }} style={styles.avatarImg} />
              : <Text style={styles.avatarText}>{initials}</Text>}
          </View>
          <View style={styles.profileInfo}>
            <Text style={styles.profileName}>{name}</Text>
            <Text style={styles.profileEmail}>{email}</Text>
            <View style={[styles.badge, gmailOk ? styles.badgeOk : styles.badgeWarn]}>
              <Text style={styles.badgeText}>
                {gmailOk ? t('● Gmail đã kết nối', '● Gmail connected') : t('● Gmail chưa kết nối', '● Gmail not connected')}
              </Text>
            </View>
          </View>
        </View>
        <View style={styles.divider} />
        <TouchableOpacity style={styles.settingRow} onPress={onChangeMode} activeOpacity={0.75}>
          <View style={[styles.iconWrap, { backgroundColor: colors.primarySoft }]}>
            <Text style={[styles.modeIcon, { color: colors.accentText }]}>{mode.icon}</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Chế độ người dùng', 'User mode')}</Text>
            <Text style={styles.settingSub}>{mode.label} · {t('Chạm để thay đổi', 'Tap to change')}</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── Appearance ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('GIAO DIỆN', 'APPEARANCE')}</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: isDark ? '#1e3a5f' : '#e8eef8' }]}>
            <Text style={styles.settingIcon}>{isDark ? '🌙' : '☀️'}</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Chế độ hiển thị', 'Display theme')}</Text>
            <Text style={styles.settingSub}>{isDark ? t('Đang dùng chế độ tối', 'Currently using dark mode') : t('Đang dùng chế độ sáng', 'Currently using light mode')}</Text>
          </View>
          <Switch
            value={isDark}
            onValueChange={toggleTheme}
            trackColor={{ false: colors.border, true: colors.primary }}
            thumbColor="#ffffff"
          />
        </View>

        <View style={styles.divider} />

        <View>
          <Text style={styles.settingTitle}>{t('Màu sắc chủ đạo', 'Accent color')}</Text>
          <Text style={styles.settingSubStandalone}>{t('Chọn màu phù hợp với phong cách của bạn', 'Pick a color that matches your style')}</Text>
          <View style={styles.accentRow}>
            {ACCENT_OPTIONS.map((opt) => (
              <TouchableOpacity
                key={opt.key}
                style={[
                  styles.accentDot,
                  { backgroundColor: opt.hex },
                  accent === opt.key && styles.accentDotSelected,
                ]}
                onPress={() => setAccent(opt.key)}
                activeOpacity={0.75}
              >
                {accent === opt.key && <View style={styles.accentCheck} />}
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={styles.divider} />

        <View>
          <Text style={styles.settingTitle}>{t('Ngôn ngữ', 'Language')}</Text>
          <Text style={styles.settingSubStandalone}>{t('Áp dụng ngay và được ghi nhớ trên thiết bị này.', 'Applied immediately and remembered on this device.')}</Text>
          <SegmentedControl
            options={[
              { value: 'vi', label: 'Tiếng Việt' },
              { value: 'en', label: 'English' },
            ]}
            value={language}
            onChange={setLanguage}
          />
        </View>
      </View>

      {/* ── Connections ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('KẾT NỐI DỊCH VỤ', 'CONNECTED SERVICES')}</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#dbeafe' }]}>
            <Text style={styles.settingIcon}>G</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Gmail & Google Calendar</Text>
            <Text style={styles.settingSub}>{gmailOk ? t('Đã sẵn sàng cho email và lịch Google', 'Ready for Gmail and Google Calendar') : t('Chưa cấu hình hoặc chưa kết nối Gmail', 'Not configured or Gmail not connected')}</Text>
          </View>
          <View style={[styles.statusPill, gmailOk ? styles.statusOk : styles.statusWarn]}>
            <Text style={styles.statusText}>{gmailOk ? t('Đã bật', 'Enabled') : t('Chưa bật', 'Disabled')}</Text>
          </View>
        </View>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#e0f2fe' }]}>
            <Text style={styles.settingIcon}>O</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Outlook Mail & Calendar</Text>
            <Text style={styles.settingSub} numberOfLines={2}>
              {outlook.connected
                ? t(`Đã kết nối ${outlook.email || 'Outlook'}`, `Connected to ${outlook.email || 'Outlook'}`)
                : outlook.configured
                  ? t('Tùy chọn thêm để tổng hợp mail và lịch Outlook', 'Optional add-on to bring in Outlook mail and calendar')
                  : t('Chưa cấu hình trên Railway', 'Not configured on Railway')}
            </Text>
          </View>
          <Button
            title={outlook.connected ? t('Ngắt', 'Disconnect') : t('Kết nối', 'Connect')}
            variant={outlook.connected ? 'secondary' : 'primary'}
            onPress={outlook.connected ? disconnectOutlook : connectOutlook}
            loading={outlookLoading}
          />
        </View>
      </View>

      {/* ── Notifications ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('THÔNG BÁO', 'NOTIFICATIONS')}</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#fef3c7' }]}>
            <Text style={styles.settingIcon}>🔔</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Thông báo đẩy', 'Push notifications')}</Text>
            <Text style={styles.settingSub}>{t('Nhận thông báo trực tiếp trên thiết bị', 'Get notifications directly on this device')}</Text>
          </View>
          <Switch
            value={pushNotif}
            onValueChange={(v) => {
              setPushNotif(v);
              if (v) Alert.alert(t('Đã bật', 'Enabled'), t('Thông báo đẩy đã được bật!', 'Push notifications are now on!'));
            }}
            trackColor={{ false: colors.border, true: colors.primary }}
            thumbColor="#ffffff"
          />
        </View>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#dbeafe' }]}>
            <Text style={styles.settingIcon}>📧</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Thông báo email', 'Email notifications')}</Text>
            <Text style={styles.settingSub}>{t('Nhận cập nhật quan trọng qua email', 'Get important updates by email')}</Text>
          </View>
          <Switch
            value={emailNotif}
            onValueChange={setEmailNotif}
            trackColor={{ false: colors.border, true: colors.primary }}
            thumbColor="#ffffff"
          />
        </View>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#d1fae5' }]}>
            <Text style={styles.settingIcon}>⏰</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Nhắc lịch', 'Schedule reminders')}</Text>
            <Text style={styles.settingSub}>{t('Nhắc nhở trước khi cuộc hẹn bắt đầu', 'Remind you before appointments start')}</Text>
          </View>
          <Switch
            value={reminderNotif}
            onValueChange={setReminderNotif}
            trackColor={{ false: colors.border, true: colors.primary }}
            thumbColor="#ffffff"
          />
        </View>
      </View>

      {/* ── Security ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('BẢO MẬT', 'SECURITY')}</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#ede9fe' }]}>
            <Text style={styles.settingIcon}>👆</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Xác thực sinh trắc học', 'Biometric authentication')}</Text>
            <Text style={styles.settingSub}>{t('Vân tay hoặc nhận dạng khuôn mặt', 'Fingerprint or face recognition')}</Text>
          </View>
          <Switch
            value={biometric}
            onValueChange={(v) => {
              if (v) {
                comingSoon('Xác thực sinh trắc học', 'Biometric authentication');
                return;
              }
              setBiometric(false);
            }}
            trackColor={{ false: colors.border, true: colors.primary }}
            thumbColor="#ffffff"
          />
        </View>

        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.settingRow}
          onPress={() => comingSoon('Đổi mật khẩu', 'Change password')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: '#fce7f3' }]}>
            <Text style={styles.settingIcon}>🔑</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Đổi mật khẩu', 'Change password')}</Text>
            <Text style={styles.settingSub}>{t('Thay đổi mật khẩu tài khoản', 'Change your account password')}</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#dcfce7' }]}>
            <Text style={styles.settingIcon}>🛡️</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Xác thực hai yếu tố', 'Two-factor authentication')}</Text>
            <Text style={styles.settingSub}>{t('Tăng cường bảo mật tài khoản (2FA)', 'Add extra account security (2FA)')}</Text>
          </View>
          <Switch
            value={twoFactor}
            onValueChange={(v) => {
              if (v) {
                comingSoon('Xác thực hai yếu tố (2FA)', 'Two-factor authentication (2FA)');
                return;
              }
              setTwoFactor(false);
            }}
            trackColor={{ false: colors.border, true: colors.primary }}
            thumbColor="#ffffff"
          />
        </View>

        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.settingRow}
          onPress={() => comingSoon('Quản lý phiên đăng nhập', 'Manage signed-in devices')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: '#ffedd5' }]}>
            <Text style={styles.settingIcon}>📱</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Phiên đăng nhập', 'Signed-in sessions')}</Text>
            <Text style={styles.settingSub}>{t('Quản lý thiết bị đăng nhập', 'Manage signed-in devices')}</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── About ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('VỀ ỨNG DỤNG', 'ABOUT')}</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Text style={styles.settingIcon}>ℹ️</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Phiên bản', 'Version')}</Text>
            <Text style={styles.settingSub}>1.0.0 (FlowMate AI)</Text>
          </View>
        </View>

        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.settingRow}
          onPress={openPrivacyPolicy}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Text style={styles.settingIcon}>📄</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Chính sách bảo mật', 'Privacy policy')}</Text>
            <Text style={styles.settingSub}>{t('Đọc chính sách sử dụng dữ liệu', 'Read our data usage policy')}</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── Data / Logout ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('DỮ LIỆU', 'DATA')}</Text>
        <Button title={t('Làm mới trạng thái', 'Refresh status')} variant="secondary" onPress={onRefresh} />
        <Button title={t('Xóa toàn bộ lịch sử', 'Clear all history')} variant="secondary" onPress={clearHistory} />
        <Button title={t('Đăng xuất', 'Sign out')} variant="danger" onPress={confirmLogout} />
      </View>

    </ScrollView>
  );
}

function hasSyncTarget(syncEvent, targets) {
  const currentTargets = Array.isArray(syncEvent?.targets) ? syncEvent.targets : [];
  return targets.some((target) => currentTargets.includes(target));
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    body: { paddingHorizontal: 16, paddingBottom: 40, paddingTop: 16, gap: 12 },

    pageTitle: {
      color: colors.text,
      fontSize: 26,
      fontWeight: '800',
      marginBottom: 2,
    },

    /* Profile row */
    profileRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 14,
    },
    avatarWrap: {
      width: 68,
      height: 68,
      borderRadius: 34,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    avatarImg: { width: 68, height: 68, borderRadius: 34 },
    avatarText: { color: '#ffffff', fontWeight: '800', fontSize: 26 },
    profileInfo: { flex: 1, gap: 3 },
    profileName:  { color: colors.text, fontSize: 17, fontWeight: '800' },
    profileEmail: { color: colors.textMuted, fontSize: 12 },
    badge: {
      alignSelf: 'flex-start',
      marginTop: 4,
      borderRadius: 999,
      paddingHorizontal: 10,
      paddingVertical: 3,
    },
    badgeOk:   { backgroundColor: colors.success },
    badgeWarn: { backgroundColor: colors.warning },
    badgeText: { color: '#ffffff', fontWeight: '700', fontSize: 11 },
    statusPill: {
      borderRadius: 999,
      paddingHorizontal: 9,
      paddingVertical: 4,
    },
    statusOk: { backgroundColor: `${colors.success}22` },
    statusWarn: { backgroundColor: `${colors.warning}22` },
    statusText: { color: colors.text, fontSize: 11, fontWeight: '800' },

    /* Section */
    section: {
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: 12,
      padding: 16,
      gap: 14,
    },
    sectionLabel: {
      color: colors.textMuted,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 0.7,
    },
    divider: { height: 1, backgroundColor: colors.border },

    /* Setting row */
    settingRow:  { flexDirection: 'row', alignItems: 'center', gap: 12 },
    iconWrap: {
      width: 36,
      height: 36,
      borderRadius: 8,
      alignItems: 'center',
      justifyContent: 'center',
    },
    settingIcon: { fontSize: 18 },
    modeIcon: { fontSize: 11, fontWeight: '900' },
    settingInfo: { flex: 1 },
    settingTitle: { color: colors.text, fontWeight: '600', fontSize: 15 },
    settingSub:   { color: colors.textMuted, fontSize: 12, marginTop: 1 },
    settingSubStandalone: { color: colors.textMuted, fontSize: 12, marginTop: 3, marginBottom: 10 },
    chevron: { color: colors.textMuted, fontSize: 22, fontWeight: '300' },

    /* Accent picker */
    accentRow: { flexDirection: 'row', gap: 12 },
    accentDot: {
      width: 34,
      height: 34,
      borderRadius: 17,
      alignItems: 'center',
      justifyContent: 'center',
    },
    accentDotSelected: {
      borderWidth: 3,
      borderColor: '#ffffff',
      elevation: 4,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.25,
      shadowRadius: 4,
    },
    accentCheck: {
      width: 10,
      height: 10,
      borderRadius: 5,
      backgroundColor: '#ffffff',
    },
  });
}
