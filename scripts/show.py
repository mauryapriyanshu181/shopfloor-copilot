"""Print an /inspect response in a readable form instead of raw JSON.

    curl -s -X POST localhost:8000/inspect -F "query=..." -F "image=@..." | python scripts/show.py
    python scripts/show.py saved_response.json
"""
import json
import sys
import textwrap


ORDER = ["crack", "dimensional_deviation", "surface_scratch", "no_defect",
         "no_image_supplied"]


def print_scoreboard(d):
    actions = [str(a) for a in d["actions"]]
    stats = d["stats"]
    print("\n  situation              " + "".join("k=%-13s" % a for a in actions) + "settles on")
    print("  " + "-" * (23 + 15 * len(actions) + 12))
    for state in ORDER + [s for s in stats if s not in ORDER]:
        if state not in stats:
            continue
        arms = stats[state]
        cells = ""
        for a in actions:
            v = arms[a]
            cells += "%-15s" % ("-" if v["n"] == 0 else "%+.2f (n=%d)" % (v["mean"], v["n"]))
        tried = all(arms[a]["n"] > 0 for a in actions)
        if not tried:
            verdict = "still trying"
        else:
            ranked = sorted(actions, key=lambda a: arms[a]["mean"], reverse=True)
            lead = arms[ranked[0]]["mean"] - arms[ranked[1]]["mean"]
            verdict = "k=%s" % ranked[0] if lead > 1 else "too close to call"
        print("  %-22s %s%s" % (state, cells, verdict))
    print()


def main():
    source = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
    d = json.load(source)

    if "stats" in d and "actions" in d:
        print_scoreboard(d)
        return

    if "decision_trace" not in d:
        print(json.dumps(d, indent=2))
        return

    cfg = d.get("config", {})
    defect = d.get("defect_detail")
    ocr = d.get("ocr")

    print()
    if defect:
        print("DEFECT     : %s  (confidence %.2f)" % (defect["category"], defect["confidence"]))
        print("EVIDENCE   : %s" % defect["evidence"])
    else:
        print("DEFECT     : no photo supplied")

    if ocr and ocr.get("work_order_id"):
        print("WORK ORDER : %s  (read off the part)" % ocr["work_order_id"])
    elif d.get("work_order_id"):
        print("WORK ORDER : %s  (supplied with the request)" % d["work_order_id"])

    print("SETTINGS   : %s paragraphs, picked by %s" % (cfg.get("rag_top_k"), cfg.get("bandit_mode")))
    print("MODEL      : %s" % cfg.get("llm_model"))

    print("\nWHAT IT DID")
    for step in d["decision_trace"]:
        print("  %d. %-24s [%s]" % (step["step"], step["tool"], step["planner"]))
        if step.get("thought"):
            print("     %s" % step["thought"][:100])
        if step.get("fallback_reason"):
            print("     fell back: %s" % step["fallback_reason"])

    action = d.get("proposed_action")
    if action:
        print("\nPROPOSED, NOT DONE")
        print("  %s -> %s" % (action["type"], action["contact"]))
        print("  status=%s  executed=%s" % (action["status"], action["executed"]))

    print("\nANSWER")
    for line in textwrap.wrap(" ".join(d["answer"].split()), 86):
        print("  " + line)

    print("\nTOOK %.2fs   id %s\n" % (d["latency_s"], d["transaction_id"]))


if __name__ == "__main__":
    main()
