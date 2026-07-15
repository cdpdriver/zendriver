import asyncio

import zendriver as zd
from zendriver import cdp
from zendriver.cdp import runtime


async def main() -> None:
    browser = await zd.start()
    page = await browser.get(
        "https://cdpdriver.github.io/examples/console.html",
    )

    # Those 2 lines are equivalent and do the same thing
    await page.send(runtime.enable())
    await page.send(cdp.runtime.enable())

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
