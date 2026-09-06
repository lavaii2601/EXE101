import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../api/google_auth.dart';
import '../config/app_icons.dart';
import '../state/app_state.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';
import '../widgets/app_screen.dart';
import 'email_detail_screen.dart';

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

// Smart Inbox (Phase 4): an additional, independent filter dimension
// alongside _kFilters above -- not a replacement for it.
const List<(String value, String vi, String en)> _kSmartBuckets = [
  ('', 'Tất cả', 'All'),
  ('action_required', 'Cần xử lý', 'Action required'),
  ('waiting', 'Đang chờ', 'Waiting'),
  ('fyi', 'Tham khảo', 'FYI'),
  ('low_priority', 'Ít quan trọng', 'Low priority'),
];

const Map<String, (String vi, String en)> _kSmartBucketLabels = {
  'action_required': ('Cần xử lý', 'Action required'),
  'waiting': ('Đang chờ', 'Waiting'),
  'fyi': ('Tham khảo', 'FYI'),
  'low_priority': ('Ít quan trọng', 'Low priority'),
};

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

  bool showSearch = false;
  final searchController = TextEditingController();
  String searchKeyword = '';
  Timer? _searchDebounce;

  bool includeRead = true;
  String smartBucket = '';
  bool sharing = false;

  @override
  void initState() {
    super.initState();
    _load();
    _loadSuggestions();
  }

  @override
  void dispose() {
    searchController.dispose();
    _searchDebounce?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final auth = await apiGet('/email/auth-status');
      final isAuthed = auth is Map && auth['authenticated'] == true;
      setState(() => authenticated = isAuthed);
      if (isAuthed) {
        final smartBucketParam = smartBucket.isNotEmpty ? '&smart_bucket=$smartBucket' : '';
        final query = 'max_results=20&include_read=$includeRead&filter=$filter&search=${Uri.encodeQueryComponent(searchKeyword)}$smartBucketParam';
        var data = await apiGet('/email/get-unread?$query&cache_only=true');
        var items = (data is Map) ? ((data['emails'] as List?) ?? (data['items'] as List?) ?? []) : [];
        // Freshly-connected accounts have nothing cached yet -- fall back to a
        // live Gmail fetch once so the inbox isn't misleadingly empty.
        final needsRefresh = data is Map && (data['cache_miss'] == true || data['needs_refresh'] == true);
        if (items.isEmpty && needsRefresh) {
          data = await apiGet('/email/get-unread?$query&fresh=true');
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
    final wasUnread = email['is_unread'] == true;
    try {
      await apiPost(wasUnread ? '/email/mark-as-read/$id' : '/email/mark-as-unread/$id');
      setState(() => email['is_unread'] = !wasUnread);
    } catch (_) {}
  }

  Future<void> _openEmailDetail(Map<String, dynamic> email) async {
    if (email['is_unread'] == true) {
      await _toggleRead(email);
    }
    if (!mounted) return;
    Navigator.push(context, MaterialPageRoute(builder: (_) => EmailDetailScreen(email: email, onToggleRead: _toggleRead)));
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 350), () {
      searchKeyword = value.trim();
      _load();
    });
  }

  void _openFilterSheet() {
    final colors = context.read<ThemeController>().colors;
    final t = context.read<LanguageController>().t;
    showModalBottomSheet(
      context: context,
      backgroundColor: colors.panel,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            return Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(t('Bộ lọc email', 'Email filters'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
                      IconButton(icon: Icon(AppIcons.emailSearchClear, color: colors.textMuted), onPressed: () => Navigator.pop(sheetContext)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(t('Hiện email đã đọc', 'Show read emails'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 14)),
                            Text(t('Tắt để chỉ xem email chưa đọc.', 'Turn off to only see unread emails.'),
                                style: TextStyle(color: colors.textMuted, fontSize: 12)),
                          ],
                        ),
                      ),
                      Switch(
                        value: includeRead,
                        activeTrackColor: colors.primary,
                        onChanged: (value) => setSheetState(() => includeRead = value),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  AppButton(
                    title: t('Áp dụng', 'Apply'),
                    onPressed: () {
                      Navigator.pop(sheetContext);
                      _load();
                    },
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _openShareSheet(Map<String, dynamic> email) {
    final colors = context.read<ThemeController>().colors;
    final t = context.read<LanguageController>().t;
    final businessWorkspaces = context.read<WorkspaceController>().workspaces.where((w) => w['type'] == 'business').toList();
    if (businessWorkspaces.isEmpty) return;
    String selectedWorkspaceId = businessWorkspaces.first['id'] as String;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: colors.panel,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            Future<void> confirmAndShare() async {
              final confirmed = await showDialog<bool>(
                context: sheetContext,
                builder: (dialogContext) => AlertDialog(
                  title: Text(t('Xác nhận chia sẻ', 'Confirm sharing')),
                  content: Text(t(
                    'Chủ sở hữu/quản trị không gian đã chọn sẽ thấy được nội dung này. Tiếp tục?',
                    "The selected workspace's owner/admin will be able to see this content. Continue?",
                  )),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: Text(t('Hủy', 'Cancel'))),
                    TextButton(onPressed: () => Navigator.pop(dialogContext, true), child: Text(t('Chia sẻ', 'Share'))),
                  ],
                ),
              );
              if (confirmed != true) return;
              setSheetState(() => sharing = true);
              try {
                await apiPost('/workspaces/$selectedWorkspaceId/shared-artifacts', {
                  'source_type': 'email_summary',
                  'title': email['subject'] as String? ?? t('Email đã chia sẻ', 'Shared email'),
                  'content': {
                    'subject': email['subject'] as String? ?? '',
                    'sender': email['sender'] as String? ?? '',
                    'summary': (email['summary'] as String?) ?? (email['snippet'] as String?) ?? '',
                    'date': email['date'] as String? ?? '',
                  },
                });
                if (sheetContext.mounted) Navigator.pop(sheetContext);
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('Đã chia sẻ vào không gian doanh nghiệp', 'Shared to the workspace'))));
                }
              } catch (e) {
                setSheetState(() => sharing = false);
                if (sheetContext.mounted) {
                  ScaffoldMessenger.of(sheetContext).showSnackBar(SnackBar(content: Text('${t('Không chia sẻ được', 'Could not share')}: $e')));
                }
              }
            }

            return Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('Chia sẻ vào không gian doanh nghiệp', 'Share to a Business workspace'),
                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
                  const SizedBox(height: 10),
                  Text(
                    t(
                      'Chủ sở hữu/quản trị không gian sẽ thấy được nội dung này sau khi xác nhận.',
                      "The workspace's owner/admin will see this content once confirmed.",
                    ),
                    style: TextStyle(color: colors.textMuted, fontSize: 12.5),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(color: colors.panelSoft, borderRadius: BorderRadius.circular(12), border: Border.all(color: colors.border)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(email['subject'] as String? ?? '', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                        const SizedBox(height: 4),
                        Text((email['summary'] as String?) ?? (email['snippet'] as String?) ?? '', maxLines: 3, overflow: TextOverflow.ellipsis, style: TextStyle(color: colors.textMuted, fontSize: 12)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(t('Không gian doanh nghiệp', 'Business workspace'), style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w600, fontSize: 12)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: businessWorkspaces.map((w) {
                      final id = w['id'] as String;
                      final active = id == selectedWorkspaceId;
                      return GestureDetector(
                        onTap: () => setSheetState(() => selectedWorkspaceId = id),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                          decoration: BoxDecoration(
                            color: active ? colors.primary : colors.panelSoft,
                            borderRadius: BorderRadius.circular(999),
                            border: Border.all(color: active ? colors.primary : colors.border),
                          ),
                          child: Text(w['name'] as String? ?? '', style: TextStyle(color: active ? Colors.white : colors.text, fontWeight: FontWeight.w600, fontSize: 12.5)),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 18),
                  AppButton(title: t('Xác nhận chia sẻ', 'Confirm sharing'), onPressed: confirmAndShare, loading: sharing),
                ],
              ),
            );
          },
        );
      },
    ).whenComplete(() {
      if (mounted) setState(() => sharing = false);
    });
  }

  void _openComposeSheet() {
    final toController = TextEditingController();
    final subjectController = TextEditingController();
    final bodyController = TextEditingController();
    bool sending = false;
    String? error;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        final colors = context.read<ThemeController>().colors;
        final t = context.read<LanguageController>().t;
        return StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            Future<void> submit() async {
              final to = toController.text.trim();
              final subject = subjectController.text.trim();
              final body = bodyController.text.trim();
              if (to.isEmpty || subject.isEmpty || body.isEmpty) {
                setSheetState(() => error = t('Vui lòng điền người nhận, tiêu đề và nội dung.', 'Please fill in recipient, subject, and body.'));
                return;
              }
              setSheetState(() {
                sending = true;
                error = null;
              });
              try {
                await apiPost('/email/send-reply', {'to': to, 'subject': subject, 'body': body});
                if (sheetContext.mounted) Navigator.pop(sheetContext);
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('Đã gửi email', 'Email sent'))));
                  _load();
                }
              } catch (e) {
                setSheetState(() {
                  sending = false;
                  error = '${t('Không gửi được email', 'Could not send email')}: $e';
                });
              }
            }

            return Padding(
              padding: EdgeInsets.only(bottom: MediaQuery.of(sheetContext).viewInsets.bottom),
              child: Container(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
                decoration: BoxDecoration(color: colors.panel, borderRadius: const BorderRadius.vertical(top: Radius.circular(24))),
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(t('Soạn email mới', 'New email'), style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
                          IconButton(icon: Icon(AppIcons.emailSearchClear, color: colors.textMuted), onPressed: () => Navigator.pop(sheetContext)),
                        ],
                      ),
                      const SizedBox(height: 4),
                      AppField(label: t('Người nhận', 'To'), controller: toController, hint: 'name@company.com', keyboardType: TextInputType.emailAddress),
                      AppField(label: t('Tiêu đề', 'Subject'), controller: subjectController, hint: t('Tiêu đề email', 'Email subject')),
                      AppField(label: t('Nội dung', 'Body'), controller: bodyController, hint: t('Nội dung email', 'Email body'), multiline: true),
                      if (error != null) ...[
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(error!, style: TextStyle(color: colors.danger, fontSize: 12.5)),
                        ),
                      ] else
                        const SizedBox(height: 6),
                      AppButton(title: t('Gửi email', 'Send email'), icon: AppIcons.emailSend, onPressed: submit, loading: sending),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final hasBusinessWorkspace = context.watch<WorkspaceController>().workspaces.any((w) => w['type'] == 'business');

    return Scaffold(
      backgroundColor: colors.background,
      floatingActionButton: authenticated
          ? FloatingActionButton(
              onPressed: _openComposeSheet,
              backgroundColor: colors.primary,
              child: Icon(AppIcons.emailCompose, color: Colors.white),
            )
          : null,
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
            Row(
              children: [
                Expanded(
                  child: SizedBox(
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
                ),
                const SizedBox(width: 8),
                _IconTrigger(
                  icon: AppIcons.emailSearch,
                  active: showSearch,
                  onTap: () => setState(() => showSearch = !showSearch),
                ),
                const SizedBox(width: 8),
                _IconTrigger(
                  icon: AppIcons.emailFilter,
                  active: !includeRead,
                  onTap: _openFilterSheet,
                ),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 36,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: _kSmartBuckets
                    .map((b) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: GestureDetector(
                            onTap: () {
                              setState(() => smartBucket = b.$1);
                              _load();
                            },
                            child: Container(
                              alignment: Alignment.center,
                              padding: const EdgeInsets.symmetric(horizontal: 14),
                              decoration: BoxDecoration(
                                color: smartBucket == b.$1 ? colors.primary : colors.panel,
                                borderRadius: BorderRadius.circular(999),
                                border: Border.all(color: smartBucket == b.$1 ? colors.primary : colors.border),
                              ),
                              child: Text(t(b.$2, b.$3),
                                  style: TextStyle(
                                    color: smartBucket == b.$1 ? Colors.white : colors.textMuted,
                                    fontWeight: FontWeight.w600,
                                    fontSize: 11.5,
                                  )),
                            ),
                          ),
                        ))
                    .toList(),
              ),
            ),
            if (showSearch) ...[
              const SizedBox(height: 10),
              TextField(
                controller: searchController,
                autofocus: true,
                onChanged: _onSearchChanged,
                style: TextStyle(color: colors.text, fontSize: 14),
                decoration: InputDecoration(
                  hintText: t('Tìm theo người gửi, tiêu đề...', 'Search sender, subject...'),
                  hintStyle: TextStyle(color: colors.inputPlaceholder),
                  prefixIcon: Icon(AppIcons.emailSearch, size: 18, color: colors.textMuted),
                  suffixIcon: searchController.text.isNotEmpty
                      ? IconButton(
                          icon: Icon(AppIcons.emailSearchClear, size: 18, color: colors.textMuted),
                          onPressed: () {
                            searchController.clear();
                            _onSearchChanged('');
                          },
                        )
                      : null,
                  filled: true,
                  fillColor: colors.panelSoft,
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: colors.border)),
                  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: colors.border)),
                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: colors.primary)),
                ),
              ),
            ],
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
                                  Icon(AppIcons.emailMeeting, size: 16, color: colors.primary),
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
                      icon: AppIcons.emailLocked,
                      title: t('Cần đăng nhập Gmail', 'Gmail sign-in required'),
                      detail: t('Kết nối Gmail để xem hộp thư và nhận gợi ý thông minh.', 'Connect Gmail to view your inbox and get smart suggestions.'),
                    ),
                    const SizedBox(height: 4),
                    AppButton(
                      title: t('Kết nối Gmail', 'Connect Gmail'),
                      icon: AppIcons.emailConnect,
                      onPressed: _connectGmail,
                      loading: connectingGmail,
                    ),
                  ],
                ),
              )
            else if (emails.isEmpty && loading)
              const Padding(padding: EdgeInsets.symmetric(vertical: 40), child: Center(child: CircularProgressIndicator()))
            else if (emails.isEmpty)
              AppCard(
                child: AppEmptyState(
                  icon: AppIcons.emailInbox,
                  title: t('Không tìm thấy email', 'No emails found'),
                  detail: searchKeyword.isNotEmpty ? t('Không có kết quả cho "$searchKeyword".', 'No results for "$searchKeyword".') : null,
                ),
              )
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
                    onTap: () => _openEmailDetail(email),
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
                                if (email['smart_bucket'] != null || hasBusinessWorkspace) ...[
                                  const SizedBox(height: 8),
                                  Row(
                                    children: [
                                      if (email['smart_bucket'] != null) ...[
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                          decoration: BoxDecoration(
                                            color: _smartBadgeColor(email['smart_bucket'] as String, colors).withValues(alpha: 0.14),
                                            borderRadius: BorderRadius.circular(999),
                                          ),
                                          child: Text(
                                            _smartBucketLabel(email['smart_bucket'] as String, t),
                                            style: TextStyle(color: _smartBadgeColor(email['smart_bucket'] as String, colors), fontWeight: FontWeight.w700, fontSize: 9.5),
                                          ),
                                        ),
                                        const Spacer(),
                                      ] else
                                        const Spacer(),
                                      if (hasBusinessWorkspace)
                                        TextButton.icon(
                                          onPressed: () => _openShareSheet(email),
                                          icon: Icon(Icons.share_outlined, size: 15, color: colors.primary),
                                          label: Text(t('Chia sẻ', 'Share'), style: TextStyle(color: colors.primary, fontSize: 11.5, fontWeight: FontWeight.w600)),
                                          style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 6), minimumSize: Size.zero, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                                        ),
                                    ],
                                  ),
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
            const SizedBox(height: 64),
          ],
        ),
      ),
    );
  }
}

class _IconTrigger extends StatelessWidget {
  final IconData icon;
  final bool active;
  final VoidCallback onTap;
  const _IconTrigger({required this.icon, required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 38,
        height: 38,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: active ? colors.primary : colors.panel,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: active ? colors.primary : colors.border),
        ),
        child: Icon(icon, size: 18, color: active ? Colors.white : colors.primary),
      ),
    );
  }
}

String _smartBucketLabel(String bucket, String Function(String, [String?]) t) {
  final pair = _kSmartBucketLabels[bucket];
  return pair == null ? bucket : t(pair.$1, pair.$2);
}

Color _smartBadgeColor(String bucket, AppColors colors) {
  if (bucket == 'action_required') return colors.danger;
  if (bucket == 'waiting') return const Color(0xFFB45309);
  if (bucket == 'low_priority') return colors.textMuted;
  return colors.primary;
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
