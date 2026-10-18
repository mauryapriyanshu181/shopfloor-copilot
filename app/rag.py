import glob
import os
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")


def _chunk(text):
    parts = [c.strip() for c in re.split(r"\n(?=## )", text)]
    return [c for c in parts if len(c) > 80]  # drop the title-only preamble


class RagIndex:
    def __init__(self, path=KNOWLEDGE_DIR):
        self.chunks = []
        for f in sorted(glob.glob(os.path.join(path, "*.md"))):
            with open(f) as fh:
                for c in _chunk(fh.read()):
                    self.chunks.append({"source": os.path.basename(f), "text": c})
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in self.chunks])

    def search(self, query, k):
        sims = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        ranked = sims.argsort()[::-1][:k]
        return [
            {"source": self.chunks[i]["source"], "text": self.chunks[i]["text"],
             "score": round(float(sims[i]), 3)}
            for i in ranked if sims[i] > 0.0
        ]
