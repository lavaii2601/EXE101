import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';

const List<(String value, String vi, String en)> _kFilters = [
  ('all', 'Tất cả', 'All'),
  ('education', 'Giáo dục', 'Education'),
  ('work', 'Công việc', 'Work'),
  ('meeting', 'Họp', 'Meeting'),
];

class EmailScreen extends StatefulWidget {
  const EmailScreen({super.key});

  @override
  State<EmailScreen> createState() => _EmailScreenState();
}

class _EmailScreenState extends State<EmailScreen> {
  List<dynamic> emails = [];
  bool loading = false;
  bool authenticated = false;
  String filter = 'all';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final auth = await apiGet('/email/auth-status');
      final isAuthed = auth is Map && auth['authenticated'] == true;
      setState(() => authenticated = isAuthed);
      if (isAuthed) {
        final category = filter == 'all' ? '' : '&category=$filter';
        final data = await apiGet('/email/get-unread?max_results=20&cache_only=true$category');
        final items = (data is Map) ? ((data['emails'] as List?) ?? (data['items'] as List?) ?? []) : [];
        setState(() => emails = items);
      } else {
        setState(() => emails = []);
      }
    } catch (_) {
      setState(() => authenticated = false);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _toggleRead(Map<String, dynamic> email) async {
    final id = email['id'];
    if (id == null) return;
    try {
      await apiPost('/email/mark-read/$id');
      setState(() => email['is_unread'] = !(email['is_unread'] == true));
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        top: false,
        child: AppScreen(
          title: t('Email', 'Email'),
          refreshing: loading,
          onRefresh: _load,
          children: [
            SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: _kFilters
                    .map((f) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: GestureDetector(
                            onTap: () {
                              setState(() => filter = f.$1);
                              _load();
                            },
                            child: Container(
                              alignment: Alignment.center,
                              padding: const EdgeInsets.symmetric(horizontal: 14),
                              decoration: BoxDecoration(
                                color: filter == f.$1 ? colors.primary : colors.panel,
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: filter == f.$1 ? colors.primary : colors.border),
                              ),
                              child: Text(t(f.$2, f.$3),
                                  style: TextStyle(color: filter == f.$1 ? Colors.white : colors.textMuted, fontWeight: FontWeight.w600, fontSize: 12)),
                            ),
                          ),
                        ))
                    .toList(),
              ),
            ),
            if (!authenticated)
              AppCard(
                child: AppEmptyState(
                  icon: Icons.mail_lock_outlined,
                  title: t('Cần đăng nhập Gmail', 'Gmail sign-in required'),
                  detail: t(
                    'Đăng nhập Google trên bản Flutter đang được hoàn thiện. Dùng bản React Native để kết nối Gmail lúc này.',
                    'Google sign-in on the Flutter build is still in progress. Use the React Native app to connect Gmail for now.',
                  ),
                ),
              )
            else if (emails.isEmpty)
              AppCard(child: AppEmptyState(icon: Icons.inbox_outlined, title: t('Không tìm thấy email', 'No emails found')))
            else
              ...emails.map((raw) {
                final email = Map<String, dynamic>.from(raw as Map);
                final unread = email['is_unread'] == true;
                final sender = (email['sender'] as String?) ?? (email['from'] as String?) ?? '';
                final initial = sender.trim().isNotEmpty ? sender.trim()[0].toUpperCase() : '?';
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Stack(
                              children: [
                                Container(
                                  width: 36,
                                  height: 36,
                                  decoration: BoxDecoration(color: colors.primary, shape: BoxShape.circle),
                                  child: Center(child: Text(initial, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700))),
                                ),
                                if (unread)
                                  Positioned(
                                    top: -1,
                                    right: -1,
                                    child: Container(
                                      width: 10,
                                      height: 10,
                                      decoration: BoxDecoration(color: colors.danger, shape: BoxShape.circle, border: Border.all(color: colors.panel, width: 2)),
                                    ),
                                  ),
                              ],
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(sender, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                                  Text(email['subject'] as String? ?? '(Không tiêu đề)',
                                      maxLines: 2, style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 14)),
                                ],
                              ),
                            ),
                          ],
                        ),
                        if ((email['snippet'] as String?)?.isNotEmpty == true) ...[
                          const SizedBox(height: 8),
                          Text(email['snippet'] as String, maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.textMuted, fontSize: 12, height: 1.4)),
                        ],
                        const SizedBox(height: 8),
                        Align(
                          alignment: Alignment.centerRight,
                          child: TextButton(
                            onPressed: () => _toggleRead(email),
                            child: Text(unread ? t('Đánh dấu đã đọc', 'Mark as read') : t('Đánh dấu chưa đọc', 'Mark as unread'),
                                style: TextStyle(color: colors.primary, fontSize: 12)),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }
}
