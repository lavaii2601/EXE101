import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as SecureStore from 'expo-secure-store';

const THEME_KEY = 'flowmate.theme';
const ACCENT_KEY = 'flowmate.accent';

export const ACCENTS = {
  blue:   { primary: '#0B5ED7', primaryDark: '#0847A6' },
  green:  { primary: '#4F7D1C', primaryDark: '#3B6114' },
  cyan:   { primary: '#167D91', primaryDark: '#105E6D' },
  yellow: { primary: '#A56800', primaryDark: '#7E4F00' },
};

// Shared corner-radius scale so every screen/component curves consistently
// instead of drifting between ad-hoc values (8, 14, 18, 20...).
export const radius = {
  control: 12,
  button: 14,
  card: 20,
  pill: 999,
};

function buildColors(isDark, accentKey) {
  const { primary, primaryDark } = ACCENTS[accentKey] || ACCENTS.blue;
  if (isDark) {
    return {
      background:       '#071827',
      panel:            '#0E2335',
      panelSoft:        '#153149',
      text:             '#F3FBFD',
      textMuted:        '#A7C2CC',
      border:           'rgba(130,214,229,0.16)',
      primary,
      primaryDark,
      primarySoft:      `${primary}24`,
      accentText:       primary,
      danger:           '#ef4444',
      success:          '#8BC34A',
      warning:          '#F6C667',
      secondaryBg:      '#17384A',
      secondaryText:    '#82D6E5',
      inputPlaceholder: '#74909B',
      shadow: {
        shadowColor: '#000000',
        shadowOffset: { width: 0, height: 6 },
        shadowOpacity: 0.28,
        shadowRadius: 14,
        elevation: 4,
      },
    };
  }
  return {
    background:       '#F4FAFB',
    panel:            '#ffffff',
    panelSoft:        '#EAF7F9',
    text:             '#173042',
    textMuted:        '#587181',
    border:           '#CBE7EC',
    primary,
    primaryDark,
    primarySoft:      `${primary}18`,
    accentText:       primary,
    danger:           '#dc2626',
    success:          '#4F7D1C',
    warning:          '#A56800',
    secondaryBg:      '#DFF4F7',
    secondaryText:    '#176B7B',
    inputPlaceholder: '#78939D',
    shadow: {
      shadowColor: '#164E63',
      shadowOffset: { width: 0, height: 6 },
      shadowOpacity: 0.08,
      shadowRadius: 14,
      elevation: 4,
    },
  };
}

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(false);
  const [accent, setAccent] = useState('blue');

  useEffect(() => {
    Promise.all([
      SecureStore.getItemAsync(THEME_KEY),
      SecureStore.getItemAsync(ACCENT_KEY),
    ]).then(([storedTheme, storedAccent]) => {
      if (storedTheme === 'dark' || storedTheme === 'light') {
        setIsDark(storedTheme === 'dark');
      }
      if (storedAccent && ACCENTS[storedAccent]) setAccent(storedAccent);
    }).catch(() => {});
  }, []);

  const toggleTheme = useCallback(() => {
    setIsDark((current) => {
      const next = !current;
      SecureStore.setItemAsync(THEME_KEY, next ? 'dark' : 'light').catch(() => {});
      return next;
    });
  }, []);

  const selectAccent = useCallback((next) => {
    const value = ACCENTS[next] ? next : 'blue';
    setAccent(value);
    SecureStore.setItemAsync(ACCENT_KEY, value).catch(() => {});
  }, []);

  const colors = useMemo(() => buildColors(isDark, accent), [isDark, accent]);

  const value = useMemo(
    () => ({
      colors,
      isDark,
      accent,
      toggleTheme,
      setAccent: selectAccent,
    }),
    [colors, isDark, accent, selectAccent, toggleTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
