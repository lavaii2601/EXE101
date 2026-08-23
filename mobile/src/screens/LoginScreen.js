import React, { useMemo, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import * as WebBrowser from 'expo-web-browser';
import { Ionicons } from '@expo/vector-icons';
import Button from '../components/Button';
import { radius, useTheme } from '../theme/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { connectGoogleAccount } from '../api/googleAuth';
import { PRIVACY_URL, TERMS_URL } from '../api/config';

function PolicyLine({ title, detail, styles }) {
  return (
    <View style={styles.policyLine}>
      <Text style={styles.policyTitle}>{title}</Text>
      <Text style={styles.policyDetail}>{detail}</Text>
    </View>
  );
}

export default function LoginScreen({ onLoggedIn }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [signingIn, setSigningIn] = useState(false);

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
      <LinearGradient
        colors={['#55BEFE', '#5A54FB', '#8171FD', '#D65EFC']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.orb}
      >
        <Ionicons name="sparkles" size={34} color="#ffffff" />
      </LinearGradient>

      <Text style={styles.brand}>FlowMate AI</Text>
      <Text style={styles.headline}>{t('Biến thông tin thành hành động', 'Turn information into action')}</Text>
      <Text style={styles.intro}>
        {t(
          'Đăng nhập bằng Google để kết nối Gmail và Calendar, sau đó chọn không gian làm việc phù hợp với bạn.',
          'Sign in with your Google email to connect Gmail and Calendar, then choose a workspace built for the way you work.'
        )}
      </Text>

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

      <Button
        title={t('Đăng nhập bằng Google', 'Sign in with Google')}
        onPress={handleSignIn}
        loading={signingIn}
        style={styles.signInButton}
      />

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
    body: { paddingHorizontal: 24, paddingTop: 46, paddingBottom: 30, alignItems: 'center' },
    orb: {
      width: 96,
      height: 96,
      borderRadius: 26,
      alignItems: 'center',
      justifyContent: 'center',
      shadowColor: '#5A54FB',
      shadowOffset: { width: 0, height: 10 },
      shadowOpacity: 0.5,
      shadowRadius: 22,
      elevation: 12,
    },
    brand: { marginTop: 20, color: colors.text, fontFamily: 'Poppins_800ExtraBold', fontSize: 28, letterSpacing: -0.4 },
    headline: { marginTop: 34, color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 23, textAlign: 'center', lineHeight: 30 },
    intro: { marginTop: 10, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 14, textAlign: 'center', lineHeight: 21 },
    policyCard: {
      width: '100%',
      marginTop: 30,
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
    signInButton: { width: '100%', minHeight: 54 },
    consent: { marginTop: 14, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 11.5, textAlign: 'center', lineHeight: 17 },
    policyLink: { marginTop: 10, color: colors.primary, fontFamily: 'Poppins_600SemiBold', fontSize: 12.5 },
  });
}
