import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as SecureStore from 'expo-secure-store';

const LANGUAGE_KEY = 'flowmate.language';
const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState('vi');

  useEffect(() => {
    SecureStore.getItemAsync(LANGUAGE_KEY).then((stored) => {
      if (stored === 'en' || stored === 'vi') setLanguageState(stored);
    }).catch(() => {});
  }, []);

  const setLanguage = useCallback((next) => {
    const value = next === 'en' ? 'en' : 'vi';
    setLanguageState(value);
    SecureStore.setItemAsync(LANGUAGE_KEY, value).catch(() => {});
  }, []);

  // Mirrors the Java app's tr(vietnamese, english) helper so existing
  // Vietnamese strings can be wrapped in place instead of rewritten against
  // a separate translation-key dictionary.
  const t = useCallback((vietnamese, english) => (
    language === 'en' ? (english ?? vietnamese) : vietnamese
  ), [language]);

  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  return useContext(LanguageContext);
}
