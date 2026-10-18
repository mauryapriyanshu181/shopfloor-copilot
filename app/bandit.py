import json
import os
import random
import threading

ACTIONS = [2, 4, 8]          # RAG top-K values the bandit chooses between
EPSILON = 0.2
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bandit_state.json")


def reward(feedback_score, latency_s):
    return feedback_score * 10.0 - latency_s


class EpsilonGreedyBandit:
    """Contextual bandit: context = defect category, arm = RAG top-K."""

    def __init__(self, path=STATE_PATH):
        self.path = path
        self.lock = threading.Lock()
        self.stats = {}
        self._load()

    def _arms(self, state):
        if state not in self.stats:
            self.stats[state] = {str(a): {"n": 0, "mean": 0.0} for a in ACTIONS}
        return self.stats[state]

    def select(self, state):
        arms = self._arms(state)
        untried = [a for a in ACTIONS if arms[str(a)]["n"] == 0]
        if untried:
            return random.choice(untried), "explore_cold_start"
        if random.random() < EPSILON:
            return random.choice(ACTIONS), "explore"
        return max(ACTIONS, key=lambda a: arms[str(a)]["mean"]), "exploit"

    def best_action(self, state):
        arms = self._arms(state)
        return max(ACTIONS, key=lambda a: arms[str(a)]["mean"])

    def update(self, state, action, r):
        with self.lock:
            arm = self._arms(state)[str(action)]
            arm["n"] += 1
            arm["mean"] += (r - arm["mean"]) / arm["n"]
            self._save()
        return arm

    def snapshot(self):
        return {s: {k: {"n": v["n"], "mean": round(v["mean"], 2)} for k, v in arms.items()}
                for s, arms in self.stats.items()
                if any(a["n"] > 0 for a in arms.values())}

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.stats = json.load(f)

    def _save(self):
        # choosing an arm creates the row in memory; only keep rows that have
        # actually been rated, so the saved scoreboard holds no empty states
        rated = {s: arms for s, arms in self.stats.items()
                 if any(a["n"] > 0 for a in arms.values())}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(rated, f, indent=2)
