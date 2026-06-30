import React from 'react';
import { Image, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { getUserMode } from '../config/userModes';

export default function ProfileHeader({ profile, status, userMode, onRefresh, onChangeMode }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const name = profile?.name || profile?.gmail_name || t('Người dùng', 'User');
  const email = profile?.gmail_email || profile?.email || t('Chưa kết nối Gmail', 'Gmail not connected');
  const avatar = profile?.avatar_url || profile?.gmail_picture;
  const gmailReady = status?.gmail_configured;
  const mode = getUserMode(userMode);

  return (
    <View style={[styles.header, { backgroundColor: colors.panel, borderBottomColor: colors.border }]}>
      <TouchableOpacity
        style={[styles.avatar, { backgroundColor: colors.primary }]}
        onPress={onRefresh}
        activeOpacity={0.85}
      >
        {avatar
          ? <Image source={{ uri: avatar }} style={styles.avatarImage} />
          : <Text style={styles.avatarText}>{name.charAt(0).toUpperCase()}</Text>}
      </TouchableOpacity>
      <TouchableOpacity style={styles.info} onPress={onChangeMode} activeOpacity={0.8}>
        <Text style={[styles.brand, { color: colors.primary }]}>FLOWMATE AI</Text>
        <Text style={[styles.name, { color: colors.text }]}>{name}</Text>
        <Text style={[styles.detail, { color: colors.textMuted }]} numberOfLines={1}>
          {mode.label} · {email}
        </Text>
      </TouchableOpacity>
      <View style={[styles.status, gmailReady ? styles.ready : styles.notReady]}>
        <Text style={styles.statusText}>{gmailReady ? t('Sẵn sàng', 'Ready') : t('Cần thiết lập', 'Setup')}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    minHeight: 72,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarImage: { width: 38, height: 38, borderRadius: 19 },
  avatarText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 15 },
  info: { flex: 1, minWidth: 0 },
  brand: { fontFamily: 'Poppins_700Bold', fontSize: 9, letterSpacing: 1, textTransform: 'uppercase' },
  name: { marginTop: 1, fontFamily: 'Poppins_700Bold', fontSize: 14 },
  detail: { marginTop: 2, fontFamily: 'Poppins_500Medium', fontSize: 11 },
  status: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  ready: { backgroundColor: '#059669' },
  notReady: { backgroundColor: '#d97706' },
  statusText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 11 },
});
