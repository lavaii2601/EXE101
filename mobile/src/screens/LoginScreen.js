import React, { useMemo, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import * as WebBrowser from 'expo-web-browser';
import { Ionicons } from '@expo/vector-icons';
import Button from '../components/Button';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { connectGoogleAccount } from '../api/googleAuth';
import { loginWithEmail, registerWithEmail } from '../api/emailAuth';
import { PRIVACY_URL, TERMS_URL } from '../api/config';

function PolicyLine({ title, detail, styles }) {
  return (
    <View style={styles.policyLine}>
      <Text style={styles.policyTitle}>{title}</Text>
      <Text style={styles.policyDetail}>{detail}</Text>
    </View>
  );
}

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
  const [signingIn, setSigningIn] = useState(false);
  const isSignup = mode === 'signup';

  const handleSignIn = async () => {
    setSigningIn(true);
    try {
      const result = await connectGoogleAccount();
      if (result.connected) {
        onLoggedIn?.();
      }
      // result.cancelled (user closed the browser) -- stay on this screen
      // quietly, no error to show.
    } catch (error) {
      Alert.alert(t('Không đăng nhập được', 'Sign-in failed'), error.message);
    } finally {
      setSigningIn(false);
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

  const openPrivacyPolicy = async () => {
    try {
      await WebBrowser.openBrowserAsync(PRIVACY_URL);
    } catch (error) {
      Alert.alert(t('Không mở được chính sách', 'Could not open policy'), error.message);
    }
  };

  const openTerms = async () => {
    try {
      await WebBrowser.openBrowserAsync(TERMS_URL);
    } catch (error) {
      Alert.alert(t('Không mở được điều khoản', 'Could not open terms'), error.message);
    }
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.body}>
      <Text style={styles.brand}>FlowMate AI</Text>

      <View style={styles.card}>
        <LinearGradient
          colors={['#55BEFE', '#5A54FB', '#8171FD', '#D65EFC']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.orb}
        >
          <Ionicons name="sparkles" size={26} color="#ffffff" />
        </LinearGradient>

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

        <View style={styles.dividerRow}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>{t('Hoặc tiếp tục với', 'Or continue with')}</Text>
          <View style={styles.dividerLine} />
        </View>

        <Button
          title="Google"
          icon="logo-google"
          variant="secondary"
          onPress={handleSignIn}
          loading={signingIn}
          style={styles.googleButton}
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
      </View>

      <View style={styles.policyCard}>
        <Text style={styles.policyHeading}>{t('Dữ liệu của bạn, do bạn kiểm soát', 'Your data, your control')}</Text>
        <PolicyLine
          styles={styles}
          title="Gmail"
          detail={t('Đọc và tóm tắt email, deadline và yêu cầu công việc.', 'Read and summarize messages, deadlines, and requests.')}
        />
        <PolicyLine
          styles={styles}
          title="Google Calendar"
          detail={t('Xem sự kiện và chỉ thay đổi sau khi bạn xác nhận.', 'Show events and create changes only after confirmation.')}
        />
        <PolicyLine
          styles={styles}
          title={t('Quyền riêng tư', 'Privacy')}
          detail={t('Chỉ lưu tóm tắt và hành động, không lưu toàn bộ nội dung email trừ khi cần thiết.', 'Store summaries and actions, not full email content unless needed.')}
        />
        <PolicyLine
          styles={styles}
          title={t('Kiểm soát', 'Control')}
          detail={t('Ngắt kết nối Google và xóa lịch sử hoạt động bất cứ lúc nào.', 'Disconnect Google and delete activity history at any time.')}
        />
      </View>

      <Text style={styles.consent}>
        {t(
          'Bằng việc tiếp tục, bạn đồng ý với Điều khoản dịch vụ, Chính sách quyền riêng tư của FlowMate AI và các quyền hiển thị trên màn hình xác nhận của Google.',
          "By continuing, you agree to FlowMate AI's Terms of Service, Privacy Policy, and the permissions shown on Google's consent screen."
        )}
      </Text>
      <TouchableOpacity onPress={openPrivacyPolicy} activeOpacity={0.75}>
        <Text style={styles.policyLink}>{t('Đọc chính sách bảo mật', 'Read privacy policy')}</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={openTerms} activeOpacity={0.75}>
        <Text style={styles.policyLink}>{t('Đọc điều khoản dịch vụ', 'Read terms of service')}</Text>
      </TouchableOpacity>
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
      borderRadius: radius.control,
      alignItems: 'center',
      justifyContent: 'center',
      shadowColor: '#5A54FB',
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
    dividerRow: { width: '100%', flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 18 },
    dividerLine: { flex: 1, height: 1, backgroundColor: colors.border },
    dividerText: { color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 },
    googleButton: { width: '100%', marginTop: 18 },
    toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 20 },
    toggleText: { color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 13 },
    toggleLink: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 13 },
    policyCard: {
      width: '100%',
      marginTop: 18,
      marginBottom: 18,
      padding: 18,
      borderRadius: radius.card,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.panel,
      ...colors.shadow,
    },
    policyHeading: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 16 },
    policyLine: { marginTop: 13 },
    policyTitle: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 13 },
    policyDetail: { marginTop: 2, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 12.5, lineHeight: 18 },
    consent: { marginTop: 4, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11.5, textAlign: 'center', lineHeight: 17 },
    policyLink: { marginTop: 10, color: colors.primary, fontFamily: 'Poppins_600SemiBold', fontSize: 12.5 },
  });
}
