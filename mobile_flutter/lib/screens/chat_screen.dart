import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../state/workspace_controller.dart';
import '../widgets/app_button.dart';
import '../widgets/app_card.dart';

class _ChatMessage {
  final String id;
  final String role;
  final String text;
  _ChatMessage({required this.id, required this.role, required this.text});
}

const List<int> _kRetentionOptions = [30, 90, 180];

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<_ChatMessage> messages = [];
  final inputController = TextEditingController();
  final scrollController = ScrollController();
  String sessionId = '';
  bool loading = false;
  String? _lastWorkspaceId;

  @override
  void initState() {
    super.initState();
    sessionId = _createSessionId();
  }

  @override
  void dispose() {
    inputController.dispose();
    scrollController.dispose();
    super.dispose();
  }

  String _createSessionId() {
    final random = Random();
    return List.generate(16, (_) => random.nextInt(16).toRadixString(16)).join();
  }

  Future<void> _send() async {
    final text = inputController.text.trim();
    if (text.isEmpty || loading) return;
    setState(() {
      messages.add(_ChatMessage(id: 'u-${DateTime.now().millisecondsSinceEpoch}', role: 'user', text: text));
      inputController.clear();
      loading = true;
    });
    _scrollToEnd();
    try {
      final data = await apiPost('/chat/message', {
        'message': text,
        'mode': 'worker',
        'session_id': sessionId,
      });
      if (data is Map && data['session_id'] != null) sessionId = data['session_id'] as String;
      setState(() {
        messages.add(_ChatMessage(
          id: 'a-${DateTime.now().millisecondsSinceEpoch}',
          role: 'assistant',
          text: (data is Map ? data['response'] as String? : null) ?? 'Không có phản hồi.',
        ));
      });
    } catch (error) {
      setState(() {
        messages.add(_ChatMessage(id: 'e-${DateTime.now().millisecondsSinceEpoch}', role: 'assistant', text: 'Lỗi kết nối: $error'));
      });
    } finally {
      if (mounted) setState(() => loading = false);
      _scrollToEnd();
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (scrollController.hasClients) {
        scrollController.animateTo(scrollController.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  void _startNewChat() {
    setState(() {
      messages.clear();
      sessionId = _createSessionId();
    });
  }

  Future<void> _openSessions() async {
    final result = await showModalBottomSheet<dynamic>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => _ChatSessionsSheet(
        currentSessionId: sessionId,
        onCurrentSessionDeleted: _startNewChat,
      ),
    );
    if (!mounted || result == null) return;
    if (result == 'new') {
      _startNewChat();
      return;
    }
    if (result is Map<String, dynamic>) {
      await _openSession(result);
    }
  }

  Future<void> _openSession(Map<String, dynamic> session) async {
    final id = session['id'] as String?;
    if (id == null || id.isEmpty) return;
    setState(() => loading = true);
    try {
      final data = await apiGet('/chat/history?limit=100&session_id=${Uri.encodeComponent(id)}');
      if (!mounted) return;
      if (data is Map && data['expired'] == true) {
        _startNewChat();
        return;
      }
      final items = (data is Map && data['history'] is List)
          ? List<Map<String, dynamic>>.from(data['history'])
          : <Map<String, dynamic>>[];
      final loaded = <_ChatMessage>[];
      for (final item in items.reversed) {
        final userText = ((item['user_message'] as String?) ?? '').trim();
        final assistantText = ((item['assistant_response'] as String?) ?? '').trim();
        if (userText.isNotEmpty) loaded.add(_ChatMessage(id: '${item['id']}-u', role: 'user', text: userText));
        if (assistantText.isNotEmpty) loaded.add(_ChatMessage(id: '${item['id']}-a', role: 'assistant', text: assistantText));
      }
      setState(() {
        messages
          ..clear()
          ..addAll(loaded);
        sessionId = (data is Map ? data['session_id'] as String? : null) ?? id;
      });
      _scrollToEnd();
    } catch (_) {
      // keep the current chat visible if the requested session failed to load
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    // ChatScreen's State survives tab switches (MainShell keeps it alive in
    // an IndexedStack) and never reloads history from the server on its
    // own, so without this it would keep showing one workspace's messages
    // after the user switches to another -- a context-leak risk even though
    // the backend itself scopes every request by workspace_id correctly.
    final workspaceId = context.watch<WorkspaceController>().currentWorkspaceId;
    if (_lastWorkspaceId != null && _lastWorkspaceId != workspaceId) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _startNewChat();
      });
    }
    _lastWorkspaceId = workspaceId;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              decoration: BoxDecoration(color: colors.panel, border: Border(bottom: BorderSide(color: colors.border))),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('WORKER MODE', style: TextStyle(color: colors.primary, fontWeight: FontWeight.w700, fontSize: 10, letterSpacing: 1)),
                        Text('FlowMate Agent', style: TextStyle(color: colors.text, fontWeight: FontWeight.w800, fontSize: 20)),
                      ],
                    ),
                  ),
                  TextButton(
                    onPressed: sessionId.isEmpty ? null : _openSessions,
                    child: Text(t('Lịch sử', 'History'), style: TextStyle(color: colors.primary)),
                  ),
                  TextButton(
                    onPressed: sessionId.isEmpty ? null : _startNewChat,
                    child: Text(t('Chat mới', 'New chat'), style: TextStyle(color: colors.primary)),
                  ),
                ],
              ),
            ),
            Expanded(
              child: messages.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(30),
                        child: Text(
                          t('Giao việc để agent đọc email, kiểm tra lịch, tóm tắt công việc hoặc chuẩn bị lịch hẹn.',
                              'Ask the agent to read email, check your schedule, summarize work, or prep a meeting.'),
                          textAlign: TextAlign.center,
                          style: TextStyle(color: colors.textMuted),
                        ),
                      ),
                    )
                  : ListView.builder(
                      controller: scrollController,
                      padding: const EdgeInsets.all(16),
                      itemCount: messages.length,
                      itemBuilder: (context, index) {
                        final m = messages[index];
                        final isUser = m.role == 'user';
                        return Align(
                          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                          child: Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                            decoration: BoxDecoration(
                              color: isUser ? colors.primary : colors.panelSoft,
                              borderRadius: BorderRadius.only(
                                topLeft: const Radius.circular(12),
                                topRight: const Radius.circular(12),
                                bottomLeft: Radius.circular(isUser ? 12 : 4),
                                bottomRight: Radius.circular(isUser ? 4 : 12),
                              ),
                              border: isUser ? null : Border.all(color: colors.border),
                            ),
                            child: Text(m.text, style: TextStyle(color: isUser ? Colors.white : colors.text, fontSize: 13, height: 1.4)),
                          ),
                        );
                      },
                    ),
            ),
            if (loading) Padding(padding: const EdgeInsets.only(bottom: 8), child: CircularProgressIndicator(color: colors.primary, strokeWidth: 2)),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: colors.panel, border: Border(top: BorderSide(color: colors.border))),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: inputController,
                      minLines: 1,
                      maxLines: 4,
                      style: TextStyle(color: colors.text, fontSize: 13),
                      decoration: InputDecoration(
                        hintText: t('Nhập tin nhắn...', 'Type a message...'),
                        hintStyle: TextStyle(color: colors.inputPlaceholder),
                        filled: true,
                        fillColor: colors.panelSoft,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: colors.border)),
                        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: colors.border)),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: colors.primary)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  IntrinsicWidth(
                    child: AppButton(title: t('Gửi', 'Send'), onPressed: loading ? null : _send, loading: false),
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

/// Lists saved chat sessions (GET /chat/sessions) and lets the user open,
/// rename, or delete one. Deleting the currently open session notifies the
/// parent via [onCurrentSessionDeleted] so it can reset to a fresh chat
/// while this sheet stays open, mirroring mobile/src/screens/ChatScreen.js's
/// deleteSession behavior. Tapping a row or "Chat mới" pops the sheet with
/// a result the parent interprets (a session map, or the string 'new').
class _ChatSessionsSheet extends StatefulWidget {
  final String currentSessionId;
  final VoidCallback onCurrentSessionDeleted;

  const _ChatSessionsSheet({
    required this.currentSessionId,
    required this.onCurrentSessionDeleted,
  });

  @override
  State<_ChatSessionsSheet> createState() => _ChatSessionsSheetState();
}

class _ChatSessionsSheetState extends State<_ChatSessionsSheet> {
  List<Map<String, dynamic>> sessions = [];
  bool loading = true;
  String editingId = '';
  int editingRetention = 90;
  bool saving = false;
  final titleController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    titleController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await apiGet('/chat/sessions?limit=40');
      final list = (data is Map && data['sessions'] is List)
          ? List<Map<String, dynamic>>.from(data['sessions'])
          : <Map<String, dynamic>>[];
      if (mounted) setState(() => sessions = list);
    } catch (_) {
      // keep whatever we had; a transient failure shouldn't blank the sheet
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  void _startEdit(Map<String, dynamic> session) {
    setState(() {
      editingId = session['id'] as String? ?? '';
      titleController.text = (session['title'] as String?) ?? '';
      editingRetention = (session['retention_days'] as num?)?.toInt() ?? 90;
    });
  }

  void _cancelEdit() => setState(() => editingId = '');

  Future<void> _saveEdit() async {
    if (editingId.isEmpty) return;
    final t = context.read<LanguageController>().t;
    final id = editingId;
    final title = titleController.text.trim();
    setState(() => saving = true);
    try {
      await apiPatch('/chat/sessions/${Uri.encodeComponent(id)}', {
        'title': title,
        'retention_days': editingRetention,
      });
      if (mounted) {
        setState(() {
          sessions = sessions.map((item) {
            if (item['id'] != id) return item;
            return {...item, 'title': title, 'retention_days': editingRetention};
          }).toList();
          editingId = '';
        });
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không lưu được đoạn chat', 'Could not save this chat'))),
        );
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _delete(Map<String, dynamic> session) async {
    final t = context.read<LanguageController>().t;
    final id = session['id'] as String? ?? '';
    if (id.isEmpty) return;
    final title = session['title'] as String? ?? '';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(t('Xóa đoạn chat?', 'Delete this chat?')),
        content: Text(title.isNotEmpty ? title : t('Đoạn chat này sẽ bị xóa ngay.', 'This chat will be deleted immediately.')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(t('Hủy', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(t('Xóa', 'Delete'))),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await apiDelete('/chat/sessions/${Uri.encodeComponent(id)}');
      if (!mounted) return;
      setState(() => sessions = sessions.where((item) => item['id'] != id).toList());
      if (id == widget.currentSessionId) widget.onCurrentSessionDeleted();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(t('Không xóa được đoạn chat', 'Could not delete this chat'))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Container(
      constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.82),
      padding: EdgeInsets.fromLTRB(20, 18, 20, MediaQuery.of(context).viewInsets.bottom + 20),
      decoration: BoxDecoration(color: colors.panel, borderRadius: const BorderRadius.vertical(top: Radius.circular(24))),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  t('Đoạn chat gần đây', 'Recent chats'),
                  style: TextStyle(color: colors.text, fontWeight: FontWeight.w700, fontSize: 17),
                ),
              ),
              IconButton(
                onPressed: () => Navigator.of(context).pop(),
                icon: Icon(Icons.close, color: colors.textMuted),
              ),
            ],
          ),
          Flexible(
            child: loading
                ? const Padding(padding: EdgeInsets.symmetric(vertical: 24), child: Center(child: CircularProgressIndicator()))
                : sessions.isEmpty
                    ? AppEmptyState(
                        icon: Icons.chat_bubble_outline,
                        title: t('Chưa có đoạn chat', 'No chats yet'),
                        detail: t('Các cuộc trò chuyện mới sẽ xuất hiện ở đây và trên web.', 'New conversations will appear here and on the web.'),
                      )
                    : ListView.separated(
                        shrinkWrap: true,
                        itemCount: sessions.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (context, index) {
                          final session = sessions[index];
                          final id = session['id'] as String? ?? '';
                          if (editingId == id) {
                            return _SessionEditBox(
                              titleController: titleController,
                              retention: editingRetention,
                              saving: saving,
                              onRetentionChanged: (value) => setState(() => editingRetention = value),
                              onSave: _saveEdit,
                              onCancel: _cancelEdit,
                            );
                          }
                          final isActive = id == widget.currentSessionId;
                          final title = (session['title'] as String?)?.trim();
                          final meta = (session['updated_at'] as String?)
                              ?? (session['created_at'] as String?)
                              ?? t('${session['retention_days'] ?? 90} ngày lưu', '${session['retention_days'] ?? 90} day retention');
                          return Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: isActive ? colors.primarySoft : colors.panelSoft,
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: isActive ? colors.primary : colors.border),
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: InkWell(
                                    onTap: () => Navigator.of(context).pop(session),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          title?.isNotEmpty == true ? title! : t('Đoạn chat', 'Chat'),
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: TextStyle(color: colors.text, fontWeight: FontWeight.w600, fontSize: 13),
                                        ),
                                        const SizedBox(height: 3),
                                        Text(
                                          meta,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: TextStyle(color: colors.textMuted, fontSize: 10),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                                TextButton(
                                  onPressed: () => _startEdit(session),
                                  child: Text(t('Sửa', 'Edit'), style: TextStyle(color: colors.primary, fontSize: 12)),
                                ),
                                TextButton(
                                  onPressed: () => _delete(session),
                                  child: Text(t('Xóa', 'Delete'), style: TextStyle(color: colors.danger, fontSize: 12)),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
          ),
          const SizedBox(height: 12),
          AppButton(
            title: t('Bắt đầu chat mới', 'Start a new chat'),
            variant: AppButtonVariant.secondary,
            onPressed: () => Navigator.of(context).pop('new'),
          ),
        ],
      ),
    );
  }
}

class _SessionEditBox extends StatelessWidget {
  final TextEditingController titleController;
  final int retention;
  final bool saving;
  final ValueChanged<int> onRetentionChanged;
  final VoidCallback onSave;
  final VoidCallback onCancel;

  const _SessionEditBox({
    required this.titleController,
    required this.retention,
    required this.saving,
    required this.onRetentionChanged,
    required this.onSave,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.panelSoft,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.primary),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AppField(label: t('Tên đoạn chat', 'Chat name'), controller: titleController, hint: t('Đoạn chat', 'Chat')),
          Text(t('Lưu trữ', 'Retention'), style: TextStyle(color: colors.textMuted, fontWeight: FontWeight.w600, fontSize: 12)),
          const SizedBox(height: 6),
          Row(
            children: _kRetentionOptions.map((days) {
              final active = days == retention;
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: GestureDetector(
                    onTap: () => onRetentionChanged(days),
                    child: Container(
                      alignment: Alignment.center,
                      padding: const EdgeInsets.symmetric(vertical: 9),
                      decoration: BoxDecoration(
                        color: active ? colors.primary : colors.panel,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: active ? colors.primary : colors.border),
                      ),
                      child: Text(
                        t('$days ngày', '$days days'),
                        style: TextStyle(color: active ? Colors.white : colors.textMuted, fontWeight: FontWeight.w600, fontSize: 11.5),
                      ),
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(child: AppButton(title: t('Lưu', 'Save'), onPressed: onSave, loading: saving)),
              const SizedBox(width: 8),
              Expanded(child: AppButton(title: t('Hủy', 'Cancel'), variant: AppButtonVariant.secondary, onPressed: saving ? null : onCancel)),
            ],
          ),
        ],
      ),
    );
  }
}
