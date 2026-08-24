import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../config/app_icons.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';

/// Full-content view for a single email, pushed when a row is tapped in
/// EmailScreen. Fetches the full body on-demand (the list only ever carries
/// a snippet) and offers an on-demand AI summary via /email/summary/<id>.
class EmailDetailScreen extends StatefulWidget {
  final Map<String, dynamic> email;
  final Future<void> Function(Map<String, dynamic>)? onToggleRead;
  const EmailDetailScreen({super.key, required this.email, this.onToggleRead});

  @override
  State<EmailDetailScreen> createState() => _EmailDetailScreenState();
}

class _EmailDetailScreenState extends State<EmailDetailScreen> {
  bool loadingBody = true;
  String body = '';
  String? bodyError;
  late String summary;
  bool summarizing = false;
  String? summaryError;
  bool togglingRead = false;
  late bool isUnread;

  @override
  void initState() {
    super.initState();
    summary = (widget.email['summary'] as String?) ?? '';
    isUnread = widget.email['is_unread'] == true;
    _loadBody();
  }

  Future<void> _toggleRead() async {
    if (widget.onToggleRead == null) return;
    setState(() => togglingRead = true);
    await widget.onToggleRead!(widget.email);
    if (mounted) {
      setState(() {
        isUnread = widget.email['is_unread'] == true;
        togglingRead = false;
      });
    }
  }

  Future<void> _loadBody() async {
    final id = widget.email['id'];
    if (id == null) {
      setState(() => loadingBody = false);
      return;
    }
    setState(() => loadingBody = true);
    try {
      final data = await apiGet('/email/get-email-body/$id');
      final fetched = (data is Map ? data['body'] as String? : null) ?? '';
      if (mounted) setState(() => body = fetched);
    } catch (error) {
      if (mounted) setState(() => bodyError = error.toString());
    } finally {
      if (mounted) setState(() => loadingBody = false);
    }
  }

  Future<void> _summarize() async {
    final id = widget.email['id'];
    if (id == null) return;
    setState(() {
      summarizing = true;
      summaryError = null;
    });
    try {
      final data = await apiPost('/email/summary/$id', {});
      final fetched = (data is Map ? data['summary'] as String? : null) ?? '';
      if (mounted) setState(() => summary = fetched);
    } catch (error) {
      if (mounted) setState(() => summaryError = error.toString());
    } finally {
      if (mounted) setState(() => summarizing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final email = widget.email;
    final sender = (email['sender'] as String?) ?? (email['from'] as String?) ?? '';
    final subject = (email['subject'] as String?)?.isNotEmpty == true ? email['subject'] as String : t('(Không tiêu đề)', '(No subject)');

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 6, 20, 6),
              child: Row(
                children: [
                  IconButton(
                    icon: Icon(AppIcons.emailBack, color: colors.text),
                    onPressed: () => Navigator.pop(context),
                  ),
                  Expanded(
                    child: Text(t('Chi tiết email', 'Email detail'),
                        style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17)),
                  ),
                  if (widget.onToggleRead != null)
                    IconButton(
                      icon: togglingRead
                          ? SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: colors.primary))
                          : Icon(isUnread ? Icons.mail_outline : Icons.mark_email_unread_outlined, color: colors.primary),
                      tooltip: isUnread ? t('Đánh dấu đã đọc', 'Mark as read') : t('Đánh dấu chưa đọc', 'Mark as unread'),
                      onPressed: togglingRead ? null : _toggleRead,
                    ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
                children: [
                  Text(subject, style: TextStyle(color: colors.text, fontWeight: FontWeight.w800, fontSize: 20, height: 1.3)),
                  const SizedBox(height: 8),
                  Text(sender, style: TextStyle(color: colors.textMuted, fontSize: 13)),
                  const SizedBox(height: 20),
                  if (summary.isNotEmpty)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(14),
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: colors.panelSoft,
                        borderRadius: BorderRadius.circular(14),
                        border: Border(left: BorderSide(color: colors.primary, width: 3)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(t('AI TÓM TẮT', 'AI SUMMARY'), style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                          const SizedBox(height: 6),
                          Text(summary, style: TextStyle(color: colors.text, fontSize: 13.5, height: 1.5)),
                        ],
                      ),
                    ),
                  if (summaryError != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(summaryError!, style: TextStyle(color: colors.danger, fontSize: 12.5)),
                    ),
                  AppButton(
                    title: summary.isNotEmpty ? t('Tóm tắt lại bằng AI', 'Re-summarize with AI') : t('Tóm tắt bằng AI', 'Summarize with AI'),
                    variant: AppButtonVariant.secondary,
                    icon: AppIcons.emailSummarize,
                    onPressed: _summarize,
                    loading: summarizing,
                  ),
                  const SizedBox(height: 22),
                  Divider(color: colors.border),
                  const SizedBox(height: 18),
                  if (loadingBody)
                    const Padding(padding: EdgeInsets.symmetric(vertical: 40), child: Center(child: CircularProgressIndicator()))
                  else if (bodyError != null)
                    Text('${t('Không tải được nội dung', 'Could not load content')}: $bodyError', style: TextStyle(color: colors.danger, fontSize: 13))
                  else
                    SelectableText(
                      body.isEmpty ? ((email['snippet'] as String?) ?? '') : body,
                      style: TextStyle(color: colors.text, fontSize: 14, height: 1.6),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
