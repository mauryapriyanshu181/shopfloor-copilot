"""Drive the running API with repeated inspections + simulated supervisor feedback,
and print how the bandit's chosen top-K shifts per defect category.

Feedback rule: helpful (1) only if the retrieved chunks cover every SOP document a
supervisor would need to action that defect, else 0. Different defects need different
amounts of context, which is the signal the contextual bandit has to pick up.
"""
import os
import sys

import requests

API = os.environ.get("API", "http://localhost:8000")
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 24
SAMPLES = os.path.join(os.path.dirname(__file__), "..", "samples")

CASES = [
    ("part_crack.png", "Is this part within tolerance?",
     {"rework_vs_scrap.md", "escalation.md"}),
    ("part_scratch.png", "Can I release this or does it need rework?",
     {"tolerances.md"}),
    ("part_dimensional.png", "Do I scrap this or re-machine it?",
     {"rework_vs_scrap.md", "tolerances.md"}),
]


def retrieved_sources(tx):
    out = set()
    for step in tx["decision_trace"]:
        obs = step.get("observation")
        if isinstance(obs, dict) and "chunks" in obs:
            out.update(c["source"] for c in obs["chunks"])
    return out


def main():
    for i in range(ROUNDS):
        name, query, expected = CASES[i % len(CASES)]
        with open(os.path.join(SAMPLES, name), "rb") as fh:
            tx = requests.post(API + "/inspect", data={"query": query},
                               files={"image": fh}).json()

        score = 1 if expected <= retrieved_sources(tx) else 0
        fb = requests.post(API + "/feedback",
                           json={"transaction_id": tx["transaction_id"], "score": score}).json()
        print("%2d  %-22s k=%s %-18s latency=%5.2fs score=%d reward=%s"
              % (i + 1, tx["defect_category"], tx["config"]["rag_top_k"],
                 tx["config"]["bandit_mode"], tx["latency_s"], score, fb.get("reward")))

    print("\nfinal bandit table:")
    for state, arms in requests.get(API + "/bandit").json()["stats"].items():
        if any(a["n"] == 0 for a in arms.values()):
            verdict = "still trying"          # no result yet, do not claim a winner
        else:
            ranked = sorted(arms, key=lambda k: arms[k]["mean"], reverse=True)
            lead = arms[ranked[0]]["mean"] - arms[ranked[1]]["mean"]
            verdict = ("best k=%s" % ranked[0]) if lead > 1 else "too close to call"
        print("  %-22s %s   -> %s" % (state, arms, verdict))


if __name__ == "__main__":
    main()
