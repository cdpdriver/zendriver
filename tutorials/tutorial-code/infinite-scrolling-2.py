import asyncio

import zendriver as zd
from zendriver import Element, Tab


async def wait_for_cards(page: Tab, initial_card_count: int) -> list[Element]:
    while True:
        card_container = await page.select("#card-container")
        cards = card_container.children
        if len(cards) > initial_card_count:
            return cards
        await asyncio.sleep(0.5)


async def main() -> None:
    browser = await zd.start()
    page = await browser.get(
        "https://cdpdriver.github.io/examples/scrollable-cards.html",
    )

    # Wait for cards to load
    cards = await wait_for_cards(page, initial_card_count=0)

    # Now we can print the cards
    # (shows first 10 cards: Card 1, Card 2...Card 9, Card 10)
    for card in cards:
        print(card.text)

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
