import base64
import time
import uuid

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from . import llm, store
from .agent import TOP_K, Agent
from .rag import RagIndex

app = FastAPI(title="ShopFloor Copilot", version="0.2.0")

rag = RagIndex()
agent = Agent(rag)


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

    record = {
        "transaction_id": str(uuid.uuid4()),
        "timestamp": store.now(),
        "inputs": {"query": query, "image_supplied": img is not None,
                   "work_order_id": work_order_id},
        "answer": result["answer"],
        "escalation": result["escalation"],
        "facts": result["facts"],
        "sources": result["sources"],
        "steps": result["steps"],
        "config": {"model": llm.PRIMARY_MODEL, "retriever": rag.method,
                   "contextual_chunks": rag.contextual, "top_k": TOP_K},
        "llm_calls": result["llm_calls"],
        "latency_s": round(time.time() - t0, 3),
    }
    store.save_transaction(record)
    return record


@app.get("/transactions/{tx_id}")
def get_transaction(tx_id: str):
    tx = store.get_transaction(tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="unknown transaction")
    return tx
