import os

from .retrievers import KNOWLEDGE_DIR, build_retriever, load_chunks


class RagIndex:
    """The agent's view of the knowledge base.

    Defaults to semantic search over sections prefixed with their document title,
    the best setup in evals/retrieval_eval.py. RETRIEVER (tfidf, bm25, semantic,
    hybrid_rrf, hybrid_weighted) and CONTEXTUAL_CHUNKS=0/1 override it.

    The agent searches the plant's rule book only. The public OSHA/FAA corpus in
    corpus/ is an eval-only distractor set (evals/retrieval_eval.py --corpus all)."""

    def __init__(self, path=KNOWLEDGE_DIR, method=None, contextual=None):
        self.method = method or os.environ.get("RETRIEVER", "semantic")
        if contextual is None:
            contextual = os.environ.get("CONTEXTUAL_CHUNKS", "1") == "1"
        self.contextual = contextual
        self.chunks = load_chunks(path, contextual=contextual)
        self.retriever = build_retriever(self.method, self.chunks)

    def search(self, query, k):
        return self.retriever.search(query, k)
