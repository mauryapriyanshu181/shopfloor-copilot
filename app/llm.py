import os
import time

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
PRIMARY_MODEL = os.environ.get("PRIMARY_MODEL", "qwen2.5:3b")
LATENCY_CEILING_S = float(os.environ.get("LATENCY_CEILING_S", "15"))


def generate(prompt, timeout=None):
    """Returns (text, model_used, latency). text is None if the call failed or timed out."""
    timeout = timeout or LATENCY_CEILING_S
    t0 = time.time()
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": PRIMARY_MODEL, "prompt": prompt, "stream": False,
                  "format": "json",   # constrain decoding so small models cannot emit prose
                  "options": {"temperature": 0.0, "num_predict": 256}},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["response"].strip(), PRIMARY_MODEL, time.time() - t0
    except Exception:
        return None, None, time.time() - t0
