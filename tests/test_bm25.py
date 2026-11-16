"""BM25: deterministic lexical retrieval."""
from governed_shared_memory.bm25 import BM25, tokenize


def test_tokenize_drops_stopwords():
    assert tokenize("The project deadline is 12 January") == [
        "project", "deadline", "12", "january",
    ]


def test_search_ranks_best_match_first():
    index = BM25([
        ("a", "project deadline is 12 January"),
        ("b", "conference budget is $800"),
        ("c", "project budget is $1200"),
    ])
    results = index.search("project deadline")
    assert results[0][0] == "a"
    assert results[0][1] > results[1][1]


def test_search_returns_nothing_for_unrelated_query():
    index = BM25([("a", "project deadline is 12 January")])
    assert index.search("quantum entanglement") == []


def test_search_respects_top_k():
    docs = [(f"d{i}", f"shared topic number {i}") for i in range(6)]
    index = BM25(docs)
    assert len(index.search("shared topic", top_k=3)) == 3


def test_empty_corpus_scores_zero():
    index = BM25([])
    assert index.search("anything") == []


def test_repeated_term_scores_higher():
    index = BM25([
        ("a", "deadline deadline deadline"),
        ("b", "deadline"),
    ])
    results = index.search("deadline")
    assert results[0][0] == "a"
