"""Ground-truth loading and ranking metrics for the retrieval eval.

A case lists `relevant` phrases copied from the knowledge docs rather than chunk ids,
so labels survive a change of chunking. A chunk is relevant if it contains one of the
phrases (case and line breaks ignored). Every phrase must match exactly one chunk:
a phrase that matches none or several is a labelling error, and loading stops.
"""
import json
import os

CASES_PATH = os.path.join(os.path.dirname(__file__), "retrieval_cases.jsonl")


def _norm(text):
    return " ".join(text.split()).lower()


def load_cases(path=CASES_PATH):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def resolve_relevant(cases, chunks):
    """Returns {case id: set of relevant chunk ids}. Raises ValueError listing every
    bad label at once, so a labelling mistake cannot quietly skew the numbers."""
    texts = [(c["chunk_id"], _norm(c["text"])) for c in chunks]
    resolved, errors = {}, []
    for case in cases:
        ids = set()
        for phrase in case["relevant"]:
            matches = [cid for cid, text in texts if _norm(phrase) in text]
            if len(matches) != 1:
                errors.append("%s: %r matches %d chunks %s"
                              % (case["id"], phrase, len(matches), matches))
            ids.update(matches)
        resolved[case["id"]] = ids
    if errors:
        raise ValueError("bad ground-truth labels:\n  " + "\n  ".join(errors))
    return resolved


def search_query(case):
    """The query the agent would send: it appends the classified defect."""
    if case.get("defect"):
        return case["query"] + " " + case["defect"].replace("_", " ")
    return case["query"]


# ---------- metrics on one ranked list ----------
# `retrieved` is a list of chunk ids, best first; `relevant` is a set of chunk ids.

def precision_at_k(retrieved, relevant, k):
    """Share of the k slots holding a relevant chunk. Capped by len(relevant) / k:
    with one relevant chunk, precision@8 can be at most 0.125."""
    return len(set(retrieved[:k]) & relevant) / float(k)


def recall_at_k(retrieved, relevant, k):
    """Share of the relevant chunks found in the top k."""
    return len(set(retrieved[:k]) & relevant) / float(len(relevant))


def hit_at_k(retrieved, relevant, k):
    """1 if at least one relevant chunk is in the top k."""
    return 1.0 if set(retrieved[:k]) & relevant else 0.0


def reciprocal_rank(retrieved, relevant):
    """1 / rank of the first relevant chunk, 0 if none was retrieved."""
    for rank, cid in enumerate(retrieved, start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


def average_precision_at_k(retrieved, relevant, k):
    """Precision at each rank (within the top k) where a relevant chunk appears,
    averaged over the relevant chunks. Unlike MRR it rewards finding *all* the
    relevant chunks near the top, not just the first; with one relevant chunk the two
    are the same. Averaged over questions this is MAP@k."""
    hits, total = 0, 0.0
    for rank, cid in enumerate(retrieved[:k], start=1):
        if cid in relevant:
            hits += 1
            total += hits / float(rank)
    return total / float(min(len(relevant), k))
