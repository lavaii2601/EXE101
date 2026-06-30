import os
import sys

from flask import Blueprint, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.knowledge import KnowledgeDocument
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
        "nguoi dung ket noi Gmail. Co the tao lich qua giao dien hoac qua chat voi Bob bang cau "
        "tu nhien nhu 'nhac minh hop voi sep luc 3 gio chieu mai' -- Bob se tu tinh ngay/gio dua "
        "tren thoi diem hien tai va hoi xac nhan truoc khi tao.",
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
        "hoac noi voi Bob truc tiep, vi du 'tu nay minh lam freelance, doi giup minh'.",
        "mode,che do,settings",
    ),
]


def _seed_if_empty():
    try:
        if KnowledgeDocument.count() == 0:
            for title, content, tags in _SEED_DOCUMENTS:
                KnowledgeDocument.create(title, content, tags=tags, source='seed')
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
