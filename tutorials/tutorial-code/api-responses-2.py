import asyncio
import json

import zendriver as zd
from zendriver.cdp.network import get_response_body


async def main() -> None:
    browser = await zd.start()

    page = browser.tabs[0]
    async with page.expect_response(".*/user-data.json") as response_expectation:
        await page.get(
            "https://cdpdriver.github.io/examples/api-request.html",
        )
        response = await response_expectation.value

    request_id = response.request_id
    body, _ = await page.send(get_response_body(request_id=request_id))
    user_data = json.loads(body)

    print("Successfully read user data response for user:", user_data["name"])
    print(json.dumps(user_data, indent=2))

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
