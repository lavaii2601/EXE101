import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Image,
  Linking,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import { Ionicons } from '@expo/vector-icons';
import Button from '../components/Button';
import SegmentedControl from '../components/SegmentedControl';
import { ACCENTS, radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { getUserMode } from '../config/userModes';
import { apiGet, apiPost } from '../api/client';
import { PRIVACY_URL, TERMS_URL } from '../api/config';
import { connectGoogleAccount } from '../api/googleAuth';
import PricingModal from '../components/PricingModal';
import WorkspaceMembersScreen from './WorkspaceMembersScreen';
import WorkHubScreen from './WorkHubScreen';
import StatusReportsScreen from './StatusReportsScreen';
import SharingCenterScreen from './SharingCenterScreen';
import { useOrgWorkspace } from '../state/OrgWorkspaceContext';

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

function formatSubscriptionRemaining(subscription, t) {
  if (!subscription?.current_period_end) {
    return t('không giới hạn', 'unlimited');
  }
  let seconds = Number(subscription?.remaining_seconds);
  if (!Number.isFinite(seconds)) {
    seconds = Math.max(0, Math.floor(
      (new Date(subscription.current_period_end).getTime() - Date.now()) / 1000
    ));
  }
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) {
    return t(
      `${days} ngày${hours ? ` ${hours} giờ` : ''}`,
      `${days} day${days === 1 ? '' : 's'}${hours ? ` ${hours}h` : ''}`
    );
  }
  if (hours) return t(`${hours} giờ ${minutes} phút`, `${hours}h ${minutes}m`);
  return t(`${Math.max(0, minutes)} phút`, `${Math.max(0, minutes)}m`);
}

export default function SettingsScreen({ profile, status, userMode, onChangeMode, onRefresh, onLogout, onAgentSync, syncEvent }) {
  const { colors, isDark, accent, toggleTheme, setAccent } = useTheme();
  const { language, setLanguage, t } = useLanguage();
  const orgWorkspace = useOrgWorkspace();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  // Business-workspace collaboration (Thành viên/Công việc/Báo cáo/Chia sẻ)
  // is scoped to the "worker" and "business" user modes -- switching to
  // another mode (student, freelancer, mentor, teacher, creator) hides
  // these even if the account is still an active Business workspace
  // member, since the whole Worker Business Subscription feature set is
  // framed around the worker persona, not a general-purpose feature.
  const canShowBusinessFeatures = userMode === 'worker' || userMode === 'business';

  const [membersVisible, setMembersVisible] = useState(false);
  const [workHubVisible, setWorkHubVisible] = useState(false);
  const [statusReportsVisible, setStatusReportsVisible] = useState(false);
  const [sharingCenterVisible, setSharingCenterVisible] = useState(false);
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
  const subscriptionRemainingLabel = formatSubscriptionRemaining(subscription, t);
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

  const callSupport = async () => {
    try {
      await Linking.openURL('tel:+84945999076');
    } catch (error) {
      Alert.alert(t('Không gọi được', 'Could not place call'), error.message);
    }
  };

  const emailSupport = async () => {
    try {
      await Linking.openURL('mailto:lecaoduyanh123@gmail.com');
    } catch (error) {
      Alert.alert(t('Không mở được email', 'Could not open email'), error.message);
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
            <Ionicons name={mode.icon} size={18} color={colors.accentText} />
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
            <Ionicons name={isDark ? 'moon' : 'sunny'} size={18} color={isDark ? '#93c5fd' : '#f59e0b'} />
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
            <Ionicons name="logo-google" size={17} color="#ea4335" />
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
            <Ionicons name="mail-outline" size={17} color="#0284c7" />
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

      {/* ── Business workspace ── */}
      {orgWorkspace.isBusiness && canShowBusinessFeatures ? (
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>{t('DOANH NGHIỆP', 'BUSINESS')}</Text>
          <TouchableOpacity style={styles.settingRow} onPress={() => setMembersVisible(true)} activeOpacity={0.75}>
            <View style={[styles.iconWrap, { backgroundColor: colors.primarySoft }]}>
              <Ionicons name="people-outline" size={18} color={colors.accentText} />
            </View>
            <View style={styles.settingInfo}>
              <Text style={styles.settingTitle}>{t('Thành viên', 'Members')}</Text>
              <Text style={styles.settingSub}>{orgWorkspace.current?.name || ''}</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.settingRow} onPress={() => setWorkHubVisible(true)} activeOpacity={0.75}>
            <View style={[styles.iconWrap, { backgroundColor: colors.primarySoft }]}>
              <Ionicons name="grid-outline" size={18} color={colors.accentText} />
            </View>
            <View style={styles.settingInfo}>
              <Text style={styles.settingTitle}>{t('Công việc', 'Work Hub')}</Text>
              <Text style={styles.settingSub}>{t('Dự án và nhiệm vụ dùng chung', 'Shared projects and tasks')}</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.settingRow} onPress={() => setStatusReportsVisible(true)} activeOpacity={0.75}>
            <View style={[styles.iconWrap, { backgroundColor: colors.primarySoft }]}>
              <Ionicons name="document-text-outline" size={18} color={colors.accentText} />
            </View>
            <View style={styles.settingInfo}>
              <Text style={styles.settingTitle}>{t('Báo cáo trạng thái', 'Status Reports')}</Text>
              <Text style={styles.settingSub}>Done / Doing / Blocked / Next / Risks</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* ── Sharing Center: not workspace-scoped, so gated on membership in
          ANY Business workspace rather than orgWorkspace.isBusiness (which
          only reflects the currently active one). ── */}
      {orgWorkspace.workspaces?.some((w) => w.type === 'business') && canShowBusinessFeatures ? (
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>{t('RIÊNG TƯ', 'PRIVACY')}</Text>
          <TouchableOpacity style={styles.settingRow} onPress={() => setSharingCenterVisible(true)} activeOpacity={0.75}>
            <View style={[styles.iconWrap, { backgroundColor: colors.primarySoft }]}>
              <Ionicons name="share-social-outline" size={18} color={colors.accentText} />
            </View>
            <View style={styles.settingInfo}>
              <Text style={styles.settingTitle}>{t('Trung tâm chia sẻ', 'Sharing Center')}</Text>
              <Text style={styles.settingSub}>{t('Nội dung cá nhân bạn đã chia sẻ', 'Personal content you have shared')}</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* ── Subscription ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('GÓI DỊCH VỤ', 'PLAN')}</Text>
        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: isPremiumTier ? '#fef3c7' : colors.primarySoft }]}>
            <Ionicons name={isPremiumTier ? 'star' : 'pricetag-outline'} size={17} color={isPremiumTier ? '#f59e0b' : colors.accentText} />
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{isPremiumTier ? 'Premium' : 'Free'}</Text>
            <Text style={styles.settingSub}>
              {isPremiumTier
                ? t(
                  `Còn ${subscriptionRemainingLabel} · Hết hạn ${subscriptionPeriodEndLabel}`,
                  `${subscriptionRemainingLabel} left · Expires ${subscriptionPeriodEndLabel}`
                )
                : t('Nâng cấp để mở khóa tính năng nâng cao', 'Upgrade to unlock advanced features')}
            </Text>
          </View>
          <Button
            title={isPremiumTier ? t('Gia hạn', 'Renew') : t('Nâng cấp', 'Upgrade')}
            variant={isPremiumTier ? 'secondary' : 'primary'}
            onPress={() => setPricingVisible(true)}
          />
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
            <Ionicons name="notifications-outline" size={18} color="#d97706" />
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
            <Ionicons name="mail-outline" size={18} color="#2563eb" />
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
            <Ionicons name="alarm-outline" size={18} color="#059669" />
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
            <Ionicons name="finger-print-outline" size={18} color="#7c3aed" />
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
            <Ionicons name="key-outline" size={18} color="#db2777" />
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
            <Ionicons name="shield-checkmark-outline" size={18} color="#16a34a" />
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
            <Ionicons name="phone-portrait-outline" size={18} color="#ea580c" />
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
            <Ionicons name="information-circle-outline" size={18} color={colors.secondaryText} />
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
            <Ionicons name="document-text-outline" size={18} color={colors.secondaryText} />
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
            <Ionicons name="reader-outline" size={18} color={colors.secondaryText} />
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Điều khoản dịch vụ', 'Terms of service')}</Text>
            <Text style={styles.settingSub}>{t('Đọc điều khoản sử dụng FlowMate', 'Read FlowMate usage terms')}</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── Support ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>{t('HỖ TRỢ', 'SUPPORT')}</Text>

        <TouchableOpacity
          style={styles.settingRow}
          onPress={callSupport}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Ionicons name="call-outline" size={18} color={colors.secondaryText} />
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Điện thoại', 'Phone')}</Text>
            <Text style={styles.settingSub}>{t('Đội ngũ CSKH FlowMate: +84 945 999 076', 'FlowMate support team: +84 945 999 076')}</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>

        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.settingRow}
          onPress={emailSupport}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Ionicons name="mail-outline" size={18} color={colors.secondaryText} />
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{t('Email', 'Email')}</Text>
            <Text style={styles.settingSub}>{t('Đội ngũ CSKH FlowMate: lecaoduyanh123@gmail.com', 'FlowMate support team: lecaoduyanh123@gmail.com')}</Text>
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

      <PricingModal
        visible={pricingVisible}
        isPremiumTier={isPremiumTier}
        subscription={subscription}
        onRefresh={onRefresh}
        onClose={() => setPricingVisible(false)}
      />
      <WorkspaceMembersScreen visible={membersVisible} onClose={() => setMembersVisible(false)} />
      <WorkHubScreen visible={workHubVisible} onClose={() => setWorkHubVisible(false)} />
      <StatusReportsScreen visible={statusReportsVisible} onClose={() => setStatusReportsVisible(false)} />
      <SharingCenterScreen visible={sharingCenterVisible} onClose={() => setSharingCenterVisible(false)} />
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
      borderRadius: radius.card,
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
      width: 38,
      height: 38,
      borderRadius: radius.control,
      alignItems: 'center',
      justifyContent: 'center',
    },
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
