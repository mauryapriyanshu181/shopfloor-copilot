import json
import os
import subprocess
import sys

import pytest

# tests never reach a real model: agent tests script the model's replies, and
# anything else hits a dead port and gets "model unavailable"
os.environ["OLLAMA_URL"] = "http://127.0.0.1:1/api/generate"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session", autouse=True)
def samples():
    if not os.path.exists(os.path.join(SAMPLES, "part_crack.png")):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "scripts", "gen_samples.py")])


def photo(name):
    import cv2
    return cv2.imread(os.path.join(SAMPLES, name))


@pytest.fixture(scope="module")
def agent():
    from app.agent import Agent
    from app.rag import RagIndex
    # BM25 keeps agent tests fast and model-free; which retriever is best is the
    # retrieval eval's job, not these tests'
    return Agent(RagIndex(method="bm25"))


def script(monkeypatch, replies):
    """Make the model reply with these actions in order. Returns the prompts it saw."""
    from app import llm
    prompts, queue = [], list(replies)

    def fake(prompt, timeout=None):
        prompts.append(prompt)
        reply = queue.pop(0) if queue else {"tool": "answer", "args": {"text": "done"}}
        return (reply if isinstance(reply, str) else json.dumps(reply)), "fake", 0.01

    monkeypatch.setattr(llm, "generate", fake)
    return prompts


def offered(prompt):
    return prompt.split("Tools you can use now:")[1].split("Worker question:")[0]


# ---------- vision and OCR ----------

@pytest.mark.parametrize("name,expected", [
    ("part_ok.png", "no_defect"),
    ("part_crack.png", "crack"),
    ("part_scratch.png", "surface_scratch"),
    ("part_dimensional.png", "dimensional_deviation"),
])
def test_classifier_labels_each_sample(name, expected):
    from app import vision
    result = vision.classify(photo(name))
    assert result["category"] == expected
    assert result["evidence"]


def test_the_work_order_is_read_off_every_sample():
    from app import ocr
    for name in ("part_ok.png", "part_crack.png", "part_scratch.png", "part_dimensional.png"):
        result = ocr.extract(photo(name))
        assert result["work_order_id"] is not None, "no work order read from %s" % name
        assert result["work_order_id"].startswith("WO-")


def test_a_stray_character_from_the_reader_still_parses():
    from app.ocr import WO_PATTERN
    for raw, expected in [("WO-1042", "1042"), ("WO0-3333", "3333"),
                          ("WO 2381", "2381"), ("W0-5678", "5678")]:
        assert WO_PATTERN.search(raw).group(1) == expected


# ---------- agent loop ----------

def test_a_photo_question_runs_the_tools_and_answers(agent, monkeypatch):
    prompts = script(monkeypatch, [
        {"tool": "inspect_photo", "args": {}},
        {"tool": "search_rules", "args": {"query": "crack scrap rule"}},
        {"tool": "lookup_work_order", "args": {}},
        {"tool": "answer", "args": {"text": "Scrap it per rework_vs_scrap.md."}},
    ])
    out = agent.run("What do I do with this?", photo("part_crack.png"))

    assert out["answer"] == "Scrap it per rework_vs_scrap.md."
    assert out["escalation"] is None
    assert [s["tool"] for s in out["steps"]] == ["inspect_photo", "search_rules",
                                                 "lookup_work_order", "answer"]
    assert out["facts"]["defect"]["category"] == "crack"
    assert out["facts"]["work_order_id"] == "WO-1042"         # read off the part
    assert out["facts"]["work_order"]["record"]["status"] == "in_process"
    assert out["sources"]
    # what earlier tools found is shown to the model on later turns
    assert "photo check: crack" in prompts[1]
    assert "[%s]" % out["sources"][0].split("#")[0] in prompts[2]


def test_an_escalation_is_proposed_never_executed(agent, monkeypatch):
    script(monkeypatch, [{"tool": "inspect_photo", "args": {}},
                         {"tool": "escalate", "args": {"reason": "crack found"}}])
    out = agent.run("Can I ship this?", photo("part_crack.png"))
    assert out["escalation"] == {"to": "shift supervisor", "reason": "crack found",
                                 "status": "PENDING_HUMAN_APPROVAL", "executed": False}
    assert "Nothing has been actioned" in out["answer"]


def test_a_tool_runs_at_most_once(agent, monkeypatch):
    prompts = script(monkeypatch, [{"tool": "inspect_photo", "args": {}},
                                   {"tool": "inspect_photo", "args": {}},
                                   {"tool": "answer", "args": {"text": "ok"}}])
    out = agent.run("Is this ok?", photo("part_ok.png"))
    assert "inspect_photo(" in offered(prompts[0])
    assert "inspect_photo(" not in offered(prompts[1])
    assert out["steps"][1]["error"] == "tool not offered at this step"
    assert out["answer"] == "ok"


def test_the_photo_tool_is_not_offered_without_a_photo(agent, monkeypatch):
    prompts = script(monkeypatch, [{"tool": "inspect_photo", "args": {}},
                                   {"tool": "answer", "args": {"text": "ok"}}])
    out = agent.run("Who do I call about a crack?")
    assert "inspect_photo(" not in offered(prompts[0])
    assert out["steps"][0]["error"] == "tool not offered at this step"
    assert out["facts"]["defect"] is None


def test_an_invalid_reply_is_recorded_and_the_loop_goes_on(agent, monkeypatch):
    script(monkeypatch, ["sure, I will inspect it", {"tool": "answer", "args": {"text": "ok"}}])
    out = agent.run("Is this ok?", photo("part_ok.png"))
    assert out["steps"][0]["error"] == "reply was not a valid tool call"
    assert out["answer"] == "ok"


def test_the_loop_stops_after_max_steps(agent, monkeypatch):
    from app.agent import MAX_STEPS
    script(monkeypatch, [{"tool": "search_rules", "args": {"query": "q"}}] * 10)
    out = agent.run("What is the crack rule?")
    assert len(out["steps"]) == MAX_STEPS
    assert out["answer"].startswith("No final answer within %d steps" % MAX_STEPS)


def test_without_a_model_it_says_so_instead_of_guessing(agent, monkeypatch):
    from app import llm
    monkeypatch.setattr(llm, "generate", lambda prompt, timeout=None: (None, None, 0.0))
    out = agent.run("What is the crack rule?")
    assert out["answer"].startswith("The assistant model is unavailable")
    assert out["sources"]                       # it still points at the closest rules
    assert out["escalation"] is None


# ---------- API ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import llm, main, store
    # tests must not write into the real audit log
    monkeypatch.setattr(store, "AUDIT_PATH", str(tmp_path / "audit_log.jsonl"))
    monkeypatch.setattr(llm, "generate", lambda prompt, timeout=None: (None, None, 0.0))
    return TestClient(main.app)


def test_inspect_returns_and_stores_a_replayable_record(client):
    with open(os.path.join(SAMPLES, "part_crack.png"), "rb") as fh:
        r = client.post("/inspect", data={"query": "Do I scrap this?"}, files={"image": fh})
    assert r.status_code == 200
    body = r.json()
    for key in ("transaction_id", "answer", "escalation", "facts", "sources", "steps",
                "config", "llm_calls", "latency_s"):
        assert key in body, key
    assert body["inputs"]["image_supplied"] is True
    assert client.get("/transactions/" + body["transaction_id"]).json() == body


def test_bad_requests_are_rejected(client):
    assert client.get("/transactions/nope").status_code == 404
    r = client.post("/inspect", data={"query": "q"},
                    files={"image": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 400
