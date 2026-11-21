# Quickstart

## Installation

To install, simply use `pip` (or your favorite package manager):

```sh
pip install zendriver
# or uv add zendriver, poetry add zendriver, etc.
```

## Basic usage

Open a browser, navigate to a page, and scrape the content:

```python
import asyncio
import zendriver as zd

async def main():
    browser = await zd.start()
    page = await browser.get('https://example.com')

    # get HTML content of the page as a string
    content = await page.get_content()

    # save a screenshot
    await page.save_screenshot()

    # close the browser window
    await browser.stop()


if __name__ == '__main__':
    asyncio.run(main())
```

## More complete example

```python
import asyncio
import zendriver as zd

async def main():
    browser = await zd.start()
    page = await browser.get('https://zendriver.dev/')

    elems = await page.select_all('*[src]')

    for elem in elems:
        await elem.flash()

    page2 = await browser.get('https://twitter.com', new_tab=True)
    page3 = await browser.get('https://github.com/ultrafunkamsterdam/nodriver', new_window=True)

    for p in (page, page2, page3):
        await p.bring_to_front()
        await p.scroll_down(200)
        await p   # wait for events to be processed
        await p.reload()
        if p != page3:
            await p.close()

if __name__ == '__main__':
    asyncio.run(main())
```

I'll leave out the async boilerplate here

```python
import zendriver as zd

browser = await zd.start(
    headless=False,
    user_data_dir="/path/to/existing/profile",  # by specifying it, it won't be automatically cleaned up when finished
    browser_executable_path="/path/to/some/other/browser",
    browser_args=['--some-browser-arg=true', '--some-other-option'],
    lang="en-US"   # this could set iso-language-code in navigator, not recommended to change
)
tab = await browser.get('https://somewebsite.com')
```

## Alternative custom options

I'll leave out the async boilerplate here

```python
import zendriver as zd

config = zd.Config()
config.headless = False
config.user_data_dir="/path/to/existing/profile",  # by specifying it, it won't be automatically cleaned up when finished
config.browser_executable_path="/path/to/some/other/browser",
config.browser_args=['--some-browser-arg=true', '--some-other-option'],
config.lang="en-US"   # this could set iso-language-code in navigator, not recommended to change
```

On Windows, we recommend using `WindowsSelectorEventLoopPolicy` for better compatibility with asyncio:

```python
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

## Headless screen

In headless mode, Chrome reports a virtual 800x600 screen at scale 1 with 24-bit color, which has nothing to do with the host and is a common headless tell. The `screen` option describes the screen the browser should report instead (Chrome 142 or newer). It is applied process-wide by Chrome itself, so pages, iframes, workers and popups all agree.

```python
import zendriver as zd

# a plain, common desktop screen
browser = await zd.start(headless=True, screen=zd.Screen(1920, 1080))

# or something closer to a MacBook Pro: a Retina screen with a menu bar, wide gamut and HDR
browser = await zd.start(
    headless=True,
    screen=zd.Screen(
        1512,
        982,
        device_pixel_ratio=2,
        color_depth=30,
        work_area_insets=(33, 0, 0, 0),  # top, right, bottom, left, in CSS pixels
        wide_gamut=True,
        hdr=True,
    ),
)
```

A more concrete example, which can be found in the ./example/ folder,
shows a script for uploading an image to imgur.

```python
import asyncio
from pathlib import Path
import zendriver as zd

# interesting, this is a typical site which runs completely on javascript, and that causes
# this script to be faster than the js can present the elements. This may be one of the downsides
# of this fast beast. You have to carefully consider timing.
DELAY = 2

async def main():
    browser = await zd.start()
    tab = await browser.get("https://imgur.com")

    # now we first need an image to upload, lets make a screenshot of the project page
    save_path = Path("screenshot.jpg").resolve()
    # create new tab with the project page
    temp_tab = await browser.get(
        "https://github.com/ultrafunkamsterdam/undetected-chromedriver", new_tab=True
    )

    # wait page to load
    await temp_tab
    # save the screenshot to the previously declared path of screenshot.jpg (which is just current directory)
    await temp_tab.save_screenshot(save_path)
    # done, discard the temp_tab
    await temp_tab.close()

    # accept goddamn cookies
    # the best_match flag will filter the best match from
    # matching elements containing "consent" and takes the
    # one having most similar text length
    consent = await tab.find("Consent", best_match=True)
    await consent.click()

    # shortcut
    await (await tab.find("new post", best_match=True)).click()

    file_input = await tab.select("input[type=file]")
    await file_input.send_file(save_path)
    # since file upload takes a while , the next buttons are not available yet

    await tab.wait(DELAY)

    # wait until the grab link becomes clickable, by waiting for the toast message
    await tab.select(".Toast-message--check")

    # this one is tricky. we are trying to find a element by text content
    # usually. the text node itself is not needed, but it's enclosing element.
    # in this case however, the text is NOT a text node, but an "placeholder" attribute of a span element.
    # so for this one, we use the flag return_enclosing_element and set it to False
    title_field = await tab.find("give your post a unique title", best_match=True)
    print(title_field)
    await title_field.send_keys("undetected zendriver")

    grab_link = await tab.find("grab link", best_match=True)
    await grab_link.click()

    # there is a delay for the link sharing popup.
    # let's pause for a sec
    await tab.wait(DELAY)

    # get inputs of which the value starts with http
    input_thing = await tab.select("input[value^=https]")

    my_link = input_thing.attrs.value

    print(my_link)
    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
```
