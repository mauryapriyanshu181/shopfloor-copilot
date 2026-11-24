"""Retrieval methods over the knowledge base, all behind one interface.

Every retriever scores every chunk for a query (`scores`) and the shared `search`
turns that into the top-k hits. Keyword methods give unrelated chunks a score of 0,
which `search` drops; semantic search gives every chunk some similarity, so it always
returns k hits. The hybrid methods combine a keyword and a semantic retriever.
"""
import glob
import hashlib
import math
import os
import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")   # scikit-learn's default token pattern

EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
# bge models are trained to see this instruction in front of short search queries
# (not in front of the passages being searched)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


# ---------- corpus ----------

def tokenize(text):
    """Shared by TF-IDF and BM25 so the keyword comparison is like for like."""
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in ENGLISH_STOP_WORDS]


def chunk_markdown(text):
    """One chunk per '## ' section; the title-only preamble is dropped."""
    parts = [c.strip() for c in re.split(r"\n(?=## )", text)]
    return [c for c in parts if len(c) > 80]


def load_chunks(path=KNOWLEDGE_DIR):
    chunks = []
    for f in sorted(glob.glob(os.path.join(path, "*.md"))):
        source = os.path.basename(f)
        with open(f) as fh:
            for text in chunk_markdown(fh.read()):
                heading = text.splitlines()[0].lstrip("# ").strip()
                chunks.append({"chunk_id": "%s#%s" % (source, heading),
                               "source": source, "heading": heading, "text": text})
    return chunks


# ---------- base ----------

class Retriever:
    name = "base"

    def __init__(self, chunks):
        self.chunks = chunks

    def scores(self, query):
        """One score per chunk, higher is better, 0 means no match."""
        raise NotImplementedError

    @staticmethod
    def _order(s):
        """Indices of chunks with a positive score, best first. Ties keep corpus order."""
        return [int(i) for i in np.argsort(-s, kind="stable") if s[i] > 0]

    def ranked(self, query, depth=None):
        order = self._order(self.scores(query))
        return order[:depth] if depth else order

    def search(self, query, k):
        s = self.scores(query)
        return [{"chunk_id": self.chunks[i]["chunk_id"], "source": self.chunks[i]["source"],
                 "text": self.chunks[i]["text"], "score": round(float(s[i]), 4)}
                for i in self._order(s)[:k]]


# ---------- keyword ----------

class TfidfRetriever(Retriever):
    name = "tfidf"

    def __init__(self, chunks):
        super().__init__(chunks)
        self.vectorizer = TfidfVectorizer(tokenizer=tokenize, lowercase=False, token_pattern=None)
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in chunks])

    def scores(self, query):
        # rows are L2-normalised, so the dot product is the cosine similarity
        return (self.matrix @ self.vectorizer.transform([query]).T).toarray().ravel()


class BM25Retriever(Retriever):
    """Okapi BM25.

    score(q, d) = sum over query terms t of
        idf(t) * tf(t, d) * (k1 + 1) / (tf(t, d) + k1 * (1 - b + b * |d| / avgdl))

    k1 caps how much repeating a term keeps helping (term-frequency saturation);
    b sets how much longer chunks are penalised. idf uses the Lucene form
    log(1 + (N - n + 0.5) / (n + 0.5)), which stays positive for very common terms.
    """
    name = "bm25"

    def __init__(self, chunks, k1=1.5, b=0.75):
        super().__init__(chunks)
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c["text"])) for c in chunks]
        self.lengths = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.avgdl = float(self.lengths.mean())
        n = len(self.docs)
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        self.idf = {t: math.log(1 + (n - df_t + 0.5) / (df_t + 0.5)) for t, df_t in df.items()}

    def scores(self, query):
        out = np.zeros(len(self.docs))
        norm = self.k1 * (1 - self.b + self.b * self.lengths / self.avgdl)
        for term in tokenize(query):
            if term not in self.idf:
                continue
            tf = np.array([d.get(term, 0) for d in self.docs], dtype=float)
            out += self.idf[term] * tf * (self.k1 + 1) / (tf + norm)
        return out


# ---------- semantic ----------

class SemanticRetriever(Retriever):
    """Dense retrieval: cosine similarity between bge embeddings.

    Chunk embeddings are cached in data/ keyed by model name and corpus text, so they
    are only recomputed when a document changes. Runs on CPU so results are the same
    on every machine; the corpus is small enough that this costs nothing noticeable.
    """
    name = "semantic"

    def __init__(self, chunks, model_name=EMBED_MODEL, cache_dir=CACHE_DIR):
        super().__init__(chunks)
        from sentence_transformers import SentenceTransformer  # heavy import, only when used
        self.model = SentenceTransformer(model_name, device="cpu")
        self.matrix = self._chunk_embeddings(model_name, cache_dir)

    def _chunk_embeddings(self, model_name, cache_dir):
        digest = hashlib.sha1(model_name.encode())
        for c in self.chunks:
            digest.update(c["text"].encode())
        path = os.path.join(cache_dir, "embeddings_%s.npy" % digest.hexdigest()[:12])
        if os.path.exists(path):
            return np.load(path)
        matrix = self.model.encode([c["text"] for c in self.chunks],
                                   normalize_embeddings=True, convert_to_numpy=True)
        os.makedirs(cache_dir, exist_ok=True)
        np.save(path, matrix)
        return matrix

    def scores(self, query):
        q = self.model.encode([QUERY_PREFIX + query], normalize_embeddings=True,
                              convert_to_numpy=True)[0]
        return self.matrix @ q


# ---------- hybrid ----------

class RRFRetriever(Retriever):
    """Reciprocal Rank Fusion: score(d) = sum over retrievers of 1 / (k_rrf + rank(d)).

    Only ranks are used, so it does not matter that BM25 scores and cosine
    similarities are on different scales. Each retriever contributes its top `depth`
    matches; a chunk outside every list scores 0.
    """

    def __init__(self, retrievers, k_rrf=60, depth=20, name=None):
        super().__init__(retrievers[0].chunks)
        self.retrievers, self.k_rrf, self.depth = retrievers, k_rrf, depth
        self.name = name or "rrf(%s)" % "+".join(r.name for r in retrievers)

    def scores(self, query):
        fused = np.zeros(len(self.chunks))
        for r in self.retrievers:
            for rank, i in enumerate(r.ranked(query, self.depth), start=1):
                fused[i] += 1.0 / (self.k_rrf + rank)
        return fused


class WeightedRetriever(Retriever):
    """Score fusion: alpha * norm(a) + (1 - alpha) * norm(b).

    Scores are min-max normalised to 0-1 over the candidate set (the union of each
    retriever's top `depth`), because raw BM25 scores and cosine similarities are
    not comparable. Chunks outside the candidate set score 0.
    """

    def __init__(self, a, b, alpha=0.5, depth=20, name=None):
        super().__init__(a.chunks)
        self.a, self.b, self.alpha, self.depth = a, b, alpha, depth
        self.name = name or "weighted(%s+%s, a=%.1f)" % (a.name, b.name, alpha)

    @staticmethod
    def _normalise(s, idx):
        vals = s[idx]
        lo, hi = vals.min(), vals.max()
        return np.ones_like(vals) if hi == lo else (vals - lo) / (hi - lo)

    def scores(self, query):
        sa, sb = self.a.scores(query), self.b.scores(query)
        idx = sorted(set(self.a.ranked(query, self.depth)) | set(self.b.ranked(query, self.depth)))
        fused = np.zeros(len(self.chunks))
        if not idx:
            return fused
        idx = np.array(idx)
        fused[idx] = (self.alpha * self._normalise(sa, idx)
                      + (1 - self.alpha) * self._normalise(sb, idx))
        # a candidate that scored the minimum in both lists would fuse to exactly 0
        # and be dropped as a non-match; keep it in, just last
        fused[idx] = np.maximum(fused[idx], 1e-9)
        return fused


# ---------- factory ----------

METHODS = ("tfidf", "bm25", "semantic", "hybrid_rrf", "hybrid_weighted")


def build_retriever(method, chunks):
    if method == "tfidf":
        return TfidfRetriever(chunks)
    if method == "bm25":
        return BM25Retriever(chunks)
    if method == "semantic":
        return SemanticRetriever(chunks)
    if method == "hybrid_rrf":
        return RRFRetriever([BM25Retriever(chunks), SemanticRetriever(chunks)], name="hybrid_rrf")
    if method == "hybrid_weighted":
        alpha = float(os.environ.get("HYBRID_ALPHA", "0.5"))
        return WeightedRetriever(BM25Retriever(chunks), SemanticRetriever(chunks),
                                 alpha=alpha, name="hybrid_weighted")
    raise ValueError("unknown retriever '%s', expected one of %s" % (method, ", ".join(METHODS)))
