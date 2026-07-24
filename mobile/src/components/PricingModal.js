import React, { useMemo, useState } from 'react';
import { Alert, Linking, Modal, Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Button from './Button';
import { useTheme } from '../theme/ThemeContext';
import { apiPost } from '../api/client';

const FEATURES = [
  { label: 'Chat với Bob (AI)', free: 'Không giới hạn', premium: 'Không giới hạn' },
  { label: 'Soạn trả lời AI', free: 'Không giới hạn', premium: 'Không giới hạn' },
  { label: 'Tóm tắt email AI', free: '10 lượt/ngày', premium: 'Không giới hạn' },
  { label: 'Xử lý nhiều bước trong 1 câu hỏi', free: 'Chưa hỗ trợ', premium: 'Có', freeLocked: true },
  { label: 'Chất lượng phản hồi AI', free: 'Tiêu chuẩn', premium: 'Nâng cao' },
  { label: 'Lưu trữ đoạn chat', free: '30 ngày', premium: 'Tới 365 ngày' },
  { label: 'Phân tích 7 ngày', free: 'Khóa', premium: 'Mở khóa', freeLocked: true },
  { label: 'Lịch sử hoạt động', free: '30 ngày', premium: 'Không giới hạn' },
];

const REASON_TEXT = {
  email_summary: 'Bạn đã dùng hết lượt tóm tắt email AI miễn phí hôm nay.',
};

const PAYMENT_METHODS = [
  { key: 'vnpay', label: 'VNPay', letter: 'V', color: '#005BAA' },
  { key: 'momo', label: 'MoMo', letter: 'M', color: '#D82D8B' },
];

// USD is a reference price only (VNPay/MoMo settle in VND) -- yearly USD is
// derived at the same ~12% discount the VND yearly price already applies
// over monthly*12, so the "save with yearly" story matches in both
// currencies instead of drifting apart under a plain FX conversion.
const PRICING = {
  monthly: { vnd: '49.000đ', usd: '1.99' },
  yearly: { vnd: '520.000đ', usd: '20.99' },
};
const YEARLY_SAVE_PERCENT = 12;

// No payment gateway is wired up yet (needs a registered VNPay/MoMo merchant
// account the app owner sets up separately), so picking a method here only
// tags the contact email -- the admin panel's "Cấp Premium" action grants it
// manually after payment happens out-of-band. Once a gateway goes live, its
// webhook can call the same models.subscription.grant_manual() the admin
// action already uses (provider='vnpay'/'momo' instead of 'manual'), turning
// the upgrade automatic without touching this screen.
const UPGRADE_CONTACT_EMAIL = 'lecaoduyanh123@gmail.com';

function formatRemainingTime(subscription) {
  if (!subscription?.current_period_end) return 'không giới hạn';
  let seconds = Number(subscription?.remaining_seconds);
  if (!Number.isFinite(seconds)) {
    seconds = Math.max(0, Math.floor(
      (new Date(subscription.current_period_end).getTime() - Date.now()) / 1000
    ));
  }
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days} ngày${hours ? ` ${hours} giờ` : ''}`;
  if (hours) return `${hours} giờ${minutes ? ` ${minutes} phút` : ''}`;
  return `${Math.max(0, minutes)} phút`;
}

export default function PricingModal({
  visible,
  onClose,
  reason,
  isPremiumTier,
  subscription,
  onRefresh,
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const [billing, setBilling] = useState('monthly');
  const [method, setMethod] = useState('vnpay');
  const [submitting, setSubmitting] = useState(false);

  const price = PRICING[billing].vnd;
  const priceUsd = PRICING[billing].usd;
  const period = billing === 'monthly' ? '/tháng' : '/năm';
  const remainingLabel = formatRemainingTime(subscription);

  const contactToUpgrade = async () => {
    const action = isPremiumTier ? 'renew' : 'purchase';
    const planLabel = billing === 'monthly'
      ? `Hàng tháng (${PRICING.monthly.vnd}/tháng ~ $${PRICING.monthly.usd})`
      : `Hàng năm (${PRICING.yearly.vnd}/năm ~ $${PRICING.yearly.usd})`;
    const methodLabel = PAYMENT_METHODS.find((item) => item.key === method)?.label || method;
    setSubmitting(true);
    try {
      await apiPost('/user/subscription/intent', { action });
    } catch (error) {
      const allowedAction = error?.data?.allowed_action;
      if (allowedAction === 'renew') {
        Alert.alert(
          'Tài khoản đã có Premium',
          'Bạn không thể mua thêm một gói mới. Hãy chọn Gia hạn Premium.'
        );
      } else if (allowedAction === 'purchase') {
        Alert.alert(
          'Premium đã hết hiệu lực',
          'Tài khoản hiện không có Premium để gia hạn. Hãy mua gói Premium mới.'
        );
      } else {
        Alert.alert('Không kiểm tra được gói', error?.message || 'Vui lòng thử lại.');
      }
      onRefresh?.();
      setSubmitting(false);
      return;
    }

    const actionLabel = isPremiumTier ? 'gia hạn' : 'nâng cấp';
    const subject = encodeURIComponent(
      isPremiumTier ? 'Gia hạn FlowMate Premium' : 'Nâng cấp FlowMate Premium'
    );
    const body = encodeURIComponent(
      `Tôi muốn ${actionLabel} gói: ${planLabel}.\nPhương thức thanh toán mong muốn: ${methodLabel}.`
    );
    try {
      await Linking.openURL(`mailto:${UPGRADE_CONTACT_EMAIL}?subject=${subject}&body=${body}`);
    } catch {
      Alert.alert('Không mở được email', `Vui lòng liên hệ ${UPGRADE_CONTACT_EMAIL}.`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      {/* Pressable (not TouchableOpacity) here -- nesting a ScrollView inside
          TouchableOpacity's legacy responder can steal real finger-drag
          gestures on device even though synthetic swipes still worked,
          leaving the sheet impossible to scroll for actual users. */}
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => {}}>
          <View style={styles.header}>
            <Text style={styles.title}>{isPremiumTier ? 'Gia hạn Premium' : 'Nâng cấp Premium'}</Text>
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
              <Text style={[styles.billingPrice, billing === 'monthly' && styles.billingLabelActive]}>{PRICING.monthly.vnd}</Text>
              <Text style={styles.billingPriceUsd}>~ ${PRICING.monthly.usd}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.billingOption, billing === 'yearly' && styles.billingOptionActive]}
              onPress={() => setBilling('yearly')}
              activeOpacity={0.85}
            >
              <View style={styles.saveBadge}><Text style={styles.saveBadgeText}>Tiết kiệm {YEARLY_SAVE_PERCENT}%</Text></View>
              <Text style={[styles.billingLabel, billing === 'yearly' && styles.billingLabelActive]}>Hàng năm</Text>
              <Text style={[styles.billingPrice, billing === 'yearly' && styles.billingLabelActive]}>{PRICING.yearly.vnd}</Text>
              <Text style={styles.billingPriceUsd}>~ ${PRICING.yearly.usd}</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.bodyScroll} showsVerticalScrollIndicator={false}>
            <PlanCard
              colors={colors}
              styles={styles}
              title="Miễn phí"
              icon="sparkles-outline"
              priceText="0đ"
              periodText="mãi mãi"
              isCurrent={!isPremiumTier}
              rows={FEATURES.map((item) => ({ label: item.label, value: item.free, locked: item.freeLocked }))}
            />
            <PlanCard
              colors={colors}
              styles={styles}
              title="Premium"
              icon="star"
              highlighted
              priceText={price}
              periodText={period}
              priceUsdText={`~ $${priceUsd}`}
              isCurrent={isPremiumTier}
              rows={FEATURES.map((item) => ({ label: item.label, value: item.premium }))}
            />

            {isPremiumTier ? (
              <View style={styles.premiumActiveNote}>
                <Ionicons name="time-outline" size={18} color={colors.success} />
                <Text style={styles.premiumActiveText}>
                  Premium còn {remainingLabel}. Bạn chỉ có thể gia hạn, không thể mua thêm gói mới.
                </Text>
              </View>
            ) : null}

            <View style={styles.paymentSection}>
              <Text style={styles.paymentTitle}>Phương thức thanh toán</Text>
              <View style={styles.paymentRow}>
                {PAYMENT_METHODS.map((item) => {
                  const selected = method === item.key;
                  return (
                    <TouchableOpacity
                      key={item.key}
                      style={[
                        styles.paymentOption,
                        selected && { borderColor: item.color, backgroundColor: `${item.color}14` },
                      ]}
                      onPress={() => setMethod(item.key)}
                      activeOpacity={0.85}
                    >
                      <View style={[styles.paymentIcon, { backgroundColor: item.color }]}>
                        <Text style={styles.paymentIconText}>{item.letter}</Text>
                      </View>
                      <Text style={styles.paymentLabel}>{item.label}</Text>
                      <View style={styles.paymentSoonBadge}>
                        <Text style={styles.paymentSoonText}>Sắp có</Text>
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          </ScrollView>

          <Button
            title={`${isPremiumTier ? 'Gia hạn' : 'Nâng cấp'} ${price}${period}`}
            onPress={contactToUpgrade}
            loading={submitting}
            style={styles.ctaButton}
          />
          <Text style={styles.ctaNote}>
            Thanh toán qua VNPay/MoMo đang được tích hợp. Hiện tại yêu cầu {isPremiumTier ? 'gia hạn' : 'nâng cấp'} được xử lý thủ công qua liên hệ.
          </Text>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function PlanCard({ colors, styles, title, icon, priceText, periodText, priceUsdText, isCurrent, rows, highlighted }) {
  return (
    <View style={[styles.card, highlighted && styles.cardHighlighted]}>
      <View style={styles.cardHeader}>
        <View style={[styles.cardIconWrap, highlighted && styles.cardIconWrapHighlighted]}>
          <Ionicons name={icon} size={16} color={highlighted ? '#ffffff' : colors.textMuted} />
        </View>
        <Text style={styles.cardTitle}>{title}</Text>
        {isCurrent ? (
          <View style={styles.currentBadge}>
            <Text style={styles.currentBadgeText}>Gói hiện tại</Text>
          </View>
        ) : null}
      </View>
      <View style={styles.cardPriceRow}>
        <Text style={[styles.cardPrice, highlighted && styles.cardPriceHighlighted]}>{priceText}</Text>
        <Text style={styles.cardPeriod}>{periodText}</Text>
        {priceUsdText ? <Text style={styles.cardPriceUsd}>{priceUsdText}</Text> : null}
      </View>
      <View style={styles.cardFeatures}>
        {rows.map((row) => (
          <View key={row.label} style={styles.cardFeatureRow}>
            <Ionicons
              name={row.locked ? 'lock-closed' : 'checkmark-circle'}
              size={14}
              color={row.locked ? colors.textMuted : (highlighted ? colors.primary : colors.success)}
            />
            <Text style={styles.cardFeatureLabel}>{row.label}</Text>
            <Text style={[styles.cardFeatureValue, highlighted && styles.cardFeatureValueHighlighted]}>
              {row.value}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function makeStyles(colors) {
  return StyleSheet.create({
    overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' },
    sheet: {
      maxHeight: '90%',
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
    billingPriceUsd: { marginTop: 2, color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 10 },
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
    bodyScroll: { maxHeight: 420 },

    card: {
      backgroundColor: colors.panelSoft,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.border,
      padding: 16,
      marginBottom: 14,
    },
    cardHighlighted: { borderColor: colors.primary, borderWidth: 1.5, backgroundColor: colors.primarySoft },
    cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
    cardIconWrap: {
      width: 28,
      height: 28,
      borderRadius: 9,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.panel,
    },
    cardIconWrapHighlighted: { backgroundColor: colors.primary },
    cardTitle: { flex: 1, color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 15 },
    currentBadge: {
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 999,
      backgroundColor: colors.success,
    },
    currentBadgeText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 9 },
    cardPriceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 5, marginBottom: 12 },
    cardPrice: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 22 },
    cardPriceHighlighted: { color: colors.primary },
    cardPeriod: { color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 11 },
    cardPriceUsd: { marginLeft: 4, color: colors.textMuted, fontFamily: 'Poppins_500Medium', fontSize: 10.5 },
    cardFeatures: { gap: 9 },
    cardFeatureRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    cardFeatureLabel: { flex: 1.5, color: colors.text, fontFamily: 'Poppins_500Medium', fontSize: 11.5, lineHeight: 15 },
    cardFeatureValue: { flex: 1, textAlign: 'right', color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 11 },
    cardFeatureValueHighlighted: { color: colors.primary },

    paymentSection: { marginBottom: 4 },
    paymentTitle: { color: colors.text, fontFamily: 'Poppins_700Bold', fontSize: 13, marginBottom: 10 },
    paymentRow: { flexDirection: 'row', gap: 10 },
    paymentOption: {
      flex: 1,
      alignItems: 'center',
      paddingVertical: 12,
      borderRadius: 14,
      borderWidth: 1.5,
      borderColor: colors.border,
      backgroundColor: colors.panel,
    },
    paymentIcon: {
      width: 32,
      height: 32,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 6,
    },
    paymentIconText: { color: '#ffffff', fontFamily: 'Poppins_700Bold', fontSize: 13 },
    paymentLabel: { color: colors.text, fontFamily: 'Poppins_600SemiBold', fontSize: 12 },
    paymentSoonBadge: {
      marginTop: 6,
      paddingHorizontal: 7,
      paddingVertical: 2,
      borderRadius: 999,
      backgroundColor: colors.border,
    },
    paymentSoonText: { color: colors.textMuted, fontFamily: 'Poppins_600SemiBold', fontSize: 8.5, letterSpacing: 0.3 },

    premiumActiveNote: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      padding: 12,
      borderRadius: 12,
      backgroundColor: `${colors.success}18`,
      marginBottom: 4,
    },
    premiumActiveText: { flex: 1, color: colors.text, fontFamily: 'Poppins_500Medium', fontSize: 12, lineHeight: 16 },

    ctaButton: { marginTop: 16 },
    ctaNote: { marginTop: 10, color: colors.textMuted, fontFamily: 'Poppins_400Regular', fontSize: 10.5, lineHeight: 15, textAlign: 'center' },
  });
}
