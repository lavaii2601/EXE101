import React, { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import Button from './Button';
import { USER_MODES } from '../config/userModes';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';

function GradientLine({ width }) {
  return (
    <LinearGradient
      colors={['#ff6fd8', '#D65EFC', '#946BFD']}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 0 }}
      style={[calendarStyles.line, { width }]}
    />
  );
}

function Sparkle() {
  return (
    <View style={calendarStyles.sparkleWrap}>
      <View style={calendarStyles.sparkleV} />
      <View style={calendarStyles.sparkleH} />
    </View>
  );
}

function CalendarIcon() {
  return (
    <View style={calendarStyles.wrap}>
      {/* Clips */}
      <View style={calendarStyles.clips}>
        <View style={calendarStyles.clip} />
        <View style={calendarStyles.clip} />
      </View>
      {/* Calendar body */}
      <View style={calendarStyles.body}>
        <GradientLine width={32} />
        <GradientLine width={26} />
        <GradientLine width={18} />
      </View>
      {/* Sparkle top-right */}
      <Sparkle />
    </View>
  );
}

const calendarStyles = StyleSheet.create({
  wrap: {
    width: 60,
    height: 60,
    alignItems: 'center',
    justifyContent: 'center',
  },
  clips: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 7,
  },
  clip: {
    width: 10,
    height: 6,
    borderRadius: 3,
    backgroundColor: 'rgba(255,255,255,0.95)',
  },
  body: {
    gap: 5,
    alignItems: 'flex-start',
  },
  line: {
    height: 4,
    borderRadius: 2,
  },
  sparkleWrap: {
    position: 'absolute',
    top: 2,
    right: 3,
    width: 14,
    height: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sparkleV: {
    position: 'absolute',
    width: 2,
    height: 13,
    borderRadius: 1,
    backgroundColor: 'rgba(255,255,255,0.95)',
  },
  sparkleH: {
    position: 'absolute',
    width: 13,
    height: 2,
    borderRadius: 1,
    backgroundColor: 'rgba(255,255,255,0.95)',
  },
});

export default function RoleSelection({ initialValue = '', onContinue, saving }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [selected, setSelected] = useState(initialValue);

  return (
    <View style={styles.root}>
      <View style={styles.brand}>
        <LinearGradient
          colors={['#55BEFE', '#5A54FB', '#8171FD', '#D65EFC']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.orb}
        >
          <CalendarIcon />
        </LinearGradient>
        <Text style={styles.eyebrow}>FLOWMATE AI</Text>
        <Text style={styles.title}>{t('Chọn chế độ của bạn', 'Choose your mode')}</Text>
        <Text style={styles.subtitle}>
          {t(
            'FlowMate sẽ thay đổi ưu tiên email, gợi ý lịch và cách AI phản hồi theo vai trò.',
            'FlowMate adapts email priorities, schedule suggestions, and AI replies to your role.'
          )}
        </Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.grid}>
          {USER_MODES.map((mode) => {
            const active = selected === mode.value;
            return (
              <TouchableOpacity
                key={mode.value}
                style={[styles.card, active && styles.cardActive]}
                onPress={() => setSelected(mode.value)}
                activeOpacity={0.85}
              >
                <View style={[styles.icon, active && styles.iconActive]}>
                  <Ionicons name={mode.icon} size={18} color={active ? '#ffffff' : colors.accentText} />
                </View>
                <Text style={styles.cardTitle}>{mode.label}</Text>
                <Text style={styles.cardDescription}>{mode.description}</Text>
                {active ? (
                  <View style={styles.checkRow}>
                    <Ionicons name="checkmark-circle" size={13} color={colors.accentText} />
                    <Text style={styles.check}>{t('Đã chọn', 'Selected')}</Text>
                  </View>
                ) : null}
              </TouchableOpacity>
            );
          })}
        </View>
        <Button
          title={t('Tiếp tục', 'Continue')}
          disabled={!selected}
          loading={saving}
          onPress={() => onContinue(selected)}
          style={styles.continueButton}
        />
      </ScrollView>
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    brand: { alignItems: 'center', paddingHorizontal: 26, paddingTop: 42, paddingBottom: 20 },
    orb: {
      width: 96,
      height: 96,
      borderRadius: 26,
      alignItems: 'center',
      justifyContent: 'center',
      shadowColor: '#5A54FB',
      shadowOffset: { width: 0, height: 10 },
      shadowOpacity: 0.50,
      shadowRadius: 22,
      elevation: 12,
    },
    eyebrow: { marginTop: 18, color: colors.accentText, fontFamily: 'Poppins_700Bold', fontSize: 11, letterSpacing: 1.4 },
    title: { marginTop: 7, color: colors.text, fontFamily: 'Poppins_800ExtraBold', fontSize: 25 },
    subtitle: { marginTop: 8, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13, textAlign: 'center', lineHeight: 20 },
    body: { paddingHorizontal: 16, paddingBottom: 30 },
    grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
    card: {
      width: '48.5%',
      minHeight: 166,
      padding: 14,
      borderRadius: radius.card,
      borderWidth: 1.5,
      borderColor: colors.border,
      backgroundColor: colors.panel,
    },
    cardActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft, ...colors.shadow },
    icon: {
      width: 38,
      height: 38,
      borderRadius: radius.control,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.panelSoft,
    },
    iconActive: { backgroundColor: colors.primary },
    cardTitle: { marginTop: 12, color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 14 },
    cardDescription: { marginTop: 5, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11, lineHeight: 16 },
    checkRow: { marginTop: 8, flexDirection: 'row', alignItems: 'center', gap: 4 },
    check: { color: colors.accentText, fontFamily: 'Poppins_700Bold', fontSize: 11 },
    continueButton: { marginTop: 18, minHeight: 52 },
  });
}
