import React, { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import Button from '../components/Button';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';

export default function WelcomeScreen({ onGetStarted, onLogIn }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.body}>
      <View style={styles.illustrationRing}>
        <LinearGradient
          colors={['#55BEFE', '#5A54FB', '#8171FD', '#D65EFC']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.illustrationOrb}
        >
          <Ionicons name="sparkles" size={52} color="#ffffff" />
        </LinearGradient>
        <View style={[styles.floatChip, styles.floatChipMail]}>
          <Ionicons name="mail" size={18} color={colors.primary} />
        </View>
        <View style={[styles.floatChip, styles.floatChipCalendar]}>
          <Ionicons name="calendar" size={18} color={colors.primary} />
        </View>
        <View style={[styles.floatChip, styles.floatChipCheck]}>
          <Ionicons name="checkmark-circle" size={16} color={colors.success} />
        </View>
      </View>

      <Text style={styles.title}>{t('Chào mừng đến với FlowMate AI', 'Welcome to FlowMate AI')}</Text>
      <Text style={styles.subtitle}>
        {t(
          'Hành trình làm việc hiệu quả và tập trung rõ ràng bắt đầu từ đây.',
          'Your journey to effortless productivity and clear focus begins here.'
        )}
      </Text>

      <View style={styles.spacer} />

      <Button
        title={t('Bắt đầu', 'Get Started')}
        icon="arrow-forward"
        onPress={onGetStarted}
        style={styles.ctaButton}
      />
      <TouchableOpacity onPress={onLogIn} activeOpacity={0.75} style={styles.logInLinkWrap}>
        <Text style={styles.logInLink}>{t('Đăng nhập', 'Log In')}</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    body: { flexGrow: 1, paddingHorizontal: 28, paddingTop: 56, paddingBottom: 30, alignItems: 'center' },
    illustrationRing: {
      width: 240,
      height: 240,
      borderRadius: 120,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.panel,
      borderWidth: 1,
      borderColor: colors.border,
      ...colors.shadow,
    },
    illustrationOrb: {
      width: 140,
      height: 140,
      borderRadius: 70,
      alignItems: 'center',
      justifyContent: 'center',
      shadowColor: '#5A54FB',
      shadowOffset: { width: 0, height: 10 },
      shadowOpacity: 0.5,
      shadowRadius: 22,
      elevation: 12,
    },
    floatChip: {
      position: 'absolute',
      width: 44,
      height: 44,
      borderRadius: radius.control,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.panel,
      borderWidth: 1,
      borderColor: colors.border,
      ...colors.shadow,
    },
    floatChipMail: { top: 8, right: 4 },
    floatChipCalendar: { bottom: 18, left: -2 },
    floatChipCheck: { bottom: 52, right: -10, width: 36, height: 36, borderRadius: radius.control - 2 },
    title: {
      marginTop: 40,
      color: colors.text,
      fontFamily: 'Poppins_800ExtraBold',
      fontSize: 26,
      textAlign: 'center',
      letterSpacing: -0.4,
    },
    subtitle: {
      marginTop: 12,
      color: colors.textMuted,
      fontFamily: 'Poppins_400Regular',
      fontSize: 14.5,
      textAlign: 'center',
      lineHeight: 22,
      maxWidth: 300,
    },
    spacer: { flexGrow: 1, minHeight: 24 },
    ctaButton: { width: '100%', minHeight: 54 },
    logInLinkWrap: { marginTop: 16, padding: 6 },
    logInLink: { color: colors.primary, fontFamily: 'Poppins_600SemiBold', fontSize: 14 },
  });
}
