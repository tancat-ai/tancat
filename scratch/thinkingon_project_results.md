# Thinking-ON project A/B (eval_harness --mode full --regenerate), spec OFF, temp 0.0

Config: AITEST_ENABLE_THINKING=1 LLM_MAX_TOKENS=16384 AITEST_RESOLUTION_TIMEOUT=300
Server: 3.6 build b10483, ctx 156160, spec OFF (manifest_thinkingon_36.json)

## Leg H — Qwen3.6-27B (thinking ON)
Resolution accuracy: 73.4% (80/109). Skeletons 8/8. No timeouts / got=0.
| story | site | correct/total | acc |
|---|---|---|---|
| eval-001 | saucedemo | 10/20 | 50% |
| eval-002 | automationexercise | 7/8 | 88% |
| eval-003 | demoqa | 7/8 | 88% |
| eval-004 | theinternet | 5/7 | 71% |
| eval-005 | lv_insurance | 16/24 | 67% |
| eval-006 | ecommerce_mock | 13/16 | 81% |
| eval-007 | banking_mock | 11/13 | 85% |
| eval-008 | banking_mock | 11/13 | 85% |

Compare:
- Leg F (3.6, thinking OFF): 76.1% (83/109)  -> thinking ON slightly LOWER
- Leg G (3.8, thinking OFF): 62.4% (68/109)

Note: eval-005 lv_insurance test-passed=0 in both off legs too — known site/evidence issue.
PENDING: Leg I (3.8 thinking ON) — same config.
