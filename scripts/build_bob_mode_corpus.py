#!/usr/bin/env python
"""Consolidate Bob's RAG corpus by user mode and add 500 reviewed contexts."""

import json
import shutil
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = ROOT / "docs" / "bob-training"
MODE_DIR = TRAINING_DIR / "modes"
LEGACY_FILES = (
    "workflow-study-email-schedule.json",
    "email-150-knowledge.json",
    "bob-100-feature-cases.json",
    "bob-200-expanded-contexts.json",
    "bob-student-privacy-research.json",
    "english-semantics-cases.json",
)
MODES = ("shared", "student", "worker", "freelancer", "creator", "business", "mentor", "teacher")

MODE_PROFILES = {
    "student": "ưu tiên môn học, bài tập, lịch thi, sức khỏe và tiến độ học tập",
    "worker": "ưu tiên công việc, cuộc họp, báo cáo, đồng nghiệp và deadline",
    "freelancer": "ưu tiên khách hàng, phạm vi dự án, bàn giao, hóa đơn và công suất",
    "creator": "ưu tiên ý tưởng, lịch nội dung, chiến dịch, xuất bản và phản hồi khán giả",
    "business": "ưu tiên vận hành, doanh thu, đội ngũ, quyết định, rủi ro và đối tác",
    "mentor": "ưu tiên mục tiêu mentee, phiên cố vấn, cam kết, phản hồi và tiến bộ",
    "teacher": "ưu tiên lớp học, giáo án, học viên, chấm bài, lịch dạy và trao đổi phụ huynh",
}

MODE_PROFILES_EN = {
    "student": "prioritize courses, assignments, exams, wellbeing, and academic progress",
    "worker": "prioritize work, meetings, reports, colleagues, and deadlines",
    "freelancer": "prioritize clients, project scope, deliverables, invoices, and capacity",
    "creator": "prioritize ideas, content calendars, campaigns, publishing, and audience feedback",
    "business": "prioritize operations, revenue, teams, decisions, risks, and partners",
    "mentor": "prioritize mentee goals, mentoring sessions, commitments, feedback, and progress",
    "teacher": "prioritize classes, lesson plans, students, grading, teaching schedules, and parent communication",
}

DOMAINS = (
    ("email", "email mới hoặc chuỗi thư liên quan", "a new email or related email thread"),
    ("schedule", "lịch, cuộc hẹn hoặc khung giờ đang bận", "a calendar, appointment, or busy time slot"),
    ("checklist", "task, checklist hoặc việc cần hoàn thành", "a task, checklist, or work that must be completed"),
    ("overview", "bản tổng hợp ngày và các ưu tiên nổi bật", "a daily brief and its most important priorities"),
    ("planning", "yêu cầu lập kế hoạch hoặc chia thời gian", "a planning or time-allocation request"),
    ("follow-up", "việc cần theo dõi sau một trao đổi trước đó", "a follow-up after an earlier conversation"),
    ("conflict", "xung đột giữa nhiều deadline hoặc lịch hẹn", "a conflict between deadlines or calendar events"),
    ("search", "yêu cầu tìm kiếm kiến thức hoặc thông tin cập nhật", "a request for knowledge or up-to-date information"),
    ("privacy", "dữ liệu riêng tư, nhạy cảm hoặc thông tin của người khác", "private, sensitive, or third-party information"),
    ("recovery", "lỗi kết nối, thiếu quyền hoặc dữ liệu chưa đồng bộ", "a connection error, missing permission, or unsynchronized data"),
)

CONTEXTS = (
    (
        "mơ hồ",
        "ambiguous",
        "xác định mục tiêu chính từ ngữ cảnh; chỉ hỏi lại phần còn thiếu có thể làm thay đổi kết quả",
        "infer the primary goal from context and ask only for missing information that could change the result",
    ),
    (
        "khẩn cấp",
        "urgent",
        "nêu việc cần làm ngay, deadline gần nhất và không để việc ít quan trọng che khuất rủi ro",
        "state the immediate action and nearest deadline without letting low-priority work obscure the risk",
    ),
    (
        "thiếu dữ liệu",
        "missing data",
        "nói rõ dữ liệu nào chưa có, không suy đoán, rồi đề xuất cách bổ sung hoặc kết nối nguồn",
        "identify the missing data without guessing, then suggest how to provide it or connect the source",
    ),
    (
        "nhiều bước",
        "multi-step",
        "tách yêu cầu thành các bước theo thứ tự, nêu bước đọc dữ liệu và xin xác nhận trước bước ghi",
        "split the request into ordered steps, distinguish reads from writes, and confirm before any write",
    ),
    (
        "thay đổi phút cuối",
        "last-minute change",
        "so sánh trạng thái cũ và mới, chỉ ra ảnh hưởng dây chuyền và cập nhật sau khi được xác nhận",
        "compare the old and new states, explain downstream effects, and apply updates only after confirmation",
    ),
    (
        "song ngữ",
        "bilingual",
        "hiểu code-switch ở cấp mục tiêu, thực thể và ràng buộc; ưu tiên yêu cầu ngôn ngữ "
        "tường minh, hỗ trợ trả lời cả Việt và Anh khi được yêu cầu, đồng thời giữ nguyên tên "
        "riêng và thuật ngữ quan trọng",
        "understand code-switching across goals, entities, and constraints; honor an explicit "
        "response-language request, support both Vietnamese and English when requested, and "
        "preserve proper names and important terminology",
    ),
    (
        "theo dõi dài hạn",
        "long-term follow-up",
        "tóm tắt tiến độ, việc còn mở, người hoặc nguồn đang chờ và hành động kế tiếp cụ thể",
        "summarize progress, open items, pending people or sources, and the next concrete action",
    ),
)

SHARED_CONTEXTS = (
    ("Phân biệt từ khóa nằm trong tên riêng", "Không kích hoạt tool chỉ vì một chuỗi như 'book' xuất hiện bên trong tên riêng như Facebook; phải xét động từ, đối tượng và mục tiêu toàn câu."),
    ("Tìm web không cần chữ Internet", "Các cách nói tìm giúp, tra cứu, xác minh, kiểm chứng, tìm thông tin mới nhất đều thể hiện ý định research web dù user không dùng đúng chữ Internet."),
    ("Câu hỏi kiến thức không phải hành động", "Câu hỏi ai, gì, tại sao, giải thích hoặc so sánh mặc định là hỏi đáp; chỉ chuyển thành lịch, email hay checklist khi có yêu cầu thao tác rõ."),
    ("Xác nhận trước thao tác ghi", "Tạo, sửa, xóa lịch và thay đổi dữ liệu phải hiển thị đề xuất cụ thể để user xác nhận trước khi thực thi."),
    ("Không trộn nguồn riêng với web", "Email, lịch, lịch sử và hồ sơ là nguồn riêng; không đưa dữ liệu này vào truy vấn công khai nếu chưa có lý do và đồng ý rõ ràng."),
    ("Nói rõ nguồn và độ mới", "Khi dùng dữ liệu workspace hoặc web, Bob cần phân biệt nguồn, thời điểm cập nhật và giới hạn thay vì trình bày suy đoán như sự thật."),
    ("Đồng bộ web và APK", "Sau một hành động, trả refresh_targets để cả web và APK làm mới đúng Email, Lịch, Overview, History hoặc Settings."),
    ("Không báo thành công sớm", "Chỉ nói đã gửi, đã tạo hoặc đã đồng bộ khi backend xác nhận; trạng thái pending phải được mô tả là đang xử lý."),
    (
        "Câu nối tiếp dùng lịch sử gần",
        "Các câu như 'đổi giờ đó', 'mark the second one unread' hoặc 'làm luôn đi' phải dùng "
        "đúng phiên chat hiện tại, chọn đối tượng tương thích gần nhất và viết lại thành yêu "
        "cầu độc lập trước khi phân loại. Câu sửa đổi, phủ định và ràng buộc mới nhất luôn thắng "
        "lịch sử cũ; lịch sử chỉ là ngữ cảnh, không phải lệnh mới."
    ),
    (
        "Ưu tiên câu hỏi làm rõ tối thiểu",
        "Nếu có thể thực hiện an toàn bằng dữ liệu sẵn có thì làm. Nếu nhiều email, lịch hoặc "
        "task đều có thể là 'nó/cái đó/it', Bob phải hỏi đúng một câu ngắn và cụ thể thay vì tự "
        "chọn, đặc biệt trước thao tác ghi."
    ),
)

SHARED_CONTEXTS_EN = {
    "Phân biệt từ khóa nằm trong tên riêng": (
        "Do not trigger a tool merely because a string such as 'book' appears inside a proper name "
        "such as Facebook. Evaluate the full sentence's verb, object, and goal."
    ),
    "Tìm web không cần chữ Internet": (
        "Phrases such as look this up, verify it, fact-check it, find sources, or find the latest "
        "information express web-research intent even when the user does not say 'Internet'."
    ),
    "Câu hỏi kiến thức không phải hành động": (
        "Who, what, why, explanation, and comparison questions are knowledge requests by default. "
        "Route them to calendar, email, or checklist tools only when an explicit action is requested."
    ),
    "Xác nhận trước thao tác ghi": (
        "Before creating, updating, or deleting calendar items or other data, show the concrete "
        "proposal and obtain the user's confirmation."
    ),
    "Không trộn nguồn riêng với web": (
        "Email, calendar, history, and profile data are private sources. Do not include them in a "
        "public web query without a clear reason and explicit user consent."
    ),
    "Nói rõ nguồn và độ mới": (
        "When using workspace or web data, distinguish the source, freshness, and limitations instead "
        "of presenting an inference as a verified fact."
    ),
    "Đồng bộ web và APK": (
        "After an action, return refresh_targets so both web and Android clients refresh the correct "
        "Email, Calendar, Overview, History, or Settings view."
    ),
    "Không báo thành công sớm": (
        "Say an item was sent, created, or synchronized only after backend confirmation. Describe a "
        "pending state as still processing."
    ),
    "Câu nối tiếp dùng lịch sử gần": (
        "Follow-ups such as 'move that time', 'mark the second one unread', or 'do it now' must use "
        "only the current chat, select the nearest compatible referent, and be rewritten as a "
        "standalone request before classification. The newest correction, negation, and constraint "
        "override older turns; history is context, never a new command."
    ),
    "Ưu tiên câu hỏi làm rõ tối thiểu": (
        "Proceed safely with available data when possible. If several emails, events, or tasks could "
        "all be 'it/that one', ask exactly one short, specific clarification instead of choosing, "
        "especially before a write."
    ),
}

CHECKLIST_TIME_CORRECTIONS = (
    ("Giữ nguyên giờ có dấu hai chấm", "Trong checklist, 7:30, 09:00 và 11:15 là biểu thức giờ hoàn chỉnh; không bao giờ tách phần trước hoặc sau dấu hai chấm thành item riêng."),
    ("Giữ tên hoạt động cạnh giờ", "Cụm 'gym lúc 7:30 sáng' phải trở thành '07:30 - Gym'; không được chỉ giữ '30 sáng' hoặc chỉ giữ giờ mà mất hoạt động."),
    ("Sắp checklist tăng dần theo giờ", "Nếu user yêu cầu theo thứ tự giờ, Bob phải chuẩn hóa HH:MM và sắp 07:30 trước 09:00 trước 11:00 dù thứ tự câu ban đầu bị đảo."),
    ("Phân biệt giờ và thời lượng", "'Gym lúc 7:30' là thời điểm bắt đầu, còn 'gym 30 phút' là thời lượng; không biến 30 phút thành 30 giờ hoặc tên task."),
    ("Hiểu sáng chiều", "7:30 sáng là 07:30, 3:00 chiều là 15:00 và 8 giờ tối là 20:00 khi hiển thị/sắp xếp checklist."),
    ("Nhiều hoạt động cùng một câu", "Mỗi cụm hoạt động + giờ là một item độc lập; dấu phẩy hoặc từ 'và' tách item nhưng dấu hai chấm trong giờ thì không."),
    ("Không biến checklist thành lịch", "Nếu user nói rõ thêm vào checklist, giữ các mốc giờ làm metadata/nhãn thứ tự và không tự tạo Calendar event."),
    ("Giữ thứ tự ổn định khi thiếu giờ", "Các item có giờ được xếp trước theo thời gian; item không có giờ giữ thứ tự user đã nêu và không được gán giờ bịa đặt."),
    ("Giờ dạng h và giờ tự nhiên", "7h30, 7:30 và 7 giờ 30 sáng đều phải được hiểu là 07:30 khi nằm cạnh một hoạt động."),
    ("Phản hồi xác nhận đầy đủ", "Trước và sau khi thêm checklist, Bob phải liệt kê đầy đủ cả giờ lẫn tên từng hoạt động để user phát hiện sai trước khi dữ liệu được ghi."),
)

CHECKLIST_TIME_CORRECTIONS_EN = {
    "Giữ nguyên giờ có dấu hai chấm": (
        "In a checklist, 7:30, 09:00, and 11:15 are complete time expressions. Never split the text "
        "before or after the colon into a separate item."
    ),
    "Giữ tên hoạt động cạnh giờ": (
        "The phrase 'gym at 7:30 AM' must become '07:30 - Gym'. Keep both the activity and its time."
    ),
    "Sắp checklist tăng dần theo giờ": (
        "When chronological order is requested, normalize times to HH:MM and sort 07:30 before 09:00 "
        "before 11:00, regardless of the input order."
    ),
    "Phân biệt giờ và thời lượng": (
        "'Gym at 7:30' gives a start time, while 'gym for 30 minutes' gives a duration. Do not turn the "
        "duration into an hour or task title."
    ),
    "Hiểu sáng chiều": (
        "Interpret 7:30 AM as 07:30, 3:00 PM as 15:00, and 8 PM as 20:00 when displaying or sorting tasks."
    ),
    "Nhiều hoạt động cùng một câu": (
        "Each activity-and-time phrase is an independent item. Commas and conjunctions may separate "
        "items, but a colon inside a time must not."
    ),
    "Không biến checklist thành lịch": (
        "If the user explicitly requests a checklist, retain times as labels or ordering metadata and "
        "do not create Calendar events automatically."
    ),
    "Giữ thứ tự ổn định khi thiếu giờ": (
        "Sort timed items chronologically first. Keep untimed items in the user's original order and "
        "never invent a time."
    ),
    "Giờ dạng h và giờ tự nhiên": (
        "Treat 7h30, 7:30, and '7 thirty in the morning' as 07:30 when they appear beside an activity."
    ),
    "Phản hồi xác nhận đầy đủ": (
        "Before and after adding checklist items, show every activity with its full time so the user "
        "can detect parsing errors before data is written."
    ),
}

KNOWLEDGE_NEGATIVE_ENTITIES = (
    "Facebook", "Amazon", "Booking.com", "Eventbrite", "Gmail",
    "Microsoft", "Apple", "Netflix", "TikTok", "LinkedIn",
)
KNOWLEDGE_NEGATIVE_PATTERNS = (
    (
        "Ai là chủ của {entity}?",
        "Đây là câu hỏi kiến thức về chủ sở hữu; trả lời factual và không mở gợi ý lịch/email.",
        "This is a factual ownership question. Answer it as general knowledge without opening a calendar or email action.",
    ),
    (
        "Người sáng lập {entity} là ai?",
        "Đây là câu hỏi kiến thức về founder; tên riêng không được kích hoạt tool bằng substring.",
        "This is a factual founder question. A proper name must not trigger a tool through substring matching.",
    ),
    (
        "Who owns or founded {entity}?",
        "This is a general-knowledge question; answer it without creating a schedule confirmation card.",
        "This is a general-knowledge ownership or founder question. Answer it without creating a schedule confirmation card.",
    ),
)
WEB_FALLBACK_CORRECTIONS = (
    ("Câu hỏi ngoài tính năng", "Nếu câu hỏi không phải Email, Lịch, Checklist, History hay Settings, Bob phải tra cứu web công khai thay vì trả lời không hỗ trợ."),
    ("Câu hỏi ai là", "Câu hỏi về người sáng lập, chủ sở hữu, lãnh đạo hoặc nhân vật phải được tìm nguồn web khi knowledge local không đủ."),
    ("Câu hỏi giải thích", "Yêu cầu giải thích khái niệm ngoài workspace nên dùng web để bổ sung dữ kiện, sau đó trả lời dễ hiểu và nêu nguồn."),
    ("Câu hỏi so sánh", "Yêu cầu so sánh sản phẩm, công nghệ hoặc tổ chức nên tra cứu thông tin hiện hành trước khi kết luận."),
    ("Thông tin có thể thay đổi", "Giá, phiên bản, CEO, chính sách, tin tức và dữ liệu hiện tại luôn cần web thay vì dựa vào trí nhớ cũ."),
    ("Không search lời chào", "Chào hỏi, cảm ơn, xác nhận ngắn và tâm sự không chứa yêu cầu thông tin thì không cần gọi web."),
    ("Không đưa email riêng lên web", "Tác vụ về email, lịch và hồ sơ riêng chỉ dùng workspace; force web fallback không được vượt qua ranh giới riêng tư."),
    ("Nguồn trong câu trả lời", "Khi web research thành công, Bob phải dựa vào kết quả lấy được và đưa URL/nguồn phù hợp thay vì nói chung chung đã tìm."),
    ("Search thất bại minh bạch", "Nếu search không có kết quả hoặc lỗi mạng, Bob nói rõ chưa xác minh được; không bịa đáp án và có thể đề nghị thử lại."),
    ("Ngôn ngữ phản hồi", "Bob trả lời theo ngôn ngữ user, dù nguồn web có thể bằng ngôn ngữ khác; giữ tên riêng và thuật ngữ chính xác."),
)

WEB_FALLBACK_CORRECTIONS_EN = {
    "Câu hỏi ngoài tính năng": (
        "If a question is outside Email, Calendar, Checklist, History, or Settings, use public web "
        "research instead of replying that the request is unsupported."
    ),
    "Câu hỏi ai là": (
        "Questions about founders, owners, leaders, or public figures require sourced web research "
        "when local knowledge is insufficient."
    ),
    "Câu hỏi giải thích": (
        "For concepts outside the private workspace, use the web to add supporting facts, then explain "
        "the result clearly and name the sources."
    ),
    "Câu hỏi so sánh": (
        "Before comparing products, technologies, or organizations, research current information and "
        "ground the conclusion in those findings."
    ),
    "Thông tin có thể thay đổi": (
        "Prices, versions, CEOs, policies, news, and other current facts require web verification rather "
        "than reliance on stale model memory."
    ),
    "Không search lời chào": (
        "Greetings, thanks, short acknowledgements, and personal conversation without an information "
        "request do not require web research."
    ),
    "Không đưa email riêng lên web": (
        "Email, calendar, and private profile tasks must remain inside the workspace. Web fallback must "
        "not cross privacy boundaries."
    ),
    "Nguồn trong câu trả lời": (
        "After successful web research, base the answer on the retrieved results and include appropriate "
        "URLs or source names instead of merely saying that a search was performed."
    ),
    "Search thất bại minh bạch": (
        "If search returns no results or the network fails, state that the claim could not be verified. "
        "Do not invent an answer, and offer to retry when appropriate."
    ),
    "Ngôn ngữ phản hồi": (
        "Reply in the user's language even when web sources use another language. Preserve proper names "
        "and exact technical terminology."
    ),
}

ENGLISH_CONCEPTS = {
    "action item": "action items and required follow-up",
    "attachment": "attachments and files",
    "auth": "authentication and account connection",
    "calendar": "calendar events, availability, and appointments",
    "checklist": "checklists, to-do items, and simple tasks",
    "confirm": "confirmation before an external or destructive action",
    "confirmation": "confirmation before an external or destructive action",
    "deadline": "deadlines, due dates, and time-sensitive work",
    "draft": "drafting without sending",
    "email": "email, inbox, threads, summaries, search, and replies",
    "follow up": "follow-up work and pending responses",
    "follow-up": "follow-up work and pending responses",
    "freeform": "general questions and free-form conversation",
    "gmail": "Gmail messages and inbox data",
    "history": "past activity and audit history",
    "internet": "public web research with sources",
    "knowledge": "knowledge lookup and grounded answers",
    "lich": "calendar events, availability, and appointments",
    "mode": "workspace mode selection and mode-specific priorities",
    "oauth": "OAuth connection, callback, and authorization",
    "overview": "daily briefs, priorities, and workspace overviews",
    "planning": "planning, prioritization, and time blocking",
    "privacy": "privacy, sensitive data, and source boundaries",
    "priority": "priority, urgency, and ordering",
    "recovery": "connection recovery, missing permissions, and synchronization errors",
    "reply": "email reply drafting without automatic sending",
    "research": "public web research with current sources",
    "safety": "safe execution, confirmations, and non-fabrication",
    "schedule": "calendar creation, updates, deletion, listing, and planning",
    "search": "search and information retrieval",
    "security": "security, credentials, and safe data handling",
    "settings": "settings and workspace mode changes",
    "student": "student courses, assignments, exams, and academic progress",
    "summary": "summaries, key points, and action extraction",
    "task": "tasks, checklists, and work to complete",
    "teacher": "teaching, classes, lesson plans, grading, and parent communication",
    "time": "dates, times, durations, and timezone interpretation",
    "todo": "to-do items and checklists",
    "triage": "triage, urgency, and what needs attention",
    "web": "public web research with current sources",
    "workflow": "multi-step workflow execution",
    "xac nhan": "confirmation before an external or destructive action",
}

TITLE_FAMILIES_EN = {
    "Email": "interpret an English request about email or an English email message",
    "Case": "apply the same intent, behavior, and safety outcome to an equivalent English request",
    "Expanded": "apply the expanded workflow rule when the same situation is described in English",
    "Privacy": "apply the same privacy boundary to equivalent English wording",
    "Student Privacy": "apply the same student privacy boundary to equivalent English wording",
    "Internet Research": "recognize equivalent English web-research language and preserve sourcing rules",
}


def _ascii_key(value):
    normalized = unicodedata.normalize("NFD", str(value or "").lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return normalized.replace("đ", "d").strip()


def _english_semantic_bridge(document, mode):
    """Create an English retrieval bridge for a legacy Vietnamese rule.

    The original Vietnamese content remains authoritative and is imported in
    the same RAG document.  This bridge supplies English concepts and intent
    phrasing so an English query retrieves that exact paired rule instead of a
    loosely related document.
    """
    concepts = []
    for raw_tag in str(document.get("tags") or "").split(","):
        tag = raw_tag.strip()
        if not tag:
            continue
        key = _ascii_key(tag)
        concept = ENGLISH_CONCEPTS.get(key)
        if concept:
            concepts.append(concept)
        elif tag.isascii():
            concepts.append(tag.replace("-", " "))

    title = str(document.get("title") or "")
    family = next(
        (meaning for prefix, meaning in TITLE_FAMILIES_EN.items() if title.startswith(prefix)),
        "apply this rule when the same situation is expressed in English",
    )
    if mode != "shared":
        concepts.append(MODE_PROFILES_EN.get(mode, f"{mode} mode priorities"))
    concepts = list(dict.fromkeys(concepts))[:12]
    concept_text = "; ".join(concepts) or "the paired workflow, intent, and safety constraints"

    return (
        "English semantic equivalent of the paired Vietnamese training rule. "
        f"When the user writes in English, {family}. "
        f"Equivalent English concepts: {concept_text}. "
        "Use the original Vietnamese content in this same document as the authoritative behavior. "
        "Preserve its factual grounding, privacy limits, confirmation requirements, and prohibition "
        "against inventing data."
    )


def attach_english_semantics(document, mode):
    paired = dict(document)
    if not str(paired.get("content_en") or "").strip():
        paired["content_en"] = _english_semantic_bridge(paired, mode)
    tags = [part.strip() for part in str(paired.get("tags") or "").split(",") if part.strip()]
    for tag in ("semantic-pair", "vi-en"):
        if tag not in tags:
            tags.append(tag)
    paired["tags"] = ",".join(tags)
    return paired


def load_legacy_documents():
    documents = []
    legacy_paths = [TRAINING_DIR / name for name in LEGACY_FILES]
    for path in legacy_paths:
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        documents.extend(raw.get("documents", []))
    if documents:
        return documents

    # Idempotent rebuild after consolidation: use the current mode files as
    # the preserved baseline and replace only the generated new-500 layer.
    for path in sorted(MODE_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        documents.extend(
            item for item in raw.get("documents", [])
            if not ({"new-500", "checklist-time-correction", "knowledge-negative-correction", "web-fallback-correction"} & set(str(item.get("tags", "")).split(",")))
        )
    return documents


def classify_mode(document):
    haystack = f"{document.get('title', '')} {document.get('tags', '')}".lower()
    for mode in MODES[1:]:
        if mode in haystack:
            return mode
    aliases = {
        "student": ("sinh vien", "hoc tap", "giao vien", "bai tap", "lich thi"),
        "worker": ("nhan vien", "cong viec", "van phong"),
        "freelancer": ("khach hang", "invoice", "du an freelance"),
        "creator": ("sang tao", "noi dung", "content"),
        "business": ("kinh doanh", "doanh nghiep", "van hanh"),
        "mentor": ("mentee", "co van"),
        "teacher": ("giang day", "hoc vien", "giao an"),
    }
    for mode, terms in aliases.items():
        if any(term in haystack for term in terms):
            return mode
    return "shared"


def build_new_contexts():
    documents = []
    index = 1
    for mode, profile in MODE_PROFILES.items():
        for domain_tag, domain_text, domain_text_en in DOMAINS:
            for context_name, context_name_en, behavior, behavior_en in CONTEXTS:
                article = "an" if context_name_en[:1].lower() in "aeiou" else "a"
                documents.append({
                    "title": f"Mode Context {index:03d} - {mode} - {domain_tag} - {context_name}",
                    "content": (
                        f"Khi user ở {mode.title()} Mode gặp ngữ cảnh {context_name} liên quan đến {domain_text}, "
                        f"Bob phải {behavior}. Cách trả lời cần {profile}; dùng dữ liệu thật đang có, không bịa "
                        "chi tiết và nêu hành động tiếp theo ngắn gọn."
                    ),
                    "content_en": (
                        f"When a user in {mode.title()} Mode describes {article} {context_name_en} situation involving "
                        f"{domain_text_en}, Bob must {behavior_en}. The response must "
                        f"{MODE_PROFILES_EN[mode]}; use only available real data, never fabricate details, "
                        "and state the next action concisely."
                    ),
                    "tags": (
                        f"mode-context-v2,new-500,{mode},{domain_tag},{context_name},"
                        f"{context_name_en},semantic-pair,vi-en"
                    ),
                })
                index += 1
    for title, content in SHARED_CONTEXTS:
        documents.append({
            "title": f"Mode Context {index:03d} - shared - {title}",
            "content": content,
            "content_en": SHARED_CONTEXTS_EN[title],
            "tags": "mode-context-v2,new-500,shared,intent,safety,semantic-pair,vi-en",
        })
        index += 1
    assert len(documents) == 500
    assert len({item["title"] for item in documents}) == 500
    return documents


def main():
    legacy = load_legacy_documents()
    additions = build_new_contexts()
    corrections = [
        {
            "title": f"Checklist Time Correction {index:02d} - {title}",
            "content": content,
            "content_en": CHECKLIST_TIME_CORRECTIONS_EN[title],
            "tags": "shared,checklist,time,checklist-time-correction,semantic-pair,vi-en",
        }
        for index, (title, content) in enumerate(CHECKLIST_TIME_CORRECTIONS, start=1)
    ]
    knowledge_corrections = []
    correction_index = 1
    for entity in KNOWLEDGE_NEGATIVE_ENTITIES:
        for question_pattern, behavior, behavior_en in KNOWLEDGE_NEGATIVE_PATTERNS:
            question = question_pattern.format(entity=entity)
            knowledge_corrections.append({
                "title": f"Knowledge Negative Correction {correction_index:02d} - {entity}",
                "content": (
                    f"Khi user hỏi '{question}', Bob phải phân loại chat.freeform/knowledge question. "
                    f"{behavior} Không trả schedule_suggestion, pending_action hoặc requires_confirmation."
                ),
                "content_en": (
                    f"When the user asks '{question}', Bob must classify it as chat.freeform or a knowledge "
                    f"question. {behavior_en} Do not return schedule_suggestion, pending_action, or "
                    "requires_confirmation."
                ),
                "tags": (
                    "shared,knowledge,negative-intent,knowledge-negative-correction,"
                    "semantic-pair,vi-en"
                ),
            })
            correction_index += 1
    web_fallback_corrections = [
        {
            "title": f"Web Fallback Correction {index:02d} - {title}",
            "content": content,
            "content_en": WEB_FALLBACK_CORRECTIONS_EN[title],
            "tags": "shared,web,research,freeform,web-fallback-correction,semantic-pair,vi-en",
        }
        for index, (title, content) in enumerate(WEB_FALLBACK_CORRECTIONS, start=1)
    ]
    grouped = {mode: [] for mode in MODES}
    for document in legacy + additions + corrections + knowledge_corrections + web_fallback_corrections:
        mode = classify_mode(document)
        grouped[mode].append(attach_english_semantics(document, mode))

    if MODE_DIR.exists():
        shutil.rmtree(MODE_DIR)
    MODE_DIR.mkdir(parents=True)
    for mode in MODES:
        payload = {
            "schema_version": 2,
            "mode": mode,
            "documents": grouped[mode],
        }
        path = MODE_DIR / f"{mode}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for name in LEGACY_FILES:
        (TRAINING_DIR / name).unlink(missing_ok=True)

    total = sum(len(items) for items in grouped.values())
    print(
        f"Consolidated {len(legacy)} existing + {len(additions)} new + "
        f"{len(corrections)} checklist corrections + {len(knowledge_corrections)} "
        f"knowledge corrections + {len(web_fallback_corrections)} web fallback corrections "
        f"= {total} documents"
    )
    for mode in MODES:
        print(f"  {mode}: {len(grouped[mode])}")


if __name__ == "__main__":
    main()
