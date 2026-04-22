import asyncio

from dotenv import load_dotenv

from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


async def test_full_pipeline():
    load_dotenv()
    print("Initializing full pipeline...")
    try:
        client = LLMClient()
        generator = TestGenerator(client=client)
        orchestrator = TestOrchestrator(generator)

        user_story = "As a user, I want to add a product to the cart so that I can buy it."
        conditions = "1. Add a product to the cart\n2. Verify product is in cart"
        target_urls = ["https://example.com"]

        print(f"Running pipeline for user story: {user_story}")
        final_code = await orchestrator.run_pipeline(user_story, conditions, target_urls)

        print("Pipeline finished successfully.")
        print("--- Final Code Snippet ---")
        print(final_code)
        print("--- End Code Snippet ---")

        if not final_code or len(final_code) < 50:
            print("UAT Failed: Final code is too short or empty.")
        else:
            print("UAT Success: Pipeline completed and generated code.")

    except Exception as e:
        print(f"UAT Failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
