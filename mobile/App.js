import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import {
  useFonts,
  Poppins_400Regular,
  Poppins_500Medium,
  Poppins_600SemiBold,
  Poppins_700Bold,
  Poppins_800ExtraBold,
} from '@expo-google-fonts/poppins';
import ChatScreen from './src/screens/ChatScreen';
import OverviewScreen from './src/screens/OverviewScreen';
import EmailScreen from './src/screens/EmailScreen';
import ScheduleScreen from './src/screens/ScheduleScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import LoginScreen from './src/screens/LoginScreen';
import ProfileHeader from './src/components/ProfileHeader';
import RoleSelection from './src/components/RoleSelection';
import { apiGet, apiPost } from './src/api/client';
import { clearPersistedSession, loadPersistedSession } from './src/api/session';
import { ThemeProvider, useTheme } from './src/theme/ThemeContext';
import { LanguageProvider, useLanguage } from './src/i18n/LanguageContext';

const tabs = [
  { key: 'overview', icon: 'stats-chart-outline', label: ['Tổng hợp', 'Overview'] },
  { key: 'chat',     icon: 'chatbubble-outline',  label: ['Chat', 'Chat'] },
  { key: 'emails',   icon: 'mail-outline',        label: ['Email', 'Email'] },
  { key: 'schedule', icon: 'calendar-outline',    label: ['Lịch', 'Calendar'] },
  { key: 'history',  icon: 'time-outline',        label: ['Lịch sử', 'History'] },
  { key: 'settings', icon: 'settings-outline',    label: ['Cài đặt', 'Settings'] },
];

export default function App() {
  const [fontsLoaded] = useFonts({
    Poppins_400Regular,
    Poppins_500Medium,
    Poppins_600SemiBold,
    Poppins_700Bold,
    Poppins_800ExtraBold,
  });

  if (!fontsLoaded) {
    return <View style={{ flex: 1, backgroundColor: '#f5f7fb' }} />;
  }

  return (
    <ThemeProvider>
      <LanguageProvider>
        <AppShell />
      </LanguageProvider>
    </ThemeProvider>
  );
}

function AppShell() {
  const { colors, isDark } = useTheme();
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState('overview');
  const [profile, setProfile] = useState(null);
  const [status, setStatus] = useState(null);
  const [userMode, setUserMode] = useState(null);
  // null = not checked yet (show loading screen), false = no backend session
  // (show LoginScreen), true = signed in with Google.
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [agentProfile, setAgentProfile] = useState(null);
  const [syncEvent, setSyncEvent] = useState({ id: 0, targets: [] });
  const [savingMode, setSavingMode] = useState(false);
  const [modePickerOpen, setModePickerOpen] = useState(false);

  const refreshShell = useCallback(async () => {
    const [profileResult, statusResult, agentResult] = await Promise.allSettled([
      apiGet('/user/profile'),
      apiGet('/status'),
      apiGet('/chat/agent-profile'),
    ]);
    if (profileResult.status === 'fulfilled' && profileResult.value.success) {
      setIsAuthenticated(true);
      setProfile(profileResult.value.user);
      setUserMode(profileResult.value.user?.user_mode || '');
    } else if (profileResult.status === 'rejected' && profileResult.reason?.status === 401) {
      // No backend session yet (fresh install, never signed in, or just
      // logged out) -- show the login screen instead of leaving the app
      // stuck on a blank loading screen or inside the authenticated shell.
      setIsAuthenticated(false);
    }
    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    }
    if (agentResult.status === 'fulfilled' && agentResult.value.success) {
      setAgentProfile(agentResult.value.agent || null);
    }
  }, []);

  useEffect(() => {
    // Restore a previously signed-in session from secure storage BEFORE the
    // first API call, so the access token is already in place -- otherwise
    // every app restart silently calls the backend as an anonymous user.
    loadPersistedSession().finally(refreshShell);
  }, [refreshShell]);

  const handleLogout = useCallback(async () => {
    try { await apiPost('/email/logout'); } catch { /* ignore */ }
    await clearPersistedSession();
    setProfile(null);
    setStatus(null);
    setUserMode(null);
    setModePickerOpen(false);
    setActiveTab('overview');
    // Drives the render below back to LoginScreen instead of leaving the
    // user stuck inside the authenticated tabs (e.g. still on Settings).
    setIsAuthenticated(false);
  }, []);

  const handleLoggedIn = useCallback(() => {
    setIsAuthenticated(null);
    refreshShell();
  }, [refreshShell]);

  const saveUserMode = useCallback(async (mode) => {
    setSavingMode(true);
    try {
      const data = await apiPost('/user/profile', { user_mode: mode });
      setProfile(data.user || profile);
      setUserMode(mode);
      setModePickerOpen(false);
    } catch (error) {
      // 401 = no backend session yet; 403 = backend also rejects unauthenticated
      // POSTs that arrive without a browser Origin header (always true for the
      // native app's fetch). Both mean "not signed in with Google yet" here --
      // keep the chosen mode locally so the user can reach the app and connect
      // Gmail from Settings/Email; it persists server-side on the next save
      // once a backend session exists.
      if (error.status === 401 || error.status === 403) {
        setUserMode(mode);
        setModePickerOpen(false);
      } else {
        Alert.alert('Không lưu được chế độ', error.message);
      }
    } finally {
      setSavingMode(false);
    }
  }, [profile]);

  const handleAgentSync = useCallback((targets = [], metadata = {}) => {
    const normalizedTargets = Array.from(new Set((Array.isArray(targets) ? targets : [])
      .filter(Boolean)));
    if (!normalizedTargets.length) return;
    setSyncEvent((current) => ({
      id: current.id + 1,
      targets: normalizedTargets,
      trace: metadata.agent_trace || null,
      at: Date.now(),
    }));
    if (normalizedTargets.some((target) => ['settings', 'profile', 'providers'].includes(target))) {
      refreshShell();
    }
  }, [refreshShell]);

  const renderScreen = () => {
    if (activeTab === 'overview') return <OverviewScreen onAgentSync={handleAgentSync} syncEvent={syncEvent} />;
    if (activeTab === 'emails')   return <EmailScreen userMode={userMode || 'worker'} onAuthChanged={refreshShell} onAgentSync={handleAgentSync} syncEvent={syncEvent} />;
    if (activeTab === 'schedule') return <ScheduleScreen onAgentSync={handleAgentSync} syncEvent={syncEvent} />;
    if (activeTab === 'history')  return <HistoryScreen syncEvent={syncEvent} />;
    if (activeTab === 'settings') return (
      <SettingsScreen
        profile={profile}
        status={status}
        userMode={userMode || 'worker'}
        onChangeMode={() => setModePickerOpen(true)}
        onRefresh={refreshShell}
        onLogout={handleLogout}
        onAgentSync={handleAgentSync}
        syncEvent={syncEvent}
      />
    );
    return <ChatScreen userMode={userMode || 'worker'} agentProfile={agentProfile} onAgentSync={handleAgentSync} />;
  };

  const styles = useMemo(() => makeStyles(colors), [colors]);

  if (isAuthenticated === null) {
    return <SafeAreaView style={styles.safe}><View style={styles.loadingScreen} /></SafeAreaView>;
  }

  if (!isAuthenticated) {
    return (
      <SafeAreaView style={styles.safe}>
        <StatusBar style={isDark ? 'light' : 'dark'} />
        <LoginScreen onLoggedIn={handleLoggedIn} />
      </SafeAreaView>
    );
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
          {tabs.map((tab) => {
            const active = activeTab === tab.key;
            return (
              <TouchableOpacity
                key={tab.key}
                style={styles.tab}
                onPress={() => setActiveTab(tab.key)}
                activeOpacity={0.85}
              >
                <Ionicons
                  name={tab.icon}
                  size={20}
                  color={active ? colors.primary : colors.textMuted}
                />
                <Text style={[styles.tabText, active && styles.tabTextActive]}>
                  {t(...tab.label)}
                </Text>
              </TouchableOpacity>
            );
          })}
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
      paddingHorizontal: 5,
      paddingTop: 6,
      paddingBottom: 14,
      backgroundColor: colors.panel,
      borderTopColor: colors.border,
      borderTopWidth: 1,
    },
    tab: {
      flex: 1,
      minHeight: 48,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: 6,
    },
    tabText: {
      color: colors.textMuted,
      fontWeight: '600',
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 10,
      marginTop: 3,
    },
    tabTextActive: { color: colors.primary },
  });
}
