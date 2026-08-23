import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../theme/ThemeContext';

export default function EmptyState({ title, detail, icon = 'file-tray-outline' }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  return (
    <View style={styles.wrap}>
      <View style={styles.iconWrap}>
        <Ionicons name={icon} size={22} color={colors.primary} />
      </View>
      <Text style={styles.title}>{title}</Text>
      {detail ? <Text style={styles.detail}>{detail}</Text> : null}
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    wrap: { padding: 22, alignItems: 'center', justifyContent: 'center' },
    iconWrap: {
      width: 46,
      height: 46,
      borderRadius: 16,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.primarySoft,
      marginBottom: 10,
    },
    title: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 14, textAlign: 'center' },
    detail: {
      marginTop: 6,
      color: colors.textMuted,
      fontFamily: 'Poppins_400Regular',
      fontSize: 12,
      textAlign: 'center',
      lineHeight: 19,
    },
  });
}
