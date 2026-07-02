"""Single source of truth for every backend capability ("tool") Bob can
execute through chat.

Three things read from this catalog instead of hardcoding their own copy:
1. IntentOrchestrator's AI classification prompt (the list of valid
   "intent" values the model is allowed to return).
2. The intent_pattern_cache safety rule (only intents that always show a
   suggestion/confirmation before writing are safe to cache -- see
   CACHEABLE_INTENTS).
3. FreeformChatAgent's "I can't do that yet" fallback message, which lists
   what Bob actually supports instead of silently pretending to help.

Adding a new capability means adding one Tool entry here, not touching
prompt text in multiple files.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    name: str
    # Terse, accent-stripped Vietnamese -- matches the style the AI
    # classification prompt already used, kept as-is for behavior parity.
    description: str
    # True => must go through propose -> explicit user confirmation ->
    # apply before writing anything (ChatContext.action_confirm gate).
    is_write: bool
    # True => safe for intent_pattern_cache to short-circuit the AI call.
    # A tool only qualifies once every code path that can resolve to it
    # always shows a suggestion/confirmation before writing -- a wrong
    # cache hit can then only ever produce a rejectable suggestion, never
    # a silent wrong write.
    cacheable: bool = False
    # Short, accented Vietnamese label for user-facing capability lists.
    user_label: str = ""


CATALOG = {
    "schedule.create": Tool(
        name="schedule.create",
        description="muon tao lich hen/su kien/nhac nho moi",
        is_write=True,
        cacheable=True,
        user_label="Tạo lịch hẹn mới",
    ),
    "schedule.update": Tool(
        name="schedule.update",
        description=(
            "muon doi/sua thoi gian hoac thong tin cua lich hen DA CO san "
            "(vi du 'doi gio hop voi sep', 'chuyen lich kham rang sang ngay khac')"
        ),
        is_write=True,
        cacheable=True,
        user_label="Sửa lịch hẹn đã có",
    ),
    "schedule.delete": Tool(
        name="schedule.delete",
        description=(
            "muon xoa/huy lich hen DA CO san "
            "(vi du 'xoa lich hop ngay mai', 'huy cuoc hen voi khach')"
        ),
        is_write=True,
        cacheable=True,
        user_label="Xóa lịch hẹn",
    ),
    "schedule.list": Tool(
        name="schedule.list",
        description="muon xem lich/su kien da co",
        is_write=False,
        user_label="Xem lịch / sự kiện",
    ),
    "schedule.suggest_plan": Tool(
        name="schedule.suggest_plan",
        description=(
            "liet ke nhieu hoat dong va muon AI XEP GIO/GOI Y LICH cu the cho tung hoat dong do "
            "(vi du co tu 'sap xep lich', 'goi y lich', 'xep gium lich', 'suggest a schedule', "
            "'plan my day') -- KHAC voi checklist.create vi nguoi dung muon ket qua la LICH co "
            "khung gio, khong phai danh sach viec don thuan. Neu cau co ca tu 'checklist' LAN tu "
            "'lich'/'sap xep lich', uu tien y dinh ro rang hon trong cau (thuong la lich neu "
            "nguoi dung noi ro 'goi y lich'/'sap xep lich')"
        ),
        # Never writes by itself -- only ever proposes time slots, applied
        # through the existing /schedule/plan-day/apply endpoint.
        is_write=False,
        cacheable=True,
        user_label="Gợi ý khung giờ cho các hoạt động trong ngày",
    ),
    "email.latest_summary": Tool(
        name="email.latest_summary",
        description="muon tom tat (cac) email moi nhat trong hop thu",
        is_write=False,
        user_label="Tóm tắt email mới nhất",
    ),
    "email.search": Tool(
        name="email.search",
        description="muon tim/xem email theo tu khoa hoac nguoi gui",
        is_write=False,
        user_label="Tìm email theo từ khóa / người gửi",
    ),
    "email.mark_read": Tool(
        name="email.mark_read",
        description="muon danh dau (cac) email DA DOC (vi du 'danh dau da xem email tu chi Lan')",
        is_write=True,
        cacheable=True,
        user_label="Đánh dấu email đã đọc",
    ),
    "email.mark_unread": Tool(
        name="email.mark_unread",
        description="muon danh dau (cac) email CHUA DOC (vi du 'danh dau email do la chua xem')",
        is_write=True,
        cacheable=True,
        user_label="Đánh dấu email chưa đọc",
    ),
    "history.list": Tool(
        name="history.list",
        description="muon xem lai lich su hoat dong DA LAM trong qua khu",
        is_write=False,
        user_label="Xem lịch sử hoạt động",
    ),
    "settings.update_mode": Tool(
        name="settings.update_mode",
        description=(
            "muon doi che do lam viec (student, worker, freelancer, creator, business, mentor, teacher)"
        ),
        is_write=True,
        cacheable=True,
        user_label="Đổi chế độ làm việc",
    ),
    "checklist.create": Tool(
        name="checklist.create",
        description=(
            "liet ke nhieu viec/hoat dong SAP lam va muon dua vao checklist/to-do DON GIAN, KHONG "
            "can gio cu the cho tung viec (vi du 'hom nay co cac hoat dong nhu X, Y, Z, dua vao "
            "checklist giup minh') -- KHAC voi history.list vi day la viec sap toi, khong phai "
            "viec da lam"
        ),
        is_write=True,
        cacheable=True,
        user_label="Thêm việc vào checklist",
    ),
}

TOOL_NAMES = tuple(CATALOG.keys())
WRITE_TOOL_NAMES = frozenset(name for name, tool in CATALOG.items() if tool.is_write)
CACHEABLE_INTENTS = frozenset(name for name, tool in CATALOG.items() if tool.cacheable)


def build_catalog_prompt_block():
    """Render the "valid intents" bullet list for the AI classification
    prompt -- same wording/order the prompt used to hardcode."""
    lines = [f"- {tool.name}: {tool.description}" for tool in CATALOG.values()]
    lines.append("- chat.freeform: tat ca truong hop khac (hoi dap thong thuong)")
    return "\n".join(lines)


def build_capabilities_summary():
    """User-facing bullet list of what Bob can currently do, shown when a
    request doesn't match any tool in the catalog."""
    return "\n".join(f"- {tool.user_label}" for tool in CATALOG.values())


AGENT_CAPABILITIES = [
    {
        'id': 'overview.daily_brief',
        'label': 'Tổng hợp ngày',
        'description': 'Gom email, lịch, deadline, task và checklist thành bức tranh ưu tiên trong ngày.',
        'workspace_sources': ['email', 'calendar', 'history'],
        'refresh_targets': ['overview', 'email', 'schedule', 'history'],
        'confirmation_required': False,
    },
    {
        'id': 'email.inbox_triage',
        'label': 'Phân loại email',
        'description': 'Đọc inbox Gmail/Outlook đã kết nối, tìm email quan trọng, email chưa đọc, email cần phản hồi.',
        'workspace_sources': ['email'],
        'refresh_targets': ['email', 'overview', 'history'],
        'confirmation_required': False,
    },
    {
        'id': 'email.summary_reply',
        'label': 'Tóm tắt và soạn trả lời',
        'description': 'Tóm tắt nội dung email, tạo nháp trả lời lịch sự và chỉ gửi email khi người dùng xác nhận.',
        'workspace_sources': ['email'],
        'refresh_targets': ['email', 'history'],
        'confirmation_required': True,
    },
    {
        'id': 'email.meeting_scan',
        'label': 'Quét lịch hẹn từ email',
        'description': 'Phát hiện email có tín hiệu họp/lịch hẹn và biến thành gợi ý lịch cần xác nhận.',
        'workspace_sources': ['email', 'calendar'],
        'refresh_targets': ['email', 'schedule', 'overview', 'history'],
        'confirmation_required': True,
    },
    {
        'id': 'schedule.manage',
        'label': 'Quản lý lịch',
        'description': 'Tạo, sửa, hủy, xóa lịch FlowMate và đồng bộ Google/Outlook Calendar khi có kết nối.',
        'workspace_sources': ['calendar'],
        'refresh_targets': ['schedule', 'calendar', 'overview', 'history'],
        'confirmation_required': True,
    },
    {
        'id': 'calendar.sync',
        'label': 'Đồng bộ calendar',
        'description': 'Đọc lịch Google/Outlook, hợp nhất với lịch FlowMate và tránh hiển thị trùng sự kiện.',
        'workspace_sources': ['calendar'],
        'refresh_targets': ['schedule', 'calendar', 'overview'],
        'confirmation_required': False,
    },
    {
        'id': 'history.audit',
        'label': 'Tra cứu lịch sử',
        'description': 'Tóm tắt các lần chat, email, lịch và thao tác agent đã thực hiện.',
        'workspace_sources': ['history'],
        'refresh_targets': ['history'],
        'confirmation_required': False,
    },
    {
        'id': 'settings.profile_mode',
        'label': 'Hồ sơ và chế độ làm việc',
        'description': 'Đọc hồ sơ, kết nối dịch vụ, đổi chế độ làm việc và áp dụng cùng một mode cho web/mobile.',
        'workspace_sources': ['profile'],
        'refresh_targets': ['settings', 'profile', 'history'],
        'confirmation_required': True,
    },
    {
        'id': 'provider.status',
        'label': 'Trạng thái AI provider',
        'description': 'Theo dõi provider AI, demo mode và fallback để người dùng biết phản hồi đến từ đâu.',
        'workspace_sources': ['profile'],
        'refresh_targets': ['providers', 'settings'],
        'confirmation_required': False,
    },
    {
        'id': 'knowledge.lookup',
        'label': 'Tra cứu kiến thức',
        'description': 'Tìm đoạn kiến thức FlowMate/mã nguồn mở liên quan (TF-IDF, không cần model embedding) để trả lời có căn cứ.',
        'workspace_sources': ['knowledge'],
        'refresh_targets': [],
        'confirmation_required': False,
    },
    {
        'id': 'internet.research',
        'label': 'Tra cứu Internet',
        'description': 'Tự tra cứu web công khai khi prompt cần thông tin mới/nguồn ngoài, đưa URL nguồn vào câu trả lời; chỉ lưu long-term lesson đã lọc khi research có giá trị học hỏi/quy trình.',
        'workspace_sources': ['internet'],
        'refresh_targets': [],
        'confirmation_required': False,
    },
    {
        'id': 'mentor.learning',
        'label': 'Học từ AI mentor',
        'description': 'Chạy nền có quota để hỏi provider như ChatGPT/OpenAI, Gemini, Claude hoặc OpenRouter critique cách Bob xử lý, rồi chỉ lưu bài học quy trình đã lọc/dedupe vào knowledge riêng của user.',
        'workspace_sources': ['knowledge'],
        'refresh_targets': [],
        'confirmation_required': False,
    },
    {
        'id': 'time.current',
        'label': 'Đọc thời gian hiện tại',
        'description': 'Trả lời giờ/ngày hiện tại bằng đồng hồ backend theo múi giờ Việt Nam UTC+7, không để AI tự đoán.',
        'workspace_sources': ['time'],
        'refresh_targets': [],
        'confirmation_required': False,
    },
]

AGENT_SYNC_TARGETS = {
    'overview': 'Tải lại tổng hợp ngày và checklist.',
    'email': 'Tải lại inbox, cache email và gợi ý họp.',
    'schedule': 'Tải lại lịch FlowMate, Google/Outlook Calendar và tuần hiện tại.',
    'calendar': 'Tải lại dữ liệu calendar hợp nhất.',
    'history': 'Tải lại lịch sử hoạt động/chat.',
    'settings': 'Tải lại cài đặt và kết nối dịch vụ.',
    'profile': 'Tải lại hồ sơ và mode người dùng.',
    'providers': 'Tải lại trạng thái AI provider.',
    'chat': 'Tải lại phiên chat hiện tại.',
}

AGENT_CONFIRMATION_REQUIRED = [
    'send_email',
    'create_schedule',
    'update_schedule',
    'delete_schedule',
    'change_user_mode',
    'disconnect_account',
    'clear_history',
]
