import React, { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Button from './Button';
import { USER_MODES } from '../config/userModes';
import { useTheme } from '../theme/ThemeContext';

function CalendarIcon() {
  return (
    <View style={calendarStyles.wrap}>
      <View style={calendarStyles.header}>
        <View style={calendarStyles.clip} /><View style={calendarStyles.clip} />
      </View>
      <View style={calendarStyles.body}>
        <View style={[calendarStyles.line, { width: 28 }]} />
        <View style={[calendarStyles.line, { width: 22, backgroundColor: '#D65EFC' }]} />
        <View style={[calendarStyles.line, { width: 16, backgroundColor: '#946BFD' }]} />
      </View>
      <View style={calendarStyles.sparkle}><Text style={{ color: '#fff', fontSize: 11 }}>✦</Text></View>
    </View>
  );
}

const calendarStyles = StyleSheet.create({
  wrap:    { width: 54, height: 54, alignItems: 'center', justifyContent: 'center' },
  header:  { flexDirection: 'row', gap: 14, marginBottom: 6 },
  clip:    { width: 4, height: 8, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.9)' },
  body:    { gap: 4, alignItems: 'flex-start' },
  line:    { height: 3.5, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.9)' },
  sparkle: { position: 'absolute', top: 2, right: 4 },
});

export default function RoleSelection({ initialValue = '', onContinue, saving }) {
  const { colors } = useTheme();
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
        <Text style={styles.title}>Chọn chế độ của bạn</Text>
        <Text style={styles.subtitle}>
          FlowMate sẽ thay đổi ưu tiên email, gợi ý lịch và cách AI phản hồi theo vai trò.
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
                  <Text style={styles.iconText}>{mode.icon}</Text>
                </View>
                <Text style={styles.cardTitle}>{mode.label}</Text>
                <Text style={styles.cardDescription}>{mode.description}</Text>
                {active ? <Text style={styles.check}>Đã chọn</Text> : null}
              </TouchableOpacity>
            );
          })}
        </View>
        <Button
          title="Tiếp tục"
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
      width: 82,
      height: 82,
      borderRadius: 22,
      alignItems: 'center',
      justifyContent: 'center',
      shadowColor: '#5A54FB',
      shadowOffset: { width: 0, height: 8 },
      shadowOpacity: 0.45,
      shadowRadius: 18,
      elevation: 10,
    },
    eyebrow: { marginTop: 18, color: colors.accentText, fontSize: 11, fontWeight: '800', letterSpacing: 1.4 },
    title: { marginTop: 7, color: colors.text, fontSize: 25, fontWeight: '900' },
    subtitle: { marginTop: 8, color: colors.textMuted, textAlign: 'center', lineHeight: 20 },
    body: { paddingHorizontal: 16, paddingBottom: 30 },
    grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
    card: {
      width: '48.5%',
      minHeight: 166,
      padding: 14,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.panel,
    },
    cardActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
    icon: {
      width: 38,
      height: 38,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.panelSoft,
    },
    iconActive: { backgroundColor: colors.primary },
    iconText: { color: '#ffffff', fontSize: 11, fontWeight: '900' },
    cardTitle: { marginTop: 12, color: colors.text, fontWeight: '800', fontSize: 14 },
    cardDescription: { marginTop: 5, color: colors.textMuted, fontSize: 11, lineHeight: 16 },
    check: { marginTop: 8, color: colors.accentText, fontSize: 11, fontWeight: '800' },
    continueButton: { marginTop: 18, borderRadius: 14, minHeight: 50 },
  });
}
