import asyncio

import zendriver as zd
from zendriver import Tab


async def create_account(page: Tab, name: str, email: str, password: str) -> None:
    # Click on the "Sign up" link
    sign_up_link = next(a for a in await page.select_all("a") if "Sign up" in a.text)
    await sign_up_link.click()
    await asyncio.sleep(0.5)

    # Fill in the sign-up form
    name_input = await page.select("#signupName")
    await name_input.send_keys(name)
    email_input = await page.select("#signupEmail")
    await email_input.send_keys(email)
    password_input = await page.select("#signupPassword")
    await password_input.send_keys(password)

    # Click the "Sign Up" button
    sign_up_button = next(
        button for button in await page.select_all("button") if "Sign Up" in button.text
    )
    await sign_up_button.click()
    await asyncio.sleep(0.5)

    # Click through confirmation dialog
    proceed_to_login = await page.find(text="Proceed to Login")
    await proceed_to_login.click()


async def login(page: Tab, email: str, password: str) -> None:
    # Fill in the login form
    email_input = await page.select("#loginEmail")
    await email_input.send_keys(email)
    password_input = await page.select("#loginPassword")
    await password_input.send_keys(password)

    # Click the "Login" button
    login_button = next(
        button for button in await page.select_all("button") if "Login" in button.text
    )
    await login_button.click()
    await asyncio.sleep(0.5)

    # Verify successful login
    message = await page.select("#message")
    if "Welcome back" in message.text_all:
        print("Login successful")
    else:
        print("Login failed")


async def main() -> None:
    browser = await zd.start()
    page = await browser.get(
        "https://cdpdriver.github.io/examples/login-page.html",
    )
    await asyncio.sleep(0.5)  # Wait for the page to load

    name = "John Doe"
    email = "john.doe@example.com"
    password = "securepassword"

    await create_account(page, name, email, password)
    await login(page, email, password)

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
