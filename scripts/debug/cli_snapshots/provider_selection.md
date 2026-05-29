# Scenario: provider_selection
**Date:** 2026-05-29 09:09:48
**Steps:** 4
**Status:** PASS
---
## Step 1: Initial menu
- **Sent:** `<wait>`
- **Duration:** 0ms
- **Status:** OK
```
[H[J┌──────────────────────────────────────────────────────────────────────────┐
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

   > Configure LLM
     Enter User Story
     Save & Exit
     Quit

├──────────────────────────────────────────────────────────────────────────┤
│ [1]Configure LLM  [2]Enter User Stor  [3]Save & Exit  [4]Quit  [Q]Quit ...│
└──────────────────────────────────────────────────────────────────────────┘

[H[J┌──────────────────────────────────────────────────────────────────────────┐
│  LLM Configuration                                                        │
│ ────────────────────────────────────────────────────────────────────────│
├──────────────────────────────────────────────────────────────────────────┤

   > Ollama
```
---
## Step 3: Select Ollama
- **Sent:** `1<Enter>`
- **Duration:** 0ms
- **Status:** OK
```
 (local)
     LM Studio (local)
     OpenAI-Compatible (local)
     OpenAI (cloud)

├──────────────────────────────────────────────────���───────────────────────┤
│ [1]Ollama (local)  [2]LM Studio (loca  [3]OpenAI-Compatib  [4]OpenAI (c...│
└──────────────────────────────────────────────────────────────────────────┘

    Base URL
```
---
## Step 4: Accept default URL
- **Sent:** `<Enter>`
- **Duration:** 0ms
- **Status:** OK
```
 (default: http://localhost:11434): (default: http://localhost:11434): 
  Could not
```
---