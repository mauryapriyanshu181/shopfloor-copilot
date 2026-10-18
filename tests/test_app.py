import os
import subprocess
import sys

import pytest

# the agent must not reach a real model during tests: point it at a dead port so
# every request falls back to the deterministic planner and stays fast
os.environ["OLLAMA_URL"] = "http://127.0.0.1:1/api/generate"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session", autouse=True)
def samples():
    if not os.path.exists(os.path.join(SAMPLES, "part_crack.png")):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "scripts", "gen_samples.py")])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1/api/generate")
    from fastapi.testclient import TestClient

    from app import bandit as bandit_mod
    from app import main
    from app import store

    # tests must not write into the real audit log or the real learning state
    monkeypatch.setattr(store, "AUDIT_PATH", str(tmp_path / "audit_log.jsonl"))
    main.bandit = bandit_mod.EpsilonGreedyBandit(path=str(tmp_path / "bandit.json"))
    main.agent.bandit = main.bandit
    return TestClient(main.app)


# ---------- vision ----------

@pytest.mark.parametrize("name,expected", [
    ("part_ok.png", "no_defect"),
    ("part_crack.png", "crack"),
    ("part_scratch.png", "surface_scratch"),
    ("part_dimensional.png", "dimensional_deviation"),
])
def test_classifier_labels_each_sample(name, expected):
    import cv2
    from app import vision
    result = vision.classify(cv2.imread(os.path.join(SAMPLES, name)))
    assert result["category"] == expected
    assert result["evidence"]


# ---------- retrieval ----------

def test_search_returns_at_most_k_and_ranks_the_crack_rule_first():
    from app.rag import RagIndex
    index = RagIndex()
    hits = index.search("do I scrap this crack", 2)
    assert len(hits) <= 2
    assert hits[0]["source"] == "rework_vs_scrap.md"


def test_larger_k_reaches_the_escalation_document():
    from app.rag import RagIndex
    index = RagIndex()
    small = {h["source"] for h in index.search("is this part within tolerance? crack", 2)}
    large = {h["source"] for h in index.search("is this part within tolerance? crack", 8)}
    assert "escalation.md" not in small
    assert "escalation.md" in large


# ---------- bandit ----------

def test_every_arm_is_tried_before_any_is_repeated(tmp_path):
    from app.bandit import ACTIONS, EpsilonGreedyBandit
    b = EpsilonGreedyBandit(path=str(tmp_path / "b.json"))
    picked = []
    for _ in ACTIONS:
        action, mode = b.select("crack")
        assert mode == "explore_cold_start"
        picked.append(action)
        b.update("crack", action, 1.0)
    assert sorted(picked) == sorted(ACTIONS)


def test_best_action_is_the_highest_mean_not_a_sample(tmp_path):
    from app.bandit import EpsilonGreedyBandit
    b = EpsilonGreedyBandit(path=str(tmp_path / "b.json"))
    for _ in range(5):
        b.update("crack", 8, 10.0)
        b.update("crack", 2, -1.0)
        b.update("crack", 4, -1.0)
    assert all(b.best_action("crack") == 8 for _ in range(50))


def test_reward_trades_helpfulness_against_latency():
    from app.bandit import reward
    assert reward(1, 0.5) == pytest.approx(9.5)
    assert reward(0, 0.5) == pytest.approx(-0.5)
    assert reward(1, 3.0) > reward(0, 0.1)


# ---------- api ----------

def test_inspect_with_an_image_returns_a_trace_and_a_category(client):
    with open(os.path.join(SAMPLES, "part_crack.png"), "rb") as fh:
        r = client.post("/inspect", data={"query": "Is this within tolerance?"},
                        files={"image": fh})
    assert r.status_code == 200
    body = r.json()
    assert body["defect_category"] == "crack"
    assert body["decision_trace"]
    assert body["config"]["rag_top_k"] in (2, 4, 8)


def test_a_crack_is_proposed_for_sign_off_and_never_executed(client):
    with open(os.path.join(SAMPLES, "part_crack.png"), "rb") as fh:
        body = client.post("/inspect", data={"query": "Do I scrap this?"},
                           files={"image": fh}).json()
    action = body["proposed_action"]
    assert action["status"] == "PENDING_HUMAN_APPROVAL"
    assert action["executed"] is False


def test_feedback_updates_the_arm_that_was_used(client):
    body = client.post("/inspect", data={"query": "Who do I escalate a crack to?"}).json()
    used = body["config"]["rag_top_k"]
    r = client.post("/feedback", json={"transaction_id": body["transaction_id"], "score": 1})
    assert r.status_code == 200
    fb = r.json()
    assert fb["updated"] is True
    assert fb["action"] == used
    assert fb["arm_stats"]["n"] == 1


def test_a_transaction_can_be_replayed(client):
    body = client.post("/inspect", data={"query": "What is the crack tolerance?"}).json()
    replay = client.get("/transactions/" + body["transaction_id"]).json()
    assert replay["decision_trace"] == body["decision_trace"]


def test_unknown_ids_and_bad_scores_are_rejected(client):
    assert client.get("/transactions/nope").status_code == 404
    assert client.post("/feedback", json={"transaction_id": "nope", "score": 1}).status_code == 404
    body = client.post("/inspect", data={"query": "hello"}).json()
    assert client.post("/feedback",
                       json={"transaction_id": body["transaction_id"], "score": 7}).status_code == 400


def test_the_work_order_is_read_off_every_sample():
    import cv2
    from app import ocr
    for name in ("part_ok.png", "part_crack.png", "part_scratch.png", "part_dimensional.png"):
        result = ocr.extract(cv2.imread(os.path.join(SAMPLES, name)))
        assert result["work_order_id"] is not None, "no work order read from %s" % name
        assert result["work_order_id"].startswith("WO-")


def test_a_stray_character_from_the_reader_still_parses():
    from app.ocr import WO_PATTERN
    for raw, expected in [("WO-1042", "1042"), ("WO0-3333", "3333"),
                          ("WO 2381", "2381"), ("W0-5678", "5678")]:
        assert WO_PATTERN.search(raw).group(1) == expected


def test_a_repeated_tool_call_is_not_run_twice():
    import cv2
    from app.agent import Agent
    from app.bandit import EpsilonGreedyBandit
    from app.rag import RagIndex
    import tempfile

    agent = Agent(RagIndex(), EpsilonGreedyBandit(path=tempfile.mktemp()))
    ctx = {"query": "q", "image": cv2.imread(os.path.join(SAMPLES, "part_crack.png")),
           "work_order_id": None, "defect": None, "ocr": None, "rag_hits": [],
           "rag_top_k": None, "bandit_mode": None, "bandit_state": None,
           "llm_calls": [], "model_used": None, "fallbacks": [],
           "tool_cache": {}, "repeated_calls": 0}

    first = agent._execute("inspect_image", {}, ctx)
    assert "repeat_of_earlier_call" not in first

    # the model often passes different arguments the second time; still a repeat
    second = agent._execute("inspect_image", {"image": "attached_image"}, ctx)
    assert second["repeat_of_earlier_call"] is True
    assert second["result"] == first
    assert ctx["repeated_calls"] == 1


def test_a_different_work_order_is_not_treated_as_a_repeat():
    from app.agent import Agent
    from app.bandit import EpsilonGreedyBandit
    from app.rag import RagIndex
    import tempfile

    agent = Agent(RagIndex(), EpsilonGreedyBandit(path=tempfile.mktemp()))
    ctx = {"query": "q", "image": None, "work_order_id": None, "defect": None,
           "ocr": None, "rag_hits": [], "rag_top_k": None, "bandit_mode": None,
           "bandit_state": None, "llm_calls": [], "model_used": None,
           "fallbacks": [], "tool_cache": {}, "repeated_calls": 0}

    agent._execute("check_work_order_status", {"work_order_id": "WO-1042"}, ctx)
    other = agent._execute("check_work_order_status", {"work_order_id": "WO-2381"}, ctx)
    again = agent._execute("check_work_order_status", {"work_order_id": "WO-1042"}, ctx)

    assert "repeat_of_earlier_call" not in other
    assert again["repeat_of_earlier_call"] is True
    assert ctx["repeated_calls"] == 1


def test_a_tool_that_has_run_is_not_offered_again(monkeypatch, tmp_path):
    """A small model ignores an instruction not to repeat itself, so the menu it is
    shown shrinks instead. It cannot pick what it is not offered."""
    import json
    import re
    import cv2
    from app import llm
    from app.agent import Agent, _tool_menu
    from app.bandit import EpsilonGreedyBandit
    from app.rag import RagIndex

    assert "inspect_image" in _tool_menu(set(), True)
    assert "inspect_image" not in _tool_menu({"inspect_image"}, True)
    # a photo tool is pointless when no photo was sent
    assert "inspect_image" not in _tool_menu(set(), False)
    # the two terminal actions are always available
    everything = {"inspect_image", "rag_search", "check_work_order_status"}
    assert "escalate" in _tool_menu(everything, True)
    assert "answer" in _tool_menu(everything, True)

    offered = []

    def greedy_model(prompt, timeout=None):
        """Always reaches for inspect_image when it is on the menu."""
        menu = re.search(r"Tools:\n(.*?)\n\nWorker", prompt, re.S).group(1)
        names = [line.split("(")[0] for line in menu.splitlines()]
        offered.append(names)
        choice = "inspect_image" if "inspect_image" in names else "answer"
        return json.dumps({"thought": "t", "tool": choice, "args": {}}), "fake", 0.01

    monkeypatch.setattr(llm, "generate", greedy_model)

    agent = Agent(RagIndex(), EpsilonGreedyBandit(path=str(tmp_path / "b.json")))
    result = agent.run("Do I scrap this?",
                       cv2.imread(os.path.join(SAMPLES, "part_dimensional.png")), None)

    assert "inspect_image" in offered[0]
    assert "inspect_image" not in offered[1]
    assert [s["tool"] for s in result["trace"]] == ["inspect_image", "answer"]
    assert result["ctx"]["repeated_calls"] == 0


def test_a_tool_that_was_not_offered_is_rejected(monkeypatch, tmp_path):
    """The model sometimes names a tool that is no longer on the menu. That turn
    should go to the next useful step, not to a call that returns nothing."""
    import json
    import cv2
    from app import llm
    from app.agent import Agent
    from app.bandit import EpsilonGreedyBandit
    from app.rag import RagIndex

    def stubborn_model(prompt, timeout=None):
        # always asks for inspect_image, whether or not it is offered
        return json.dumps({"thought": "t", "tool": "inspect_image", "args": {}}), "fake", 0.01

    monkeypatch.setattr(llm, "generate", stubborn_model)

    agent = Agent(RagIndex(), EpsilonGreedyBandit(path=str(tmp_path / "b.json")))
    result = agent.run("Can I release this?",
                       cv2.imread(os.path.join(SAMPLES, "part_scratch.png")), None)

    tools = [s["tool"] for s in result["trace"]]
    assert tools.count("inspect_image") == 1, tools
    assert result["trace"][-1]["tool"] in ("answer", "escalate"), tools
    assert any("was not offered" in f["reason"] for f in result["ctx"]["fallbacks"])


def test_a_state_with_no_ratings_is_not_recorded(tmp_path):
    """Choosing an arm creates the row in memory, but an unrated state should not
    appear in the saved scoreboard or in what /bandit reports."""
    import json
    from app.bandit import EpsilonGreedyBandit

    path = tmp_path / "b.json"
    b = EpsilonGreedyBandit(path=str(path))

    b.select("no_defect")           # chosen, but never rated
    b.update("crack", 8, 5.0)       # this is what triggers the save

    assert "no_defect" not in json.load(open(path))
    assert "no_defect" not in b.snapshot()
    assert "crack" in b.snapshot()


def test_the_photo_tool_is_hidden_when_no_photo_was_sent(monkeypatch, tmp_path):
    """A text-only question should never spend a turn asking to look at a photo
    that does not exist, even when the model asks for it."""
    import json
    from app import llm
    from app.agent import Agent
    from app.bandit import EpsilonGreedyBandit
    from app.rag import RagIndex

    def keen_model(prompt, timeout=None):
        return json.dumps({"thought": "t", "tool": "inspect_image", "args": {}}), "fake", 0.01

    monkeypatch.setattr(llm, "generate", keen_model)

    agent = Agent(RagIndex(), EpsilonGreedyBandit(path=str(tmp_path / "b.json")))
    result = agent.run("Who do I escalate a crack to?", None, None)

    tools = [s["tool"] for s in result["trace"]]
    assert "inspect_image" not in tools, tools
    assert result["trace"][-1]["tool"] in ("answer", "escalate"), tools
