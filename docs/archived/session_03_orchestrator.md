# Session 03: Orchestrator Refinement & Error Handling

## Overview
The goal of this session is to transform the "happy path" pipeline into a production-ready orchestration layer. We will focus on robust error handling, complex replacement logic, and ensuring the final generated code is syntactically correct and executable.

## Core Objectives

### 1. Robust String Replacement (`src/orchestrator.py`)
The current implementation appends resolutions as comments. This session will implement actual string manipulation to:
- Locate `{{ACTION:description}}` patterns in the skeleton.
- Replace them with either a Playwright locator (e.g., `page.locator(".submit-btn")`) or a `pytest.skip()` call.
- Ensure that if a replacement fails, the code remains syntactically valid to prevent breaking the entire test suite.

### 
### 2. Error Resilience and Network Stability (`src/scraper.py`)
Scraping is prone to failure (404s, timeouts, SSL errors). We will implement:
- **Retry Logic**: Implement exponential backoff for failed `httpx` requests.
- **Partial Success Handling**: If one URL in a list fails to scrape, the orchestrator should continue with the remaining URLs rather than crashing the whole pipeline.
- **Timeout Management**: Strict enforcement of timeouts to prevent the automation from hanging during large-scale scrapes.

### 3. Advanced Resolver Logic (`src/placeholder_resolver.py`)
Refining how we handle ambiguous matches:
- **Confidence Scoring**: Introduce a secondary check for elements that have high text overlap but low structural relevance.
- **Multi-Page Context**: Ensuring the resolver correctly identifies which page an element belongs to when multiple URLs are being processed.

## Success Criteria
- [x] The `TestOrchestrator` produces a `.py` file where all placeholders are replaced by real code or explicit skips.
- [x] The scraper can handle a partial failure (one URL down, others up) without interrupting the pipeline.
- [x] The system is resilient to malformed HTML or missing metadata in the scraped elements.