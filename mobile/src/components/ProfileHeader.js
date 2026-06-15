import React from 'react';
import { Image, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useTheme } from '../theme/ThemeContext';
import { getUserMode } from '../config/userModes';

export default function ProfileHeader({ profile, status, userMode, onRefresh, onChangeMode }) {
  const { colors } = useTheme();
  const name = profile?.name || profile?.gmail_name || 'Nguoi dung';
  const email = profile?.gmail_email || profile?.email || 'Chua ket noi Gmail';
  const avatar = profile?.avatar_url || profile?.gmail_picture;
  const gmailReady = status?.gmail_configured;
  const mode = getUserMode(userMode);

  return (
    <View style={[styles.header, { backgroundColor: colors.background }]}>
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
        <Text style={[styles.name, { color: colors.text }]}>{name}</Text>
        <Text style={[styles.detail, { color: colors.accentText }]} numberOfLines={1}>
          {mode.label} · {email}
        </Text>
      </TouchableOpacity>
      <View style={[styles.status, gmailReady ? styles.ready : styles.notReady]}>
        <Text style={styles.statusText}>{gmailReady ? 'Ready' : 'Setup'}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    minHeight: 68,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarImage: { width: 38, height: 38, borderRadius: 19 },
  avatarText: { color: '#ffffff', fontWeight: '900', fontSize: 15 },
  info: { flex: 1, minWidth: 0 },
  name: { fontWeight: '800', fontSize: 14 },
  detail: { marginTop: 3, fontSize: 11 },
  status: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 },
  ready: { backgroundColor: '#059669' },
  notReady: { backgroundColor: '#d97706' },
  statusText: { color: '#ffffff', fontWeight: '800', fontSize: 10 },
});
