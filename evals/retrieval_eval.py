"""Compare retrieval methods on the ground-truth cases in retrieval_cases.jsonl.

    python -m evals.retrieval_eval                          # every method
    python -m evals.retrieval_eval --methods tfidf,bm25     # keyword only, no model needed
    python -m evals.retrieval_eval --failures hybrid_rrf    # cases a method misses at k=4

Prints markdown tables and saves the full run (config, metrics, every case's ranked
list) to evals/results/ so runs can be compared over time.
"""
import argparse
import datetime
import json
import os
import subprocess
import time
from collections import defaultdict

from app.retrievers import (EMBED_MODEL, BM25Retriever, RRFRetriever, SemanticRetriever,
                            TfidfRetriever, WeightedRetriever, load_chunks)

from .retrieval_metrics import (hit_at_k, load_cases, precision_at_k, recall_at_k,
                                reciprocal_rank, resolve_relevant, search_query)

KS = (1, 2, 4, 8)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "evals", "results")

KEYWORD_METHODS = ["tfidf", "bm25"]
ALL_METHODS = KEYWORD_METHODS + ["semantic", "hybrid_rrf", "hybrid_rrf_tfidf",
                                 "hybrid_weighted_0.3", "hybrid_weighted_0.5",
                                 "hybrid_weighted_0.7"]
LEGEND = """\
- hybrid_rrf: RRF of BM25 + semantic; hybrid_rrf_tfidf: RRF of TF-IDF + semantic
- hybrid_weighted_a: a * BM25 + (1 - a) * semantic, scores min-max normalised"""


def build_methods(names, contextual=False, include_public=False):
    chunks = load_chunks(contextual=contextual, include_public=include_public)
    tfidf, bm25 = TfidfRetriever(chunks), BM25Retriever(chunks)
    methods = {"tfidf": tfidf, "bm25": bm25}
    if any(n not in KEYWORD_METHODS for n in names):
        sem = SemanticRetriever(chunks)
        methods["semantic"] = sem
        methods["hybrid_rrf"] = RRFRetriever([bm25, sem], name="hybrid_rrf")
        methods["hybrid_rrf_tfidf"] = RRFRetriever([tfidf, sem], name="hybrid_rrf_tfidf")
        for a in (0.3, 0.5, 0.7):
            name = "hybrid_weighted_%.1f" % a
            methods[name] = WeightedRetriever(bm25, sem, alpha=a, name=name)
    unknown = [n for n in names if n not in methods]
    if unknown:
        raise SystemExit("unknown method(s): %s. Choose from: %s"
                         % (", ".join(unknown), ", ".join(ALL_METHODS)))
    return chunks, {n: methods[n] for n in names}


def evaluate(method, cases, relevant):
    method.search("warm up", 1)   # first call loads lazily; keep it out of the timing
    rows = []
    for case in cases:
        t0 = time.perf_counter()
        hits = method.search(search_query(case), max(KS))
        ms = (time.perf_counter() - t0) * 1000
        retrieved = [h["chunk_id"] for h in hits]
        rel = relevant[case["id"]]
        row = {"id": case["id"], "split": case["split"], "category": case["category"],
               "defect": case.get("defect"), "query": case["query"],
               "relevant": sorted(rel), "retrieved": retrieved,
               "mrr": reciprocal_rank(retrieved, rel), "ms": ms}
        for k in KS:
            row["p@%d" % k] = precision_at_k(retrieved, rel, k)
            row["r@%d" % k] = recall_at_k(retrieved, rel, k)
            row["hit@%d" % k] = hit_at_k(retrieved, rel, k)
        rows.append(row)
    return rows


def mean_metrics(rows):
    keys = [m % k for m in ("r@%d", "p@%d", "hit@%d") for k in KS] + ["mrr", "ms"]
    out = {key: sum(r[key] for r in rows) / len(rows) for key in keys} if rows else {}
    out["n"] = len(rows)
    return out


# ---------- reporting ----------

def summary_table(results, split):
    cols = ["R@%d" % k for k in KS] + ["P@%d" % k for k in KS] + ["MRR", "ms/q"]
    lines = ["| method | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    n = None
    for name, rows in results.items():
        picked = [r for r in rows if split == "all" or r["split"] == split]
        m = mean_metrics(picked)
        n = m["n"]
        vals = (["%.2f" % m["r@%d" % k] for k in KS] + ["%.2f" % m["p@%d" % k] for k in KS]
                + ["%.2f" % m["mrr"], "%.2f" % m["ms"]])
        lines.append("| %s | %s |" % (name, " | ".join(vals)))
    return "### %s split (%d cases)\n\n" % (split, n) + "\n".join(lines)


def category_table(results, k=4):
    cats = sorted({r["category"] for rows in results.values() for r in rows})
    lines = ["| method | " + " | ".join(cats) + " |", "|---" * (len(cats) + 1) + "|"]
    for name, rows in results.items():
        vals = []
        for c in cats:
            picked = [r for r in rows if r["category"] == c]
            vals.append("%.2f" % (sum(r["r@%d" % k] for r in picked) / len(picked)))
        lines.append("| %s | %s |" % (name, " | ".join(vals)))
    return "### Recall@%d by question type (all splits)\n\n" % k + "\n".join(lines)


def failures(rows, k=4):
    out = []
    for r in rows:
        if r["r@%d" % k] < 1.0:
            missing = [c for c in r["relevant"] if c not in r["retrieved"][:k]]
            out.append("%s [%s] %r\n    missing: %s\n    top %d:  %s"
                       % (r["id"], r["category"], r["query"], ", ".join(missing), k,
                          ", ".join(r["retrieved"][:k]) or "(nothing)"))
    return "\n".join(out) or "(no misses)"


def _git():
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                      stderr=subprocess.DEVNULL).decode().strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT,
                                             stderr=subprocess.DEVNULL).strip())
        return {"sha": sha, "dirty": dirty}
    except Exception:
        return {"sha": "unknown", "dirty": None}


def save(results, chunks, names, contextual, corpus="plant"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    git = _git()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = ("_contextual" if contextual else "") + ("_all" if corpus == "all" else "")
    path = os.path.join(RESULTS_DIR, "retrieval_%s_%s%s.json" % (stamp, git["sha"], tag))
    payload = {
        "timestamp": stamp, "git": git, "ks": list(KS), "n_chunks": len(chunks),
        "contextual_chunks": contextual, "corpus": corpus,
        "embed_model": EMBED_MODEL if any(n not in KEYWORD_METHODS for n in names) else None,
        "methods": {
            name: {"summary": {s: mean_metrics([r for r in rows if s == "all" or r["split"] == s])
                               for s in ("dev", "test", "all")},
                   "cases": rows}
            for name, rows in results.items()},
    }
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=1)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--methods", default=",".join(ALL_METHODS),
                    help="comma-separated, from: " + ", ".join(ALL_METHODS))
    ap.add_argument("--failures", metavar="METHOD",
                    help="also list the cases this method misses at k=4")
    ap.add_argument("--contextual", action="store_true",
                    help="prefix every section with its document title before indexing")
    ap.add_argument("--corpus", choices=("plant", "all"), default="plant",
                    help="plant = the plant's rule book only; all = plus public OSHA/FAA docs")
    ap.add_argument("--no-save", action="store_true", help="do not write evals/results/")
    args = ap.parse_args()

    names = [n.strip() for n in args.methods.split(",") if n.strip()]
    chunks, methods = build_methods(names, contextual=args.contextual,
                                    include_public=args.corpus == "all")
    cases = load_cases()
    relevant = resolve_relevant(cases, chunks)

    results = {name: evaluate(m, cases, relevant) for name, m in methods.items()}

    print("## Retrieval eval: %d cases, %d chunks (corpus: %s), contextual headers %s\n"
          % (len(cases), len(chunks), args.corpus, "on" if args.contextual else "off"))
    print(LEGEND + "\n")
    for split in ("dev", "test"):
        print(summary_table(results, split) + "\n")
    print(category_table(results) + "\n")

    if args.failures:
        if args.failures not in results:
            raise SystemExit("--failures %s: that method was not run" % args.failures)
        print("### %s misses at k=4\n\n%s\n" % (args.failures, failures(results[args.failures])))

    if not args.no_save:
        print("saved %s" % os.path.relpath(save(results, chunks, names, args.contextual,
                                                args.corpus), ROOT))


if __name__ == "__main__":
    main()
