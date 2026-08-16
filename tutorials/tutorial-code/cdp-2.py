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

    def console_handler(event: cdp.runtime.ConsoleAPICalled) -> None:
        joined_args = ", ".join([str(it.value) for it in event.args])
        print(f"Console message: {event.type_} - {joined_args}")

    # Those 2 lines are equivalent and do the same thing
    page.add_handler(runtime.ConsoleAPICalled, console_handler)
    page.add_handler(cdp.runtime.ConsoleAPICalled, console_handler)

    await (await page.select("#myButton")).click()
    await page.wait(1) # Wait for the console messages to be printed

    # Remember to remove handlers to stop listening to console events
    page.remove_handlers(runtime.ConsoleAPICalled, console_handler)
    page.remove_handlers(cdp.runtime.ConsoleAPICalled, console_handler)

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
