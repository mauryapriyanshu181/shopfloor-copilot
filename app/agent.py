"""ShopFloor Copilot agent: a small tool-calling loop.

Each turn the model sees the worker's question, everything learned so far, and the
tools it may still use. It replies with one JSON object: call a tool, or finish with
an answer or an escalation. An escalation is only proposed; a supervisor signs it.

Each tool runs at most once, and a tool that cannot help (looking at a photo that
was never sent) is not offered. Small models otherwise repeat themselves.
"""
import json
import re

from . import llm, ocr, vision

MAX_STEPS = 5
TOP_K = 4   # retrieval eval (300 questions): hybrid search finds ~89% of relevant sections at k=4; k=8 adds ~6%

MOCK_WORK_ORDERS = {
    "WO-1042": {"status": "in_process", "part": "P-series housing", "qty": 50,
                "machine": "CNC-07", "open_ncr": False},
    "WO-2381": {"status": "on_hold", "part": "injection cover", "qty": 120,
                "machine": "IM-02", "open_ncr": True},
}

TOOLS = {
    "inspect_photo": "inspect_photo() - find the defect in the attached photo and read the "
                     "work order stamped on the part",
    "search_rules": "search_rules(query) - search the plant's SOPs, tolerances and "
                    "escalation rules",
    "lookup_work_order": "lookup_work_order(work_order_id) - get the work order's status "
                         "from the ERP",
}
FINISH = {
    "answer": "answer(text) - reply to the worker; name the document each rule comes from",
    "escalate": "escalate(reason) - hand the part to the shift supervisor; nothing is "
                "actioned until they sign",
}

PROMPT = """You are ShopFloor Copilot, a quality assistant on a machining shop floor.
Decide the next step. Reply with ONE JSON object and nothing else:
{{"thought": "<one sentence>", "tool": "<tool name>", "args": {{...}}}}

Tools you can use now:
{tools}

Worker question: {question}
Photo attached: {has_photo}

What you know so far:
{facts}

Rule passages found:
{passages}

Guidelines:
- If a photo is attached, inspect it before judging the part.
- Base every claim on the rule passages and name the document it comes from.
- Scrap and stop-the-line decisions are not yours to make: escalate them.
"""


def _parse(text):
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None
    try:
        obj = json.loads(match.group())
    except ValueError:
        return None
    if not isinstance(obj, dict) or "tool" not in obj:
        return None
    if not isinstance(obj.get("args"), dict):
        obj["args"] = {}
    return obj


class Agent:
    def __init__(self, rag):
        self.rag = rag

    # ---------- tools ----------

    def _inspect_photo(self, state, args):
        state["defect"] = vision.classify(state["image"])
        state["ocr"] = ocr.extract(state["image"])
        if not state["work_order_id"]:
            state["work_order_id"] = state["ocr"].get("work_order_id")
        return {"defect": state["defect"], "work_order_read": state["ocr"].get("work_order_id")}

    def _search_rules(self, state, args):
        query = args.get("query") or state["question"]
        hits = self.rag.search(query, TOP_K)
        state["passages"].extend(h for h in hits if h["chunk_id"] not in
                                 {p["chunk_id"] for p in state["passages"]})
        return {"query": query, "found": [h["chunk_id"] for h in hits]}

    def _lookup_work_order(self, state, args):
        wo = (args.get("work_order_id") or state["work_order_id"] or "").upper()
        record = MOCK_WORK_ORDERS.get(wo)
        state["work_order"] = {"id": wo, "record": record or "not found in ERP"}
        return state["work_order"]

    def _menu(self, state, used):
        """Tools still worth calling: each runs once; the photo tool needs a photo."""
        tools = [t for t in TOOLS if t not in used]
        if state["image"] is None and "inspect_photo" in tools:
            tools.remove("inspect_photo")
        return tools + list(FINISH)

    # ---------- prompt ----------

    def _prompt(self, state, menu):
        facts = []
        if state["defect"]:
            d = state["defect"]
            facts.append("photo check: %s (confidence %.2f; %s)"
                         % (d["category"], d["confidence"], d["evidence"]))
        if state["work_order_id"]:
            facts.append("work order: %s" % state["work_order_id"])
        if state["work_order"]:
            facts.append("ERP record: %s" % json.dumps(state["work_order"]["record"]))
        passages = "\n\n".join("[%s] %s" % (p["source"], p["text"]) for p in state["passages"])
        return PROMPT.format(
            tools="\n".join(TOOLS.get(t) or FINISH[t] for t in menu),
            question=state["question"], has_photo=state["image"] is not None,
            facts="\n".join("- " + f for f in facts) or "(nothing yet)",
            passages=passages or "(none yet)")

    # ---------- loop ----------

    def run(self, question, image=None, work_order_id=None):
        state = {"question": question, "image": image, "work_order_id": work_order_id,
                 "defect": None, "ocr": None, "work_order": None, "passages": []}
        steps, llm_calls = [], []

        for _ in range(MAX_STEPS):
            used = {s["tool"] for s in steps if "observation" in s}
            menu = self._menu(state, used)
            raw, model, latency = llm.generate(self._prompt(state, menu))
            llm_calls.append({"model": model, "latency_s": round(latency, 2)})

            if raw is None:
                return self._result(state, steps, llm_calls, answer=self._unavailable(state))

            action = _parse(raw)
            if action is None:
                steps.append({"tool": None, "error": "reply was not a valid tool call",
                              "raw": raw[:200]})
                continue
            tool, args = action["tool"], action["args"]
            step = {"tool": tool, "args": args, "thought": action.get("thought", "")}

            if tool not in menu:
                step["error"] = "tool not offered at this step"
                steps.append(step)
                continue

            if tool == "answer":
                steps.append(step)
                return self._result(state, steps, llm_calls,
                                    answer=args.get("text") or "(the model gave no text)")

            if tool == "escalate":
                steps.append(step)
                reason = args.get("reason") or "no reason given"
                escalation = {"to": "shift supervisor", "reason": reason,
                              "status": "PENDING_HUMAN_APPROVAL", "executed": False}
                answer = ("Escalated to the shift supervisor for sign-off. Nothing has been "
                          "actioned yet. Reason: %s" % reason)
                return self._result(state, steps, llm_calls, answer=answer,
                                    escalation=escalation)

            step["observation"] = getattr(self, "_" + tool)(state, args)
            steps.append(step)

        return self._result(state, steps, llm_calls,
                            answer="No final answer within %d steps. %s"
                                   % (MAX_STEPS, self._sources_line(state)))

    # ---------- endings ----------

    def _sources_line(self, state):
        if not state["passages"]:
            return "No rule passages were found."
        return "Rule passages found: %s." % ", ".join(p["chunk_id"] for p in state["passages"])

    def _unavailable(self, state):
        """No model: say so plainly and point at the closest rules instead of guessing."""
        if not state["passages"]:
            state["passages"] = self.rag.search(state["question"], TOP_K)
        return "The assistant model is unavailable, so no answer was generated. " \
               + self._sources_line(state)

    @staticmethod
    def _result(state, steps, llm_calls, answer, escalation=None):
        return {"answer": answer, "escalation": escalation, "steps": steps,
                "llm_calls": llm_calls,
                "facts": {"defect": state["defect"], "ocr": state["ocr"],
                          "work_order_id": state["work_order_id"],
                          "work_order": state["work_order"]},
                "sources": [p["chunk_id"] for p in state["passages"]]}
