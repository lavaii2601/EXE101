import React, { useCallback, useMemo, useState } from 'react';
import { Alert, Modal, Text, View, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Button from './Button';
import { radius, useTheme } from '../theme/ThemeContext';

// Alert.alert can't be styled or animated -- it's the bare OS dialog. This
// is the one connectGoogleAccount() error (google_account_already_linked_
// elsewhere) worth a real card + a "Thử tài khoản khác" retry action,
// matching web/frontend's gmailLinkConflictModal (same copy, same two
// actions). RN's own Modal already animates its mount/unmount
// (animationType="fade" below) -- no Animated API needed.
export default function GoogleAuthConflictModal({ visible, message, onClose, onRetry }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <View style={styles.iconWrap}>
            <Ionicons name="warning" size={26} color="#E65100" />
          </View>
          <Text style={styles.title}>Tài khoản Google đã được liên kết</Text>
          <Text style={styles.message}>{message}</Text>
          <View style={styles.actions}>
            <Button title="Đóng" variant="secondary" onPress={onClose} style={styles.actionButton} />
            <Button title="Thử tài khoản khác" onPress={onRetry} style={styles.actionButton} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

// Shared by every connectGoogleAccount() caller (Email/Overview/Schedule/
// Settings screens). Keeps the same one-call ergonomics a plain
// Alert.alert(...) would have had -- callers just call showError() from
// their catch block -- by owning its own visible/message/onRetry state.
export function useGoogleAuthErrorModal() {
  const [state, setState] = useState(null); // { message, onRetry } | null

  const showError = useCallback((error, { title = 'Không kết nối được Google', onRetry } = {}) => {
    if (error?.code === 'google_account_already_linked_elsewhere' && onRetry) {
      setState({ message: error.message, onRetry });
      return;
    }
    // Any other Google-auth error keeps using the plain system alert --
    // only this one case has a meaningful retry action worth a custom card.
    Alert.alert(title, error?.message || String(error));
  }, []);

  const close = useCallback(() => setState(null), []);
  const retry = useCallback(() => {
    const onRetry = state?.onRetry;
    setState(null);
    onRetry?.();
  }, [state]);

  const modal = (
    <GoogleAuthConflictModal
      visible={!!state}
      message={state?.message || ''}
      onClose={close}
      onRetry={retry}
    />
  );

  return { modal, showError };
}

function makeStyles(colors) {
  return StyleSheet.create({
    backdrop: {
      flex: 1,
      backgroundColor: 'rgba(15,23,42,0.5)',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    },
    card: {
      width: '100%',
      maxWidth: 400,
      backgroundColor: colors.panel,
      borderRadius: radius.card,
      padding: 28,
      alignItems: 'center',
      ...colors.shadow,
    },
    iconWrap: {
      width: 56,
      height: 56,
      borderRadius: 28,
      backgroundColor: '#FFF3E0',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 14,
    },
    title: {
      color: colors.text,
      fontFamily: 'Poppins_700Bold',
      fontSize: 17,
      textAlign: 'center',
      marginBottom: 10,
    },
    message: {
      color: colors.textMuted,
      fontFamily: 'Poppins_400Regular',
      fontSize: 13.5,
      lineHeight: 20,
      textAlign: 'center',
      marginBottom: 22,
    },
    actions: {
      flexDirection: 'row',
      gap: 10,
      width: '100%',
    },
    actionButton: {
      flex: 1,
    },
  });
}
