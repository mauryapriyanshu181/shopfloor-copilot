import json
import re
import time

from . import llm, ocr, vision

MAX_STEPS = 4
MIN_LLM_BUDGET_S = 2.0   # below this, a model call is not worth starting

MOCK_WORK_ORDERS = {
    "WO-1042": {"status": "in_process", "part": "P-series housing", "qty": 50,
                "machine": "CNC-07", "open_ncr": False},
    "WO-2381": {"status": "on_hold", "part": "injection cover", "qty": 120,
                "machine": "IM-02", "open_ncr": True},
}

GATHERING_TOOLS = [
    ("rag_search", "rag_search(query)            - search the plant SOP / tolerance / escalation knowledge base"),
    ("inspect_image", "inspect_image()              - run the OpenCV defect classifier and OCR on the attached photo"),
    ("check_work_order_status", "check_work_order_status(work_order_id) - look up the work order in the ERP"),
]
TERMINAL_TOOLS = [
    "escalate(reason)             - hand the case to a human; use for cracks, scrap, or conflicting data",
    "answer(text)                 - give the line worker the final grounded answer",
]


def _offerable(used, has_image):
    """A tool is on the menu only if it has not run yet and can do something.
    Looking at a photo that was never sent costs a whole model call to learn
    nothing, and saying 'Image attached: False' in the prompt does not stop a
    small model asking for it."""
    return [(name, spec) for name, spec in GATHERING_TOOLS
            if name not in used and not (name == "inspect_image" and not has_image)]


def _allowed_tools(used, has_image):
    return {name for name, _ in _offerable(used, has_image)} | {"answer", "escalate"}


def _tool_menu(used, has_image):
    return "\n".join([spec for _, spec in _offerable(used, has_image)] + TERMINAL_TOOLS)

PROMPT = """You are ShopFloor Copilot, a QA assistant on a CNC shop floor.
Decide the single next step. Reply with ONE json object and nothing else:
{{"thought": "...", "tool": "<tool name>", "args": {{...}}}}

Tools:
{tools}

Worker question: {query}
Image attached: {has_image}
Work order supplied: {work_order_id}
Already done: {already_run}

Retrieved SOP passages:
{passages}

Steps so far:
{history}

Rules: inspect the image before reasoning about a defect. Ground every claim in
rag_search results. Never state a scrap or stop-line decision as done - escalate it.
"""


def _passages(ctx):
    seen, out = set(), []
    for hit in ctx["rag_hits"]:
        key = (hit["source"], hit["text"][:60])
        if key in seen:
            continue
        seen.add(key)
        out.append("[%s] %s" % (hit["source"], hit["text"]))
    return "\n\n".join(out) or "(none retrieved yet)"


def _first_sentences(text, limit=2):
    """SOP paragraphs are hard-wrapped in the source files; quote a sentence or
    two rather than pasting the whole section at the worker."""
    out = re.split(r"(?<=\.)\s+", text)[:limit]
    return " ".join(out)


def _obs_summary(step):
    obs = step.get("observation", "")
    if isinstance(obs, dict) and "chunks" in obs:
        return "retrieved %d passage(s) at top_k=%s, listed above" % (len(obs["chunks"]), obs["top_k"])
    return json.dumps(obs)[:200]


def _parse(text):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        obj = json.loads(match.group())
    except ValueError:
        return None
    if "tool" not in obj:
        return None
    obj.setdefault("args", {})
    obj.setdefault("thought", "")
    return obj


class Agent:
    def __init__(self, rag, bandit):
        self.rag = rag
        self.bandit = bandit

    # ---------- tools ----------

    def _inspect_image(self, ctx):
        if ctx["image"] is None:
            return {"error": "no image supplied"}
        defect = vision.classify(ctx["image"])
        text = ocr.extract(ctx["image"])
        ctx["defect"] = defect
        ctx["ocr"] = text
        if not ctx["work_order_id"]:
            ctx["work_order_id"] = text.get("work_order_id")
        return {"defect": defect, "ocr": text}

    def _rag_search(self, ctx, query):
        state = ctx["defect"]["category"] if ctx["defect"] else "no_image_supplied"
        if ctx["rag_top_k"] is None:
            ctx["rag_top_k"], ctx["bandit_mode"] = self.bandit.select(state)
            ctx["bandit_state"] = state
        search_query = query or ctx["query"]
        if ctx["defect"]:
            search_query += " " + ctx["defect"]["category"].replace("_", " ")
        hits = self.rag.search(search_query, ctx["rag_top_k"])
        ctx["rag_hits"].extend(hits)
        return {"query": search_query, "top_k": ctx["rag_top_k"], "selected_by": ctx["bandit_mode"],
                "chunks": [{"source": h["source"], "score": h["score"],
                            "text": h["text"][:400]} for h in hits]}

    def _check_work_order(self, ctx, wo):
        wo = (wo or ctx["work_order_id"] or "").upper()
        return {"work_order_id": wo, "record": MOCK_WORK_ORDERS.get(wo, "not found in ERP")}

    @staticmethod
    def _cache_key(tool, args):
        # inspect_image takes no arguments, so any second call is a repeat whatever
        # the model passes; the other tools are only a repeat for the same arguments
        if tool == "inspect_image":
            return "inspect_image"
        return "%s:%s" % (tool, json.dumps(args, sort_keys=True))

    def _execute(self, tool, args, ctx):
        key = self._cache_key(tool, args)
        if key in ctx["tool_cache"]:
            ctx["repeated_calls"] += 1
            return {"repeat_of_earlier_call": True,
                    "note": "this was already run and returned the result below; "
                            "do not call it again, move on to answer or escalate",
                    "result": ctx["tool_cache"][key]}

        if tool == "inspect_image":
            result = self._inspect_image(ctx)
        elif tool == "rag_search":
            result = self._rag_search(ctx, args.get("query"))
        elif tool == "check_work_order_status":
            result = self._check_work_order(ctx, args.get("work_order_id"))
        else:
            return {"error": "unknown tool '%s'" % tool}

        ctx["tool_cache"][key] = result
        return result

    # ---------- planning ----------

    def _fallback_decision(self, ctx, used):
        if ctx["image"] is not None and "inspect_image" not in used:
            return {"thought": "An image is attached, classify it first.",
                    "tool": "inspect_image", "args": {}, "planner": "rule_fallback"}
        if "rag_search" not in used:
            return {"thought": "Look up the governing SOP text.",
                    "tool": "rag_search", "args": {"query": ctx["query"]}, "planner": "rule_fallback"}
        if ctx["work_order_id"] and "check_work_order_status" not in used:
            return {"thought": "Confirm the work order in the ERP.",
                    "tool": "check_work_order_status",
                    "args": {"work_order_id": ctx["work_order_id"]}, "planner": "rule_fallback"}
        if ctx["defect"] and ctx["defect"]["category"] in ("crack", "dimensional_deviation"):
            return {"thought": "Non-conforming part, this needs a human.",
                    "tool": "escalate",
                    "args": {"reason": "%s detected (%s)" % (ctx["defect"]["category"],
                                                             ctx["defect"]["evidence"])},
                    "planner": "rule_fallback"}
        return {"thought": "Answer from the retrieved SOP text.", "tool": "answer",
                "args": {"text": self._template_answer(ctx)}, "planner": "rule_fallback"}

    def _template_answer(self, ctx):
        lines = []
        if ctx["defect"]:
            lines.append("Classifier result: %s (confidence %.2f, %s)."
                         % (ctx["defect"]["category"], ctx["defect"]["confidence"],
                            ctx["defect"]["evidence"]))
        if ctx["work_order_id"]:
            lines.append("Work order read from the part: %s." % ctx["work_order_id"])
        for hit in ctx["rag_hits"][:2]:
            body = " ".join(hit["text"].split("\n", 1)[-1].split())
            lines.append("Per %s: %s" % (hit["source"], _first_sentences(body)))
        if not lines:
            lines.append("No SOP passage matched this question. Ask the shift supervisor, ext 4120.")
        return " ".join(lines)

    def _fallback(self, ctx, used, reason):
        if ctx["model_used"] is None:
            ctx["model_used"] = "template_fallback"
        decision = self._fallback_decision(ctx, used)
        decision["fallback_reason"] = reason
        return decision

    def _decide(self, ctx, trace, deadline):
        used = {s["tool"] for s in trace}

        # fix 2: the ceiling is a budget for the whole request, not per call
        remaining = deadline - time.time()
        if remaining < MIN_LLM_BUDGET_S:
            return self._fallback(ctx, used, "%.0fs latency budget exhausted"
                                  % llm.LATENCY_CEILING_S)

        history = "\n".join("%d. %s -> %s" % (i + 1, s["tool"], _obs_summary(s))
                            for i, s in enumerate(trace)) or "(none yet)"

        has_image = ctx["image"] is not None
        prompt = PROMPT.format(tools=_tool_menu(used, has_image), query=ctx["query"],
                               has_image=has_image,
                               work_order_id=ctx["work_order_id"] or "none",
                               already_run=", ".join(sorted(used)) or "none",
                               passages=_passages(ctx), history=history)
        raw, model, latency = llm.generate(prompt, timeout=remaining)
        ctx["llm_calls"].append({"model": model or "unavailable", "latency_s": round(latency, 2)})

        if raw is None:
            return self._fallback(ctx, used, "model unreachable or call exceeded remaining budget")

        ctx["model_used"] = model
        decision = _parse(raw)
        if decision is None:
            return self._fallback(ctx, used, "model returned unparseable plan")

        # small models reach for a tool that is no longer on the menu; spend the
        # turn on the next useful step rather than on a call that returns nothing
        if decision["tool"] not in _allowed_tools(used, has_image):
            return self._fallback(ctx, used,
                                  "model asked for '%s', which was not offered" % decision["tool"])

        decision["planner"] = "llm"
        return decision

    # ---------- loop ----------

    def run(self, query, image, work_order_id):
        ctx = {"query": query, "image": image, "work_order_id": work_order_id,
               "defect": None, "ocr": None, "rag_hits": [], "rag_top_k": None,
               "bandit_mode": None, "bandit_state": None, "llm_calls": [],
               "model_used": None, "fallbacks": [],
               "tool_cache": {}, "repeated_calls": 0}

        trace, answer, proposed_action = [], None, None
        deadline = time.time() + llm.LATENCY_CEILING_S
        useful_steps, attempts = 0, 0

        while useful_steps < MAX_STEPS and attempts < MAX_STEPS:
            attempts += 1
            d = self._decide(ctx, trace, deadline)
            step = {"step": len(trace) + 1, "thought": d.get("thought", ""),
                    "tool": d["tool"], "args": d.get("args", {}), "planner": d["planner"]}
            if d.get("fallback_reason"):
                step["fallback_reason"] = d["fallback_reason"]
                ctx["fallbacks"].append({"step": step["step"], "reason": d["fallback_reason"]})

            if d["tool"] == "answer":
                answer = d["args"].get("text") or self._template_answer(ctx)
                step["observation"] = "final answer produced"
                trace.append(step)
                break

            if d["tool"] == "escalate":
                reason = d["args"].get("reason", "unspecified")
                contact = "Shift Supervisor Anita Rao, ext 4120"
                proposed_action = {"type": "escalate", "reason": reason,
                                   "contact": contact,
                                   "status": "PENDING_HUMAN_APPROVAL", "executed": False}
                answer = ("Escalate this to %s. Nothing has been actioned yet - it needs a "
                          "human sign-off. Reason: %s. %s"
                          % (contact, reason.rstrip(". "), self._template_answer(ctx)))
                step["observation"] = "escalation proposed, not executed"
                trace.append(step)
                break

            observation = self._execute(d["tool"], d.get("args", {}), ctx)
            step["observation"] = observation
            trace.append(step)
            # a repeat produced nothing new, so it does not spend one of the steps
            if not observation.get("repeat_of_earlier_call"):
                useful_steps += 1

        if answer is None:
            answer = self._template_answer(ctx)

        if ctx["rag_top_k"] is None:
            ctx["bandit_state"] = ctx["defect"]["category"] if ctx["defect"] else "no_image_supplied"

        return {"answer": answer, "trace": trace, "proposed_action": proposed_action, "ctx": ctx}
