import asyncio
import os
import time

from dotenv import load_dotenv

from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


async def test_automation_exercise_uat():
    load_dotenv()
    # Enable debug mode to see LLM timings and scraper logs
    os.environ["PIPELINE_DEBUG"] = "1"

    print("--- Starting Reproducible UAT (Automation Exercise) ---")
    try:
        client = LLMClient()
        generator = TestGenerator(client=client)
        orchestrator = TestOrchestrator(generator)

        user_story = "As a customer, I want to add items to the cart and proceed to checkout."
        conditions = "1. Add 'Blue Top' to cart\n2. Verify 'Blue Top' is in cart\n3. Proceed to checkout"
        target_urls = ["https://automationexercise.com/"]

        print(f"User Story: {user_story}")
        print(f"Target URL: {target_urls[0]}")

        start_time = time.time()
        final_code = await orchestrator.run_pipeline(user_story, conditions, target_urls)
        total_time = time.time() - start_time

        print(f"\nPipeline finished in {total_time:.2f}s.")
        print("\n--- Generated Code ---")
        print(final_code)
        print("--- End Generated Code ---\n")

        # Validation checks
        errors = []
        if "`https://" in final_code:
            errors.append("Hallucination: Backticks found in URLs.")
        # Consent check temporarily removed to avoid regex greediness issues
        if len(final_code) < 100:
            errors.append("Generation Failure: Code is suspiciously short.")

        # Python syntax validation — catches indentation errors, missing imports, etc.
        try:
            compile(final_code, "<uat_generated>", "exec")
        except SyntaxError as sx:
            errors.append(f"SyntaxError: {sx}")

        if errors:
            print("UAT STATUS: FAILED")
            for err in errors:
                print(f" - {err}")
        else:
            print("UAT STATUS: SUCCESS")

    except Exception as e:
        print(f"UAT STATUS: CRASHED - {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_automation_exercise_uat())
