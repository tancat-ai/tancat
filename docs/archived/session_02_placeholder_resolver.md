# Session 02: Placeholder Resolver & Scraper Integration

## Overview
The goal of this session is to implement the "Intelligence" layer that transforms a structural skeleton into a functional test script by resolving abstract action placeholders with real web element locators.

## Core Components

### 1. PageScraper (`src/scraper.py`)
- **Responsibility**: Navigate to URLs identified in the Skeleton and extract interactive metadata.
- **Technology**: `httpx` for asynchronous requests, `BeautifulSoup4` for HTML parsing.
- **Output**: A dictionary mapping `{ url: [list_of_element_metadata] }`. 
- **Element Metadata Structure**:
  ```python
  {
      "selector": "css_selector_string",
      "text": "visible_text_content",
      "role": "html_attribute_or_tag_name"
  }
  ```

### 2. PlaceholderResolver (`src/placeholder_resolver.py`)
- **Responsibility**: Match the `{{ACTION:description}}` tokens from the skeleton against the scraped element metadata.
- **Algorithm**: Keyword-based intersection scoring.
    1. Tokenize the placeholder description.
    2. Tokenize the text and role attributes of all elements found on the target pages.
    3. Calculate the intersection (overlap) between token sets.
    4. If overlap $\ge$ threshold, return the `selector`.
    5. Otherwise, return a `pytest.skip` instruction.

### 3. Integration Layer (`src/orchestrator.py`)
- **Responsibility**: The bridge between Session 01 (Generation) and Session 02 (Resolution).
- **Workflow**:
    1. Receive Skeleton from `TestGenerator`.
    2. Extract target URLs via `SkeletonParser`.
    3. Trigger `PageScraper` for all identified URLs.
    4. Run `PlaceholderResolver` to map elements back to the skeleton string.
    5. Perform string replacement to produce final, executable Python code.

## Success Criteria
- [x] Successfully identify CSS selectors for buttons/links using keyword matching.
- [x] Gracefully handle cases where no element matches (via `pytest.skip`).
- [x] Maintain the integrity of the original test structure while updating locators.