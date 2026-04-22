import asyncio

from dotenv import load_dotenv

from src.llm_client import LLMClient


async def test_llm_call():
    load_dotenv()
    print("Initializing LLMClient...")
    try:
        client = LLMClient()
        print(f"Provider: {client.provider_name}")
        print(f"Model: {client.model}")
        print(f"Base URL: {client.base_url}")

        prompt = "Say 'LLM is working' if you can hear me."
        print(f"Sending prompt: {prompt}")

        # Test sync call
        print("Testing sync generate_test...")
        response_sync = client.generate_test(prompt)
        print(f"Sync Response: {response_sync}")

        # Test async call
        print("Testing async generate...")
        response_async = await client.generate(prompt)
        print(f"Async Response: {response_async}")

        print("UAT Success: LLM is reachable and responding.")
    except Exception as e:
        print(f"UAT Failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_llm_call())
