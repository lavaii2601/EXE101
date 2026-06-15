import React, { useMemo } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity } from 'react-native';
import { useTheme } from '../theme/ThemeContext';

export default function Button({ title, onPress, variant = 'primary', disabled, loading, style }) {
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
        <Text style={[styles.text, isSecondary && styles.secondaryText]}>{title}</Text>
      )}
    </TouchableOpacity>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    button: {
      minHeight: 42,
      paddingHorizontal: 14,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.primary,
    },
    secondary: { backgroundColor: colors.secondaryBg },
    danger:    { backgroundColor: colors.danger },
    disabled:  { opacity: 0.55 },
    text:      { color: '#ffffff', fontWeight: '700' },
    secondaryText: { color: colors.secondaryText },
  });
}
