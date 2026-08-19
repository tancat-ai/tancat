"""3.6 fairness probe: does Qwen3.6 think? Does enable_thinking=False change it?

Same prompt/payload as the 3.8 probes so results are directly comparable.
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
        "5. ASSERT the inventory page is displayed",
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
    if reasoning:
        print(f"    reasoning head: {reasoning[:80]!r}")


base_payload: dict[str, object] = {
    "model": model_id,
    "messages": [{"role": "user", "content": prompt}],
    "stream": False,
    "temperature": 0.0,
    "max_tokens": 4096,
}

print("=== DEFAULT (no thinking knob) ===")
for i in (1, 2):
    run(f"default-{i}", dict(base_payload))

print("=== A) enable_thinking=False via chat_template_kwargs ===")
for i in (1, 2):
    payload = dict(base_payload)
    payload["chat_template_kwargs"] = {"enable_thinking": False}
    run(f"nothink-{i}", payload)
