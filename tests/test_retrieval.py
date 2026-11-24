import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.retrievers import (BM25Retriever, Retriever, RRFRetriever,  # noqa: E402
                            TfidfRetriever, WeightedRetriever, load_chunks)
from evals.retrieval_metrics import (hit_at_k, load_cases, precision_at_k,  # noqa: E402
                                     recall_at_k, reciprocal_rank, resolve_relevant,
                                     search_query)


def _chunks(*texts):
    return [{"chunk_id": "c%d" % i, "source": "toy.md", "heading": "h", "text": t}
            for i, t in enumerate(texts)]


class Fixed(Retriever):
    """A retriever that returns preset scores, to test fusion on its own."""

    def __init__(self, chunks, scores, name="fixed"):
        super().__init__(chunks)
        self._scores, self.name = np.array(scores, dtype=float), name

    def scores(self, query):
        return self._scores


# ---------- keyword ----------

def test_bm25_matches_hand_computed_scores():
    # N=3, lengths 3/2/3, avgdl=8/3, df(crack)=2 -> idf=ln(1.6); k1=1.5, b=0.75
    # c0: tf=2 -> 0.4700 * 5 / (2 + 1.5 * (0.25 + 0.75 * 3 / (8/3))) = 0.6455
    # c2: tf=1 -> 0.4700 * 2.5 / (1 + 1.640625)                     = 0.4450
    bm25 = BM25Retriever(_chunks("crack crack scrap", "scratch polish", "crack polish rework"))
    assert bm25.scores("crack") == pytest.approx([0.6455, 0.0, 0.4450], abs=1e-4)
    assert [h["chunk_id"] for h in bm25.search("crack", 5)] == ["c0", "c2"]


def test_bm25_ignores_words_not_in_the_corpus():
    bm25 = BM25Retriever(_chunks("crack crack scrap", "scratch polish"))
    assert bm25.search("lubricant", 5) == []


def test_keyword_methods_share_stop_word_handling():
    chunks = _chunks("the crack is on the face", "polish the scratch")
    for r in (TfidfRetriever(chunks), BM25Retriever(chunks)):
        # 'the' and 'is' are stop words, so only 'crack' can match
        assert [h["chunk_id"] for h in r.search("is the crack", 5)] == ["c0"]


# ---------- fusion ----------

def test_rrf_sums_reciprocal_ranks():
    chunks = _chunks("a", "b", "c")
    a = Fixed(chunks, [3, 2, 1])       # ranks c0=1, c1=2, c2=3
    b = Fixed(chunks, [2, 0, 3])       # ranks c2=1, c0=2, c1 not matched
    rrf = RRFRetriever([a, b], k_rrf=60)
    assert rrf.scores("q") == pytest.approx([1 / 61 + 1 / 62, 1 / 62, 1 / 63 + 1 / 61])
    assert [h["chunk_id"] for h in rrf.search("q", 3)] == ["c0", "c2", "c1"]


def test_rrf_only_counts_each_retrievers_top_depth():
    chunks = _chunks("a", "b", "c")
    rrf = RRFRetriever([Fixed(chunks, [3, 2, 1])], k_rrf=60, depth=2)
    assert rrf.scores("q")[2] == 0.0


def test_weighted_fusion_alpha_picks_between_the_two_orders():
    chunks = _chunks("a", "b", "c")
    a = Fixed(chunks, [10, 5, 1])      # a prefers c0
    b = Fixed(chunks, [0.1, 0.2, 0.9])  # b prefers c2, on a different scale
    order = lambda alpha: [h["chunk_id"] for h in WeightedRetriever(a, b, alpha=alpha).search("q", 3)]
    assert order(1.0)[0] == "c0"
    assert order(0.0)[0] == "c2"
    assert len(order(0.5)) == 3        # the lowest candidate is kept, just ranked last


# ---------- metrics ----------

def test_ranking_metrics_on_a_toy_list():
    retrieved, relevant = ["a", "b", "c", "d"], {"b", "e"}
    assert precision_at_k(retrieved, relevant, 2) == 0.5
    assert recall_at_k(retrieved, relevant, 2) == 0.5
    assert recall_at_k(retrieved, relevant, 4) == 0.5
    assert hit_at_k(retrieved, relevant, 1) == 0.0
    assert hit_at_k(retrieved, relevant, 2) == 1.0
    assert reciprocal_rank(retrieved, relevant) == 0.5
    assert reciprocal_rank(["x"], relevant) == 0.0


def test_the_agent_query_includes_the_defect():
    assert search_query({"query": "Can I rework this?", "defect": "surface_scratch"}) \
        == "Can I rework this? surface scratch"
    assert search_query({"query": "Who do I call?", "defect": None}) == "Who do I call?"


# ---------- ground truth ----------

def test_every_label_phrase_matches_exactly_one_chunk():
    cases = load_cases()
    resolved = resolve_relevant(cases, load_chunks())   # raises on any bad label
    assert len(resolved) == len(cases)
    assert len({c["id"] for c in cases}) == len(cases), "duplicate case ids"
    assert {c["split"] for c in cases} == {"dev", "test"}


def test_a_bad_label_is_reported_not_skipped():
    chunks = _chunks("crack rule", "crack contacts")
    with pytest.raises(ValueError, match="matches 2 chunks"):
        resolve_relevant([{"id": "x", "relevant": ["crack"]}], chunks)
    with pytest.raises(ValueError, match="matches 0 chunks"):
        resolve_relevant([{"id": "y", "relevant": ["lubricant"]}], chunks)


def test_contextual_chunks_add_the_title_and_keep_the_ids():
    plain, ctx = load_chunks(), load_chunks(contextual=True)
    assert [c["chunk_id"] for c in plain] == [c["chunk_id"] for c in ctx]
    contacts = next(c for c in ctx if c["chunk_id"] == "escalation.md#Contacts")
    assert contacts["text"].startswith("# Escalation Contacts and Rules\n## Contacts")
    # labels still resolve, so plain and contextual runs are scored on the same truth
    resolve_relevant(load_cases(), ctx)


# ---------- semantic (only when the model is already downloaded) ----------

def _local_model():
    pytest.importorskip("sentence_transformers")
    from sentence_transformers import SentenceTransformer

    from app.retrievers import EMBED_MODEL
    try:
        SentenceTransformer(EMBED_MODEL, device="cpu", local_files_only=True)
    except Exception:
        pytest.skip("embedding model not downloaded yet; run the retrieval eval once")


def test_semantic_search_finds_a_crack_without_the_word_crack(tmp_path):
    _local_model()
    from app.retrievers import SemanticRetriever
    sem = SemanticRetriever(load_chunks(), cache_dir=str(tmp_path))
    top = [h["chunk_id"] for h in sem.search("Can a fractured housing still be used?", 4)]
    assert any(cid.endswith("Crack tolerance") or cid.endswith("Rule R1 - Crack") for cid in top)

