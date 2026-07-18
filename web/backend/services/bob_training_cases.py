"""Deterministic, labelled training corpus for Bob's workspace intents.

The project does not fine-tune a foundation model.  These examples serve two
real purposes instead of being passive documentation only:

* :mod:`training_intent_classifier` learns an offline fallback classifier
  from them, so paraphrases can still be routed when an AI provider is down.
* deployment/local training can import them in compact batches into Bob's RAG
  knowledge base.

Every tool in ``tool_catalog`` owns exactly 500 unique examples.  Keeping the
corpus generated from reviewed building blocks avoids committing a very large,
repetitive JSON file while still making the count reproducible and testable.
"""

from services.tool_catalog import TOOL_NAMES


CASES_PER_INTENT = 500

_PREFIXES = (
    "Bob,",
    "Giup minh",
    "Lam on",
    "Ban co the",
    "Please",
)

_SUFFIXES = (
    "nhe",
    "giup toi",
    "ngay bay gio",
    "tren FlowMate",
    "cho tai khoan nay",
    "va bao ket qua",
    "dung du lieu that",
    "neu co the",
    "please",
    "cam on Bob",
)

# Ten reviewed semantic cores x five prefixes x ten suffixes = 500 labelled
# examples per intent.  Cores intentionally mix Vietnamese, English and
# everyday shorthand because that is how the product is used in practice.
_CORES = {
    "schedule.create": (
        "tao lich hop voi sep luc 3 gio chieu mai",
        "nhac toi goi khach hang vao 9 gio sang thu hai",
        "dat lich kham rang luc 14 gio ngay mai",
        "them su kien review du an vao 4 gio chieu nay",
        "hen gap doi tac luc 10 gio sang tuan sau",
        "schedule a client call tomorrow at 3pm",
        "set a reminder to submit the report at 5pm today",
        "book a planning meeting next Monday at 9am",
        "cho minh mot lich tap gym luc 6 gio sang mai",
        "tao event demo san pham vao 15 gio thu sau",
    ),
    "schedule.update": (
        "doi lich hop voi sep sang 5 gio chieu mai",
        "chuyen lich kham rang sang 9 gio thu sau",
        "sua gio meeting du an thanh 14 gio hom nay",
        "day cuoc hen voi khach sang tuan sau",
        "doi dia diem lich hop sang phong B",
        "reschedule the client call to tomorrow at 4pm",
        "move my dentist appointment to next Friday",
        "change the project meeting to 10am",
        "lui lich review bao cao them mot ngay",
        "cap nhat cuoc hen doi tac thanh 3 gio chieu",
    ),
    "schedule.delete": (
        "xoa lich hop voi sep ngay mai",
        "huy lich kham rang thu sau",
        "bo su kien review du an khoi lich",
        "xoa cuoc hen voi khach hang",
        "huy meeting buoi chieu nay",
        "cancel tomorrow's client meeting",
        "delete my dentist appointment",
        "remove the project review from my calendar",
        "khong di hop nua huy lich do",
        "xoa nhac nho nop bao cao",
    ),
    "schedule.list": (
        "hom nay toi co lich gi",
        "xem lich ngay mai cua toi",
        "tuan sau co cuoc hop nao khong",
        "liet ke cac su kien sap toi",
        "cho toi xem calendar tuan nay",
        "what is on my calendar today",
        "show my meetings next week",
        "do I have any events tomorrow",
        "kiem tra lich trong bay ngay toi",
        "lich chieu nay co trong khong",
    ),
    "schedule.suggest_plan": (
        "sap xep lich cho tap gym doc sach va nau com",
        "goi y khung gio cho cac viec hom nay",
        "xep giup toi lich hoc lam bai va nghi ngoi",
        "chia thoi gian cho ba hoat dong nay",
        "lap ke hoach theo gio cho ngay mai",
        "plan my day with work exercise and reading",
        "suggest time slots for these activities",
        "build a daily schedule for my task list",
        "toi co nhieu viec hay xep gio hop ly",
        "goi y lich tranh trung cac cuoc hop da co",
    ),
    "email.latest_summary": (
        "tom tat email moi nhat",
        "noi toi noi dung ba mail gan day",
        "inbox hom nay co gi quan trong",
        "doc nhanh cac email vua nhan",
        "tom luoc nam thu moi nhat",
        "summarize my latest emails",
        "give me a summary of today's inbox",
        "what are my three newest messages about",
        "mail moi nhat noi gi vay",
        "quet inbox va tom tat thu vua den",
    ),
    "email.search": (
        "tim email tu chi Lan ve hop dong",
        "kiem mail co tu khoa bao cao",
        "mail nao hom qua noi ve deadline",
        "tim thu cua khach hang ABC",
        "xem email co file bang gia",
        "find emails from John about the project",
        "search my inbox for the invoice",
        "show messages containing quarterly report",
        "kiem lai mail hop tuan truoc",
        "tim email chua doc cua giao vien",
    ),
    "email.mark_read": (
        "danh dau email tu chi Lan la da doc",
        "cho ba mail moi nhat thanh da xem",
        "mark email hop dong as read",
        "danh dau cac thu hom nay da doc",
        "bo trang thai chua doc cua mail nay",
        "mark these messages as read",
        "set the latest email to read",
        "clear unread status for project emails",
        "toi xem roi danh dau mail do da doc",
        "chuyen email cua sep sang da xem",
    ),
    "email.mark_unread": (
        "danh dau email nay la chua doc",
        "chuyen mail cua sep ve chua xem",
        "mark email hop dong as unread",
        "de lai ba thu nay chua doc",
        "bat lai trang thai chua xem cho mail",
        "mark these messages as unread",
        "set the latest email to unread",
        "restore unread status for project emails",
        "toi se doc sau danh dau chua doc",
        "giu email cua khach o trang thai chua xem",
    ),
    "history.list": (
        "hom nay toi da lam gi",
        "xem lai lich su hoat dong",
        "Bob vua xu ly nhung viec nao",
        "liet ke cac thao tac gan day",
        "cho xem nhat ky hom qua",
        "show my recent activity history",
        "what did I do today",
        "list actions Bob completed yesterday",
        "nay gio minh da lam gi roi",
        "kiem tra lich su chat va lich",
    ),
    "settings.update_mode": (
        "doi che do cua toi sang student",
        "tu nay toi lam freelancer",
        "chuyen profile thanh worker",
        "toi la giao vien hay dung teacher mode",
        "bat che do business cho toi",
        "switch my workspace mode to creator",
        "change my profile to mentor mode",
        "use student mode from now on",
        "minh moi di lam doi sang nhan vien",
        "cap nhat che do lam viec thanh freelancer",
    ),
    "checklist.create": (
        "them tap gym vao checklist",
        "cho doc sach va nau com vao danh sach viec",
        "tao todo nop bao cao gap",
        "hom nay can hoc bai don nha va mua do",
        "them viec goi khach hang vao checklist",
        "add exercise and reading to my checklist",
        "create a todo for submitting the report",
        "put these tasks on today's checklist",
        "ghi lai viec cham meo va tuoi cay",
        "them ba dau viec nay vao todo hom nay",
    ),
}


def generate_training_cases(intent, count=CASES_PER_INTENT):
    """Return exactly ``count`` unique labelled phrases for one intent."""
    if intent not in _CORES:
        raise ValueError(f"Unsupported training intent: {intent}")
    if count < 1 or count > CASES_PER_INTENT:
        raise ValueError(f"count must be between 1 and {CASES_PER_INTENT}")

    cases = []
    for core in _CORES[intent]:
        for prefix in _PREFIXES:
            for suffix in _SUFFIXES:
                cases.append(f"{prefix} {core}, {suffix}".strip())
    # The construction above is deliberately exact and deterministic.  Keep
    # the assertion close to it so future edits cannot silently reduce the
    # promised coverage.
    assert len(cases) == CASES_PER_INTENT
    assert len(set(cases)) == CASES_PER_INTENT
    return cases[:count]


def iter_labelled_cases(count_per_intent=CASES_PER_INTENT):
    for intent in TOOL_NAMES:
        for phrase in generate_training_cases(intent, count=count_per_intent):
            yield {"text": phrase, "intent": intent}


def build_rag_training_documents(batch_size=50):
    """Pack examples into compact RAG documents instead of 6,000 DB rows."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    documents = []
    for intent in TOOL_NAMES:
        cases = generate_training_cases(intent)
        for offset in range(0, len(cases), batch_size):
            batch = cases[offset:offset + batch_size]
            part = offset // batch_size + 1
            content = [
                f"Intent dung: {intent}.",
                "Cac cau sau deu phai duoc Bob hieu theo intent tren:",
            ]
            content.extend(f"{index}. {phrase}" for index, phrase in enumerate(batch, start=offset + 1))
            documents.append({
                "title": f"Bob intent 500 - {intent} - phan {part:02d}",
                "content": "\n".join(content),
                "tags": f"bob,training,intent,{intent},500-cases",
            })
    return documents


assert set(_CORES) == set(TOOL_NAMES), "Every catalog tool must have a 500-case training set"
