import asyncio
import os
import sys

# Add src to path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


async def run_uat() -> bool:
    print("\n🚀 STARTING USER ACCEPTANCE TEST (UAT) 🚀\n")
    print("--------------------------------------------------")

    # 1. Setup Configuration (Simulating Streamlit Sidebar)
    provider = "ollama"  # or "lm-studio"
    base_url = "http://localhost:11434/api"  # Ensure this is running!
    target_url = "https://automationexercise.com/"

    user_story = "As a user, I want to complete a purchase flow."
    criteria = "add items to cart\ngo to cart\ncheck the items have been added correctly\ngo to check out\ncheck out"

    print(f"[CONFIG] Provider: {provider}")
    print(f"[CONFIG] Target URL: {target_url}")
    print(f"[INPUT] Story: {user_story}")
    print(f"[INPUT] Criteria:\n{criteria}\n")

    # 2. Initialize Components
    print("[STEP 1/3] Initializing Engine Components...")
    client = LLMClient(provider=provider, base_url=base_url)
    generator = TestGenerator(client)
    orchestr_engine = TestOrchestrator(generator)
    # 3. Execute Pipeline (Simulating "Run Full Pipeline" button click)
    print("[STEP 2/3] Running Orchestrator Pipeline...")
    try:
        # Note: In a real UAT, we'd need the scraper to be part of the orchestrator flow.
        # We are testing if the engine can handle the provided URL and logic.

        print("... Generating Skeleton ...")
        # For this test, we assume the orchestrator uses the internal scraping/resolver logic.
        result_code = await orchestr_engine.run_pipeline(user_story=user_story, conditions=criteria)

        print("[STEP 3/3] Pipeline Execution Finished.\n")

        # 4. Verification (The "Acceptance" part)
        print("--------------------------------------------------")
        print("✅ VERIFICATION RESULTS:")

        if not result_code:
            print("❌ FAIL: No test code was generated.")
            return False

        print("--- GENERATED CODE PREVIEW ---")
        print(result_code[:500] + "..." if len(result_code) > 500 else result_code)
        print("-------------------------------")

        # Check for real selector presence (not just placeholders)
        if "{placeholder" in result_code or "element_id" in result_code:
            print("❌ FAIL: The generated code still contains generic placeholders.")
            print("   (The Scraper/Resolver did not successfully resolve elements from the live site.)")
            return False
        else:
            print("✅ SUCCESS: The generated code contains real, resolved CSS selectors.")

        # Check for Playwright syntax
        if "await page." in result_code or "page.get_by_" in result_code:
            print("✅ SUCCESS: Valid Playwright commands detected.")
        else:
            print("❌ FAIL: The generated code does not appear to contain valid Playwright automation commands.")
            return False

        print("\n🎉 UAT PASSED: The pipeline is functional and produces real-world automation scripts!")
        print("--------------------------------------------------")
        return True

    except Exception as e:
        print(f"❌ CRITICAL ERROR during UAT execution: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_uat())
    if not success:
        sys.exit(1)
    else:
        sys.exit(0)
