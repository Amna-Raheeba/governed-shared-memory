"""Pure-Python BM25 retrieval over memory texts.

No embeddings, no network: retrieval is lexical, deterministic, and
fast enough for the memory sizes this library targets (hundreds to
low thousands of records). The same scorer is used by the store's
``search`` and by the evaluation harness, so retrieval numbers are
reproducible from the same code path.
"""
from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[a-z0-9']+")

STOPWORDS = {
    "a", "an", "the", "in", "of", "for", "and", "or", "to", "on", "with",
    "by", "at", "from", "was", "were", "are", "is", "be", "been", "than",
    "that", "this", "it", "its", "as", "into", "both", "when", "while",
    "what", "which", "who", "how", "does", "do", "did", "not", "no",
}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


class BM25:
    """BM25 (k1=1.5, b=0.75) over a fixed corpus of (doc_id, text) pairs."""

    def __init__(self, docs: list[tuple[str, str]], k1: float = 1.5,
                 b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self.doc_lens: list[int] = []
        self.term_freqs: list[Counter] = []
        self.doc_freq: Counter = Counter()
        for doc_id, text in docs:
            toks = tokenize(text)
            self.doc_ids.append(doc_id)
            self.doc_lens.append(max(len(toks), 1))
            tf = Counter(toks)
            self.term_freqs.append(tf)
            for term in tf:
                self.doc_freq[term] += 1
        self.n_docs = len(docs)
        self.avg_len = (
            sum(self.doc_lens) / self.n_docs if self.n_docs else 1.0
        )

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        # Robertson idf with +1 floor so unseen terms score 0, not negative.
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    def score(self, query: str, index: int) -> float:
        q_terms = tokenize(query)
        if not q_terms or index >= self.n_docs:
            return 0.0
        tf = self.term_freqs[index]
        doc_len = self.doc_lens[index]
        total = 0.0
        for term in set(q_terms):
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = self._idf(term)
            denom = freq + self.k1 * (1 - self.b + self.b * doc_len / self.avg_len)
            total += idf * freq * (self.k1 + 1) / denom
        return total

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Return [(doc_id, score)] sorted by score desc, score > 0 only."""
        scored = [
            (self.doc_ids[i], self.score(query, i))
            for i in range(self.n_docs)
        ]
        scored = [(d, s) for d, s in scored if s > 0]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:top_k]
