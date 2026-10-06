import React, { useMemo, useState } from 'react';
import { Alert, Image, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Button from '../components/Button';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { connectGoogleAccount } from '../api/googleAuth';
import { loginWithEmail, registerWithEmail, setPassword as setPasswordApi } from '../api/emailAuth';

function InputRow({ icon, styles, colors, right, ...inputProps }) {
  return (
    <View style={styles.inputRow}>
      <Ionicons name={icon} size={17} color={colors.textMuted} style={styles.inputIcon} />
      <TextInput
        style={styles.inputField}
        placeholderTextColor={colors.inputPlaceholder}
        {...inputProps}
      />
      {right}
    </View>
  );
}

export default function LoginScreen({ onLoggedIn }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);

  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const [needsPassword, setNeedsPassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [settingPassword, setSettingPassword] = useState(false);
  const isSignup = mode === 'signup';

  // Google is no longer a login method on its own -- this is the one-time
  // bridge for an account that only ever signed in via Google (no password
  // set yet) to regain access. It never creates a new account; see
  // oauth2callback's intent=recover branch.
  const handleRecoverViaGoogle = async () => {
    setRecovering(true);
    try {
      const result = await connectGoogleAccount('recover');
      if (result.connected) {
        if (result.needsPassword) {
          setNeedsPassword(true);
        } else {
          onLoggedIn?.();
        }
      }
      // result.cancelled (user closed the browser) -- stay on this screen
      // quietly, no error to show.
    } catch (error) {
      Alert.alert(t('Không khôi phục được', 'Recovery failed'), error.message);
    } finally {
      setRecovering(false);
    }
  };

  const handleSetPassword = async () => {
    if (newPassword.length < 8) {
      Alert.alert(t('Mật khẩu quá ngắn', 'Password too short'), t('Mật khẩu phải có ít nhất 8 ký tự.', 'Password must be at least 8 characters.'));
      return;
    }
    setSettingPassword(true);
    try {
      await setPasswordApi(newPassword);
      onLoggedIn?.();
    } catch (error) {
      Alert.alert(t('Không lưu được mật khẩu', 'Could not save password'), error.data?.message || error.message);
    } finally {
      setSettingPassword(false);
    }
  };

  const handleSubmit = async () => {
    if (isSignup && !name.trim()) {
      Alert.alert(t('Thiếu thông tin', 'Missing info'), t('Vui lòng nhập họ tên.', 'Please enter your full name.'));
      return;
    }
    if (!email.trim() || !password) {
      Alert.alert(t('Thiếu thông tin', 'Missing info'), t('Vui lòng nhập email và mật khẩu.', 'Please enter your email and password.'));
      return;
    }
    setSubmitting(true);
    try {
      if (isSignup) {
        await registerWithEmail({ name: name.trim(), email: email.trim(), password });
      } else {
        await loginWithEmail({ email: email.trim(), password });
      }
      onLoggedIn?.();
    } catch (error) {
      const message = error.data?.message || error.message;
      Alert.alert(
        isSignup ? t('Không tạo được tài khoản', 'Could not create account') : t('Không đăng nhập được', 'Sign-in failed'),
        message
      );
    } finally {
      setSubmitting(false);
    }
  };

  const toggleMode = () => {
    setMode((current) => (current === 'login' ? 'signup' : 'login'));
    setPassword('');
  };

  const forgotPassword = () => {
    Alert.alert(
      t('Sắp có', 'Coming soon'),
      t(
        'Khôi phục mật khẩu qua email sẽ có trong bản cập nhật tới.',
        'Email password recovery is coming in a future update.'
      )
    );
  };

  if (needsPassword) {
    return (
      <ScrollView style={styles.root} contentContainerStyle={styles.body}>
        <Text style={styles.brand}>FlowMate AI</Text>
        <View style={styles.card}>
          <Image source={require('../../assets/logo.png')} style={styles.orb} resizeMode="contain" />
          <Text style={styles.title}>{t('Đặt mật khẩu cho tài khoản', 'Set an account password')}</Text>
          <Text style={styles.subtitle}>
            {t(
              'Tài khoản này trước đây chỉ đăng nhập bằng Google. Hãy đặt một mật khẩu FlowMate để đăng nhập trực tiếp từ lần sau.',
              'This account previously only signed in via Google. Set a FlowMate password to sign in directly from now on.'
            )}
          </Text>
          <View style={styles.field}>
            <Text style={styles.label}>{t('Mật khẩu mới', 'New Password')}</Text>
            <InputRow
              icon="lock-closed-outline"
              styles={styles}
              colors={colors}
              value={newPassword}
              onChangeText={setNewPassword}
              placeholder="••••••••"
              secureTextEntry
              autoCapitalize="none"
            />
            <Text style={styles.hint}>{t('Tối thiểu 8 ký tự.', 'Must be at least 8 characters.')}</Text>
          </View>
          <Button
            title={t('Lưu mật khẩu', 'Save Password')}
            icon="arrow-forward"
            onPress={handleSetPassword}
            loading={settingPassword}
            style={styles.submitButton}
          />
        </View>
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.body}>
      <Text style={styles.brand}>FlowMate AI</Text>

      <View style={styles.card}>
        <Image source={require('../../assets/logo.png')} style={styles.orb} resizeMode="contain" />

        <Text style={styles.title}>
          {isSignup ? t('Tạo tài khoản', 'Create Account') : t('Chào mừng trở lại', 'Welcome Back')}
        </Text>
        <Text style={styles.subtitle}>
          {isSignup
            ? t('Tham gia FlowMate AI ngay hôm nay.', 'Join FlowMate AI today.')
            : t('Vui lòng nhập thông tin để đăng nhập.', 'Please enter your details to sign in.')}
        </Text>

        {isSignup ? (
          <View style={styles.field}>
            <Text style={styles.label}>{t('Họ và tên', 'Full Name')}</Text>
            <InputRow
              icon="person-outline"
              styles={styles}
              colors={colors}
              value={name}
              onChangeText={setName}
              placeholder={t('Nhập họ và tên', 'Enter your full name')}
            />
          </View>
        ) : null}

        <View style={styles.field}>
          <Text style={styles.label}>{t('Email', 'Email Address')}</Text>
          <InputRow
            icon="mail-outline"
            styles={styles}
            colors={colors}
            value={email}
            onChangeText={setEmail}
            placeholder="name@company.com"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
          />
        </View>

        <View style={styles.field}>
          <View style={styles.labelRow}>
            <Text style={styles.label}>{t('Mật khẩu', 'Password')}</Text>
            {!isSignup ? (
              <TouchableOpacity onPress={forgotPassword} hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}>
                <Text style={styles.forgotLink}>{t('Quên mật khẩu?', 'Forgot Password?')}</Text>
              </TouchableOpacity>
            ) : null}
          </View>
          <InputRow
            icon="lock-closed-outline"
            styles={styles}
            colors={colors}
            value={password}
            onChangeText={setPassword}
            placeholder={isSignup ? t('Tạo mật khẩu', 'Create a password') : '••••••••'}
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            right={
              <TouchableOpacity onPress={() => setShowPassword((v) => !v)} hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}>
                <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={18} color={colors.textMuted} />
              </TouchableOpacity>
            }
          />
          {isSignup ? <Text style={styles.hint}>{t('Tối thiểu 8 ký tự.', 'Must be at least 8 characters.')}</Text> : null}
        </View>

        <Button
          title={isSignup ? t('Tạo tài khoản', 'Create Account') : t('Đăng nhập', 'Sign In')}
          icon={isSignup ? 'arrow-forward' : undefined}
          onPress={handleSubmit}
          loading={submitting}
          style={styles.submitButton}
        />

        <View style={styles.toggleRow}>
          <Text style={styles.toggleText}>
            {isSignup ? t('Đã có tài khoản?', 'Already have an account?') : t('Chưa có tài khoản?', "Don't have an account?")}
          </Text>
          <TouchableOpacity onPress={toggleMode} hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}>
            <Text style={styles.toggleLink}>
              {isSignup ? t('Đăng nhập', 'Sign In') : t('Đăng ký', 'Sign up')}
            </Text>
          </TouchableOpacity>
        </View>

        {!isSignup ? (
          <TouchableOpacity
            onPress={handleRecoverViaGoogle}
            disabled={recovering}
            hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
            style={styles.recoverLinkRow}
          >
            <Text style={styles.recoverLink}>
              {recovering
                ? t('Đang khôi phục...', 'Recovering...')
                : t('Từng đăng nhập bằng Google? Khôi phục tài khoản', 'Previously signed in with Google? Recover your account')}
            </Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </ScrollView>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    body: { paddingHorizontal: 20, paddingTop: 40, paddingBottom: 30, alignItems: 'center' },
    brand: { color: colors.text, fontFamily: 'Poppins_800ExtraBold', fontSize: 22, letterSpacing: -0.4, marginBottom: 18 },
    card: {
      width: '100%',
      padding: 22,
      borderRadius: radius.card,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.panel,
      alignItems: 'center',
      ...colors.shadow,
    },
    orb: {
      width: 64,
      height: 64,
      shadowColor: '#0058DE',
      shadowOffset: { width: 0, height: 8 },
      shadowOpacity: 0.4,
      shadowRadius: 16,
      elevation: 8,
    },
    title: { marginTop: 16, color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 20, textAlign: 'center' },
    subtitle: { marginTop: 4, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13, textAlign: 'center' },
    field: { width: '100%', marginTop: 18 },
    label: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 12.5 },
    labelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    forgotLink: { color: colors.primary, fontFamily: 'Poppins_600SemiBold', fontSize: 12 },
    hint: { marginTop: 6, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11 },
    inputRow: {
      marginTop: 7,
      minHeight: 48,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 9,
      paddingHorizontal: 13,
      borderRadius: radius.control,
      borderWidth: 1.5,
      borderColor: colors.border,
      backgroundColor: colors.panelSoft,
    },
    inputIcon: { marginTop: 1 },
    inputField: {
      flex: 1,
      minHeight: 46,
      color: colors.text,
      fontFamily: 'Poppins_400Regular',
      fontSize: 14,
    },
    submitButton: { width: '100%', marginTop: 22 },
    toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 20 },
    toggleText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13 },
    toggleLink: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 13 },
    recoverLinkRow: { marginTop: 14 },
    recoverLink: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11.5, textDecorationLine: 'underline', textAlign: 'center' },
  });
}
