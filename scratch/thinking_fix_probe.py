"""Probe B: fix candidates for the thinking-budget collapse.

Variants (K=2 each):
  A) chat_template_kwargs={"enable_thinking": False}  (jinja-level switch)
  B) /no_think in-band soft switch in the prompt
  C) max_tokens raised to 16384 (let thinking finish)

Reports per call: elapsed, finish_reason, content len, reasoning len.
"""

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


def run(name: str, payload: dict[str, object]) -> None:
    t0 = time.monotonic()
    try:
        resp = httpx.post(f"{BASE}/v1/chat/completions", json=payload, timeout=900)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[{name}] REQUEST FAILED after {time.monotonic() - t0:.1f}s: {exc}")
        return
    dt = time.monotonic() - t0
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    usage = data.get("usage", {})
    print(
        f"[{name}] {dt:.1f}s finish={choice.get('finish_reason')} "
        f"content={len(content)} reasoning={len(reasoning)} "
        f"completion_tokens={usage.get('completion_tokens')}"
    )
    if content:
        print(f"    content head: {content[:80]!r}")


base_payload: dict[str, object] = {
    "model": model_id,
    "messages": [{"role": "user", "content": prompt}],
    "stream": False,
    "temperature": 0.0,
    "max_tokens": 4096,
}

print("=== A) enable_thinking=False via chat_template_kwargs ===")
for i in (1, 2):
    payload = dict(base_payload)
    payload["chat_template_kwargs"] = {"enable_thinking": False}
    run(f"A{i}", payload)

print("=== B) /no_think in-band ===")
for i in (1, 2):
    payload = dict(base_payload)
    payload["messages"] = [{"role": "user", "content": "/no_think\n" + prompt}]
    run(f"B{i}", payload)

print("=== C) max_tokens=16384 (thinking allowed to finish) ===")
for i in (1,):
    payload = dict(base_payload)
    payload["max_tokens"] = 16384
    run(f"C{i}", payload)
