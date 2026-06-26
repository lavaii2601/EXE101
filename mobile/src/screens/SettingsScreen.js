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
import { ACCENTS, useTheme } from '../theme/ThemeContext';
import { getUserMode } from '../config/userModes';
import { apiGet, apiPost } from '../api/client';

const ACCENT_OPTIONS = [
  { key: 'charcoal', hex: '#242423' },
  { key: 'blue',     hex: '#2563eb' },
  { key: 'purple',   hex: '#7c3aed' },
  { key: 'green',    hex: '#059669' },
  { key: 'orange',   hex: '#ea580c' },
];

export default function SettingsScreen({ profile, status, userMode, onChangeMode, onRefresh, onLogout }) {
  const { colors, isDark, accent, toggleTheme, setAccent } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [pushNotif,     setPushNotif]     = useState(false);
  const [emailNotif,    setEmailNotif]    = useState(true);
  const [reminderNotif, setReminderNotif] = useState(true);
  const [biometric,     setBiometric]     = useState(false);
  const [twoFactor,     setTwoFactor]     = useState(false);
  const [outlook,       setOutlook]       = useState({ configured: false, connected: false });
  const [outlookLoading, setOutlookLoading] = useState(false);

  const name     = profile?.name || profile?.gmail_name || 'Người dùng';
  const email    = profile?.gmail_email || profile?.email || 'Chưa kết nối Gmail';
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

  const confirmLogout = () => {
    Alert.alert('Đăng xuất', 'Bạn có chắc muốn đăng xuất?', [
      { text: 'Hủy', style: 'cancel' },
      { text: 'Đăng xuất', style: 'destructive', onPress: onLogout },
    ]);
  };

  const comingSoon = (feature) =>
    Alert.alert('Sắp có', `"${feature}" sẽ có trong phiên bản tiếp theo.`);

  const clearHistory = () => {
    Alert.alert('Xóa toàn bộ lịch sử', 'Chat, email và hoạt động lịch đã ghi nhận sẽ bị xóa.', [
      { text: 'Hủy', style: 'cancel' },
      {
        text: 'Xóa',
        style: 'destructive',
        onPress: async () => {
          try {
            const data = await apiPost('/chat/clear-all');
            Alert.alert('Đã xóa dữ liệu', `${data.deleted_count || 0} mục đã được xóa.`);
          } catch (error) {
            Alert.alert('Không xóa được dữ liệu', error.message);
          }
        },
      },
    ]);
  };

  const connectOutlook = async () => {
    setOutlookLoading(true);
    try {
      const data = await apiGet('/outlook/auth-url');
      if (!data.auth_url) throw new Error('Server chưa trả về đường dẫn đăng nhập Outlook.');
      await WebBrowser.openBrowserAsync(data.auth_url);
      await loadOutlookStatus();
      onRefresh?.();
    } catch (error) {
      Alert.alert(
        outlook.configured ? 'Không mở được Outlook OAuth' : 'Outlook chưa được cấu hình',
        outlook.configured
          ? error.message
          : 'Thêm MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET và MICROSOFT_REDIRECT_URI trên Railway trước.'
      );
    } finally {
      setOutlookLoading(false);
    }
  };

  const disconnectOutlook = () => {
    Alert.alert('Ngắt Outlook', 'Bạn có chắc muốn ngắt kết nối Outlook khỏi FlowMate?', [
      { text: 'Hủy', style: 'cancel' },
      {
        text: 'Ngắt kết nối',
        style: 'destructive',
        onPress: async () => {
          setOutlookLoading(true);
          try {
            await apiPost('/outlook/logout');
            await loadOutlookStatus();
            onRefresh?.();
          } catch (error) {
            Alert.alert('Không ngắt được Outlook', error.message);
          } finally {
            setOutlookLoading(false);
          }
        },
      },
    ]);
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.body}>

      <Text style={styles.pageTitle}>Cài đặt</Text>

      {/* ── Profile ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>TÀI KHOẢN</Text>
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
                {gmailOk ? '● Gmail đã kết nối' : '● Gmail chưa kết nối'}
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
            <Text style={styles.settingTitle}>Chế độ người dùng</Text>
            <Text style={styles.settingSub}>{mode.label} · Chạm để thay đổi</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── Appearance ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>GIAO DIỆN</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: isDark ? '#1e3a5f' : '#e8eef8' }]}>
            <Text style={styles.settingIcon}>{isDark ? '🌙' : '☀️'}</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Chế độ hiển thị</Text>
            <Text style={styles.settingSub}>{isDark ? 'Đang dùng chế độ tối' : 'Đang dùng chế độ sáng'}</Text>
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
          <Text style={styles.settingTitle}>Màu sắc chủ đạo</Text>
          <Text style={styles.settingSubStandalone}>Chọn màu phù hợp với phong cách của bạn</Text>
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
      </View>

      {/* ── Connections ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>KẾT NỐI DỊCH VỤ</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#dbeafe' }]}>
            <Text style={styles.settingIcon}>G</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Gmail & Google Calendar</Text>
            <Text style={styles.settingSub}>{gmailOk ? 'Đã sẵn sàng cho email và lịch Google' : 'Chưa cấu hình hoặc chưa kết nối Gmail'}</Text>
          </View>
          <View style={[styles.statusPill, gmailOk ? styles.statusOk : styles.statusWarn]}>
            <Text style={styles.statusText}>{gmailOk ? 'Đã bật' : 'Chưa bật'}</Text>
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
                ? `Đã kết nối ${outlook.email || 'Outlook'}`
                : outlook.configured
                  ? 'Tùy chọn thêm để tổng hợp mail và lịch Outlook'
                  : 'Chưa cấu hình trên Railway'}
            </Text>
          </View>
          <Button
            title={outlook.connected ? 'Ngắt' : 'Kết nối'}
            variant={outlook.connected ? 'secondary' : 'primary'}
            onPress={outlook.connected ? disconnectOutlook : connectOutlook}
            loading={outlookLoading}
          />
        </View>
      </View>

      {/* ── Notifications ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>THÔNG BÁO</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#fef3c7' }]}>
            <Text style={styles.settingIcon}>🔔</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Thông báo đẩy</Text>
            <Text style={styles.settingSub}>Nhận thông báo trực tiếp trên thiết bị</Text>
          </View>
          <Switch
            value={pushNotif}
            onValueChange={(v) => {
              setPushNotif(v);
              if (v) Alert.alert('Đã bật', 'Thông báo đẩy đã được bật!');
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
            <Text style={styles.settingTitle}>Thông báo email</Text>
            <Text style={styles.settingSub}>Nhận cập nhật quan trọng qua email</Text>
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
            <Text style={styles.settingTitle}>Nhắc lịch</Text>
            <Text style={styles.settingSub}>Nhắc nhở trước khi cuộc hẹn bắt đầu</Text>
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
        <Text style={styles.sectionLabel}>BẢO MẬT</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#ede9fe' }]}>
            <Text style={styles.settingIcon}>👆</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Xác thực sinh trắc học</Text>
            <Text style={styles.settingSub}>Vân tay hoặc nhận dạng khuôn mặt</Text>
          </View>
          <Switch
            value={biometric}
            onValueChange={(v) => {
              if (v) {
                comingSoon('Xác thực sinh trắc học');
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
          onPress={() => comingSoon('Đổi mật khẩu')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: '#fce7f3' }]}>
            <Text style={styles.settingIcon}>🔑</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Đổi mật khẩu</Text>
            <Text style={styles.settingSub}>Thay đổi mật khẩu tài khoản</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#dcfce7' }]}>
            <Text style={styles.settingIcon}>🛡️</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Xác thực hai yếu tố</Text>
            <Text style={styles.settingSub}>Tăng cường bảo mật tài khoản (2FA)</Text>
          </View>
          <Switch
            value={twoFactor}
            onValueChange={(v) => {
              if (v) {
                comingSoon('Xác thực hai yếu tố (2FA)');
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
          onPress={() => comingSoon('Quản lý phiên đăng nhập')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: '#ffedd5' }]}>
            <Text style={styles.settingIcon}>📱</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Phiên đăng nhập</Text>
            <Text style={styles.settingSub}>Quản lý thiết bị đăng nhập</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── About ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>VỀ ỨNG DỤNG</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Text style={styles.settingIcon}>ℹ️</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Phiên bản</Text>
            <Text style={styles.settingSub}>1.0.0 (FlowMate AI)</Text>
          </View>
        </View>

        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.settingRow}
          onPress={() => comingSoon('Chính sách bảo mật')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Text style={styles.settingIcon}>📄</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Chính sách bảo mật</Text>
            <Text style={styles.settingSub}>Đọc chính sách sử dụng dữ liệu</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── Data / Logout ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>DỮ LIỆU</Text>
        <Button title="Làm mới trạng thái" variant="secondary" onPress={onRefresh} />
        <Button title="Xóa toàn bộ lịch sử" variant="secondary" onPress={clearHistory} />
        <Button title="Đăng xuất" variant="danger" onPress={confirmLogout} />
      </View>

    </ScrollView>
  );
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
