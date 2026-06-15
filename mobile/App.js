import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import ChatScreen from './src/screens/ChatScreen';
import EmailScreen from './src/screens/EmailScreen';
import ScheduleScreen from './src/screens/ScheduleScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import ProfileHeader from './src/components/ProfileHeader';
import RoleSelection from './src/components/RoleSelection';
import { apiGet, apiPost } from './src/api/client';
import { ThemeProvider, useTheme } from './src/theme/ThemeContext';

const tabs = [
  { key: 'chat',     icon: 'AI', label: 'Chat' },
  { key: 'emails',   icon: '@',  label: 'Email' },
  { key: 'schedule', icon: '31', label: 'Lich' },
  { key: 'history',  icon: 'LG', label: 'Nhat ky' },
  { key: 'settings', icon: '...', label: 'Setting' },
];

export default function App() {
  return (
    <ThemeProvider>
      <AppShell />
    </ThemeProvider>
  );
}

function AppShell() {
  const { colors, isDark } = useTheme();
  const [activeTab, setActiveTab] = useState('chat');
  const [profile, setProfile] = useState(null);
  const [status, setStatus] = useState(null);
  const [userMode, setUserMode] = useState(null);
  const [savingMode, setSavingMode] = useState(false);
  const [modePickerOpen, setModePickerOpen] = useState(false);

  const refreshShell = useCallback(async () => {
    const [profileResult, statusResult] = await Promise.allSettled([
      apiGet('/user/profile'),
      apiGet('/status'),
    ]);
    if (profileResult.status === 'fulfilled' && profileResult.value.success) {
      setProfile(profileResult.value.user);
      setUserMode(profileResult.value.user?.user_mode || '');
    }
    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    }
  }, []);

  useEffect(() => {
    refreshShell();
  }, [refreshShell]);

  const handleLogout = useCallback(async () => {
    try { await apiPost('/email/logout'); } catch { /* ignore */ }
    setProfile(null);
    setStatus(null);
    setActiveTab('chat');
  }, []);

  const saveUserMode = useCallback(async (mode) => {
    setSavingMode(true);
    try {
      const data = await apiPost('/user/profile', { user_mode: mode });
      setProfile(data.user || profile);
      setUserMode(mode);
      setModePickerOpen(false);
    } catch (error) {
      Alert.alert('Khong luu duoc che do', error.message);
    } finally {
      setSavingMode(false);
    }
  }, [profile]);

  const renderScreen = () => {
    if (activeTab === 'emails')   return <EmailScreen userMode={userMode || 'worker'} onAuthChanged={refreshShell} />;
    if (activeTab === 'schedule') return <ScheduleScreen />;
    if (activeTab === 'history')  return <HistoryScreen />;
    if (activeTab === 'settings') return (
      <SettingsScreen
        profile={profile}
        status={status}
        userMode={userMode || 'worker'}
        onChangeMode={() => setModePickerOpen(true)}
        onRefresh={refreshShell}
        onLogout={handleLogout}
      />
    );
    return <ChatScreen userMode={userMode || 'worker'} />;
  };

  const styles = useMemo(() => makeStyles(colors), [colors]);

  if (userMode === null) {
    return <SafeAreaView style={styles.safe}><View style={styles.loadingScreen} /></SafeAreaView>;
  }

  if (!userMode || modePickerOpen) {
    return (
      <SafeAreaView style={styles.safe}>
        <StatusBar style="light" />
        <RoleSelection initialValue={userMode} onContinue={saveUserMode} saving={savingMode} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style={isDark ? 'light' : 'dark'} />
      <View style={styles.app}>
        <ProfileHeader
          profile={profile}
          status={status}
          userMode={userMode}
          onRefresh={refreshShell}
          onChangeMode={() => setModePickerOpen(true)}
        />
        <View style={styles.content}>{renderScreen()}</View>
        <View style={styles.tabBar}>
          {tabs.map((tab) => (
            <TouchableOpacity
              key={tab.key}
              style={[styles.tab, activeTab === tab.key && styles.tabActive]}
              onPress={() => setActiveTab(tab.key)}
              activeOpacity={0.85}
            >
              <Text style={[styles.tabIcon, activeTab === tab.key && styles.tabTextActive]}>
                {tab.icon}
              </Text>
              <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    </SafeAreaView>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: colors.background },
    app:  { flex: 1, backgroundColor: colors.background },
    loadingScreen: { flex: 1, backgroundColor: colors.background },
    content: { flex: 1 },
    tabBar: {
      flexDirection: 'row',
      gap: 3,
      paddingHorizontal: 5,
      paddingTop: 8,
      paddingBottom: 12,
      backgroundColor: colors.panel,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    tab: {
      flex: 1,
      minHeight: 48,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 12,
      backgroundColor: 'transparent',
    },
    tabActive: { backgroundColor: colors.primarySoft },
    tabIcon: { color: colors.textMuted, fontWeight: '900', fontSize: 12, marginBottom: 3 },
    tabText: { color: colors.textMuted, fontWeight: '700', fontSize: 9 },
    tabTextActive: { color: colors.accentText },
  });
}
