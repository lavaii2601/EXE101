import React, { useMemo, useState } from 'react';
import { Modal, Platform, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import Button from './Button';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';

function parseValue(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

// Builds YYYY-MM-DDTHH:MM:SS in local time (no timezone offset applied) --
// matches the plain-text format the schedule API already expects.
function toLocalIso(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
}

function formatDisplay(date, language) {
  const locale = language === 'en' ? 'en-GB' : 'vi-VN';
  const datePart = date.toLocaleDateString(locale);
  const timePart = date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  return `${datePart}  ${timePart}`;
}

// @react-native-community/datetimepicker has no web implementation, so the
// web target keeps the original free-text ISO input instead of crashing.
export default function DateTimeField({ label, value, onChange, placeholder }) {
  const { colors } = useTheme();
  const { language, t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [stage, setStage] = useState(null); // 'date' | 'time' | 'datetime' | null
  const [draftDate, setDraftDate] = useState(null);
  const selected = parseValue(value);

  if (Platform.OS === 'web') {
    return (
      <View style={styles.group}>
        <Text style={styles.label}>{label}</Text>
        <TextInput
          style={styles.input}
          value={value}
          onChangeText={onChange}
          placeholder={placeholder}
          placeholderTextColor={colors.inputPlaceholder}
        />
      </View>
    );
  }

  const openPicker = () => {
    setDraftDate(selected || new Date());
    setStage(Platform.OS === 'android' ? 'date' : 'datetime');
  };

  const handleAndroidChange = (event, picked) => {
    if (event.type === 'dismissed' || !picked) {
      setStage(null);
      return;
    }
    if (stage === 'date') {
      setDraftDate(picked);
      setStage('time');
      return;
    }
    const merged = new Date(draftDate);
    merged.setHours(picked.getHours(), picked.getMinutes(), 0, 0);
    setStage(null);
    onChange(toLocalIso(merged));
  };

  const handleIosChange = (event, picked) => {
    if (picked) setDraftDate(picked);
  };

  const confirmIos = () => {
    setStage(null);
    onChange(toLocalIso(draftDate || new Date()));
  };

  return (
    <View style={styles.group}>
      <Text style={styles.label}>{label}</Text>
      <TouchableOpacity style={styles.input} onPress={openPicker} activeOpacity={0.75}>
        <Text style={selected ? styles.valueText : styles.placeholderText}>
          {selected ? formatDisplay(selected, language) : (placeholder || t('Chạm để chọn', 'Tap to pick'))}
        </Text>
      </TouchableOpacity>

      {stage && Platform.OS === 'android' && (
        <DateTimePicker
          value={draftDate || new Date()}
          mode={stage}
          is24Hour
          onChange={handleAndroidChange}
        />
      )}

      {stage && Platform.OS === 'ios' && (
        <Modal transparent animationType="fade" visible onRequestClose={() => setStage(null)}>
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <DateTimePicker
                value={draftDate || new Date()}
                mode="datetime"
                display="spinner"
                onChange={handleIosChange}
              />
              <View style={styles.modalActions}>
                <Button title={t('Hủy', 'Cancel')} variant="secondary" onPress={() => setStage(null)} />
                <Button title={t('Xong', 'Done')} onPress={confirmIos} />
              </View>
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    group: { marginBottom: 12 },
    label: { color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 12, marginBottom: 6 },
    input: {
      minHeight: 46,
      borderColor: colors.border,
      borderWidth: 1.5,
      borderRadius: radius.control,
      backgroundColor: colors.panelSoft,
      color: colors.text,
      paddingHorizontal: 14,
      justifyContent: 'center',
    },
    valueText: { color: colors.text, fontFamily: 'Poppins_400Regular', fontSize: 14 },
    placeholderText: { color: colors.inputPlaceholder, fontFamily: 'Poppins_400Regular', fontSize: 14 },
    modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
    modalCard: { backgroundColor: colors.panel, padding: 16, borderTopLeftRadius: 16, borderTopRightRadius: 16 },
    modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 10, marginTop: 10 },
  });
}
