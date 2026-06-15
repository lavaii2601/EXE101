import React, { useMemo, useState } from 'react';
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
import Button from '../components/Button';
import { ACCENTS, useTheme } from '../theme/ThemeContext';
import { getUserMode } from '../config/userModes';
import { apiPost } from '../api/client';

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

  const name     = profile?.name || profile?.gmail_name || 'Nguoi dung';
  const email    = profile?.gmail_email || profile?.email || 'Chua ket noi Gmail';
  const avatar   = profile?.avatar_url || profile?.gmail_picture;
  const gmailOk  = status?.gmail_configured;
  const initials = name.charAt(0).toUpperCase();
  const mode = getUserMode(userMode);

  const confirmLogout = () => {
    Alert.alert('Dang xuat', 'Ban co chac muon dang xuat?', [
      { text: 'Huy', style: 'cancel' },
      { text: 'Dang xuat', style: 'destructive', onPress: onLogout },
    ]);
  };

  const comingSoon = (feature) =>
    Alert.alert('Sap co', `"${feature}" se co trong phien ban tiep theo.`);

  const clearHistory = () => {
    Alert.alert('Xoa toan bo lich su', 'Chat, email va hoat dong lich da ghi nhan se bi xoa.', [
      { text: 'Huy', style: 'cancel' },
      {
        text: 'Xoa',
        style: 'destructive',
        onPress: async () => {
          try {
            const data = await apiPost('/chat/clear-all');
            Alert.alert('Da xoa du lieu', `${data.deleted_count || 0} muc da duoc xoa.`);
          } catch (error) {
            Alert.alert('Khong xoa duoc du lieu', error.message);
          }
        },
      },
    ]);
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.body}>

      <Text style={styles.pageTitle}>Setting</Text>

      {/* ── Profile ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>TAI KHOAN</Text>
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
                {gmailOk ? '● Gmail ket noi' : '● Gmail chua ket noi'}
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
            <Text style={styles.settingTitle}>Che do nguoi dung</Text>
            <Text style={styles.settingSub}>{mode.label} · Cham de thay doi</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── Appearance ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>GIAO DIEN</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: isDark ? '#1e3a5f' : '#e8eef8' }]}>
            <Text style={styles.settingIcon}>{isDark ? '🌙' : '☀️'}</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Che do hien thi</Text>
            <Text style={styles.settingSub}>{isDark ? 'Dang dung che do toi' : 'Dang dung che do sang'}</Text>
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
          <Text style={styles.settingTitle}>Mau sac chu dao</Text>
          <Text style={styles.settingSubStandalone}>Chon mau phu hop voi phong cach cua ban</Text>
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

      {/* ── Notifications ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>THONG BAO</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#fef3c7' }]}>
            <Text style={styles.settingIcon}>🔔</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Thong bao day</Text>
            <Text style={styles.settingSub}>Nhan thong bao truc tiep tren thiet bi</Text>
          </View>
          <Switch
            value={pushNotif}
            onValueChange={(v) => {
              setPushNotif(v);
              if (v) Alert.alert('Da bat', 'Thong bao day da duoc bat!');
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
            <Text style={styles.settingTitle}>Thong bao email</Text>
            <Text style={styles.settingSub}>Nhan cap nhat quan trong qua email</Text>
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
            <Text style={styles.settingTitle}>Nhac lich</Text>
            <Text style={styles.settingSub}>Nhac nho truoc khi cuoc hen bat dau</Text>
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
        <Text style={styles.sectionLabel}>BAO MAT</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#ede9fe' }]}>
            <Text style={styles.settingIcon}>👆</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Xac thuc sinh trac hoc</Text>
            <Text style={styles.settingSub}>Van tay hoac nhan dang khuon mat</Text>
          </View>
          <Switch
            value={biometric}
            onValueChange={(v) => {
              if (v) {
                comingSoon('Xac thuc sinh trac hoc');
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
          onPress={() => comingSoon('Doi mat khau')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: '#fce7f3' }]}>
            <Text style={styles.settingIcon}>🔑</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Doi mat khau</Text>
            <Text style={styles.settingSub}>Thay doi mat khau tai khoan</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: '#dcfce7' }]}>
            <Text style={styles.settingIcon}>🛡️</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Xac thuc hai yeu to</Text>
            <Text style={styles.settingSub}>Tang cuong bao mat tai khoan (2FA)</Text>
          </View>
          <Switch
            value={twoFactor}
            onValueChange={(v) => {
              if (v) {
                comingSoon('Xac thuc hai yeu to (2FA)');
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
          onPress={() => comingSoon('Quan ly phien dang nhap')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: '#ffedd5' }]}>
            <Text style={styles.settingIcon}>📱</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Phien dang nhap</Text>
            <Text style={styles.settingSub}>Quan ly thiet bi dang nhap</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── About ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>VE UNG DUNG</Text>

        <View style={styles.settingRow}>
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Text style={styles.settingIcon}>ℹ️</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Phien ban</Text>
            <Text style={styles.settingSub}>1.0.0 (FlowMate AI)</Text>
          </View>
        </View>

        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.settingRow}
          onPress={() => comingSoon('Chinh sach bao mat')}
          activeOpacity={0.75}
        >
          <View style={[styles.iconWrap, { backgroundColor: colors.secondaryBg }]}>
            <Text style={styles.settingIcon}>📄</Text>
          </View>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Chinh sach bao mat</Text>
            <Text style={styles.settingSub}>Doc chinh sach su dung du lieu</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── Logout ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>DU LIEU</Text>
        <Button title="Lam moi trang thai" variant="secondary" onPress={onRefresh} />
        <Button title="Xoa toan bo lich su" variant="secondary" onPress={clearHistory} />
        <Button title="Dang xuat" variant="danger" onPress={confirmLogout} />
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
