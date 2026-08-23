import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as SecureStore from 'expo-secure-store';

const THEME_KEY = 'flowmate.theme';
const ACCENT_KEY = 'flowmate.accent';

export const ACCENTS = {
  charcoal: { primary: '#242423', primaryDark: '#1e1e1d' },
  blue:     { primary: '#2563eb', primaryDark: '#1d4ed8' },
  purple:   { primary: '#6c63ff', primaryDark: '#5951e8' },
  green:    { primary: '#059669', primaryDark: '#047857' },
  orange:   { primary: '#ea580c', primaryDark: '#c2410c' },
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
  const { primary, primaryDark } = ACCENTS[accentKey] || ACCENTS.purple;
  if (isDark) {
    return {
      background:       '#0B1020',
      panel:            '#12182A',
      panelSoft:        '#192137',
      text:             '#F7F8FF',
      textMuted:        '#9DA8C3',
      border:           'rgba(255,255,255,0.08)',
      primary,
      primaryDark,
      primarySoft:      `${primary}24`,
      accentText:       primary,
      danger:           '#ef4444',
      success:          '#34d399',
      warning:          '#fbbf24',
      secondaryBg:      '#202A43',
      secondaryText:    '#E5E9F7',
      inputPlaceholder: '#5c5c70',
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
    background:       '#F4F6FC',
    panel:            '#ffffff',
    panelSoft:        '#F7F8FD',
    text:             '#182033',
    textMuted:        '#667085',
    border:           '#E4E7F0',
    primary,
    primaryDark,
    primarySoft:      `${primary}18`,
    accentText:       primary,
    danger:           '#dc2626',
    success:          '#16a34a',
    warning:          '#d97706',
    secondaryBg:      '#EEF0FF',
    secondaryText:    '#4338CA',
    inputPlaceholder: '#9aa8bc',
    shadow: {
      shadowColor: '#172033',
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
  const [accent, setAccent] = useState('purple');

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
    const value = ACCENTS[next] ? next : 'purple';
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
