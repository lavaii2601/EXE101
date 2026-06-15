import React, { useMemo } from 'react';
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

const ACCENT_OPTIONS = [
  { key: 'charcoal', hex: '#242423' },
  { key: 'blue',     hex: '#2563eb' },
  { key: 'purple',   hex: '#7c3aed' },
  { key: 'green',    hex: '#059669' },
  { key: 'orange',   hex: '#ea580c' },
];

export default function ProfileScreen({ profile, status, onLogout }) {
  const { colors, isDark, accent, toggleTheme, setAccent } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const name     = profile?.name || profile?.gmail_name || 'Teacher';
  const email    = profile?.gmail_email || profile?.email || 'Chua ket noi Gmail';
  const avatar   = profile?.avatar_url || profile?.gmail_picture;
  const gmailOk  = status?.gmail_configured;
  const initials = name.charAt(0).toUpperCase();

  const confirmLogout = () => {
    Alert.alert('Dang xuat', 'Ban co chac muon dang xuat?', [
      { text: 'Huy', style: 'cancel' },
      { text: 'Dang xuat', style: 'destructive', onPress: onLogout },
    ]);
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.body}>

      {/* ── Account Info ── */}
      <View style={styles.hero}>
        <View style={styles.avatarWrap}>
          {avatar
            ? <Image source={{ uri: avatar }} style={styles.avatarImg} />
            : <Text style={styles.avatarText}>{initials}</Text>}
        </View>
        <Text style={styles.heroName}>{name}</Text>
        <Text style={styles.heroEmail}>{email}</Text>
        <View style={[styles.badge, gmailOk ? styles.badgeOk : styles.badgeWarn]}>
          <Text style={styles.badgeText}>
            {gmailOk ? '● Gmail ket noi' : '● Gmail chua ket noi'}
          </Text>
        </View>
      </View>

      {/* ── Appearance ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>GIAO DIEN</Text>

        <View style={styles.settingRow}>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Giao dien toi</Text>
            <Text style={styles.settingSub}>{isDark ? 'Dang bat' : 'Dang tat'}</Text>
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
          <Text style={styles.settingTitle}>Mau chu dao</Text>
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

      {/* ── Settings ── */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>CAI DAT</Text>

        <View style={styles.settingRow}>
          <Text style={styles.settingIcon}>🔔</Text>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Thong bao</Text>
            <Text style={styles.settingSub}>Bat thong bao day</Text>
          </View>
          <Switch
            value={false}
            onValueChange={() =>
              Alert.alert('Sap co', 'Tinh nang nay se co trong phien ban tiep theo.')
            }
            trackColor={{ false: colors.border, true: colors.primary }}
            thumbColor="#ffffff"
          />
        </View>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <Text style={styles.settingIcon}>🌐</Text>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Ngon ngu</Text>
            <Text style={styles.settingSub}>Tieng Viet</Text>
          </View>
        </View>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <Text style={styles.settingIcon}>🔒</Text>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Bao mat</Text>
            <Text style={styles.settingSub}>Mat khau & xac thuc</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </View>

        <View style={styles.divider} />

        <View style={styles.settingRow}>
          <Text style={styles.settingIcon}>ℹ️</Text>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>Phien ban</Text>
            <Text style={styles.settingSub}>1.0.0 (FlowMate AI)</Text>
          </View>
        </View>
      </View>

      {/* ── Logout ── */}
      <View style={styles.section}>
        <Button title="Dang xuat" variant="danger" onPress={confirmLogout} />
      </View>

    </ScrollView>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    body: { paddingHorizontal: 16, paddingBottom: 32, gap: 16 },

    /* Hero */
    hero: {
      alignItems: 'center',
      paddingTop: 28,
      paddingBottom: 10,
      gap: 6,
    },
    avatarWrap: {
      width: 90,
      height: 90,
      borderRadius: 45,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 6,
    },
    avatarImg: { width: 90, height: 90, borderRadius: 45 },
    avatarText: { color: '#ffffff', fontWeight: '800', fontSize: 36 },
    heroName:  { color: colors.text, fontSize: 20, fontWeight: '800' },
    heroEmail: { color: colors.textMuted, fontSize: 13 },
    badge: {
      marginTop: 4,
      borderRadius: 999,
      paddingHorizontal: 12,
      paddingVertical: 5,
    },
    badgeOk:   { backgroundColor: colors.success },
    badgeWarn: { backgroundColor: colors.warning },
    badgeText: { color: '#ffffff', fontWeight: '700', fontSize: 12 },

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
    settingRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
    settingIcon: { fontSize: 20, width: 28, textAlign: 'center' },
    settingInfo: { flex: 1 },
    settingTitle: { color: colors.text, fontWeight: '600', fontSize: 15 },
    settingSub:   { color: colors.textMuted, fontSize: 12, marginTop: 1 },
    chevron:      { color: colors.textMuted, fontSize: 22, fontWeight: '300' },

    /* Accent picker */
    accentRow: { flexDirection: 'row', gap: 14, marginTop: 10 },
    accentDot: {
      width: 36,
      height: 36,
      borderRadius: 18,
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
