import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../theme/ThemeContext';

export default function EmptyState({ title, detail }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      {detail ? <Text style={styles.detail}>{detail}</Text> : null}
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    wrap: { padding: 22, alignItems: 'center', justifyContent: 'center' },
    title: { color: colors.text, fontWeight: '700', textAlign: 'center' },
    detail: {
      marginTop: 6,
      color: colors.textMuted,
      textAlign: 'center',
      lineHeight: 20,
    },
  });
}
