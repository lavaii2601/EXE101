import React, { useMemo, useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { radius, useTheme } from '../theme/ThemeContext';

export default function Field({ label, value, onChangeText, placeholder, multiline, keyboardType, inputStyle }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [focused, setFocused] = useState(false);

  return (
    <View style={styles.group}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={[styles.input, multiline && styles.multiline, focused && styles.inputFocused, inputStyle]}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.inputPlaceholder}
        multiline={multiline}
        keyboardType={keyboardType}
        textAlignVertical={multiline ? 'top' : 'center'}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    group:   { marginBottom: 12 },
    label:   { color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 12, marginBottom: 6 },
    input: {
      minHeight: 46,
      borderColor: colors.border,
      borderWidth: 1.5,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      color: colors.text,
      fontFamily: 'Poppins_400Regular',
      fontSize: 14,
      paddingHorizontal: 14,
      paddingVertical: 11,
    },
    inputFocused: { borderColor: colors.primary, backgroundColor: colors.panel },
    multiline: { minHeight: 92 },
  });
}
