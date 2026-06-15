import React, { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import Button from './Button';
import { USER_MODES } from '../config/userModes';
import { useTheme } from '../theme/ThemeContext';

export default function RoleSelection({ initialValue = '', onContinue, saving }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [selected, setSelected] = useState(initialValue);

  return (
    <View style={styles.root}>
      <View style={styles.brand}>
        <View style={styles.orb}><Text style={styles.orbText}>AI</Text></View>
        <Text style={styles.eyebrow}>FLOWMATE AI</Text>
        <Text style={styles.title}>Chon che do cua ban</Text>
        <Text style={styles.subtitle}>
          FlowMate se thay doi uu tien email, goi y lich va cach AI phan hoi theo vai tro.
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
                {active ? <Text style={styles.check}>Da chon</Text> : null}
              </TouchableOpacity>
            );
          })}
        </View>
        <Button
          title="Tiep tuc"
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
      width: 78,
      height: 78,
      borderRadius: 39,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.primary,
      borderWidth: 8,
      borderColor: 'rgba(108,99,255,0.18)',
    },
    orbText: { color: '#ffffff', fontSize: 24, fontWeight: '900' },
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
