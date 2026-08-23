import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/client.dart';
import '../state/language_controller.dart';
import '../state/theme_controller.dart';
import '../widgets/app_button.dart';

class _ChatMessage {
  final String id;
  final String role;
  final String text;
  _ChatMessage({required this.id, required this.role, required this.text});
}

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

  @override
  Widget build(BuildContext context) {
    final colors = context.watch<ThemeController>().colors;
    final t = context.watch<LanguageController>().t;

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
                    onPressed: () => setState(() {
                      messages.clear();
                      sessionId = _createSessionId();
                    }),
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
