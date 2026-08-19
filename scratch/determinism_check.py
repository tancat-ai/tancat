"""Throwaway evidence step 1: skeleton-generation determinism at pinned temp.

Generates the same small story twice through the LINEAR path
(TestGenerator.generate_skeleton -> LLMClient.generate) and reports whether
the two skeletons are byte-identical. PIPELINE_DEBUG=1 makes llm_client print
the delivered temp per call (evidence the pin is delivered).
"""

import asyncio
import os

os.environ["PIPELINE_DEBUG"] = "1"
os.environ.setdefault("RAG_ENABLED", "0")

from src.llm_client import LLMClient
from src.test_generator import TestGenerator

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


async def main() -> None:
    generator = TestGenerator(client=LLMClient())
    skeletons: list[str] = []
    for i in (1, 2):
        print(f"--- generation {i} ---", flush=True)
        skeleton = await generator.generate_skeleton(
            user_story=STORY,
            conditions=CONDITIONS,
            target_urls=URLS,
            expected_count=5,
        )
        skeletons.append(skeleton)
        print(f"--- generation {i} done: {len(skeleton)} chars ---", flush=True)

    identical = skeletons[0] == skeletons[1]
    print("=" * 60)
    print(f"IDENTICAL: {identical}")
    if not identical:
        import difflib

        diff = difflib.unified_diff(
            skeletons[0].splitlines(), skeletons[1].splitlines(), lineterm="", n=1
        )
        print("\n".join(list(diff)[:80]))


asyncio.run(main())
