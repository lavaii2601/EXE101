#!/usr/bin/env python
"""Consolidate Bob's RAG corpus by user mode and add 500 reviewed contexts."""

import json
import shutil
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

DOMAINS = (
    ("email", "email mới hoặc chuỗi thư liên quan"),
    ("schedule", "lịch, cuộc hẹn hoặc khung giờ đang bận"),
    ("checklist", "task, checklist hoặc việc cần hoàn thành"),
    ("overview", "bản tổng hợp ngày và các ưu tiên nổi bật"),
    ("planning", "yêu cầu lập kế hoạch hoặc chia thời gian"),
    ("follow-up", "việc cần theo dõi sau một trao đổi trước đó"),
    ("conflict", "xung đột giữa nhiều deadline hoặc lịch hẹn"),
    ("search", "yêu cầu tìm kiếm kiến thức hoặc thông tin cập nhật"),
    ("privacy", "dữ liệu riêng tư, nhạy cảm hoặc thông tin của người khác"),
    ("recovery", "lỗi kết nối, thiếu quyền hoặc dữ liệu chưa đồng bộ"),
)

CONTEXTS = (
    ("mơ hồ", "xác định mục tiêu chính từ ngữ cảnh; chỉ hỏi lại phần còn thiếu có thể làm thay đổi kết quả"),
    ("khẩn cấp", "nêu việc cần làm ngay, deadline gần nhất và không để việc ít quan trọng che khuất rủi ro"),
    ("thiếu dữ liệu", "nói rõ dữ liệu nào chưa có, không suy đoán, rồi đề xuất cách bổ sung hoặc kết nối nguồn"),
    ("nhiều bước", "tách yêu cầu thành các bước theo thứ tự, nêu bước đọc dữ liệu và xin xác nhận trước bước ghi"),
    ("thay đổi phút cuối", "so sánh trạng thái cũ và mới, chỉ ra ảnh hưởng dây chuyền và cập nhật sau khi được xác nhận"),
    ("song ngữ", "trả lời theo ngôn ngữ user đang dùng, giữ nguyên tên riêng và thuật ngữ quan trọng"),
    ("theo dõi dài hạn", "tóm tắt tiến độ, việc còn mở, người hoặc nguồn đang chờ và hành động kế tiếp cụ thể"),
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
    ("Câu nối tiếp dùng lịch sử gần", "Các câu như 'đổi giờ đó' hoặc 'làm luôn đi' cần dùng phiên chat hiện tại để giải tham chiếu nhưng không lấy lịch sử cũ làm yêu cầu mới."),
    ("Ưu tiên câu hỏi làm rõ tối thiểu", "Nếu có thể thực hiện an toàn bằng dữ liệu sẵn có thì làm; nếu thiếu lựa chọn làm thay đổi kết quả, hỏi đúng một câu ngắn và cụ thể."),
)

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

KNOWLEDGE_NEGATIVE_ENTITIES = (
    "Facebook", "Amazon", "Booking.com", "Eventbrite", "Gmail",
    "Microsoft", "Apple", "Netflix", "TikTok", "LinkedIn",
)
KNOWLEDGE_NEGATIVE_PATTERNS = (
    ("Ai là chủ của {entity}?", "Đây là câu hỏi kiến thức về chủ sở hữu; trả lời factual và không mở gợi ý lịch/email."),
    ("Người sáng lập {entity} là ai?", "Đây là câu hỏi kiến thức về founder; tên riêng không được kích hoạt tool bằng substring."),
    ("Who owns or founded {entity}?", "This is a general-knowledge question; answer it without creating a schedule confirmation card."),
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
        for domain_tag, domain_text in DOMAINS:
            for context_name, behavior in CONTEXTS:
                documents.append({
                    "title": f"Mode Context {index:03d} - {mode} - {domain_tag} - {context_name}",
                    "content": (
                        f"Khi user ở {mode.title()} Mode gặp ngữ cảnh {context_name} liên quan đến {domain_text}, "
                        f"Bob phải {behavior}. Cách trả lời cần {profile}; dùng dữ liệu thật đang có, không bịa "
                        "chi tiết và nêu hành động tiếp theo ngắn gọn."
                    ),
                    "tags": f"mode-context-v2,new-500,{mode},{domain_tag},{context_name}",
                })
                index += 1
    for title, content in SHARED_CONTEXTS:
        documents.append({
            "title": f"Mode Context {index:03d} - shared - {title}",
            "content": content,
            "tags": "mode-context-v2,new-500,shared,intent,safety",
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
            "tags": "shared,checklist,time,checklist-time-correction",
        }
        for index, (title, content) in enumerate(CHECKLIST_TIME_CORRECTIONS, start=1)
    ]
    knowledge_corrections = []
    correction_index = 1
    for entity in KNOWLEDGE_NEGATIVE_ENTITIES:
        for question_pattern, behavior in KNOWLEDGE_NEGATIVE_PATTERNS:
            question = question_pattern.format(entity=entity)
            knowledge_corrections.append({
                "title": f"Knowledge Negative Correction {correction_index:02d} - {entity}",
                "content": (
                    f"Khi user hỏi '{question}', Bob phải phân loại chat.freeform/knowledge question. "
                    f"{behavior} Không trả schedule_suggestion, pending_action hoặc requires_confirmation."
                ),
                "tags": "shared,knowledge,negative-intent,knowledge-negative-correction",
            })
            correction_index += 1
    web_fallback_corrections = [
        {
            "title": f"Web Fallback Correction {index:02d} - {title}",
            "content": content,
            "tags": "shared,web,research,freeform,web-fallback-correction",
        }
        for index, (title, content) in enumerate(WEB_FALLBACK_CORRECTIONS, start=1)
    ]
    grouped = {mode: [] for mode in MODES}
    for document in legacy + additions + corrections + knowledge_corrections + web_fallback_corrections:
        grouped[classify_mode(document)].append(document)

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
