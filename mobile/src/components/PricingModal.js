import React, { useMemo, useState } from 'react';
import { Linking, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Button from './Button';
import { useTheme } from '../theme/ThemeContext';

const FEATURES = [
  { label: 'Chat với Bob (AI)', free: 'Không giới hạn', premium: 'Không giới hạn' },
  { label: 'Soạn trả lời AI', free: 'Không giới hạn', premium: 'Không giới hạn' },
  { label: 'Tóm tắt email AI', free: '10 lượt/ngày', premium: 'Không giới hạn' },
  { label: 'Xử lý nhiều bước trong 1 câu hỏi', free: 'Chưa hỗ trợ', premium: 'Có' },
  { label: 'Chất lượng phản hồi AI', free: 'Tiêu chuẩn', premium: 'Nâng cao' },
  { label: 'Lưu trữ đoạn chat', free: '30 ngày', premium: 'Tới 365 ngày' },
  { label: 'Phân tích 7 ngày', free: 'Khóa', premium: 'Mở khóa' },
  { label: 'Lịch sử hoạt động', free: '30 ngày', premium: 'Không giới hạn' },
];

const REASON_TEXT = {
  email_summary: 'Bạn đã dùng hết lượt tóm tắt email AI miễn phí hôm nay.',
};

// No payment processor is wired up yet (Google Play Billing needs a Play
// Console account only the app owner can set up), so the CTA opens an honest
// contact flow instead of faking an in-app purchase -- the admin panel's new
// "Cấp Premium" action grants it manually after payment happens out-of-band.
const UPGRADE_CONTACT_EMAIL = 'lecaoduyanh123@gmail.com';

export default function PricingModal({ visible, onClose, reason }) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [billing, setBilling] = useState('monthly');

  const price = billing === 'monthly' ? '49.000đ' : '490.000đ';
  const period = billing === 'monthly' ? '/tháng' : '/năm';

  const contactToUpgrade = () => {
    const planLabel = billing === 'monthly' ? 'Hàng tháng (49.000đ/tháng)' : 'Hàng năm (490.000đ/năm)';
    const subject = encodeURIComponent('Nâng cấp FlowMate Premium');
    const body = encodeURIComponent(`Tôi muốn nâng cấp gói: ${planLabel}.`);
    Linking.openURL(`mailto:${UPGRADE_CONTACT_EMAIL}?subject=${subject}&body=${body}`).catch(() => {});
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <TouchableOpacity style={styles.overlay} activeOpacity={1} onPress={onClose}>
        <TouchableOpacity style={styles.sheet} activeOpacity={1} onPress={() => {}}>
          <View style={styles.header}>
            <Text style={styles.title}>Nâng cấp Premium</Text>
            <TouchableOpacity onPress={onClose} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name="close" size={22} color={colors.textMuted} />
            </TouchableOpacity>
          </View>
          {reason && REASON_TEXT[reason] ? (
            <Text style={styles.reasonText}>{REASON_TEXT[reason]}</Text>
          ) : null}

          <View style={styles.billingToggle}>
            <TouchableOpacity
              style={[styles.billingOption, billing === 'monthly' && styles.billingOptionActive]}
              onPress={() => setBilling('monthly')}
              activeOpacity={0.85}
            >
              <Text style={[styles.billingLabel, billing === 'monthly' && styles.billingLabelActive]}>Hàng tháng</Text>
              <Text style={[styles.billingPrice, billing === 'monthly' && styles.billingLabelActive]}>49.000đ</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.billingOption, billing === 'yearly' && styles.billingOptionActive]}
              onPress={() => setBilling('yearly')}
              activeOpacity={0.85}
            >
              <View style={styles.saveBadge}><Text style={styles.saveBadgeText}>Tiết kiệm 17%</Text></View>
              <Text style={[styles.billingLabel, billing === 'yearly' && styles.billingLabelActive]}>Hàng năm</Text>
              <Text style={[styles.billingPrice, billing === 'yearly' && styles.billingLabelActive]}>490.000đ</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.featureScroll} showsVerticalScrollIndicator={false}>
            <View style={styles.tableHeaderRow}>
              <Text style={[styles.tableHeaderCell, styles.featureCol]}>Tính năng</Text>
              <Text style={[styles.tableHeaderCell, styles.valueCol]}>Free</Text>
              <Text style={[styles.tableHeaderCell, styles.valueCol, styles.premiumHeaderText]}>Premium</Text>
            </View>
            {FEATURES.map((item) => (
              <View key={item.label} style={styles.tableRow}>
                <Text style={[styles.featureLabel, styles.featureCol]}>{item.label}</Text>
                <Text style={[styles.freeValue, styles.valueCol]}>{item.free}</Text>
                <Text style={[styles.premiumValue, styles.valueCol]}>{item.premium}</Text>
              </View>
            ))}
          </ScrollView>

          <Button title={`Nâng cấp ${price}${period}`} onPress={contactToUpgrade} style={styles.ctaButton} />
          <Text style={styles.ctaNote}>
            Mở email liên hệ để nâng cấp — thanh toán trong ứng dụng qua Google Play sẽ sớm ra mắt.
          </Text>
        </TouchableOpacity>
      </TouchableOpacity>
    </Modal>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' },
    sheet: {
      maxHeight: '86%',
      backgroundColor: colors.panel,
      borderTopLeftRadius: 24,
      borderTopRightRadius: 24,
      padding: 20,
      paddingBottom: 28,
      gap: 4,
    },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
    title: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 19 },
    reasonText: {
      marginBottom: 8,
      padding: 10,
      borderRadius: 10,
      backgroundColor: `${colors.primary}18`,
      color: colors.primary,
      fontFamily: 'Poppins_600SemiBold',
      fontSize: 12,
      lineHeight: 17,
    },
    billingToggle: { flexDirection: 'row', gap: 10, marginTop: 6, marginBottom: 14 },
    billingOption: {
      flex: 1,
      alignItems: 'center',
      paddingVertical: 12,
      borderRadius: 14,
      borderWidth: 1.5,
      borderColor: colors.border,
      backgroundColor: colors.panelSoft,
    },
    billingOptionActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
    billingLabel: { color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 12 },
    billingLabelActive: { color: colors.primary },
    billingPrice: { marginTop: 3, color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 16 },
    saveBadge: {
      position: 'absolute',
      top: -10,
      alignSelf: 'center',
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 999,
      backgroundColor: colors.success,
    },
    saveBadgeText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 9 },
    featureScroll: { maxHeight: 320 },
    tableHeaderRow: {
      flexDirection: 'row',
      paddingBottom: 8,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    tableHeaderCell: { color: colors.textMuted, fontFamily: 'Poppins_700Bold', fontSize: 10, letterSpacing: 0.5, textTransform: 'uppercase' },
    premiumHeaderText: { color: colors.primary },
    tableRow: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: 10,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    featureCol: { flex: 1.4, minWidth: 0, paddingRight: 6 },
    valueCol: { flex: 1, textAlign: 'center' },
    featureLabel: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 12, lineHeight: 16 },
    freeValue: { color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 11 },
    premiumValue: { color: colors.primary, fontFamily: 'Poppins_700Bold', fontSize: 11 },
    ctaButton: { marginTop: 16 },
    ctaNote: { marginTop: 10, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 10.5, lineHeight: 15, textAlign: 'center' },
  });
}
