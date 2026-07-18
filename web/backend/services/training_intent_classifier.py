"""Small offline intent classifier trained from Bob's labelled cases."""

import math
from collections import Counter, defaultdict

from services.bob_training_cases import iter_labelled_cases
from services.knowledge_service import _tokenize


def _features(text):
    tokens = _tokenize(text)
    features = list(tokens)
    features.extend(f"{left}_{right}" for left, right in zip(tokens, tokens[1:]))
    return features


class TrainingIntentClassifier:
    """Balanced multinomial Naive Bayes classifier with no ML dependency."""

    def __init__(self, cases=None):
        self._counts = defaultdict(Counter)
        self._totals = Counter()
        self._documents = Counter()
        self._vocabulary = set()
        self._train(cases if cases is not None else iter_labelled_cases())

    def _train(self, cases):
        for case in cases:
            intent = case["intent"]
            features = _features(case["text"])
            self._counts[intent].update(features)
            self._totals[intent] += len(features)
            self._documents[intent] += 1
            self._vocabulary.update(features)

    @property
    def intents(self):
        return tuple(self._documents)

    def classify(self, text):
        features = _features(text)
        if not features or not self._documents:
            return None
        vocabulary_size = max(1, len(self._vocabulary))
        total_documents = sum(self._documents.values())
        scores = {}
        for intent, document_count in self._documents.items():
            score = math.log(document_count / total_documents)
            denominator = self._totals[intent] + vocabulary_size
            counts = self._counts[intent]
            for feature in features:
                score += math.log((counts.get(feature, 0) + 1) / denominator)
            scores[intent] = score

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_intent, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else best_score - 10
        # Normalize the log margin by message size.  This is intentionally a
        # conservative confidence: the trained fallback only routes when the
        # vocabulary provides a clear lead over the runner-up.
        margin = max(0.0, best_score - second_score) / max(1, len(features))
        confidence = 1.0 - math.exp(-margin)
        return {
            "intent": best_intent,
            "confidence": round(confidence, 4),
            "margin": round(best_score - second_score, 4),
        }


training_intent_classifier = TrainingIntentClassifier()
