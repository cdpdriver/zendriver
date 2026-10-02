import asyncio

import zendriver as zd
from zendriver import Element, Tab


async def wait_for_cards(page: Tab, initial_card_count: int) -> list[Element]:
    while True:
        card_container = await page.select("#card-container")
        cards = card_container.children
        if len(cards) > initial_card_count:
            print("Loaded new cards. Current count:", len(cards))
            return cards
        await asyncio.sleep(0.5)


def get_lucky_card(cards: list[Element]) -> Element | None:
    for card in cards:
        if "Congratulations, you found the lucky card!" in card.text_all:
            return card

    return None


async def main() -> None:
    browser = await zd.start()
    page = await browser.get(
        "https://cdpdriver.github.io/examples/scrollable-cards.html",
    )

    # Wait for the first batch of cards to load
    cards = await wait_for_cards(page, initial_card_count=0)

    # Loop until we find the lucky card
    while (lucky_card := get_lucky_card(cards)) is None:
        # Scroll to the bottom of the page
        await page.scroll_down(1000, speed=7777)  # 10x page height, likely to be enough

        # Get the new cards
        cards = await wait_for_cards(page, initial_card_count=len(cards))

    if lucky_card:
        print(f"Lucky card found: Card {cards.index(lucky_card) + 1}")

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
