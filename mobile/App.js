import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, AppState, SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
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

const NEW_MAIL_POLL_INTERVAL_MS = 5000;

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
  const [newMailNotice, setNewMailNotice] = useState(null);
  const [unseenMailCount, setUnseenMailCount] = useState(0);
  const lastSeenMailId = useRef(null);
  const mailNoticeTimer = useRef(null);

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

  useEffect(() => {
    if (!isAuthenticated) return undefined;

    let active = true;
    let checking = false;

    const dismissLater = () => {
      if (mailNoticeTimer.current) clearTimeout(mailNoticeTimer.current);
      mailNoticeTimer.current = setTimeout(() => {
        if (active) setNewMailNotice(null);
      }, 8000);
    };

    const checkForNewMail = async () => {
      if (checking) return;
      checking = true;
      try {
        const data = await apiGet('/email/new-mail-check');
        if (!active || !data?.success || !data.latest_id) return;

        // The first successful check establishes a baseline. Bob only
        // announces IDs that appear after that, so opening the app does not
        // produce a misleading popup for an old unread message.
        if (lastSeenMailId.current === null) {
          lastSeenMailId.current = data.latest_id;
          return;
        }
        if (data.latest_id === lastSeenMailId.current) return;

        lastSeenMailId.current = data.latest_id;
        setNewMailNotice({
          id: data.latest_id,
          sender: String(data.latest_sender || '').split('<')[0].trim(),
          subject: String(data.latest_subject || '').trim(),
          meetingSuggestion: data.meeting_suggestion || null,
        });
        setUnseenMailCount((count) => count + 1);
        dismissLater();
      } catch (error) {
        // Gmail may not be connected yet. This background agent must remain
        // silent and retry later instead of interrupting the current tab.
        if (error?.status !== 401) console.warn('New mail check failed:', error);
      } finally {
        checking = false;
      }
    };

    checkForNewMail();
    const interval = setInterval(checkForNewMail, NEW_MAIL_POLL_INTERVAL_MS);
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') checkForNewMail();
    });

    return () => {
      active = false;
      clearInterval(interval);
      subscription.remove();
      if (mailNoticeTimer.current) clearTimeout(mailNoticeTimer.current);
    };
  }, [isAuthenticated]);

  const handleLogout = useCallback(async () => {
    try { await apiPost('/email/logout'); } catch { /* ignore */ }
    await clearPersistedSession();
    setProfile(null);
    setStatus(null);
    setUserMode(null);
    setModePickerOpen(false);
    setNewMailNotice(null);
    lastSeenMailId.current = null;
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
    if (activeTab === 'overview') return <OverviewScreen onAgentSync={handleAgentSync} syncEvent={syncEvent} onNavigate={setActiveTab} />;
    if (activeTab === 'emails')   return <EmailScreen userMode={userMode || 'worker'} onAuthChanged={refreshShell} onAgentSync={handleAgentSync} onNavigate={setActiveTab} syncEvent={syncEvent} />;
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
        {newMailNotice ? (
          <View style={styles.mailNotice} accessibilityRole="alert">
            <View style={styles.mailNoticeIcon}>
              <Ionicons name="mail-unread-outline" size={21} color="#FFFFFF" />
            </View>
            <View style={styles.mailNoticeBody}>
              <Text style={styles.mailNoticeTitle}>
                {newMailNotice.meetingSuggestion
                  ? t('Bob phát hiện một lịch hẹn', 'Bob found an appointment')
                  : t('Bob phát hiện email mới', 'Bob spotted new mail')}
              </Text>
              <Text style={styles.mailNoticeText} numberOfLines={2}>
                {[newMailNotice.sender, newMailNotice.subject].filter(Boolean).join(' — ')
                  || t('Bạn vừa nhận được một email mới.', 'You just received a new email.')}
              </Text>
            </View>
            <TouchableOpacity
              style={styles.mailNoticeAction}
              onPress={() => {
                if (newMailNotice.meetingSuggestion) {
                  setActiveTab('schedule');
                  handleAgentSync(['email', 'schedule', 'overview']);
                } else {
                  setUnseenMailCount(0);
                  setActiveTab('emails');
                }
                setNewMailNotice(null);
              }}
            >
              <Text style={styles.mailNoticeActionText}>{t('Xem', 'View')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.mailNoticeClose}
              onPress={() => setNewMailNotice(null)}
              accessibilityLabel={t('Đóng thông báo', 'Dismiss notification')}
            >
              <Ionicons name="close" size={18} color="#FFFFFF" />
            </TouchableOpacity>
          </View>
        ) : null}
        <View style={styles.tabBar}>
          {tabs.map((tab) => {
            const active = activeTab === tab.key;
            const showMailBadge = tab.key === 'emails' && unseenMailCount > 0;
            return (
              <TouchableOpacity
                key={tab.key}
                style={styles.tab}
                onPress={() => {
                  if (tab.key === 'emails') setUnseenMailCount(0);
                  setActiveTab(tab.key);
                }}
                activeOpacity={0.85}
              >
                <View style={styles.tabIconWrap}>
                  <Ionicons
                    name={tab.icon}
                    size={20}
                    color={active ? colors.primary : colors.textMuted}
                    style={[styles.tabIcon, active && styles.tabIconActive]}
                  />
                  {showMailBadge ? (
                    <View style={styles.tabBadge}>
                      <Text style={styles.tabBadgeText}>{unseenMailCount > 9 ? '9+' : unseenMailCount}</Text>
                    </View>
                  ) : null}
                </View>
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
    mailNotice: {
      position: 'absolute',
      top: 74,
      left: 14,
      right: 14,
      zIndex: 100,
      elevation: 12,
      minHeight: 72,
      flexDirection: 'row',
      alignItems: 'center',
      padding: 12,
      paddingRight: 34,
      borderRadius: 16,
      backgroundColor: '#6842E3',
      shadowColor: '#000000',
      shadowOffset: { width: 0, height: 6 },
      shadowOpacity: 0.22,
      shadowRadius: 12,
    },
    mailNoticeIcon: {
      width: 38,
      height: 38,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'rgba(255,255,255,0.16)',
      marginRight: 10,
    },
    mailNoticeBody: { flex: 1 },
    mailNoticeTitle: { color: '#FFFFFF', fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    mailNoticeText: { color: 'rgba(255,255,255,0.88)', fontFamily: 'Poppins_400Regular', fontSize: 11.5 },
    mailNoticeAction: { paddingHorizontal: 10, paddingVertical: 7, marginLeft: 6 },
    mailNoticeActionText: { color: '#FFFFFF', fontFamily: 'Poppins_600SemiBold', fontSize: 12 },
    mailNoticeClose: { position: 'absolute', top: 5, right: 5, padding: 5 },
    tabBar: {
      flexDirection: 'row',
      paddingHorizontal: 8,
      paddingTop: 8,
      paddingBottom: 12,
      backgroundColor: colors.panel,
      borderTopColor: colors.border,
      borderTopWidth: 1,
      ...colors.shadow,
    },
    tab: {
      flex: 1,
      minHeight: 52,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: 4,
    },
    tabIconWrap: { position: 'relative' },
    tabIcon: { paddingHorizontal: 12, paddingVertical: 4, borderRadius: 999 },
    tabIconActive: { backgroundColor: colors.primarySoft, overflow: 'hidden' },
    tabBadge: {
      position: 'absolute',
      top: -2,
      right: 4,
      minWidth: 15,
      height: 15,
      borderRadius: 8,
      paddingHorizontal: 3,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: '#ef4444',
      borderWidth: 1.5,
      borderColor: colors.panel,
    },
    tabBadgeText: { color: '#FFFFFF', fontFamily: 'Poppins_700Bold', fontSize: 8.5, lineHeight: 10 },
    tabText: {
      color: colors.textMuted,
      fontWeight: '600',
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 9.5,
      marginTop: 2,
    },
    tabTextActive: { color: colors.primary },
  });
}
