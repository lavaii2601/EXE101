import os
import sys

from flask import Blueprint, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.knowledge import KnowledgeDocument
from services.colloquial_knowledge_seed import COLLOQUIAL_SEED_DOCUMENTS
from services.knowledge_service import KnowledgeService
from utils.user_context import get_current_user_id

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/api/knowledge')
knowledge_service = KnowledgeService()

# Bob's starter knowledge base: FlowMate's own real feature set, written so
# Bob can ground "how does X work" answers instead of guessing. Anyone can
# add more material later (including open-source docs) via POST below --
# this seed only runs once, the first time the table is empty.
_SEED_DOCUMENTS = [
    (
        "Bob la ai",
        "Bob la AI agent ben trong FlowMate, dong vai tro tro ly cong viec: doc email, "
        "lich, lich su hoat dong va ho so de tra loi co can cu, khong bia dat thong tin. "
        "Bob khong bao gio tiet lo AI provider/model nao dang chay ben duoi. Cac hanh dong "
        "nhay cam (tao lich, doi cai dat, gui email...) chi thuc hien sau khi nguoi dung xac nhan.",
        "bob,gioi thieu,agent",
    ),
    (
        "Tab Tong hop (Overview)",
        "Tab Tong hop gop du lieu tu Email va Lich trong ngay duoc chon thanh mot bai tom tat "
        "do AI tao. Email duoc cache toi 36 gio; he thong tu kiem tra email moi mỗi 5 phut va "
        "chi goi lai AI tom tat khi phat hien thay doi, khong ton AI call khi khong co gi moi. "
        "Nguoi dung co the bam vao tung email trong danh sach tong hop de xem ngay noi dung goc, "
        "khong can sang tab Email.",
        "overview,tong hop,email,lich",
    ),
    (
        "Tab Email",
        "Tab Email hien thi hop thu Gmail da ket noi, ho tro loc theo trang thai (da doc/chua doc), "
        "tom tat noi dung bang AI, va tu dong quet email de phat hien tin hieu lich hen/cuoc hop "
        "(meeting suggestion) de goi y tao lich. Nguoi dung phai xac nhan truoc khi mot goi y duoc "
        "tao thanh lich thuc su.",
        "email,gmail,meeting suggestion",
    ),
    (
        "Tab Lich (Schedule/Calendar)",
        "Tab Lich quan ly cac lich hen cua FlowMate va dong bo hai chieu voi Google Calendar khi "
        "nguoi dung ket noi Gmail. Co the tao/sua/xoa lich qua giao dien hoac qua chat voi Bob "
        "bang cau tu nhien (xem tai lieu rieng 've cach noi de tao/doi/xoa lich' de biet vi du cu "
        "the).",
        "lich,calendar,schedule,bob",
    ),
    (
        "Tab Lich su (History)",
        "Tab Lich su ghi lai cac hoat dong: tin nhan chat, email da tom tat, lich da tao/sua/xoa, "
        "va thay doi cai dat. Day la nguon du lieu Bob dung de hieu nguoi dung da lam gi truoc do "
        "khi duoc hoi lai.",
        "lich su,history,hoat dong",
    ),
    (
        "Che do lam viec (User mode)",
        "FlowMate co 7 che do lam viec de ca nhan hoa cach Bob uu tien thong tin: student (sinh "
        "vien), worker (nhan vien van phong), freelancer (tu do), creator (sang tao noi dung), "
        "business (kinh doanh), mentor (co van), teacher (giao vien). Doi che do qua tab Cai dat "
        "hoac noi truc tiep voi Bob trong chat (xem tai lieu rieng 've cach doi che do qua chat' "
        "de biet vi du cu the).",
        "mode,che do,settings",
    ),
    (
        "Checklist trong tab Tong hop",
        "Tab Tong hop co mot checklist gop viec tu lich va viec tu them thu cong, sap xep theo "
        "thu tu: viec chua xong truoc, viec duoc ghim len dau, han gan nhat, do uu tien cao nhat, "
        "moi tao nhat. Co the them viec qua o 'Them nhanh' bang cau tu nhien (vi du 'tap yoga, "
        "cham meo, don nha'), hoac noi thang voi Bob trong chat kieu 'hom nay minh co cac hoat "
        "dong nhu X, Y, Z, dua vao checklist giup minh' -- Bob se tu tach tung viec va them ngay, "
        "khong can xac nhan vi day la thao tac it rui ro, co the xoa lai duoc. Neu nguoi dung noi "
        "ro mot viec la 'gap'/'khan cap'/'quan trong', viec do duoc ghim len dau va uu tien cao "
        "hon; neu noi 'khong gap'/'ranh thi lam', viec do se xuong cuoi danh sach.",
        "checklist,them nhanh,uu tien,bob,chat",
    ),
    (
        "Goi y lich tu danh sach hoat dong",
        "Khi nguoi dung liet ke nhieu hoat dong trong chat va noi ro muon 'sap xep lich'/'goi y "
        "lich' (khac voi chi muon dua vao checklist), Bob se dung engine xep lich gioi thieu khung "
        "gio cu the cho tung hoat dong, tranh trung voi lich da co san -- vi du yoga thuong duoc "
        "xep dau gio sang, cham thu cung dau ngay, viec nha vao buoi toi. Day la goi y, Bob KHONG "
        "tu tao lich that: nguoi dung phai xem va bam 'Ap dung' (co the sua gio/tieu de truoc khi "
        "ap dung) thi cac su kien moi duoc tao that trong FlowMate va dong bo Google Calendar.",
        "lich,goi y,sap xep,schedule,bob",
    ),
    (
        "Kho kien thuc noi bo cua Bob",
        "Bob dung mot kho tai lieu rieng (RAG, tim bang TF-IDF) de tra cuu khi tro chuyen, nhung "
        "kho nay AN voi nguoi dung -- khong co tab hay man hinh nao tren web/mobile de nguoi dung "
        "tu xem, them, sua hay xoa tai lieu. Moi tai lieu co nguon (source): 'seed' la kien thuc "
        "goc ve FlowMate duoc dong bo san tu code, 'auto' la Bob tu hoc duoc tu hoi thoai (xem muc "
        "'Bob tu hoc tri nho'). Neu nguoi dung hoi cach them/sua kien thuc cho Bob, tra loi rang "
        "hien khong co cong cu tu quan ly -- kien thuc duoc Bob tu hoc qua hoi thoai hoac cap nhat "
        "boi doi phat trien.",
        "kien thuc,knowledge,rag,noi bo",
    ),
    (
        "Bob tu hoc tri nho tu hoi thoai",
        "Bob khong the 'hoc' theo nghia cap nhat trong so AI that su (gioi han ky thuat chung cua "
        "moi AI qua API), nhung co the tu dong ghi nho: sau moi tin nhan co dau hieu dang nho (sua "
        "loi Bob, neu so thich/quy tac ca nhan, cach xung ho rieng...), mot buoc kiem tra ngam se "
        "trich xuat va luu lai thanh tai lieu kien thuc rieng cho dung nguoi dung do (gan nhan "
        "source='auto'), khong can nguoi dung tu nhap. Lan chat sau co lien quan, Bob tu tra cuu "
        "lai. Tri nho tu hoc cua moi nguoi dung hoan toan rieng biet, khong bao gio hien thi cho "
        "nguoi dung khac. Day la du lieu noi bo, nguoi dung khong co cach nao tu xem/sua/xoa truc "
        "tiep -- neu Bob nho sai, nguoi dung chi co the noi lai cho Bob biet trong chat de Bob ghi "
        "nho lai cho dung.",
        "tu hoc,tri nho,memory,bob,rieng tu",
    ),
    (
        "Bob tra cuu Internet va tu hoc co nguon",
        "Bob co the tra cuu Internet cong khai khi prompt yeu cau tim tren mang hoac can thong tin "
        "moi/cap nhat. Ket qua web duoc dua vao context voi URL nguon va Bob phai neu nguon khi "
        "dung fact ben ngoai. Bob khong tu crawl nen lien tuc; moi lan research bi gioi han so ket "
        "qua, thoi gian tai va kich thuoc trang. Neu bat WEB_RESEARCH_AUTO_LEARN_ENABLED, Bob KHONG "
        "luu raw search result hang loat; Bob chi luu bai hoc web da duoc rut gon/loc trung voi "
        "source='web' khi query co tinh chat hoc hoi, quy trinh, best practice hoac cai thien agent.",
        "internet,web,research,tu hoc,nguon,bob",
    ),
    (
        "Bob hoc tu AI mentor",
        "Bob co the hoc cach xu ly thong tin va hanh dong tu cac AI mentor da cau hinh tren backend "
        "nhu OpenAI/ChatGPT, Gemini, Claude, OpenRouter, Mistral hoac Ollama. Sau mot luot chat phu "
        "hop, mot tien trinh nen co the gui yeu cau da gioi han cho 1-2 provider mentor de nho critique "
        "cach Bob xu ly. Mentor chi duoc tra ve mot bai hoc quy trinh tong quat (source='mentor'), vi du "
        "cach dung nguon, cach hoi xac nhan, cach tach viec hoac tranh hanh dong rui ro. Co quota/ngay va "
        "loc trung de tranh lam roi knowledge DB. Bob khong tu train lai trong so model nen; day la co che "
        "hoc bang knowledge/RAG rieng theo user va khong duoc dung de bo qua xac nhan cua nguoi dung.",
        "mentor,ai-peer,chatgpt,gemini,claude,tu hoc,bob",
    ),
    (
        "Bob ho tro song ngu Viet-Anh",
        "Bob hieu va phan loai yeu cau dung bang ca tieng Viet lan tieng Anh (vi du 'Schedule a "
        "meeting tomorrow at 3pm' hoac 'tao lich hop luc 3 gio chieu mai' deu duoc hieu giong "
        "nhau). Bob tra loi bang dung ngon ngu nguoi dung vua dung trong tin nhan moi nhat, tru "
        "khi duoc yeu cau doi ngon ngu khac.",
        "song ngu,bilingual,tieng anh,tieng viet",
    ),
    (
        "Cach noi de Bob tao lich hen moi",
        "Noi tu nhien, khong can dien form: vi du 'nhac minh hop voi sep luc 3 gio chieu mai', "
        "'dat lich kham rang thu 5 tuan sau 9 gio sang', 'trong 2 tieng nua goi lai cho khach'. "
        "Bob tu tinh ngay/gio cu the dua tren thoi diem hien tai. Neu cau co danh dau noi dung ro "
        "rang (vi du 'voi noi dung la: ...'), Bob chi lay phan sau danh dau lam mo ta su kien, "
        "khong lay nguyen ca cau lenh. Neu khong neu ten rieng, Bob tu dat tieu de ngan gon tu noi "
        "dung. Sau khi hieu, Bob LUON hoi xac nhan truoc khi tao that, khong tu y tao ngay.",
        "lich,tao lich,schedule create,vi du,bob",
    ),
    (
        "Cach noi de Bob doi gio hoac xoa lich hen",
        "Vi du 'doi gio hop voi sep sang 5 gio chieu mai', 'huy cuoc hen voi khach ngay mai', "
        "'cancel my meeting with John'. Bob tim trong cac lich hen sap toi (14 ngay ke tu hom nay) "
        "co tieu de khop voi tu khoa trong cau. Neu tim thay dung 1 lich, Bob hien thi lai thong "
        "tin hien tai va hoi xac nhan truoc khi sua/xoa. Neu khop nhieu lich, Bob liet ke ra va hoi "
        "nguoi dung chon ro lich nao. Neu khong tim thay, Bob bao khong tim duoc va goi y noi ro "
        "ten lich hon.",
        "lich,doi lich,xoa lich,schedule update,schedule delete,vi du,bob",
    ),
    (
        "Cach hoi Bob ve lich sap toi hoac da co",
        "Vi du 'tuan sau minh co lich gi khong', 'hom nay co lich gi', 'do i have any meetings "
        "this week', 'what's on my calendar'. Bob tra loi dua tren du lieu lich that trong "
        "FlowMate (da dong bo Google Calendar neu co ket noi), khong bia dat su kien khong ton tai.",
        "lich,xem lich,schedule list,vi du,bob",
    ),
    (
        "Cach hoi Bob tom tat hoac tim email",
        "Tom tat: 'tom tat 3 email moi nhat', 'email nao moi nhat trong hop thu'. Tim kiem: 'tim "
        "email tu chi Lan ve hop dong', 'co email nao tu cong ty X tuan nay khong'. Danh dau: "
        "'danh dau email tu chi Lan la da doc', 'danh dau email do la chua xem'. Tat ca deu can "
        "Gmail da ket noi (qua nut Dang nhap o tab Email) thi Bob moi doc duoc hop thu that.",
        "email,gmail,tom tat,tim kiem,danh dau,vi du,bob",
    ),
    (
        "Gioi han hien tai: nhung gi Bob CHUA lam duoc",
        "De tranh hieu lam, Bob hien KHONG lam duoc nhung viec sau qua chat: (1) xoa hoac sua mot "
        "viec cu the trong checklist bang loi noi -- phai bam nut xoa (x) tren giao dien web hoac "
        "mobile; (2) tu dong gui email -- Bob chi soan nhap tra loi, nguoi dung phai bam 'Gui luon' "
        "de xac nhan gui that; (3) tu y tao/sua/xoa lich hen ma khong hoi xac nhan truoc; (4) doc "
        "du lieu cua nguoi dung khac -- moi du lieu (lich, email, lich su, tri nho tu hoc) chi "
        "thuoc ve dung tai khoan dang dang nhap.",
        "gioi han,chua ho tro,bob,luu y",
    ),
    (
        "Cach hoi Bob ve lich su hoat dong da qua",
        "Dung khi muon xem lai VIEC DA LAM truoc do, vi du 'lich su hoat dong hom qua the nao', "
        "'nay minh da lam gi roi nhi', 'what did I do today'. Khac voi cau liet ke hoat dong SAP "
        "lam (vi du 'hom nay co cac hoat dong nhu X, Y, Z') -- cau do se duoc hieu la muon tao "
        "checklist hoac goi y lich, khong phai xem lich su.",
        "lich su,history,vi du,bob",
    ),
    (
        "Cach doi che do lam viec qua chat",
        "Noi truc tiep voi Bob, vi du 'tu nay minh lam freelance roi, doi giup minh', 'minh moi "
        "chuyen sang lam giao vien'. Bob tu nhan dien che do tuong ung trong 7 che do (student, "
        "worker, freelancer, creator, business, mentor, teacher) va cap nhat ngay, khong can vao "
        "tab Cai dat.",
        "che do,mode,settings,vi du,bob",
    ),
    (
        "Bob xac nhan truoc khi ghi du lieu nhu the nao",
        "Bob chia hanh dong ghi du lieu thanh 2 nhom theo do rui ro. Nhom CAN xac nhan truoc (khong "
        "tu lam ngay): tao/sua/xoa lich hen, ap dung goi y lich nhieu hoat dong, gui email (chi "
        "soan nhap, phai bam 'Gui luon'). Nhom KHONG can xac nhan vi it rui ro va de hoan tac: them "
        "viec vao checklist (xoa lai duoc qua nut x), doi che do lam viec, danh dau email da "
        "doc/chua doc, tim kiem/tom tat email (chi doc, khong sua du lieu). Nguyen tac: hanh dong "
        "tao ra ket qua kho hoan tac hoac anh huong ben ngoai (vd dong bo Google Calendar, gui mail "
        "that) luon can nguoi dung xac nhan; hanh dong de sua/xoa lai trong app thi Bob lam ngay de "
        "tiet kiem thao tac cho nguoi dung.",
        "xac nhan,confirm,an toan,chinh sach,bob",
    ),
    (
        "Gioi han: mot tin nhan hien chi xu ly mot y dinh",
        "Bob hien phan loai moi tin nhan thanh DUY NHAT mot y dinh chinh (vi du tao lich, hoac "
        "them checklist, hoac tom tat email...). Neu mot cau chua nhieu yeu cau khac nhau cung luc "
        "(vi du 'tao lich hop 3 gio VA nhac toi chuan bi tai lieu truoc 30 phut'), Bob chi bat duoc "
        "y chinh (thuong la tao lich), khong tu tach thanh nhieu hanh dong rieng. Cach dung tot "
        "nhat hien tai: gui tung yeu cau trong tin nhan rieng de Bob xu ly chinh xac tung viec.",
        "gioi han,nhieu y dinh,multi intent,bob,luu y",
    ),
]

_ALL_SEED_DOCUMENTS = _SEED_DOCUMENTS + COLLOQUIAL_SEED_DOCUMENTS


def _seed_if_empty():
    """Despite the legacy name (app.py imports this as `seed_knowledge_base`
    and calls it once at startup), this keeps every source='seed' document
    fully in sync with _ALL_SEED_DOCUMENTS above, every time the app starts --
    not just a one-time insert:
    - a title not seen before is created
    - an existing seed doc whose content/tags changed here is updated in place
    - a seed doc whose title was REMOVED from the seed lists above is deleted
    'manual' (legacy rows from the now-removed Knowledge tab UI) and 'auto'
    (Bob's per-user learned memories) documents are never touched by any of
    this -- only source='seed' rows are managed declaratively from this
    file. There is no user-facing UI to create 'manual' documents anymore;
    this knowledge base is internal to Bob (see knowledge.py routes, still
    used for RAG search and auto-learned memory storage)."""
    try:
        existing_seed_by_title = {
            doc['title']: doc
            for doc in KnowledgeDocument.get_all(limit=2000)
            if doc.get('source') == 'seed'
        }
        wanted_titles = set()
        changed = False
        for title, content, tags in _ALL_SEED_DOCUMENTS:
            wanted_titles.add(title)
            current = existing_seed_by_title.get(title)
            if current is None:
                KnowledgeDocument.create(title, content, tags=tags, source='seed')
                changed = True
            elif current.get('content') != content or current.get('tags') != tags:
                KnowledgeDocument.update(current['id'], content=content, tags=tags)
                changed = True

        for title, doc in existing_seed_by_title.items():
            if title not in wanted_titles:
                KnowledgeDocument.delete(doc['id'])
                changed = True

        if changed:
            knowledge_service.rebuild_index()
    except Exception:
        pass


@knowledge_bp.route('', methods=['GET'])
def list_documents():
    get_current_user_id(request)
    documents = KnowledgeDocument.get_all(limit=500)
    return jsonify({'success': True, 'documents': documents, 'count': len(documents)})


@knowledge_bp.route('', methods=['POST'])
def create_document():
    get_current_user_id(request)
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    tags = (data.get('tags') or '').strip()
    if not title or not content:
        return jsonify({'success': False, 'error': 'title and content are required'}), 400

    document = knowledge_service.add_document(title, content, tags=tags, source=data.get('source') or 'manual')
    return jsonify({'success': True, 'document': document}), 201


@knowledge_bp.route('/<int:doc_id>', methods=['PUT'])
def update_document(doc_id):
    get_current_user_id(request)
    data = request.get_json() or {}
    if not KnowledgeDocument.get_by_id(doc_id):
        return jsonify({'success': False, 'error': 'not_found'}), 404

    title = data.get('title')
    content = data.get('content')
    tags = data.get('tags')
    if title is not None and not title.strip():
        return jsonify({'success': False, 'error': 'title cannot be empty'}), 400
    if content is not None and not content.strip():
        return jsonify({'success': False, 'error': 'content cannot be empty'}), 400

    document = knowledge_service.update_document(
        doc_id,
        title=title.strip() if title is not None else None,
        content=content.strip() if content is not None else None,
        tags=tags.strip() if tags is not None else None,
    )
    return jsonify({'success': True, 'document': document})


@knowledge_bp.route('/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    get_current_user_id(request)
    deleted = knowledge_service.delete_document(doc_id)
    if not deleted:
        return jsonify({'success': False, 'error': 'not_found'}), 404
    return jsonify({'success': True})


@knowledge_bp.route('/search', methods=['GET'])
def search_documents():
    get_current_user_id(request)
    query = request.args.get('q', '').strip()
    top_k = min(max(request.args.get('top_k', 3, type=int), 1), 10)
    if not query:
        return jsonify({'success': False, 'error': 'q is required'}), 400
    results = knowledge_service.search(query, top_k=top_k)
    return jsonify({'success': True, 'results': results})
