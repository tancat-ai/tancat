import asyncio

from src.journey_scraper import JourneyScraper, JourneyStep

# Run the journey scraper to capture the popup
scraper = JourneyScraper(starting_url='https://automationexercise.com')

steps = [
    JourneyStep(action="navigate", url="https://automationexercise.com", description="home"),
    JourneyStep(action="click", description="Dress category link"),
    JourneyStep(action="click", description="Add to cart button"),
    JourneyStep(action="scrape", description="capture popup state"),
]

result = asyncio.run(scraper.scrape_journey(steps))
print("--- Captured Pages ---")
for url, elems in result.items():
    print(f"{url}: {len(elems)} elements")
    # Look for confirmation/addition/popup elements
    for e in elems:
        text = str(e.get('text', '')).lower()
        if any(term in text for term in ['confirm', 'added', 'popup', 'success', 'thank']):
            print(f"  MATCH: text='{e.get('text')}' | role='{e.get('role')}' | selector='{e.get('selector')}'")
