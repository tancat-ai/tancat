# B-065 acceptance re-run blocked: local LLM server stalls mid-request

> **⚠️ UPDATE (same day) — ROOT CAUSE FOUND. Read this first.**
>
> The coding agent running this session IS served by the **same llama.cpp
> instance on :8080** (`PI_PROVIDER=local-llama`,
> `PI_MODEL=qwen3.8-27b-ud-q4_k_xl`, `OPENAI_BASE_URL=http://localhost:8080/v1`).
> Every time the agent generated a response, its huge session context
> occupied the single inference slot (and KV headroom), stalling the
> background pipeline's next request until the 600s timeout. Probes run
> inside bash tool calls always succeeded because the agent's generation
> is paused during tool execution. The "fix" is not server-side: **run the
> re-run while the agent makes zero LLM calls** (launch via a tool call, then
> no agent interaction for ~30–40 min). Second attempt (23:30 launch) still
> died at 23:40:57: call 1 OK, call 2 wedged for 602s — the agent's LAUNCH-
> ANNOUNCEMENT turn (huge-context prefill) occupied the slot while call 2 was
> in flight; the server recovered on its own ~1h later. ANY agent turn can
> wedge the shared slot for >10 min. The re-run script now retries timeout-
> class failures 10× with 90s backoff (scratch-only monkeypatch of
> `LLMClient._complete_sync`), so a wedge no longer kills the run. Remaining
> useful content below: the
> verification record (§2), the re-run mechanics (§8), and what "pass"
> looks like. The stall-pattern analysis (§3–§7) is superseded by this note.

Date: 2026-09-16. Author: session agent (Claude in pi). All data below is from
today's session; log files and repro scripts are listed in §8.

---

## 1. The task in one paragraph

B-065 fixed two selector-builder defects (Tailwind variant classes mangled into
nonexistent classes; `a[href]` selectors losing the host). The plan
(`docs/plans/NEXT_SESSIONS_IMPROVEMENTS.md`, Session 1) defines "done" as:
re-run the **35-criterion landing-page story** end-to-end (regenerate the test
suite with the LLM, then execute it against the locally served `landing/` page)
and see the red count drop from **23 failed / 25 passed** (baseline,
`scratch/rerun48.log`, 673s) to **≈8 failed**. The re-run needs the local LLM
server (LM Studio → Qwen3.8-27B-GGUF) to handle ~35 skeleton-fragment calls
(~2K-token prompts, ~17s each) plus a dozen more resolution calls, without a
600s stall.

## 2. What is DONE and verified (do not re-derive)

- Code changes: `src/scraper.py` (JS + Python builders: raw href in selectors,
  CSS-escaped class tokens, six-digit unicode escape for leading-digit classes,
  new `raw_href` element key), `src/locator_builder.py` (escape helpers,
  `build_robust_locator` prefers the element's own `classes` key, escape-aware
  selector fallback, raw-href preference).
- 21 new unit tests in `tests/test_scraper.py` + `tests/test_locator_builder.py`,
  each asserting the emitted selector **matches the fixture in a real CSS engine**
  (soupsieve via bs4).
- **Full suite: 3209 passed, 0 failed.** ruff + mypy + `scripts/smoke.py` (39/39) clean.
- **Eval harness static: 97.9% resolution accuracy — identical to baseline**
  (`scripts/eval/eval_harness.py compare` shows 0.0pp drift on all metrics).
- Ground truth in **real Chromium** (Blink): all 7 selectors emitted by the JS
  builder match the fixture page, including `.\000033xl\:flex` (leading-digit
  escape). The baseline's `.5.5.bg-slate-800…` selector is rejected by Playwright
  with "Did you mean to CSS.escape it?" — that failure mode is gone.
- What the fix does NOT change: the landing page itself (its real defects — TBD
  buy links, loom placeholders, 403 noir image, missing meta/OG/canonical/
  favicon/privacy/terms — will still fail; that is the expected ≈8 reds).

## 3. The failure mode, precisely

The LLM server (LM Studio dev server, llama.cpp **Vulkan** build,
`Qwen3.8-27B-GGUF` `Q4_K_XL_v2`, OpenAI-compatible API on
`http://localhost:8080/v1`) completes most requests but **intermittently stops
responding mid-request**. Client side: `httpx.ReadTimeout` after exactly 600s
(`AITEST_GENERATION_TIMEOUT` default; no response bytes, no error, no partial
stream — non-streaming `stream: false` requests).

**Observed pattern across 6 pipeline attempts:** 1–5 requests succeed (15–26s
each), then the next request never completes → 600s timeout → pipeline aborts
(the skeleton phase needs all 35 fragments).

| # | Time | Config | LLM calls that succeeded | Then |
|---|------|--------|--------------------------|------|
| 1 | ~10:54 | original | 1 (skeleton, 156.9s, 14.6K chars) | call 2 → 600s timeout |
| 2 | ~11:44 | original | 1 (skeleton, 156.9s, 14.6K chars) | call 2 → 600s timeout |
| 3 | ~15:01 | new ("thinking off") | 2 (fragments, 19.7s/17.5s) | call 3 → 600s timeout |
| 4 | ~15:29 | new | 5 (fragments, 17–26s) | call 6 → 600s timeout |
| 5 | ~19:43 | new | 1 (fragment, 19.3s) | call 2 → 600s timeout |
| 6 | ~20:00 | new + no-keepalive httpx patch | 3 (fragments) | call 4 → 602s timeout |

Contrast: **19 standalone probe requests sent back-to-back today never stalled**
(§5). Yesterday (2026-09-15) the identical pipeline + server completed the whole
story (baseline run). The user relaunched LM Studio today with **the same model
but a different config, "thinking turned off"**.

## 4. Environment

- Machine: AMD Strix Halo / Radeon 8060S, 64GB unified memory, ~48GB GPU commit.
  Qwen3.8-27B Q4_K_XL + KV ≈ 36GB → ~12GB headroom. Windows 11.
- Server: LM Studio (llama.cpp Vulkan build, rolling builds in
  `C:\Users\l_a_c\llama.ccp config\` — outside this repo), OpenAI-compatible
  `:8080`. `.env`: `LLM_PROVIDER=openai-local`, `OPENAI_BASE_URL=http://localhost:8080`.
- Client: `src/llm_client.py` → `src/llm_providers/__init__.py`
  (`LMStudioProvider`/`OpenAIProvider`): one long-lived `httpx.Client`
  (`base_url="http://localhost:8080/v1"`, constructor `timeout=300`, per-request
  `timeout=600` for generation). Exact payload for the failing call type:
  ```json
  {
    "model": "C:\\Users\\l_a_c\\.lmstudio\\models\\unsloth\\Qwen3.8-27B-GGUF\\Qwen3.8-27B-UD-Q4_K_XL_v2.gguf",
    "messages": [
      {"role": "system", "content": "<617-char instruction>"},
      {"role": "user", "content": "<~7.1K-char per-condition skeleton prompt, ~2040 prompt_tokens>"}
    ],
    "stream": false, "temperature": 0.0, "max_tokens": 4096
  }
  ```
  (No `chat_template_kwargs` — fragment calls pass `enable_thinking=None`, so the
  server-side config governs thinking mode.)
- Successful fragment response shape (verified — this is a VALID complete
  answer, not a truncation):
  ````
  ```python
  import pytest
  from playwright.sync_api import Page, expect

  def test_tc01_01_hero_headline_visible_on_load(page: Page):
      {GOTO:http://localhost:8079/}
      {ASSERT:hero headline visible}
  ```
  ````
  (finish=stop, 57–85 completion_tokens.)
- The pipeline process also hosts pymilvus/milvus-lite (RAG store, in-process
  gRPC). It emits `GOAWAY ... too_many_pings` (ENHANCE_YOUR_CALM) lines on the
  console — see §6 red herrings.

## 5. Everything tried, with results

**Probes (standalone processes, one `httpx.Client` each) — ALL SUCCEEDED:**

| Probe | Requests | Result |
|---|---|---|
| 2+2 sanity (after first failure) | 1 | 4.5s, content "4" |
| 2+2 before run 3 | 1 | 7s — **but degenerate output** (old config: model looped "The user is asking me to respond to the user…" until max_tokens) |
| 2000-word essay (`max_tokens: 2500`) | 1 | 164s, 12015 chars, finish=stop |
| 6.6K-char input, `max_tokens: 100` | 1 | 13.7s |
| `stall_probe.py` — 12× identical 6.6K-char requests | 12 | all OK, 7.5s each |
| `stall_probe2.py` — 6× REAL captured fragment prompts (no system msg, max_tokens 2000) | 6 | all OK, 13.5–17.1s |
| `stall_probe3.py` — 6× REAL fragment prompts with the EXACT pipeline payload (system+user, temp 0.0, max_tokens 4096) | 6 | all OK, 14.6–19.4s, prompt_tokens≈2040 |

**Pipeline attempts:** all 6 failed per §3 table.

**Workarounds tried in the re-run script (`scratch/rerun_b065.py`):**
- Switching from `orchestrator.run_pipeline` to the CLI-grade
  `src.ui_pipeline.run_pipeline` (writes the artifact package; needed anyway —
  the former path loses generated code).
- `AITEST_ENABLE_THINKING` left unset (fragments don't send the flag regardless;
  server config governs — user's config has thinking off).
- **No-keepalive httpx patch** (force `Limits(max_keepalive_connections=0)` for
  every `httpx.Client` in the process, killing pooled-connection reuse): did NOT
  fix it (run 6: 3 OK then 602s timeout). **Keep-alive/stale-connection
  hypothesis: not confirmed.**

**Health probes around the failures:** the server answered single sanity requests
fast both right after failures and between them — i.e. it is not globally dead,
it stalls specific requests.

## 6. Red herrings investigated and ruled out

1. **milvus-lite gRPC `GOAWAY too_many_pings`** — in-process pymilvus
   keepalive chatter (the RAG store uses `MilvusClient(<local file>)`). Unrelated
   to LM Studio's HTTP API. Appears in the log near failures but is not the
   channel carrying the LLM requests.
2. **Thinking mode** — under the ORIGINAL config the model was genuinely
   degenerate (infinite self-referential loop, zero content). After the user's
   relaunch, all probe outputs are clean and fast. Fragment calls send no
   `chat_template_kwargs`, so the new server-side config governs; probe3
   (identical payload) produced valid 57–85-token skeletons, not reasoning burn.
3. **Prompt size/content** — the exact failing prompts (captured verbatim,
   `scratch/b065_prompt_dump.jsonl`) complete fine when sent from standalone
   processes, including the one that timed out inside the pipeline (prompt 6 /
   TC01.06).
4. **Payload differences** — replicated exactly (system message, temp, max_tokens,
   stream flag); no difference found.
5. **Keep-alive connection pooling** — see §5.
6. **Server down / model unloaded** — sanity requests answered throughout.

## 7. Remaining hypotheses (ranked, for the next diagnosis)

1. **Server-side stall under the pipeline's request cadence/state.** The pipeline
   fires back-to-back 2K-token requests with ~2–10s gaps, 35+ times in a row,
   from a process that is also running a gRPC server thread and heavy I/O. Probes
   fire similar requests but from idle processes. Possible causes: KV-cache /
   Vulkan memory leak per request, a worker that dies after N inferences,
   batch/queue handling in the user's NEW LM Studio config. Check: LM Studio
   console/server logs during a failure, GPU memory over the 35-request span
   (`rocm-smi` or task manager), and whether reverting to yesterday's LM Studio
   config (which completed the identical pipeline) fixes it.
2. **The new "thinking off" model config** itself (context length, KV cache size,
   mlock, Vulkan flags, batch size) interacts badly with repeated requests.
   Yesterday's config ran the full pipeline fine with the same model.
3. **Client-side process state** (something about the pipeline process's socket
   usage — Playwright not yet started at skeleton phase, but gRPC + file I/O
   are). Lower probability given the no-keepalive patch result, but not fully
   excluded (the patch only touched httpx pooling).
4. **Windows/network-stack interaction** with the specific llama.cpp build —
   test by serving the same GGUF via a plain `llama-server` (the user's
   llama.cpp builds live in `C:\Users\l_a_c\llama.ccp config\`) instead of
   LM Studio.

**Suggested first experiments (cheap → expensive):**
- a) Re-run `uv run python scratch/stall_probe3.py` **from inside a process that
  first seeds the RAG store** (e.g. after instantiating the pipeline), to see if
  co-residency with milvus-lite/gRPC reproduces the stall.
- b) Run `scratch/rerun_b065.py` while tailing LM Studio's own server log and
  `rocm-smi`/GPU memory; correlate the stall with server-side state.
- c) Revert LM Studio to yesterday's working config and re-run.
- d) Serve the GGUF with bare `llama-server` on :8080 and re-run.

## 8. Artifacts & commands

**Files**
- `scratch/rerun_b065.py` — the re-run script (uses `src.ui_pipeline.run_pipeline`,
  pom_mode=True, writes the package, then runs the 48-test suite; logs to
  `scratch/rerun_b065_gen.log` + `scratch/rerun_b065_suite.log`). The story and
  35 criteria are embedded; the landing page must be served on :8079 first:
  `cd landing && python -m http.server 8079`.
- `scratch/b065_prompt_dump.jsonl` — 6 real captured skeleton-fragment prompts
  (verbatim, incl. the one that timed out in-pipeline).
- `scratch/capture_prompt.py` — prompt-capture harness (monkeypatches
  `LLMClient.generate`).
- `scratch/stall_probe.py` / `stall_probe2.py` / `stall_probe3.py` — the probes
  from §5 (probe3 = exact pipeline payload replica).
- `scratch/rerun_b065_gen.log` — latest generation log (run 6, failed).
- `scratch/rerun48.log` — BASELINE suite result: `23 failed, 25 passed in 673.02s`.
- `generated_tests/test_20260915_194227_as_a_prospective_customer_i_want_to_review_the_ta/`
  — baseline 48-test package (pre-fix selectors; do not use for acceptance).
- `scratch/landing_page_story.md` — the 35-criterion story (source of truth).
- Health probe (run before any re-attempt):
  ```
  uv run python -c "import httpx,time; t=time.time(); r=httpx.post('http://localhost:8080/chat/completions', json={'model':'local','messages':[{'role':'user','content':'What is 2+2? Answer with just the number.'}],'max_tokens':50,'temperature':0}, timeout=120); print(round(time.time()-t,1), r.json()['choices'][0]['message']['content'])"
  ```
  Expect `~5 4`. (Degenerate output = server state bad, don't re-run.)

**Acceptance criteria for the re-run**
- 48 tests generated (35 criteria → ~48 tests, POM mode) and executed against
  `http://localhost:8079/`.
- Expected: **≈8 failed / ~40 passed** (the reds should be the page's real
  defects: TBD purchase links ×2, loom placeholder ×2–3, 403 noir image, missing
  meta description/OG/canonical/favicon/privacy/terms — NOT selector timeouts).
- A selector timeout like `waiting for locator(".hover...")` = the fix did not
  land; investigate before trusting counts.
- On success: record the row in `docs/plans/NEXT_SESSIONS_IMPROVEMENTS.md`
  Appendix A; B-065 status update in `BACKLOG.md` happens at ship-it only.

## 9. What a "more capable LLM" is NOT being asked to do

- Re-verify the code fix (done, §2) or re-litigate the escape formats
  (soupsieve + Blink both verified, §2).
- Modify `src/llm_client.py` / `src/llm_providers/` without explicit instruction
  (protected files per AGENTS.md — document findings in BACKLOG.md instead).
- The re-run is a **server-stability** problem, not a prompt or code problem:
  the identical prompts complete from idle processes; they stall from the
  pipeline process after 1–5 successes.
