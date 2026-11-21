import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';

class ProfileHeader extends StatelessWidget {
  final Map<String, dynamic>? profile;
  final VoidCallback onRefresh;
  final VoidCallback onChangeMode;

  const ProfileHeader(
      {super.key,
      required this.profile,
      required this.onRefresh,
      required this.onChangeMode});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    final name = (profile?['name'] as String?)?.isNotEmpty == true
        ? profile!['name'] as String
        : t('Người dùng', 'User');
    final avatarUrl = (profile?['avatar_url'] as String?) ?? '';
    final gmailReady = profile?['gmail_connected'] == true;
    final isPremium = (profile?['subscription']?['tier']) == 'premium';

    return Container(
      constraints: const BoxConstraints(minHeight: 68),
      padding: const EdgeInsets.fromLTRB(16, 10, 12, 8),
      color: Colors.transparent,
      child: Row(
        children: [
          GestureDetector(
            onTap: onRefresh,
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: colors.primary.withValues(alpha: 0.12),
                shape: BoxShape.circle,
                border:
                    Border.all(color: colors.primary.withValues(alpha: 0.14)),
              ),
              child: avatarUrl.isNotEmpty
                  ? ClipOval(
                      child: Image.network(avatarUrl,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => _initial(name, colors)),
                    )
                  : _initial(name, colors),
            ),
          ),
          const SizedBox(width: 9),
          Expanded(
            child: GestureDetector(
              onTap: onChangeMode,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'FlowMate AI',
                    style: TextStyle(
                        color: colors.primary,
                        fontWeight: FontWeight.w800,
                        fontSize: 12),
                  ),
                  const SizedBox(height: 5),
                  Row(
                    children: [
                      Container(
                        width: 5,
                        height: 5,
                        decoration: BoxDecoration(
                          color: gmailReady ? colors.success : colors.warning,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 5),
                      Flexible(
                        child: Text(
                          gmailReady
                              ? t('Gmail đã kết nối', 'Gmail connected')
                              : t('Gmail chưa kết nối', 'Gmail not connected'),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: gmailReady ? colors.success : colors.warning,
                            fontWeight: FontWeight.w600,
                            fontSize: 9.5,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          if (isPremium)
            Container(
              margin: const EdgeInsets.only(right: 4),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFFF4C364).withValues(alpha: 0.22),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text('PRO',
                  style: TextStyle(
                      color: colors.warning,
                      fontWeight: FontWeight.w800,
                      fontSize: 9)),
            ),
          IconButton(
            tooltip: t('Làm mới', 'Refresh'),
            onPressed: onRefresh,
            visualDensity: VisualDensity.compact,
            icon: Icon(Icons.notifications_none_rounded,
                color: colors.primary, size: 22),
          ),
        ],
      ),
    );
  }

  Widget _initial(String name, AppColors colors) {
    return Center(
      child: Text(
        name.isNotEmpty ? name[0].toUpperCase() : '?',
        style: TextStyle(
            color: colors.primary, fontWeight: FontWeight.w800, fontSize: 15),
      ),
    );
  }
}
