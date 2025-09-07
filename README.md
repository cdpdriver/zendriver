# Zendriver ✌️

[![License](https://img.shields.io/github/license/cdpdriver/zendriver)](LICENSE)
[![Pypi Version](https://img.shields.io/pypi/v/zendriver)](https://pypi.org/project/zendriver/)
[![Issues](https://img.shields.io/github/issues/cdpdriver/zendriver)]()
[![Pull Requests](https://img.shields.io/github/issues-pr/cdpdriver/zendriver)]()
[![codecov](https://codecov.io/github/cdpdriver/zendriver/branch/main/graph/badge.svg?token=F7K641TYFZ)](https://codecov.io/github/cdpdriver/zendriver)

> This package is a fork of [`ultrafunkamsterdam/nodriver`](https://github.com/ultrafunkamsterdam/nodriver/), created to add new features, compile unmerged bugfixes, and increase community engagement.

* **Documentation:** [zendriver.dev](https://zendriver.dev)
* **AI-generated wiki:** [deepwiki.com/cdpdriver/zendriver](https://deepwiki.com/cdpdriver/zendriver)

Zendriver is a blazing fast, async-first, undetectable webscraping/web automation framework implemented using the Chrome Devtools Protocol. Visit websites, scrape content, and run JavaScript using a real browser (no Selenium/Webdriver) all with just a few lines of Python.

**Docker support is here!** Check out [`cdpdriver/zendriver-docker`](https://github.com/cdpdriver/zendriver-docker) for an example of how to run Zendriver with a real, GPU-accelerated browser (not headless) in a Docker container. (Linux-only)

## Features

- **Undetectable** - Zendriver uses the Chrome Devtools Protocol instead of Selenium/WebDriver, making it (almost) impossible to detect
- **Blazing fast** - Chrome Devtools Protocol is _fast_, much faster than previous Selenium/WebDriver solutions. CDP combined with an async Python API makes Zendriver highly performant.
- **Feature complete and easy to use** - Packed with allowing you to get up and running in just a few lines of code.
- **First-class Docker support** - Traditionally, browser automation has been incredibly difficult to package with Docker, especially if you want to run real, GPU-accelerated Chrome (not headless). Now, deploying with Docker is easier than ever using the officially supported [zendriver-docker project template](https://github.com/cdpdriver/zendriver-docker).
- **Automatic cookie and profile management** - By default, uses fresh profile on each run, cleaning up on exit. Or, save and load cookies to a file to avoid repeating tedious login steps.
- **Smart element lookup** - Find elements selector or text, including iframe content. This could also be used as wait condition for a element to appear, since it will retry for the duration of `timeout` until found. Single element lookup by text using `tab.find()` accepts a `best_match flag`, which will not naively return the first match, but will match candidates by closest matching text length.
- **Easy debugging** - Descriptive `repr` for elements, which represents the element as HTML, makes debugging much easier.

## Installation

To install, simply use `pip` (or your favorite package manager):

```sh
pip install zendriver
# or uv add zendriver, poetry add zendriver, etc.
```

## Usage

Example for visiting [https://www.browserscan.net/bot-detection](https://www.browserscan.net/bot-detection) and saving a screenshot of the results:

```python
import asyncio

import zendriver as zd


async def main():
    browser = await zd.start()
    page = await browser.get("https://www.browserscan.net/bot-detection")
    await page.save_screenshot("browserscan.png")
    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

Check out the [Quickstart](https://zendriver.dev/quickstart/) for more information and examples.

## Rationale for the fork

Zendriver remains committed to `nodriver`'s goals of staying undetected for all modern anti-bot solutions and also keeps with the batteries-included approach of its predecessor. Unfortunately, contributions to the original [`nodriver` repo](https://github.com/ultrafunkamsterdam/nodriver/) are heavily restricted, making it difficult to submit issues or pull requests. At the time of writing, there are several pull requests open to fix critical bugs which have beeen left unaddressed for many months.

Zendriver aims to change this by:

1. Including open pull requests in the original `nodriver` repo as part of the initial release
2. Modernizing the development process to include static analysis tools such as [`ruff`](https://docs.astral.sh/ruff/) and [`mypy`](https://mypy-lang.org/), reducing the number of easy-to-catch bugs which make it through in the future
3. Opening up the issue tracker and pull requests for community contributions, allowing the project to continue to grow along with its community.

With these changes in place, we hope to further development of state-of-the-art open-source web automation tools even further, helping to once again make the web truly open for all.

## Contributing

Contributions of all types are always welcome! Please see [CONTRIBUTING.md](https://github.com/cdpdriver/zendriver/blob/main/CONTRIBUTING.md) for details on how to contribute.

### Getting additional help

If you have a question, bug report, or want to make a general inquiry about the project, please create a new GitHub issue. If you are having a problem with Zendriver, please make sure to include your operating system, Chrome version, code example demonstrating the issue, and any other information that may be relevant.

Questions directed to any personal accounts outside of GitHub will be ignored.

## Sponsors

### Powered by
[![JetBrains logo.](https://resources.jetbrains.com/storage/products/company/brand/logos/jetbrains.svg)](https://jb.gg/OpenSource)
