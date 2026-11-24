import os

from .retrievers import KNOWLEDGE_DIR, build_retriever, load_chunks


class RagIndex:
    """The agent's view of the knowledge base. The search method is picked with the
    RETRIEVER environment variable (tfidf, bm25, semantic, hybrid_rrf,
    hybrid_weighted); evals/retrieval_eval.py compares them."""

    def __init__(self, path=KNOWLEDGE_DIR, method=None):
        self.method = method or os.environ.get("RETRIEVER", "tfidf")
        self.chunks = load_chunks(path)
        self.retriever = build_retriever(self.method, self.chunks)

    def search(self, query, k):
        return self.retriever.search(query, k)
