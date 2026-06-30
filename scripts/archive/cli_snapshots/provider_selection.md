# Scenario: provider_selection
**Date:** 2026-06-29 22:54:50
**Steps:** 4
**Status:** PASS
---
## Step 1: Initial menu
- **Sent:** `<wait>`
- **Duration:** 0ms
- **Status:** OK
```

==============================================================================
┌──────────────────────────────────────────────────────────────────────────┐
│  AI Playwright
```
---
## Step 2: Select Configure LLM
- **Sent:** `1<Enter>`
- **Duration:** 0ms
- **Status:** OK
```
 Test Generator                                             │
│  Generate Playwright tests from user stories with AI                      │
├──────────────────────────────────────────────────────────────────────────┤

   State:
     LLM : ollama / qwen3.5:9b

   > [1] Configure LLM
     [2] Enter User Story
     [3] Load Existing Generated Tests
     [4] Save & Exit
     [5] Quit

├──────────────────────────────────────────────────────────────────────────┤
│ [1]Configure LLM  [2]Enter User Story...                                  │
└──────────────────────────────────────────────────────────────────────────┘

   Enter selection: 
==============================================================================
┌──────────────────────────────────────────────────────────────────────────┐
│  LLM Configuration                                                        │
│ ────────────────────────────────────────────────────────────────────────│
├──────────────────────────────────────────────────────────────────────────┤

   > [1] Ollama
```
---
## Step 3: Select Ollama
- **Sent:** `1<Enter>`
- **Duration:** 0ms
- **Status:** OK
```
 (local)
     [2] LM Studio (local)
     [3] OpenAI-Compatible (local)
     [4] OpenAI (cloud)

├──────────────────────────────────────────────────────────────────────────┤
│ [1]Ollama  [2]LM Studio  [3]OpenAI-Compatible  [4]OpenAI  [Q]Quit         │
└──────────────────────────────────────────────────────────────────────────┘

   Enter selection:   Base URL
```
---
## Step 4: Accept default URL
- **Sent:** `<Enter>`
- **Duration:** 0ms
- **Status:** OK
```
 (default: http://localhost:11434):   ⚠ Connection to http://localhost:11434 timed out: timed out

  Could not
```
---