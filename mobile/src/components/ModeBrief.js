import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { getUserMode } from '../config/userModes';
import { useTheme } from '../theme/ThemeContext';

export default function ModeBrief({ userMode, stats = [] }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const mode = getUserMode(userMode);

  return (
    <View style={styles.card}>
      <Text style={styles.label}>AI BRIEF · {mode.shortLabel.toUpperCase()}</Text>
      <Text style={styles.title}>Hom nay nen tap trung vao dieu gi?</Text>
      <Text style={styles.description}>{mode.description}</Text>
      {stats.length ? (
        <View style={styles.stats}>
          {stats.map((item) => (
            <View key={item.label} style={styles.stat}>
              <Text style={styles.statValue}>{item.value}</Text>
              <Text style={styles.statLabel}>{item.label}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    card: {
      marginHorizontal: 16,
      marginBottom: 12,
      padding: 16,
      borderRadius: 20,
      borderWidth: 1,
      borderColor: 'rgba(108,99,255,0.32)',
      backgroundColor: colors.primarySoft,
    },
    label: { color: colors.accentText, fontSize: 10, fontWeight: '900', letterSpacing: 1.1 },
    title: { marginTop: 8, color: colors.text, fontSize: 17, fontWeight: '900' },
    description: { marginTop: 6, color: colors.textMuted, lineHeight: 19, fontSize: 12 },
    stats: { flexDirection: 'row', gap: 8, marginTop: 14 },
    stat: {
      flex: 1,
      paddingHorizontal: 10,
      paddingVertical: 9,
      borderRadius: 12,
      backgroundColor: 'rgba(255,255,255,0.06)',
    },
    statValue: { color: colors.text, fontWeight: '900', fontSize: 16 },
    statLabel: { marginTop: 2, color: colors.textMuted, fontSize: 9, fontWeight: '700' },
  });
}
