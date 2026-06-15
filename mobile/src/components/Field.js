import React, { useMemo } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { useTheme } from '../theme/ThemeContext';

export default function Field({ label, value, onChangeText, placeholder, multiline, keyboardType }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  return (
    <View style={styles.group}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={[styles.input, multiline && styles.multiline]}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.inputPlaceholder}
        multiline={multiline}
        keyboardType={keyboardType}
        textAlignVertical={multiline ? 'top' : 'center'}
      />
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    group:   { marginBottom: 12 },
    label:   { color: colors.textMuted, fontWeight: '700', marginBottom: 6 },
    input: {
      minHeight: 44,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: 8,
      backgroundColor: colors.panel,
      color: colors.text,
      paddingHorizontal: 12,
      paddingVertical: 10,
    },
    multiline: { minHeight: 92 },
  });
}
