import React, { useMemo } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../theme/ThemeContext';

export default function Screen({ title, children, refreshing, onRefresh, actions }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Text style={styles.title}>{title}</Text>
        {actions ? <View style={styles.actions}>{actions}</View> : null}
      </View>
      <ScrollView
        contentContainerStyle={styles.body}
        refreshControl={
          onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} /> : undefined
        }
      >
        {children}
      </ScrollView>
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1 },
    header: {
      paddingHorizontal: 16,
      paddingVertical: 12,
      backgroundColor: colors.background,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 10,
    },
    title: { color: colors.text, fontSize: 22, fontWeight: '800' },
    actions: { flexDirection: 'row', gap: 8 },
    body: { paddingHorizontal: 16, paddingBottom: 18, gap: 12 },
  });
}
