import math
from collections import Counter

from models.intent_pattern import IntentPattern
from services.knowledge_service import _tokenize

# Same TF-IDF + cosine similarity approach as KnowledgeService, kept as a
# separate small index on purpose: this searches AI-classified message
# *phrasings*, not FlowMate reference docs, so mixing them into one index
# would make knowledge_service.search() (used to ground chat answers) start
# returning raw user message fragments as if they were "kien thuc tham khao".

_SIMILARITY_THRESHOLD = 0.6


class IntentPatternCache:
    """Two-stage TF-IDF cache over AI-classified message phrasings.

    Stage 1 (candidate): every new phrasing the AI resolves for a
    CACHEABLE_INTENTS intent starts here. The AI is still called for every
    similar future message during this stage -- quota is spent on purpose
    so the same intent gets confirmed by the AI multiple times before
    Bob trusts it alone.

    Stage 2 (trusted): once the AI has agreed on the same intent
    IntentPattern.CONFIRM_THRESHOLD times for similar enough phrasings,
    the pattern graduates and `lookup()` can answer from it directly,
    skipping the AI call entirely -- this is where the quota savings
    actually happen, after the pattern has proven itself."""

    def __init__(self):
        self._candidate_index = None
        self._trusted_index = None

    def _get_index(self, status):
        cache_attr = '_trusted_index' if status == 'trusted' else '_candidate_index'
        index = getattr(self, cache_attr)
        if index is None:
            index = _TfidfIndex(IntentPattern.get_all(limit=10000, status=status))
            setattr(self, cache_attr, index)
        return index

    def _invalidate(self):
        self._candidate_index = None
        self._trusted_index = None

    def lookup(self, message, min_score=_SIMILARITY_THRESHOLD):
        """Only ever searches TRUSTED patterns -- candidates still being
        confirmed must never short-circuit the AI call."""
        index = self._get_index('trusted')
        match = index.best_match(message, min_score=min_score)
        if not match:
            return None
        pattern_id, score = match
        IntentPattern.increment_hit(pattern_id)
        pattern = index.patterns_by_id[pattern_id]
        return {'intent': pattern['intent'], 'score': round(score, 4)}

    def observe(self, phrase, intent, confidence=0.6, min_score=_SIMILARITY_THRESHOLD):
        """Called every time the AI resolves a CACHEABLE_INTENTS intent.
        Reinforces a similar existing candidate if the intent agrees, or
        starts a brand new candidate otherwise. Never touches trusted
        patterns (those are already proven; new confirmations only build
        up fresh candidates)."""
        candidate_index = self._get_index('candidate')
        match = candidate_index.best_match(phrase, min_score=min_score)
        if match:
            pattern_id, _score = match
            existing = candidate_index.patterns_by_id[pattern_id]
            if existing['intent'] == intent:
                IntentPattern.reinforce(pattern_id)
                self._invalidate()
                return
            # Conflicting phrasing/intent pair -- don't reinforce a
            # mismatch, just let this start its own separate candidate below.

        IntentPattern.create(phrase, intent, confidence=confidence, status='candidate', confirm_count=1)
        self._invalidate()


class _TfidfIndex:
    """One-shot TF-IDF index over a fixed list of pattern rows."""

    def __init__(self, patterns):
        self.patterns_by_id = {pattern['id']: pattern for pattern in patterns}
        self._idf = {}
        self._doc_vectors = {}
        self._doc_norms = {}
        self._build(patterns)

    def _build(self, patterns):
        doc_tokens = {}
        doc_frequency = Counter()
        for pattern in patterns:
            tokens = _tokenize(pattern.get('phrase', ''))
            doc_tokens[pattern['id']] = tokens
            for term in set(tokens):
                doc_frequency[term] += 1

        total = len(patterns) or 1
        self._idf = {
            term: math.log((total + 1) / (df + 1)) + 1
            for term, df in doc_frequency.items()
        }
        for pattern_id, tokens in doc_tokens.items():
            vector = self._tfidf_vector(tokens)
            self._doc_vectors[pattern_id] = vector
            self._doc_norms[pattern_id] = math.sqrt(sum(weight * weight for weight in vector.values())) or 1.0

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
            vector[term] = (count / max_count) * idf
        return vector

    def best_match(self, message, min_score):
        if not self._doc_vectors:
            return None
        query_tokens = _tokenize(message)
        query_vector = self._tfidf_vector(query_tokens)
        if not query_vector:
            return None
        query_norm = math.sqrt(sum(weight * weight for weight in query_vector.values())) or 1.0

        best_score, best_id = 0.0, None
        for pattern_id, doc_vector in self._doc_vectors.items():
            shared_terms = query_vector.keys() & doc_vector.keys()
            if not shared_terms:
                continue
            dot = sum(query_vector[term] * doc_vector[term] for term in shared_terms)
            score = dot / (query_norm * self._doc_norms[pattern_id])
            if score > best_score:
                best_score, best_id = score, pattern_id

        if best_id is None or best_score < min_score:
            return None
        return best_id, best_score


intent_pattern_cache = IntentPatternCache()
