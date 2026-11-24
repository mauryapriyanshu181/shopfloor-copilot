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


# ---------- how sure are we? ----------
# With ~50 queries one query moves recall by ~0.02, so a difference between two
# methods means little on its own. The bootstrap resamples the queries with
# replacement many times and reports where the mean lands 95% of the time.

def bootstrap_ci(values, n_boot=2000, seed=0, level=0.95):
    """(mean, low, high) of the mean of `values` over bootstrap resamples."""
    import numpy as np
    v = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = v[rng.integers(0, len(v), size=(n_boot, len(v)))].mean(axis=1)
    tail = (1 - level) / 2 * 100
    return float(v.mean()), float(np.percentile(means, tail)), float(np.percentile(means, 100 - tail))


def paired_comparison(a, b, n_boot=2000, seed=0):
    """Compare two methods on the same queries: per-query difference a - b.

    Returns the mean difference with its bootstrap interval, plus how many queries
    a won, tied and lost. If the interval includes 0, the data cannot tell the two
    methods apart."""
    diffs = [x - y for x, y in zip(a, b)]
    mean, low, high = bootstrap_ci(diffs, n_boot, seed)
    return {"diff": mean, "low": low, "high": high,
            "wins": sum(d > 0 for d in diffs), "ties": sum(d == 0 for d in diffs),
            "losses": sum(d < 0 for d in diffs)}
