import React, { createContext, useContext, useMemo, useState } from 'react';

export const ACCENTS = {
  charcoal: { primary: '#242423', primaryDark: '#1e1e1d' },
  blue:     { primary: '#2563eb', primaryDark: '#1d4ed8' },
  purple:   { primary: '#6c63ff', primaryDark: '#5951e8' },
  green:    { primary: '#059669', primaryDark: '#047857' },
  orange:   { primary: '#ea580c', primaryDark: '#c2410c' },
};

function buildColors(isDark, accentKey) {
  const { primary, primaryDark } = ACCENTS[accentKey] || ACCENTS.charcoal;
  if (isDark) {
    return {
      background:       '#0e0e12',
      panel:            '#16161d',
      panelSoft:        '#1e1e28',
      text:             '#f0f0f8',
      textMuted:        '#9191a8',
      border:           'rgba(255,255,255,0.08)',
      primary,
      primaryDark,
      primarySoft:      'rgba(108,99,255,0.14)',
      accentText:       '#a78bfa',
      danger:           '#ef4444',
      success:          '#34d399',
      warning:          '#fbbf24',
      secondaryBg:      '#252533',
      secondaryText:    '#d8d8e8',
      inputPlaceholder: '#5c5c70',
    };
  }
  return {
    background:       '#f5f7fb',
    panel:            '#ffffff',
    panelSoft:        '#f8fafc',
    text:             '#172033',
    textMuted:        '#5f6f89',
    border:           '#dfe6f1',
    primary,
    primaryDark,
    primarySoft:      'rgba(108,99,255,0.10)',
    accentText:       '#6c63ff',
    danger:           '#dc2626',
    success:          '#16a34a',
    warning:          '#d97706',
    secondaryBg:      '#e8eef8',
    secondaryText:    '#22314a',
    inputPlaceholder: '#9aa8bc',
  };
}

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(true);
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
