import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import ChatScreen from './src/screens/ChatScreen';
import OverviewScreen from './src/screens/OverviewScreen';
import EmailScreen from './src/screens/EmailScreen';
import ScheduleScreen from './src/screens/ScheduleScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import ProfileHeader from './src/components/ProfileHeader';
import RoleSelection from './src/components/RoleSelection';
import { apiGet, apiPost } from './src/api/client';
import { ThemeProvider, useTheme } from './src/theme/ThemeContext';

const tabs = [
  { key: 'overview', icon: 'AI', label: 'Tổng hợp' },
  { key: 'chat',     icon: '💬', label: 'Chat' },
  { key: 'emails',   icon: '✉',  label: 'Email' },
  { key: 'schedule', icon: '📅', label: 'Lịch' },
  { key: 'history',  icon: '🕐', label: 'Lịch sử' },
  { key: 'settings', icon: '⚙',  label: 'Cài đặt' },
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
  const [activeTab, setActiveTab] = useState('overview');
  const [profile, setProfile] = useState(null);
  const [status, setStatus] = useState(null);
  const [userMode, setUserMode] = useState(null);
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
      setProfile(profileResult.value.user);
      setUserMode(profileResult.value.user?.user_mode || '');
    }
    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    }
    if (agentResult.status === 'fulfilled' && agentResult.value.success) {
      setAgentProfile(agentResult.value.agent || null);
    }
  }, []);

  useEffect(() => {
    refreshShell();
  }, [refreshShell]);

  const handleLogout = useCallback(async () => {
    try { await apiPost('/email/logout'); } catch { /* ignore */ }
    setProfile(null);
    setStatus(null);
    setActiveTab('overview');
  }, []);

  const saveUserMode = useCallback(async (mode) => {
    setSavingMode(true);
    try {
      const data = await apiPost('/user/profile', { user_mode: mode });
      setProfile(data.user || profile);
      setUserMode(mode);
      setModePickerOpen(false);
    } catch (error) {
      Alert.alert('Không lưu được chế độ', error.message);
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
    if (activeTab === 'overview') return <OverviewScreen syncEvent={syncEvent} />;
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
