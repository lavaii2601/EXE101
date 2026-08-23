import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../api/google_auth.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';

const List<(String value, String vi, String en)> _kFilters = [
  ('all', 'Tất cả', 'All'),
  ('education', 'Giáo dục', 'Education'),
  ('work', 'Công việc', 'Work'),
  ('meeting', 'Họp', 'Meeting'),
  ('promotion', 'Khuyến mãi', 'Promotions'),
  ('finance', 'Tài chính', 'Finance'),
  ('personal', 'Cá nhân', 'Personal'),
  ('other', 'Khác', 'Other'),
];

class EmailScreen extends StatefulWidget {
  const EmailScreen({super.key});

  @override
  State<EmailScreen> createState() => _EmailScreenState();
}

class _EmailScreenState extends State<EmailScreen> {
  List<dynamic> emails = [];
  List<dynamic> suggestions = [];
  bool loading = false;
  bool connectingGmail = false;
  bool authenticated = false;
  String filter = 'all';

  @override
  void initState() {
    super.initState();
    _load();
    _loadSuggestions();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final auth = await apiGet('/email/auth-status');
      final isAuthed = auth is Map && auth['authenticated'] == true;
      setState(() => authenticated = isAuthed);
      if (isAuthed) {
        var data = await apiGet('/email/get-unread?max_results=20&include_read=true&filter=$filter&cache_only=true');
        var items = (data is Map) ? ((data['emails'] as List?) ?? (data['items'] as List?) ?? []) : [];
        // Freshly-connected accounts have nothing cached yet -- fall back to a
        // live Gmail fetch once so the inbox isn't misleadingly empty.
        final needsRefresh = data is Map && (data['cache_miss'] == true || data['needs_refresh'] == true);
        if (items.isEmpty && needsRefresh) {
          data = await apiGet('/email/get-unread?max_results=20&include_read=true&filter=$filter&fresh=true');
          items = (data is Map) ? ((data['emails'] as List?) ?? (data['items'] as List?) ?? []) : [];
        }
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

  Future<void> _loadSuggestions() async {
    try {
      final data = await apiGet('/email/meeting-suggestions');
      final items = (data is Map) ? (data['suggestions'] as List?) ?? [] : [];
      if (mounted) setState(() => suggestions = items);
    } catch (_) {}
  }

  Future<void> _connectGmail() async {
    final t = context.read<LanguageController>().t;
    final appLinks = context.read<AppLinks>();
    setState(() => connectingGmail = true);
    try {
      final result = await connectGoogleAccount(appLinks);
      if (result.connected && mounted) {
        await context.read<AppState>().refreshShell();
        await _load();
        await _loadSuggestions();
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('${t('Kết nối Gmail thất bại', 'Failed to connect Gmail')}: $error')));
      }
    } finally {
      if (mounted) setState(() => connectingGmail = false);
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
          onRefresh: () async {
            await _load();
            await _loadSuggestions();
          },
          children: [
            SizedBox(
              height: 38,
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
                              padding: const EdgeInsets.symmetric(horizontal: 16),
                              decoration: BoxDecoration(
                                color: filter == f.$1 ? colors.primary : colors.panel,
                                borderRadius: BorderRadius.circular(999),
                                border: Border.all(color: filter == f.$1 ? colors.primary : colors.border),
                              ),
                              child: Text(t(f.$2, f.$3),
                                  style: TextStyle(
                                    color: filter == f.$1 ? Colors.white : colors.textMuted,
                                    fontWeight: FontWeight.w600,
                                    fontSize: 12.5,
                                  )),
                            ),
                          ),
                        ))
                    .toList(),
              ),
            ),
            if (suggestions.isNotEmpty)
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('GỢI Ý THÔNG MINH', 'SMART SUGGESTIONS'),
                      style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                  const SizedBox(height: 8),
                  SizedBox(
                    height: 108,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      itemCount: suggestions.length > 5 ? 5 : suggestions.length,
                      separatorBuilder: (_, __) => const SizedBox(width: 10),
                      itemBuilder: (context, index) {
                        final s = Map<String, dynamic>.from(suggestions[index] as Map);
                        final title = (s['title'] as String?) ?? (s['subject'] as String?) ?? t('Lịch hẹn từ email', 'Meeting from email');
                        final meta = s['start_time'] != null ? _formatSuggestionTime(s['start_time'] as String) : ((s['sender'] as String?) ?? '');
                        return Container(
                          width: 210,
                          padding: const EdgeInsets.all(13),
                          decoration: BoxDecoration(
                            color: colors.primarySoft,
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: colors.primary.withValues(alpha: 0.2)),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(Icons.event_outlined, size: 16, color: colors.primary),
                                  const SizedBox(width: 6),
                                  Text(t('Lịch hẹn', 'Meeting'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 11)),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Text(title, maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 13, height: 1.25)),
                              const Spacer(),
                              if (meta.isNotEmpty)
                                Text(meta, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w600, fontSize: 11)),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ),
            if (!authenticated)
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    AppEmptyState(
                      icon: Icons.mail_lock_outlined,
                      title: t('Cần đăng nhập Gmail', 'Gmail sign-in required'),
                      detail: t('Kết nối Gmail để xem hộp thư và nhận gợi ý thông minh.', 'Connect Gmail to view your inbox and get smart suggestions.'),
                    ),
                    const SizedBox(height: 4),
                    AppButton(
                      title: t('Kết nối Gmail', 'Connect Gmail'),
                      icon: Icons.link,
                      onPressed: _connectGmail,
                      loading: connectingGmail,
                    ),
                  ],
                ),
              )
            else if (emails.isEmpty)
              AppCard(child: AppEmptyState(icon: Icons.inbox_outlined, title: t('Không tìm thấy email', 'No emails found')))
            else
              ...emails.map((raw) {
                final email = Map<String, dynamic>.from(raw as Map);
                final unread = email['is_unread'] == true;
                final sender = (email['sender'] as String?) ?? (email['from'] as String?) ?? '';
                final senderName = sender.split('<').first.trim();
                final initial = senderName.isNotEmpty ? senderName[0].toUpperCase() : '?';
                final time = _formatEmailTime((email['date'] as String?) ?? (email['email_date'] as String?) ?? '');
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(16),
                    onTap: () => _toggleRead(email),
                    child: Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: unread ? colors.primarySoft : colors.panel,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: unread ? colors.primary.withValues(alpha: 0.28) : colors.border),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Stack(
                            clipBehavior: Clip.none,
                            children: [
                              Container(
                                width: 38,
                                height: 38,
                                decoration: BoxDecoration(color: colors.primary, shape: BoxShape.circle),
                                child: Center(child: Text(initial, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700))),
                              ),
                              if (unread)
                                Positioned(
                                  top: -2,
                                  right: -2,
                                  child: Container(
                                    width: 11,
                                    height: 11,
                                    decoration: BoxDecoration(color: colors.danger, shape: BoxShape.circle, border: Border.all(color: colors.panel, width: 2)),
                                  ),
                                ),
                            ],
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(senderName.isEmpty ? t('Người gửi', 'Sender') : senderName,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                                    ),
                                    if (time.isNotEmpty)
                                      Text(time, style: TextStyle(color: colors.textMuted, fontSize: 11, fontWeight: FontWeight.w500)),
                                  ],
                                ),
                                const SizedBox(height: 2),
                                Text(email['subject'] as String? ?? t('(Không tiêu đề)', '(No subject)'),
                                    maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 14)),
                                if ((email['snippet'] as String?)?.isNotEmpty == true) ...[
                                  const SizedBox(height: 4),
                                  Text(email['snippet'] as String,
                                      maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.textMuted, fontSize: 12.5, height: 1.4)),
                                ],
                              ],
                            ),
                          ),
                        ],
                      ),
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

String _formatEmailTime(String raw) {
  if (raw.isEmpty) return '';
  final parsed = DateTime.tryParse(raw);
  if (parsed != null) {
    return '${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
  }
  final match = RegExp(r'(\d{1,2}):(\d{2})').firstMatch(raw);
  if (match != null) {
    return '${match.group(1)!.padLeft(2, '0')}:${match.group(2)}';
  }
  return '';
}

String _formatSuggestionTime(String raw) {
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return '';
  const weekdays = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];
  final weekday = weekdays[parsed.weekday - 1];
  return '$weekday, ${parsed.day.toString().padLeft(2, '0')}/${parsed.month.toString().padLeft(2, '0')} '
      '${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
}
