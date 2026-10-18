import base64
import time
import uuid

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import store
from .agent import Agent
from .bandit import ACTIONS, EpsilonGreedyBandit, reward
from .rag import RagIndex

app = FastAPI(title="ShopFloor Copilot", version="0.1.0")

rag = RagIndex()
bandit = EpsilonGreedyBandit()
agent = Agent(rag, bandit)


class Feedback(BaseModel):
    transaction_id: str
    score: int


def _decode(data):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="could not decode image")
    return img


@app.post("/inspect")
def inspect(query: str = Form(...),
            work_order_id: str = Form(None),
            image: UploadFile = File(None),
            image_b64: str = Form(None)):
    t0 = time.time()

    img = None
    if image is not None:
        img = _decode(image.file.read())
    elif image_b64:
        img = _decode(base64.b64decode(image_b64))

    result = agent.run(query, img, work_order_id)
    ctx = result["ctx"]
    latency = round(time.time() - t0, 3)

    record = {
        "transaction_id": str(uuid.uuid4()),
        "timestamp": store.now(),
        "inputs": {"query": query, "image_supplied": img is not None,
                   "work_order_id": work_order_id},
        "answer": result["answer"],
        "defect_category": ctx["defect"]["category"] if ctx["defect"] else None,
        "defect_detail": ctx["defect"],
        "ocr": ctx["ocr"],
        "work_order_id": ctx["work_order_id"],
        "config": {
            "llm_model": ctx["model_used"] or "template_fallback",
            "rag_top_k": ctx["rag_top_k"],
            "bandit_state": ctx["bandit_state"],
            "bandit_mode": ctx["bandit_mode"],
            "fallbacks": ctx["fallbacks"],
            "repeated_tool_calls": ctx["repeated_calls"],
            "llm_calls": ctx["llm_calls"],
        },
        "decision_trace": result["trace"],
        "proposed_action": result["proposed_action"],
        "latency_s": latency,
    }

    store.save_transaction(record)
    return record


@app.post("/feedback")
def feedback(fb: Feedback):
    if fb.score not in (0, 1):
        raise HTTPException(status_code=400, detail="score must be 0 or 1")

    tx = store.get_transaction(fb.transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="unknown transaction")

    action = tx["config"]["rag_top_k"]
    if action is None:
        return {"updated": False, "reason": "this transaction took no bandit action"}

    state = tx["config"]["bandit_state"]
    r = round(reward(fb.score, tx["latency_s"]), 3)
    arm = bandit.update(state, action, r)

    store.append_audit({"event": "feedback", "timestamp": store.now(),
                        "transaction_id": fb.transaction_id, "score": fb.score,
                        "state": state, "action": action, "reward": r})

    return {"updated": True, "state": state, "action": action, "reward": r,
            "arm_stats": {"n": arm["n"], "mean_reward": round(arm["mean"], 3)},
            "current_best_action": bandit.best_action(state)}


@app.get("/transactions/{tx_id}")
def get_transaction(tx_id: str):
    tx = store.get_transaction(tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="unknown transaction")
    return tx


@app.get("/bandit")
def bandit_state():
    return {"actions": ACTIONS, "stats": bandit.snapshot()}
