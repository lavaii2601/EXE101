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
import { PRIVACY_URL, TERMS_URL } from '../api/config';
import { connectGoogleAccount } from '../api/googleAuth';
import PricingModal from '../components/PricingModal';

const USAGE_LABELS = {
  email_summary: ['Tóm tắt email AI', 'AI email summaries'],
};

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
  const [gmailAuth,      setGmailAuth]      = useState(null);
  const [gmailLoading,   setGmailLoading]   = useState(false);
  const [pricingVisible, setPricingVisible] = useState(false);

  const subscription = profile?.subscription;
  const isPremiumTier = subscription?.tier === 'premium';
  const subscriptionPeriodEndLabel = subscription?.current_period_end
    ? new Date(subscription.current_period_end).toLocaleDateString('vi-VN')
    : '';
  const usageEntries = Object.entries(subscription?.usage || {})
    .filter(([action]) => USAGE_LABELS[action])
    .map(([action, entry]) => [t(...USAGE_LABELS[action]), entry]);

  const name     = profile?.name || profile?.gmail_name || t('Người dùng', 'User');
  const email    = profile?.gmail_email || profile?.email || t('Chưa kết nối Gmail', 'Gmail not connected');
  const avatar   = profile?.avatar_url || profile?.gmail_picture;
  const gmailOk  = status?.gmail_configured;
  const initials = name.charAt(0).toUpperCase();
  const mode = getUserMode(userMode);

  const loadGmailAuth = useCallback(async () => {
    try {
      const data = await apiGet('/email/auth-status');
      setGmailAuth(data);
    } catch {
      setGmailAuth({ authenticated: false });
    }
  }, []);

  useEffect(() => { loadGmailAuth(); }, [loadGmailAuth]);
  useEffect(() => {
    if (!syncEvent?.id) return;
    if (hasSyncTarget(syncEvent, ['settings', 'profile', 'providers', 'email'])) {
      loadGmailAuth();
      onRefresh?.();
    }
  }, [loadGmailAuth, onRefresh, syncEvent]);

  const reconnectGmail = async () => {
    setGmailLoading(true);
    try {
      const result = await connectGoogleAccount();
      if (!result.connected) return;
      await loadGmailAuth();
      onRefresh?.();
      onAgentSync?.(['settings', 'profile', 'email', 'schedule', 'overview']);
    } catch (error) {
      Alert.alert(t('Không mở được Google OAuth', 'Could not open Google OAuth'), error.message);
    } finally {
      setGmailLoading(false);
    }
  };

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

  const openTerms = async () => {
    try {
      await WebBrowser.openBrowserAsync(TERMS_URL);
    } catch (error) {
      Alert.alert(t('Không mở được điều khoản', 'Could not open terms'), error.message);
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
            <Text style={styles.profileEmail} numberOfLines={1}>{email}</Text>
            <View style={[styles.badge, gmailAuth?.authenticated ? styles.badgeOk : styles.badgeWarn]}>
              <Text style={styles.badgeText}>
                {gmailAuth?.authenticated ? t('● Gmail đã kết nối', '● Gmail connected') : t('● Gmail chưa kết nối', '● Gmail not connected')}
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
            <Text style={styles.settingSub} numberOfLines={2}>
              {gmailAuth?.authenticated
                ? (gmailAuth.gmail_email || t('Đã kết nối', 'Connected'))
                : gmailOk
                  ? t('Chưa đăng nhập Gmail', 'Gmail not signed in')
                  : t('Chưa cấu hình trên Railway', 'Not configured on Railway')}
            </Text>
          </View>
          <Button
            title={gmailAuth?.authenticated ? t('Đăng nhập lại', 'Reconnect') : t('Kết nối', 'Connect')}
            variant={gmailAuth?.authenticated ? 'secondary' : 'primary'}
            onPress={reconnectGmail}
            loading={gmailLoading}
          />
        </View>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#e0f2fe' }]}>
            <Text style={styles.settingIcon}>O</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Outlook Mail & Calendar</Text>
            <Text style={styles.settingSub} numberOfLines={2}>
              {t('Đang phát triển, chưa thể kết nối', 'In development, not connectable yet')}
            </Text>
          </View>
          <View style={[styles.statusPill, styles.statusWarn]}>
            <Text style={styles.statusText}>{t('Sắp ra mắt', 'Coming soon')}</Text>
          </View>
        </View>
      </View>

      {/* ── Subscription ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('GÓI DỊCH VỤ', 'PLAN')}</Text>
        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: isPremiumTier ? '#fef3c7' : colors.primarySoft }]}>
            <Text style={styles.settingIcon}>{isPremiumTier ? '★' : 'F'}</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{isPremiumTier ? 'Premium' : 'Free'}</Text>
            <Text style={styles.settingSub}>
              {isPremiumTier
                ? t(`Hết hạn ${subscriptionPeriodEndLabel}`, `Expires ${subscriptionPeriodEndLabel}`)
                : t('Nâng cấp để mở khóa tính năng nâng cao', 'Upgrade to unlock advanced features')}
            </Text>
          </View>
          {!isPremiumTier ? (
            <Button title={t('Nâng cấp', 'Upgrade')} onPress={() => setPricingVisible(true)} />
          ) : null}
        </View>
        {!isPremiumTier && usageEntries.length ? (
          <>
            <View style={styles.divider} />
            {usageEntries.map(([label, entry]) => (
              <View key={label} style={styles.usageRow}>
                <Text style={styles.usageLabel}>{label}</Text>
                <View style={styles.usageBarTrack}>
                  <View style={[styles.usageBarFill, { width: `${Math.min(100, (entry.used / Math.max(1, entry.limit)) * 100)}%` }]} />
                </View>
                <Text style={styles.usageValue}>{entry.used}/{entry.limit}</Text>
              </View>
            ))}
          </>
        ) : null}
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

        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.settingRow}
          onPress={openTerms}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Text style={styles.settingIcon}>📃</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Điều khoản dịch vụ', 'Terms of service')}</Text>
            <Text style={styles.settingSub}>{t('Đọc điều khoản sử dụng FlowMate', 'Read FlowMate usage terms')}</Text>
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

      <PricingModal visible={pricingVisible} onClose={() => setPricingVisible(false)} />
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
      fontFamily: 'Poppins_800ExtraBold',
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
    avatarText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 26 },
    profileInfo: { flex: 1, gap: 3 },
    profileName:  { color: colors.text, fontSize: 17, fontFamily: 'Poppins_700Bold' },
    profileEmail: { color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 12 },
    badge: {
      alignSelf: 'flex-start',
      marginTop: 4,
      borderRadius: 999,
      paddingHorizontal: 10,
      paddingVertical: 3,
    },
    badgeOk:   { backgroundColor: colors.success },
    badgeWarn: { backgroundColor: colors.warning },
    badgeText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 11 },
    statusPill: {
      borderRadius: 999,
      paddingHorizontal: 9,
      paddingVertical: 4,
    },
    statusOk: { backgroundColor: `${colors.success}22` },
    statusWarn: { backgroundColor: `${colors.warning}22` },
    statusText: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 11 },

    /* Section */
    section: {
      backgroundColor: colors.panel,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: 14,
      padding: 16,
      gap: 14,
      ...colors.shadow,
    },
    sectionLabel: {
      color: colors.primary,
      fontSize: 10,
      fontFamily: 'Poppins_700Bold',
      letterSpacing: 1.2,
      textTransform: 'uppercase',
    },
    divider: { height: 1, backgroundColor: colors.border },
    usageRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 12 },
    usageLabel: { width: 110, color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 11 },
    usageBarTrack: { flex: 1, height: 6, borderRadius: 999, overflow: 'hidden', backgroundColor: `${colors.primary}18` },
    usageBarFill: { height: 6, borderRadius: 999, backgroundColor: colors.primary },
    usageValue: { width: 40, textAlign: 'right', color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 11 },

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
    settingInfo: { flex: 1, flexShrink: 1, minWidth: 0 },
    settingTitle: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 14, flexShrink: 1 },
    settingSub:   { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12, marginTop: 1, flexShrink: 1 },
    settingSubStandalone: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12, marginTop: 3, marginBottom: 10, flexShrink: 1 },
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
