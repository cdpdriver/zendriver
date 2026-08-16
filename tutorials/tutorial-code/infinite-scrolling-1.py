import asyncio

import zendriver as zd


async def main() -> None:
    browser = await zd.start()
    page = await browser.get(
        "https://cdpdriver.github.io/examples/scrollable-cards.html",
    )

    # Not yet loaded, so empty
    card_container = await page.select("#card-container")
    cards = card_container.children
    print(cards)  # []

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
