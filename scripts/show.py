"""Print an /inspect response in a readable form instead of raw JSON.

    curl -s -X POST localhost:8000/inspect -F "query=..." -F "image=@..." | python scripts/show.py
    python scripts/show.py saved_response.json
"""
import json
import sys
import textwrap


def main():
    source = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
    d = json.load(source)
    if "steps" not in d:
        print(json.dumps(d, indent=2))
        return

    facts = d.get("facts", {})
    defect = facts.get("defect")
    print()
    if defect:
        print("DEFECT     : %s  (confidence %.2f)" % (defect["category"], defect["confidence"]))
        print("EVIDENCE   : %s" % defect["evidence"])
    else:
        print("DEFECT     : photo not inspected")
    if facts.get("work_order_id"):
        print("WORK ORDER : %s" % facts["work_order_id"])
    cfg = d.get("config", {})
    print("SETUP      : %s, %s search, top %s" % (cfg.get("model"), cfg.get("retriever"),
                                                  cfg.get("top_k")))

    print("\nSTEPS")
    for i, step in enumerate(d["steps"], 1):
        print("  %d. %s %s" % (i, step.get("tool"), json.dumps(step.get("args", {}))))
        if step.get("thought"):
            print("     %s" % step["thought"][:100])
        if step.get("error"):
            print("     error: %s" % step["error"])

    if d.get("escalation"):
        e = d["escalation"]
        print("\nESCALATION (proposed, not done)")
        print("  to %s, status=%s, executed=%s" % (e["to"], e["status"], e["executed"]))

    print("\nANSWER")
    for line in textwrap.wrap(" ".join(d["answer"].split()), 86):
        print("  " + line)
    if d.get("sources"):
        print("\nSOURCES    : %s" % ", ".join(d["sources"]))
    print("\nTOOK %.2fs, %d model call(s)   id %s\n"
          % (d["latency_s"], len(d.get("llm_calls", [])), d["transaction_id"]))


if __name__ == "__main__":
    main()
