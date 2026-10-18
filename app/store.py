import json
import os
import threading
from datetime import datetime, timezone

AUDIT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "audit_log.jsonl")

_transactions = {}
_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def save_transaction(record):
    with _lock:
        _transactions[record["transaction_id"]] = record
    append_audit(record)


def get_transaction(tx_id):
    return _transactions.get(tx_id)


def append_audit(entry):
    os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
    with _lock:
        with open(AUDIT_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
