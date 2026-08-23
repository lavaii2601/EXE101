import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../config/user_modes.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';

class ProfileHeader extends StatelessWidget {
  final Map<String, dynamic>? profile;
  final VoidCallback onRefresh;
  final VoidCallback onChangeMode;

  const ProfileHeader({super.key, required this.profile, required this.onRefresh, required this.onChangeMode});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    final name = (profile?['name'] as String?)?.isNotEmpty == true ? profile!['name'] as String : t('Người dùng', 'User');
    final email = (profile?['gmail_email'] as String?) ?? (profile?['email'] as String?) ?? t('Chưa kết nối Gmail', 'Gmail not connected');
    final avatarUrl = (profile?['avatar_url'] as String?) ?? '';
    final gmailReady = profile?['gmail_connected'] == true;
    final isPremium = (profile?['subscription']?['tier']) == 'premium';
    final mode = getUserMode(profile?['user_mode'] as String?);

    return Container(
      constraints: const BoxConstraints(minHeight: 76),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      decoration: BoxDecoration(
        color: colors.panel,
        border: Border(bottom: BorderSide(color: colors.border)),
      ),
      child: Row(
        children: [
          GestureDetector(
            onTap: onRefresh,
            child: Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(color: colors.primary, borderRadius: BorderRadius.circular(14)),
              child: avatarUrl.isNotEmpty
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(14),
                      child: Image.network(avatarUrl, fit: BoxFit.cover, errorBuilder: (_, __, ___) => _initial(name)),
                    )
                  : _initial(name),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: GestureDetector(
              onTap: onChangeMode,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('FLOWMATE AI',
                      style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 9, letterSpacing: 1.2)),
                  const SizedBox(height: 1),
                  Text(name, style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 15)),
                  const SizedBox(height: 2),
                  Text('${mode.label} · $email',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: colors.textMuted, fontSize: 11)),
                ],
              ),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (isPremium)
                Container(
                  margin: const EdgeInsets.only(bottom: 5),
                  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                  decoration: BoxDecoration(color: const Color(0xFFF59E0B), borderRadius: BorderRadius.circular(999)),
                  child: Text('★ Premium', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 10)),
                ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: gmailReady ? const Color(0xFF059669) : const Color(0xFFD97706),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  gmailReady ? t('Sẵn sàng', 'Ready') : t('Cần thiết lập', 'Setup'),
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 11),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _initial(String name) {
    return Center(
      child: Text(
        name.isNotEmpty ? name[0].toUpperCase() : '?',
        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15),
      ),
    );
  }
}
