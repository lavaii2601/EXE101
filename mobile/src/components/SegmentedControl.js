import React, { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity } from 'react-native';
import { useTheme } from '../theme/ThemeContext';

export default function SegmentedControl({ options, value, onChange }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.wrap}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <TouchableOpacity
            key={option.value}
            style={[styles.option, active && styles.active]}
            onPress={() => onChange(option.value)}
            activeOpacity={0.85}
          >
            <Text style={[styles.text, active && styles.activeText]}>{option.label}</Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    wrap:       { gap: 8, paddingVertical: 2 },
    option: {
      minHeight: 36,
      justifyContent: 'center',
      paddingHorizontal: 12,
      borderRadius: 12,
      backgroundColor: colors.secondaryBg,
    },
    active:     { backgroundColor: colors.primary },
    text:       { color: colors.secondaryText, fontWeight: '700' },
    activeText: { color: '#ffffff' },
  });
}
