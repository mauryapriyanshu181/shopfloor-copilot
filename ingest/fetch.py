"""Download the public reference documents listed in corpus/sources.json.

    python -m ingest.fetch            # download what is missing or changed
    python -m ingest.fetch --force    # download everything again

Raw files go to corpus/raw/ (not committed: the FAA PDF alone is ~21 MB). What was
downloaded, when, and its SHA-256 go to corpus/manifest.json (committed), so a parse
can always be traced back to the exact bytes it came from. A source whose file is
already on disk with the checksum recorded in the manifest is skipped.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "corpus")
RAW_DIR = os.path.join(CORPUS, "raw")
SOURCES_PATH = os.path.join(CORPUS, "sources.json")
MANIFEST_PATH = os.path.join(CORPUS, "manifest.json")

EXTENSIONS = {"ecfr_xml": "xml", "pdf": "pdf"}
HEADERS = {"User-Agent": "shopfloor-copilot-ingest/0.1"}   # requests also asks for gzip


def load_sources():
    with open(SOURCES_PATH) as fh:
        config = json.load(fh)
    for s in config["sources"]:
        s["url"] = s["url"].format(ecfr_date=config.get("ecfr_date", ""))
        s["file"] = "%s.%s" % (s["id"], EXTENSIONS[s["format"]])
    return config["sources"]


def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {}
    with open(MANIFEST_PATH) as fh:
        return {m["id"]: m for m in json.load(fh)}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(source, force=False, manifest=None):
    """Download one source unless an identical copy is already on disk.
    Returns its manifest entry."""
    path = os.path.join(RAW_DIR, source["file"])
    known = (manifest or {}).get(source["id"])
    if not force and known and os.path.exists(path) and sha256(path) == known["sha256"] \
            and known["url"] == source["url"]:
        print("  %-22s unchanged, skipped" % source["id"])
        return known

    resp = requests.get(source["url"], headers=HEADERS, timeout=300)
    resp.raise_for_status()
    if not resp.content:
        raise ValueError("%s: empty response" % source["id"])
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(resp.content)
    entry = {"id": source["id"], "file": source["file"], "url": source["url"],
             "bytes": len(resp.content), "sha256": sha256(path),
             "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
             "license": source["license"]}
    print("  %-22s %8.1f KB  %s" % (source["id"], entry["bytes"] / 1024.0, entry["sha256"][:12]))
    return entry


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="download even if unchanged")
    args = ap.parse_args()

    manifest = load_manifest()
    entries = []
    for source in load_sources():
        try:
            entries.append(fetch(source, args.force, manifest))
        except Exception as exc:
            sys.exit("failed on %s: %s" % (source["id"], exc))
    with open(MANIFEST_PATH, "w") as fh:
        json.dump(entries, fh, indent=1)
    print("manifest written: %s" % os.path.relpath(MANIFEST_PATH, ROOT))


if __name__ == "__main__":
    main()
