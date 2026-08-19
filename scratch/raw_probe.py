"""Throwaway evidence probe: what does the raw /v1/chat/completions response
actually contain when the provider sees 'empty content'?

Dumps the full message dict, finish_reason and usage for K identical calls
(temp=0) using the exact skeleton prompt from determinism_check.py.
"""

import json
import time

import httpx

from src.prompt_builder import PromptBuilder, build_skeleton_prompt

BASE = "http://localhost:8080"
STORY = "As a user, I can log in to SauceDemo with valid credentials and see the inventory page."
CONDITIONS = "\n".join(
    [
        "1. Navigate to the login page",
        "2. Fill the username field with standard_user",
        "3. Fill the password field with secret_sauce",
        "4. Click the login button",
        "5. ASSERT the inventory/products page is displayed",
    ]
)
URLS = ["https://www.saucedemo.com/"]

prompt = PromptBuilder(
    build_skeleton_prompt(
        user_story=STORY,
        conditions=CONDITIONS,
        known_urls_block="\n".join(f"- {u}" for u in URLS),
        expected_count=5,
    )
).render().text + "\n\nIMPORTANT: You must generate exactly 5 test functions (one per criterion)."

model_id = httpx.get(f"{BASE}/v1/models", timeout=5).json()["data"][0]["id"]
print(f"model_id={model_id}")

K = 3
for i in range(1, K + 1):
    t0 = time.monotonic()
    resp = httpx.post(
        f"{BASE}/v1/chat/completions",
        json={
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0.0,
            "max_tokens": 4096,
        },
        timeout=600,
    )
    dt = time.monotonic() - t0
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    print(f"--- call {i}: {dt:.1f}s finish_reason={choice.get('finish_reason')}")
    print(f"    usage={data.get('usage')}")
    for key, value in msg.items():
        if isinstance(value, str):
            print(f"    msg[{key}]: len={len(value)} head={value[:120]!r}")
        else:
            print(f"    msg[{key}]: {value!r}")
    # any unexpected top-level keys (reasoning buckets, timings)?
    extra = set(data) - {"id", "object", "created", "model", "choices", "usage"}
    if extra:
        print(f"    EXTRA top-level keys: {extra}")
