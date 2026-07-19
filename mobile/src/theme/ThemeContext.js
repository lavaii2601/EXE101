import React, { createContext, useContext, useMemo, useState } from 'react';

export const ACCENTS = {
  charcoal: { primary: '#242423', primaryDark: '#1e1e1d' },
  blue:     { primary: '#2563eb', primaryDark: '#1d4ed8' },
  purple:   { primary: '#6c63ff', primaryDark: '#5951e8' },
  green:    { primary: '#059669', primaryDark: '#047857' },
  orange:   { primary: '#ea580c', primaryDark: '#c2410c' },
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

  const colors = useMemo(() => buildColors(isDark, accent), [isDark, accent]);

  const value = useMemo(
    () => ({
      colors,
      isDark,
      accent,
      toggleTheme: () => setIsDark((v) => !v),
      setAccent,
    }),
    [colors, isDark, accent]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
