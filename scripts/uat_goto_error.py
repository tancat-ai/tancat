"""UAT script to replicate the GOTO error in the Streamlit app."""

import asyncio
import os
import sys

# Ensure the project root is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()
os.environ["PIPELINE_DEBUG"] = "1"

from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


async def test_pipeline():
    print("Initializing pipeline with lm-studio provider...")
    client = LLMClient(
        provider="lm-studio",
        base_url="http://localhost:1234",
        model="qwen3.6-35b-a3b",
    )
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator)

    user_story = "As a customer I want to add items to cart"
    conditions = """1. add items to cart
2. go to cart
3. check the items have been added correctly
4. go to check out
5. check out

(Total: 5 criteria)"""
    target_urls = ["https://automationexercise.com/"]

    print(f"User story: {user_story}")
    print(f"Conditions:\n{conditions}")
    print(f"Target URLs: {target_urls}")
    print("-" * 60)

    try:
        final_code = await orchestrator.run_pipeline(
            user_story=user_story,
            conditions=conditions,
            target_urls=target_urls,
            consent_mode="auto-dismiss",
        )
        print("-" * 60)
        print("Pipeline completed successfully!")
        print(f"Final code length: {len(final_code)} chars")
        print(f"Final code preview:\n{final_code[:500]}")
    except Exception as e:
        print("-" * 60)
        print(f"Pipeline failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_pipeline())
