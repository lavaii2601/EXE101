import math
import re
import unicodedata
from collections import Counter

from models.knowledge import KnowledgeDocument

# Pure-Python TF-IDF + cosine similarity. No ML dependency (no numpy/torch/
# sentence-transformers) -- appropriate for a knowledge base sized at dozens
# to low hundreds of documents, and trivially "open source" since it's just
# a well-known IR algorithm with no model weights or licensing involved.

_STOPWORDS = {
    'la', 'va', 'cua', 'cac', 'mot', 'nhung', 'cho', 'voi', 'khi', 'de',
    'trong', 'ngoai', 'tren', 'duoi', 'nay', 'do', 'thi', 'lai', 'roi',
    'the', 'a', 'an', 'of', 'and', 'to', 'in', 'on', 'is', 'are', 'for',
}


def _normalize_text(value):
    value = unicodedata.normalize('NFD', str(value or '').lower())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn')
    return value.replace('đ', 'd')


def _tokenize(value):
    tokens = re.findall(r'[a-z0-9]+', _normalize_text(value))
    return [token for token in tokens if len(token) >= 2 and token not in _STOPWORDS]


class KnowledgeService:
    """Retrieval-augmented lookup over KnowledgeDocument rows."""

    def __init__(self):
        self._idf = {}
        self._doc_vectors = {}
        self._doc_norms = {}
        self._documents_by_id = {}
        self._built = False

    def _ensure_index(self):
        if self._built:
            return
        self.rebuild_index()

    def rebuild_index(self):
        documents = KnowledgeDocument.get_all(limit=10000)
        self._documents_by_id = {doc['id']: doc for doc in documents}

        doc_tokens = {}
        doc_frequency = Counter()
        for doc in documents:
            text = f"{doc.get('title', '')} {doc.get('content', '')} {doc.get('tags', '')}"
            tokens = _tokenize(text)
            doc_tokens[doc['id']] = tokens
            for term in set(tokens):
                doc_frequency[term] += 1

        total_docs = len(documents) or 1
        self._idf = {
            term: math.log((total_docs + 1) / (df + 1)) + 1
            for term, df in doc_frequency.items()
        }

        self._doc_vectors = {}
        self._doc_norms = {}
        for doc_id, tokens in doc_tokens.items():
            vector = self._tfidf_vector(tokens)
            self._doc_vectors[doc_id] = vector
            self._doc_norms[doc_id] = math.sqrt(sum(weight * weight for weight in vector.values())) or 1.0

        self._built = True

    def _tfidf_vector(self, tokens):
        if not tokens:
            return {}
        term_counts = Counter(tokens)
        max_count = max(term_counts.values())
        vector = {}
        for term, count in term_counts.items():
            idf = self._idf.get(term)
            if not idf:
                continue
            tf = count / max_count
            vector[term] = tf * idf
        return vector

    def search(self, query, top_k=3, min_score=0.08, user_id=None, mode=None):
        """user_id=None searches the whole library (admin/manual UI use).
        Pass the requesting user's id from chat so per-user auto-learned
        memories from OTHER users are excluded from candidates -- the
        shared global docs (user_id IS NULL) are always visible to everyone.

        When ``mode`` is supplied, a document explicitly tagged for another
        FlowMate mode is excluded. Untagged/shared rules and per-user memories
        remain visible. This prevents a Worker chat from retrieving a highly
        similar Student/Teacher template merely because the generated corpus
        uses parallel wording.
        """
        self._ensure_index()
        if not self._doc_vectors:
            return []

        query_tokens = _tokenize(query)
        query_vector = self._tfidf_vector(query_tokens)
        if not query_vector:
            return []
        query_norm = math.sqrt(sum(weight * weight for weight in query_vector.values())) or 1.0

        scored = []
        valid_modes = {
            "student", "worker", "freelancer", "creator",
            "business", "mentor", "teacher",
        }
        requested_mode = str(mode or "").strip().lower()
        if requested_mode not in valid_modes:
            requested_mode = ""
        for doc_id, doc_vector in self._doc_vectors.items():
            document = self._documents_by_id.get(doc_id, {})
            doc_owner = document.get('user_id')
            if user_id is not None:
                if doc_owner and doc_owner != user_id:
                    continue
            if requested_mode and not doc_owner:
                tags = {
                    tag.strip().lower()
                    for tag in str(document.get("tags") or "").split(",")
                    if tag.strip()
                }
                tagged_modes = tags & valid_modes
                if tagged_modes and requested_mode not in tagged_modes:
                    continue
            shared_terms = query_vector.keys() & doc_vector.keys()
            if not shared_terms:
                continue
            dot = sum(query_vector[term] * doc_vector[term] for term in shared_terms)
            score = dot / (query_norm * self._doc_norms[doc_id])
            if score >= min_score:
                scored.append((score, doc_id))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, doc_id in scored[:top_k]:
            doc = self._documents_by_id.get(doc_id)
            if doc:
                results.append({**doc, 'relevance': round(score, 4)})
        return results

    def add_document(self, title, content, tags='', source='manual', user_id=None):
        document = KnowledgeDocument.create(title, content, tags=tags, source=source, user_id=user_id)
        self._built = False
        return document

    def update_document(self, doc_id, title=None, content=None, tags=None):
        document = KnowledgeDocument.update(doc_id, title=title, content=content, tags=tags)
        if document:
            self._built = False
        return document

    def delete_document(self, doc_id):
        deleted = KnowledgeDocument.delete(doc_id)
        if deleted:
            self._built = False
        return deleted
