import asyncio

import zendriver as zd


async def main() -> None:
    browser = await zd.start()

    # TODO: Read the API response
    page = await browser.get(
        "https://cdpdriver.github.io/examples/api-request.html",
    )

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
