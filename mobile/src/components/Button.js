import React, { useMemo } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radius, useTheme } from '../theme/ThemeContext';

export default function Button({ title, onPress, variant = 'primary', disabled, loading, icon, style }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const isSecondary = variant === 'secondary';
  const isDanger    = variant === 'danger';

  return (
    <TouchableOpacity
      style={[
        styles.button,
        isSecondary && styles.secondary,
        isDanger    && styles.danger,
        disabled    && styles.disabled,
        style,
      ]}
      activeOpacity={0.85}
      disabled={disabled || loading}
      onPress={onPress}
    >
      {loading ? (
        <ActivityIndicator color={isSecondary ? colors.primary : '#ffffff'} />
      ) : (
        <View style={styles.content}>
          <Text style={[styles.text, isSecondary && styles.secondaryText]}>{title}</Text>
          {icon ? (
            <Ionicons name={icon} size={16} color={isSecondary ? colors.secondaryText : '#ffffff'} />
          ) : null}
        </View>
      )}
    </TouchableOpacity>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    button: {
      minHeight: 48,
      paddingHorizontal: 18,
      borderRadius: radius.button,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.primary,
      ...colors.shadow,
    },
    secondary: { backgroundColor: colors.secondaryBg, shadowOpacity: 0, elevation: 0 },
    danger:    { backgroundColor: colors.danger },
    disabled:  { opacity: 0.55, shadowOpacity: 0, elevation: 0 },
    content:   { flexDirection: 'row', alignItems: 'center', gap: 8 },
    text:      { color: '#ffffff', fontWeight: '700', fontSize: 14, fontFamily: 'Poppins_700Bold', letterSpacing: 0.2 },
    secondaryText: { color: colors.secondaryText, fontFamily: 'Poppins_600SemiBold' },
  });
}
