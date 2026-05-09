import asyncio
from src.llm_client import LLMClient
from src.prompt_utils import get_skeleton_prompt_template, prepare_conditions_for_generation
import os
from dotenv import load_dotenv

async def main():
    load_dotenv()
    LLMClient.set_session_provider("lm-studio", model="qwen3.6-35b-a3b")
    client = LLMClient()
    user_story = "As a user, I want to log in to the shopping site, add items to my cart, verify the items in the cart, proceed to checkout, and complete the checkout process."
    conditions = """1. Log in with username standard_user and password secret_sauce
2. Add at least one item (e.g. Sauce Labs Backpack) to the cart
3. Navigate to the shopping cart page
4. Verify the added item appears correctly in the cart
5. Navigate to the checkout page
6. Complete the checkout process and verify success (Thank You page)"""
    
    prompt = get_skeleton_prompt_template(expected_count=6)
    prompt = prompt.format(
        user_story=user_story,
        conditions=prepare_conditions_for_generation(conditions),
        known_urls_block="- https://www.saucedemo.com"
    )
    
    print("Sending prompt...")
    res = await client.generate(prompt)
    print("==== LLM OUTPUT ====")
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
