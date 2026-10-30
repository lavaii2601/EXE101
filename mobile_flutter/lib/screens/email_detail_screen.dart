import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api/client.dart';
import '../config/app_icons.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';

/// aiQuota is the {action, allowed, used, limit, remaining} map every
/// quota-gated AI route now returns on success (see utils/quota.py's
/// enforce_ai_quota) -- previously discarded after a successful call, so
/// there was no way to show how many uses of a Premium-gated feature are
/// left without the user first running out. Returns '' when not applicable.
String _formatQuotaRemainingLabel(
    Map<String, dynamic>? aiQuota, String Function(String, [String?]) t) {
  final limit = aiQuota?['limit'];
  if (aiQuota == null || limit is! num || limit <= 0) return '';
  final remaining = aiQuota['remaining'];
  return t('Còn ${remaining ?? 0}/${limit.toInt()} lượt hôm nay',
      '${remaining ?? 0}/${limit.toInt()} left today');
}

/// Mirrors mobile/src/utils (and web's equivalent) well enough for a simple
/// attachment-size label -- no need for a package just for this.
String _formatFileSize(dynamic rawSize) {
  final bytes = rawSize is num ? rawSize.toDouble() : double.tryParse('$rawSize') ?? 0;
  if (bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  var value = bytes;
  var unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  final formatted = unitIndex == 0 ? value.toStringAsFixed(0) : value.toStringAsFixed(1);
  return '$formatted ${units[unitIndex]}';
}

/// Whether an HTML email body is safe to hand to flutter_html.
///
/// flutter_html's text content is fine, but its table layout support is
/// unreliable for the deeply-nested `<table>` grids real-world templates
/// (bank receipts especially) use for the *entire* message layout -- it can
/// silently paint nothing even though the underlying text is there (proven
/// by the AI summary reading it fine from the same markup). A short-text
/// check alone doesn't catch this, since the text exists in the markup and
/// only fails to *paint*, so we also treat heavily-tabled markup as unsafe
/// and fall back to the plain-text body instead of an empty white card.
bool _htmlLooksRenderable(String html) {
  final visibleText = html.replaceAll(RegExp(r'<[^>]*>'), ' ').replaceAll(RegExp(r'&[a-zA-Z#0-9]+;'), ' ').replaceAll(RegExp(r'\s+'), ' ').trim();
  if (visibleText.length < 40) return false;
  final tableCount = RegExp(r'<table', caseSensitive: false).allMatches(html).length;
  return tableCount < 3;
}

// Mirrors the exact section headers services/extractive_summary.py's
// summarize_structured() and ai_service.py's _EMAIL_SUMMARY_SYSTEM_PROMPT
// both emit, and the equivalent parser in web (utils.js) and RN
// (EmailScreen.js) -- so AI-generated and local-fallback summaries render
// through the same labelled-sections card on every platform.
const Map<String, IconData> _summarySectionIcons = {
  'TÓM TẮT': Icons.auto_awesome_outlined,
  'ĐIỂM CHÍNH': Icons.list_alt_outlined,
  'CẦN LÀM': Icons.check_box_outlined,
  'THỜI HẠN': Icons.schedule_outlined,
  'TÀI LIỆU': Icons.attach_file_outlined,
};

const Map<String, List<String>> _summarySectionLabels = {
  'TÓM TẮT': ['Tóm tắt', 'Summary'],
  'ĐIỂM CHÍNH': ['Điểm chính', 'Key points'],
  'CẦN LÀM': ['Cần làm', 'Action items'],
  'THỜI HẠN': ['Thời hạn', 'Deadlines'],
  'TÀI LIỆU': ['Tài liệu', 'Documents'],
};

class _EmailSummarySection {
  final String? title;
  final String body;
  const _EmailSummarySection(this.title, this.body);
}

List<_EmailSummarySection> _parseEmailSummarySections(String summary) {
  final text = summary.trim();
  if (text.isEmpty) return [];
  final blocks = text.split(RegExp(r'\n{2,}'));
  final sections = <_EmailSummarySection>[];
  for (final block in blocks) {
    final lines = block.split('\n');
    final firstLine = lines.first.trim();
    // Case-insensitive: the backend always emits exact uppercase headers,
    // but an AI call that drifts on casing (e.g. "Cần làm") must still be
    // recognized as its section instead of silently glomming onto
    // whichever section came before it.
    final matchedHeader = _summarySectionLabels.keys.firstWhere(
      (header) => header.toUpperCase() == firstLine.toUpperCase(),
      orElse: () => '',
    );
    if (matchedHeader.isNotEmpty) {
      sections.add(_EmailSummarySection(matchedHeader, lines.skip(1).join('\n').trim()));
    } else if (sections.isNotEmpty) {
      // A stray blank line inside one section's own body must not be
      // mistaken for the start of a new, untitled section.
      final last = sections.removeLast();
      sections.add(_EmailSummarySection(last.title, '${last.body}\n\n$block'.trim()));
    } else {
      sections.add(_EmailSummarySection(null, block.trim()));
    }
  }
  return sections.where((section) => section.body.isNotEmpty).toList();
}

Widget _buildEmailSummarySections(String summary, AppColors colors, String Function(String, [String?]) t) {
  final sections = _parseEmailSummarySections(summary);
  if (sections.isEmpty) {
    return Text(summary, style: TextStyle(color: colors.text, fontSize: 13.5, height: 1.5));
  }
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: sections.map((section) {
      final title = section.title;
      final icon = title != null ? _summarySectionIcons[title] : null;
      final labels = title != null ? _summarySectionLabels[title] : null;
      final lines = section.body.split('\n').where((line) => line.trim().isNotEmpty).toList();
      final isBulletList = lines.isNotEmpty && lines.every((line) => line.trim().startsWith('-'));
      return Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (title != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (icon != null) Icon(icon, size: 14, color: colors.primary),
                    if (icon != null) const SizedBox(width: 5),
                    Text(
                      labels != null ? t(labels[0], labels[1]) : title,
                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 11.5),
                    ),
                  ],
                ),
              ),
            if (isBulletList)
              ...lines.map((line) => Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(
                      '•  ${line.trim().replaceFirst(RegExp(r'^[-•]\s*'), '')}',
                      style: TextStyle(color: colors.text, fontSize: 13.5, height: 1.5),
                    ),
                  ))
            else
              Text(section.body, style: TextStyle(color: colors.text, fontSize: 13.5, height: 1.5)),
          ],
        ),
      );
    }).toList(),
  );
}

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
  String htmlBody = '';
  String? bodyError;
  late String summary;
  // email['summary'] is pre-populated server-side with a truncated snippet
  // fallback for every email (see routes/email/list.py's
  // _hydrate_email_for_list), so it's non-empty long before any real AI
  // summary exists -- summary_type is the only reliable way to tell a real
  // AI summary ('ai_cached') from that preview placeholder.
  late String summaryType;
  // Whether "Tóm tắt bằng AI" was explicitly pressed for the email this
  // screen is showing -- the summary card only ever renders when this is
  // true, never just because summary_type carried over as 'ai_cached'
  // from an earlier session's list fetch. Opening an email is for
  // reading the real message, not a second opinion next to it.
  // summaryType itself is kept as-is for the button label ("Tóm tắt lại"
  // vs "Tóm tắt"), which should still reflect whether a cached summary
  // exists even before the user asks to see it.
  bool summaryRequested = false;
  bool summarizing = false;
  String? summaryError;
  // {action, allowed, used, limit, remaining} from the summarize response's
  // ai_quota field -- shows "X/Y left today" right after a successful
  // summary instead of only once the user has already run out.
  Map<String, dynamic>? summaryQuota;
  bool togglingRead = false;
  late bool isUnread;
  List<Map<String, dynamic>> attachments = [];
  String downloadingAttachmentId = '';

  @override
  void initState() {
    super.initState();
    summary = '';
    summaryType = (widget.email['summary_type'] as String?) ?? '';
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
      final emailData = data is Map ? data['email'] as Map? : null;
      final fetchedHtml = (emailData?['html_body'] as String?) ?? '';
      final fetchedAttachments = emailData?['attachments'];
      if (mounted) {
        setState(() {
          body = fetched;
          htmlBody = fetchedHtml;
          attachments = fetchedAttachments is List
              ? fetchedAttachments.whereType<Map>().map((a) => a.cast<String, dynamic>()).toList()
              : [];
        });
      }
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
      final quota = data is Map ? data['ai_quota'] as Map? : null;
      if (mounted) {
        setState(() {
          summary = fetched;
          summaryType = 'ai_cached';
          summaryRequested = true;
          summaryQuota = quota?.cast<String, dynamic>();
        });
      }
    } catch (error) {
      if (mounted) setState(() => summaryError = error.toString());
    } finally {
      if (mounted) setState(() => summarizing = false);
    }
  }

  // Saves into the OS temp directory rather than asking for a documents-
  // folder dependency (path_provider) just for this -- matches RN's own
  // "save + confirm, no auto-open" behavior rather than trying to launch a
  // viewer, since url_launcher can't carry this app's Bearer-token auth to
  // an external app anyway and a bare file:// open is unreliable per-platform.
  Future<void> _downloadAttachment(Map<String, dynamic> attachment) async {
    final id = widget.email['id'];
    final attachmentId = attachment['id'];
    if (id == null || attachmentId == null) return;
    final t = context.read<LanguageController>().t;
    setState(() => downloadingAttachmentId = '$attachmentId');
    try {
      final bytes = await apiGetBytes(
          '/email/attachment/${Uri.encodeComponent('$id')}/${Uri.encodeComponent('$attachmentId')}');
      final rawName = (attachment['filename'] as String?) ?? 'attachment';
      final safeName = rawName
          .replaceAll(RegExp(r'[^\p{L}\p{N}._() -]+', unicode: true), '_')
          .replaceFirst(RegExp(r'^\.+'), '')
          .trim();
      final filename = safeName.isEmpty ? 'attachment' : safeName;
      final file = File('${Directory.systemTemp.path}${Platform.pathSeparator}$filename');
      await file.writeAsBytes(bytes);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(
                '${t('Đã lưu', 'Saved')} "$rawName" ${t('vào bộ nhớ ứng dụng', 'to app storage')}')));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(
                '${t('Không tải được file đính kèm', 'Could not download the attachment')}: $error')));
      }
    } finally {
      if (mounted) setState(() => downloadingAttachmentId = '');
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;
    final email = widget.email;
    final sender = (email['sender'] as String?) ?? (email['from'] as String?) ?? '';
    final subject = (email['subject'] as String?)?.isNotEmpty == true ? email['subject'] as String : t('(Không tiêu đề)', '(No subject)');
    final htmlHasText = htmlBody.isNotEmpty && _htmlLooksRenderable(htmlBody);

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
                  if (summary.isNotEmpty && summaryRequested)
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
                          _buildEmailSummarySections(summary, colors, t),
                          if (_formatQuotaRemainingLabel(summaryQuota, t).isNotEmpty) ...[
                            const SizedBox(height: 8),
                            Text(_formatQuotaRemainingLabel(summaryQuota, t),
                                style: TextStyle(color: colors.textMuted, fontSize: 11.5, fontWeight: FontWeight.w600)),
                          ],
                        ],
                      ),
                    ),
                  if (summaryError != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(summaryError!, style: TextStyle(color: colors.danger, fontSize: 12.5)),
                    ),
                  AppButton(
                    title: summaryType == 'ai_cached' ? t('Tóm tắt lại bằng AI', 'Re-summarize with AI') : t('Tóm tắt bằng AI', 'Summarize with AI'),
                    variant: AppButtonVariant.secondary,
                    icon: AppIcons.emailSummarize,
                    onPressed: _summarize,
                    loading: summarizing,
                  ),
                  const SizedBox(height: 10),
                  AppButton(
                    title: t('Chuyển tiếp', 'Forward'),
                    variant: AppButtonVariant.secondary,
                    onPressed: () => Navigator.pop(context, {
                      'action': 'forward',
                      // body/widget.email['body'] can differ: _loadBody()
                      // fetches the full content into this screen's own
                      // state, separate from the snippet-only map the list
                      // originally passed in -- use whichever is richer so
                      // the forwarded quote isn't just the list snippet.
                      'email': {
                        ...email,
                        if (body.isNotEmpty) 'body': body,
                      },
                    }),
                  ),
                  if (attachments.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Text(
                      '${t('ĐÍNH KÈM', 'ATTACHMENTS')} (${attachments.length})',
                      style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1),
                    ),
                    const SizedBox(height: 8),
                    ...attachments.map((attachment) {
                      final attachmentId = '${attachment['id']}';
                      final filename = (attachment['filename'] as String?) ?? t('Tệp đính kèm', 'Attachment');
                      final sizeLabel = _formatFileSize(attachment['size']);
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        decoration: BoxDecoration(
                          color: colors.panelSoft,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          children: [
                            Icon(Icons.attach_file, size: 18, color: colors.textMuted),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(filename, maxLines: 1, overflow: TextOverflow.ellipsis,
                                      style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13)),
                                  if (sizeLabel.isNotEmpty)
                                    Padding(
                                      padding: const EdgeInsets.only(top: 2),
                                      child: Text(sizeLabel, style: TextStyle(color: colors.textMuted, fontSize: 11.5)),
                                    ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            downloadingAttachmentId == attachmentId
                                ? SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: colors.primary))
                                : IconButton(
                                    icon: Icon(Icons.download_outlined, color: colors.primary, size: 20),
                                    tooltip: t('Tải xuống', 'Download'),
                                    onPressed: () => _downloadAttachment(attachment),
                                  ),
                          ],
                        ),
                      );
                    }),
                  ],
                  const SizedBox(height: 22),
                  Divider(color: colors.border),
                  const SizedBox(height: 18),
                  if (loadingBody)
                    const Padding(padding: EdgeInsets.symmetric(vertical: 40), child: Center(child: CircularProgressIndicator()))
                  else if (bodyError != null)
                    Text('${t('Không tải được nội dung', 'Could not load content')}: $bodyError', style: TextStyle(color: colors.danger, fontSize: 13))
                  else if (htmlHasText)
                    // HTML emails assume a white reading surface and often set
                    // their own inline background/text colors (which win over
                    // our style map, same as a real browser's cascade) --
                    // fighting that to force dark-mode text is unreliable, so
                    // this mirrors how Gmail/Outlook render email bodies: a
                    // fixed white card regardless of the app's theme.
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(14)),
                      child: Html(
                        data: htmlBody,
                        onLinkTap: (url, attributes, element) {
                          if (url != null) launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
                        },
                        style: {
                          'body': Style(
                            margin: Margins.zero,
                            padding: HtmlPaddings.zero,
                            color: const Color(0xFF1A1A1A),
                            fontSize: FontSize(14),
                            lineHeight: const LineHeight(1.6),
                          ),
                          'a': Style(color: colors.primary, textDecoration: TextDecoration.underline),
                        },
                      ),
                    )
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
