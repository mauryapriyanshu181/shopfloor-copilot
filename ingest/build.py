"""Parse the raw downloads, cut them into chunks, check the result, write the corpus.

    python -m ingest.build

Reads corpus/raw/ (see ingest/fetch.py), writes:
    corpus/chunks.jsonl          one chunk per line: id, text, heading, citation, source...
    corpus/quality_report.json   counts and problems found, per source

Chunking: consecutive blocks of the same section (an OSHA top-level paragraph such as
1910.147(c), or an FAA numbered paragraph such as 4-58) are packed together up to
TARGET_WORDS. A block longer than that is split at sentence ends (or at table rows).
A small leftover at the end of a section is merged into the chunk before it.

The embedding model reads at most 512 tokens and silently ignores the rest, so a chunk
over HARD_MAX_WORDS (~380 words, safely under 512 tokens) stops the build.
"""
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

from .fetch import CORPUS, RAW_DIR, ROOT, load_sources
from .parse import parse_ecfr, parse_faa

CHUNKS_PATH = os.path.join(CORPUS, "chunks.jsonl")
REPORT_PATH = os.path.join(CORPUS, "quality_report.json")

TARGET_WORDS = 250
MIN_WORDS = 40
HARD_MAX_WORDS = 380


def _words(text):
    return len(text.split())


def _split_long(block):
    """Pieces of one over-long block, each under TARGET_WORDS where possible."""
    text = block["text"]
    parts = text.split("\n") if block.get("kind") == "table" else \
        re.split(r"(?<=[.;:])\s+(?=[A-Z(])", text)
    pieces, current = [], []
    for part in parts:
        if current and _words(" ".join(current + [part])) > TARGET_WORDS:
            pieces.append(" ".join(current))
            current = []
        current.append(part)
    if current:
        pieces.append(" ".join(current))
    # a single sentence over the limit (rare): hard cut by words
    out = []
    for p in pieces:
        w = p.split()
        while len(w) > TARGET_WORDS:
            out.append(" ".join(w[:TARGET_WORDS]))
            w = w[TARGET_WORDS:]
        out.append(" ".join(w))
    return [dict(block, text=p) for p in out if p.strip()]


def _group_key(block):
    """Blocks that may share a chunk: same section and, for OSHA, the same
    top-level paragraph letter."""
    top = re.match(r"^\(([a-z])\)", block["path"] or "")
    return (block["source"], block["section"], top.group(1) if top else block["path"])


def chunk_blocks(blocks):
    groups = defaultdict(list)
    order = []
    for b in blocks:
        key = _group_key(b)
        if key not in groups:
            order.append(key)
        for piece in (_split_long(b) if _words(b["text"]) > TARGET_WORDS else [b]):
            groups[key].append(piece)

    chunks, merged = [], 0
    for key in order:
        packs = []
        for b in groups[key]:
            if packs and _words(" ".join(x["text"] for x in packs[-1] + [b])) <= TARGET_WORDS:
                packs[-1].append(b)
            else:
                packs.append([b])
        if len(packs) > 1 and sum(_words(x["text"]) for x in packs[-1]) < MIN_WORDS:
            tail = packs.pop()
            packs[-1].extend(tail)
            merged += 1
        for pack in packs:
            first = pack[0]
            chunks.append({
                "source": first["source"], "doc_title": first["doc_title"],
                "heading": first["heading"].strip(), "citation": first["citation"].strip(),
                "url": first["url"],
                "body": "\n".join(x["text"] for x in pack),
                # osha-1910.147#(c)(4), faa-ac43.13-1b#4-58; appendices use their section
                "anchor": first["path"] if (first["path"] or "").startswith("(") else first["section"],
            })
    return chunks, merged


def _assign_ids(chunks):
    seen = Counter()
    for c in chunks:
        base = "%s#%s" % (c["source"], c.pop("anchor"))
        seen[base] += 1
        c["chunk_id"] = base if seen[base] == 1 else "%s~%d" % (base, seen[base])
        c["text"] = "## %s\n%s" % (c["heading"], c.pop("body"))
        c["words"] = _words(c["text"])
    return chunks


MIN_BODY_WORDS = 10      # below this a chunk is a heading with no rule in it
MIN_LETTER_SHARE = 0.2   # below this a chunk is a table of numbers, useless for search


def _letter_share(text):
    return sum(ch.isalpha() for ch in text) / float(max(1, len(text)))


def _table_like(text):
    """Probably a table, or text that came out of the PDF badly: kept, but reported."""
    tokens = text.split()
    lone = sum(len(t) == 1 and t.isalpha() and t not in ("a", "A", "I") for t in tokens)
    return _letter_share(text) < 0.5 or lone > 0.15 * max(1, len(tokens))


def drop_unusable(chunks):
    """Heading-only fragments and number-only tables carry nothing a question can match."""
    kept, tiny, numeric = [], [], []
    for c in chunks:
        body = c["text"].split("\n", 1)[-1]
        if _words(body) < MIN_BODY_WORDS:
            tiny.append(c["chunk_id"])
        elif _letter_share(body) < MIN_LETTER_SHARE:
            numeric.append(c["chunk_id"])
        else:
            kept.append(c)
    return kept, tiny, numeric


def quality_check(chunks):
    """Hard problems stop the build; soft ones are reported."""
    errors, report = [], {}
    by_source = defaultdict(list)
    for c in chunks:
        by_source[c["source_id"]].append(c)
        if not c["text"].strip():
            errors.append("%s: empty chunk" % c["chunk_id"])
        if c["words"] > HARD_MAX_WORDS:
            errors.append("%s: %d words, over the embedding limit of ~%d"
                          % (c["chunk_id"], c["words"], HARD_MAX_WORDS))
        if not c.get("citation") or not c.get("url"):
            errors.append("%s: no citation or url" % c["chunk_id"])
    ids = Counter(c["chunk_id"] for c in chunks)
    errors += ["%s: duplicate chunk id" % i for i, n in ids.items() if n > 1]

    for source_id, items in by_source.items():
        words = [c["words"] for c in items]
        report[source_id] = {
            "chunks": len(items),
            "words": {"total": sum(words), "min": min(words),
                      "median": statistics.median(words), "max": max(words)},
            "table_like": [c["chunk_id"] for c in items if _table_like(c["text"])],
        }
    return errors, report


def drop_duplicates(chunks):
    seen, kept, dropped = set(), [], []
    for c in chunks:
        key = " ".join(c["text"].split("\n", 1)[-1].lower().split())
        if key in seen:
            dropped.append(c["chunk_id"])
            continue
        seen.add(key)
        kept.append(c)
    return kept, dropped


def build():
    all_chunks, parse_info = [], {}
    for source in load_sources():
        path = os.path.join(RAW_DIR, source["file"])
        if not os.path.exists(path):
            sys.exit("missing %s: run python -m ingest.fetch first" % os.path.relpath(path, ROOT))
        if source["format"] == "ecfr_xml":
            with open(path, "rb") as fh:
                blocks, info = parse_ecfr(fh.read(), source), {}
        else:
            blocks, info = parse_faa(path, source)
        chunks, merged = chunk_blocks(blocks)
        if not chunks:
            sys.exit("%s produced no chunks" % source["id"])
        for c in chunks:
            c["source_id"], c["license"] = source["id"], source["license"]
        all_chunks += _assign_ids(chunks)
        parse_info[source["id"]] = dict(info, blocks=len(blocks), small_tails_merged=merged)

    all_chunks, duplicates = drop_duplicates(all_chunks)
    all_chunks, tiny, numeric = drop_unusable(all_chunks)
    errors, report = quality_check(all_chunks)
    for source_id, info in parse_info.items():
        report.setdefault(source_id, {}).update(info)
    report["_totals"] = {"chunks": len(all_chunks), "duplicates_dropped": duplicates,
                         "heading_only_dropped": tiny, "number_tables_dropped": numeric,
                         "target_words": TARGET_WORDS, "hard_max_words": HARD_MAX_WORDS}
    with open(REPORT_PATH, "w") as fh:
        json.dump(report, fh, indent=1)
    if errors:
        sys.exit("quality check failed:\n  " + "\n  ".join(errors[:50]))

    with open(CHUNKS_PATH, "w") as fh:
        for c in all_chunks:
            fh.write(json.dumps({k: c[k] for k in ("chunk_id", "source", "source_id", "doc_title",
                                                   "heading", "text", "citation", "url",
                                                   "license", "words")}) + "\n")

    print("%-22s %7s %7s %7s %7s %11s" % ("source", "chunks", "median", "max", "words", "table-like"))
    for source_id, r in report.items():
        if source_id.startswith("_"):
            continue
        print("%-22s %7d %7d %7d %7d %11d" % (source_id, r["chunks"], r["words"]["median"],
                                               r["words"]["max"], r["words"]["total"],
                                               len(r["table_like"])))
    print("total %d chunks; dropped %d exact duplicates, %d heading-only, %d number tables"
          % (len(all_chunks), len(duplicates), len(tiny), len(numeric)))
    print("wrote %s and %s" % (os.path.relpath(CHUNKS_PATH, ROOT), os.path.relpath(REPORT_PATH, ROOT)))


if __name__ == "__main__":
    build()
