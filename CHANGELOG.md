# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Fix `browser.stopped` to detect when the browser was closed by the user. @puc9
- Fix typo in `Browser._handle_target_update` that prevented target_info updates @puc9
- Fix [#128](https://github.com/cdpdriver/zendriver/issues/218): TimeoutError caused by Tab.xpath @ionutcatana

### Added

### Changed

- Fix `.dockerignore` @tomokinakamaru

### Removed


## [0.14.3] - 2025-09-28

### Fixed

- Fix WebRTC IP Leaks @ethcipher

### Added

- Add `disable_webRTC` and `disable_webGL` agrs to `Config` class @ethcipher

## [0.14.2] - 2025-09-09

### Fixed

- Fix `evaluate` to return the correct value instead of None for falsy values @thromer

## [0.14.1] - 2025-09-07

### Fixed

- Fix calls to `evaluate` that return JSON: only set `serialization_options` when `return_by_value=False` @thromer
- Fix [#184](https://github.com/cdpdriver/zendriver/issues/184): `download_path` error in `DownloadExpectation` @MadsHangaard

## [0.14.0] - 2025-08-28

### Fixed

- Add nodriver evaluate serialization options for improved JavaScript evaluation @dbrun3

### Added

- Allow reset expect and intercept @nathanfallet

## [0.13.1] - 2025-07-27

### Fixed

- Remove unnecessary usage of `typing_extensions` (fixes `No module named 'typing_extensions'` error) @stephanlensky
- Fix verify_cf() @H1steria
- Fix relative coordinates of flash_point() @H1steria

### Added

- Add flash_point() to Tab.mouse_click() @H1steria

### Changed

- Remove Connection `__getattr__` and replace it with declared `@property` @nathanfallet
- Deprecate Element `__getattr__` and add `get(name: str)` method @nathanfallet

## [0.13.0] - 2025-07-24

### Fixed

- Gracefully close the browser process on exit @nathanfallet

### Added

- Add support for Brave browser @H1steria

## [0.12.1] - 2025-07-17

### Fixed

- Remove usage of StrEnum to fix compatibility with Python 3.10 @stephanlensky

## [0.12.0] - 2025-07-17

### Added

- Added `Tab.intercept` @nathanfallet

## [0.11.0] - 2025-07-16

### Added

- Complete rewrite of keyboard input system with new `KeyEvents` class in `zendriver.core.keys` @hvgupta
  - Added support for modifiers (Ctrl, Alt, Shift, Meta)
  - Added support for special keys including arrows, escape, delete and backspace
  - Added `KeyEvents.from_text()` class method for converting plain text to cdp events
  - Added `KeyEvents.from_mixed_input()` class method for handling mixed sequences of text, special keys to cdp events
  - Proper Handling of shift variants of keys
  - Comprehensive key event types: `CHAR`, `KEY_DOWN`, `KEY_UP`
  - Added key event type (`DOWN_AND_UP`) as a combination of `KEY_DOWN` and `KEY_UP`

### Changed

- `Element.send_keys()` now uses the new `KeyEvents` system (it is still backwards compatible with passing a string) @hvgupta
- Key event processing now properly handles modifier key sequences @hvgupta
- Update CDP schemas @nathanfallet

## [0.10.2] - 2025-07-06

### Fixed

- Refactor to asynchronous handlers to avoid blocking the listening loop @nathanfallet

## [0.10.1] - 2025-07-06

### Fixed

- Added `Tab.flash_point` from nodriver @nathanfallet
- Ensured loading is finished in expect @nathanfallet

## [0.10.0] - 2025-07-05

### Fixed

- Refactor element waiting loops in `find_*` and `select*` methods. @H1steria
- Improve `query_selector` error handling to consistently return `None` when a node is not found. @H1steria
- Add user_agent option to allow bypassing cloudflare javascript challenge in headless mode. @H1steria
- Fixed `lang` parameter never being set in `Browser.start` @nathanfallet

### Added

- Added `mouse_move` and `mouse_click` methods from nodriver. @H1steria

## [0.9.0] - 2025-07-01

### Added

- Added `speed` in `Tab.scroll_down` and `Tab.scroll_up` methods to control the scroll speed @nathanfallet
- Allow to wait for promise in `Element.apply` method @nathanfallet
- Added `Element.clear_input_by_deleting` to handle inputs with custom delete behavior @nathanfallet
- Added `Tab.xpath` from nodriver @nathanfallet

## [0.8.1] - 2025-06-07

### Fixed

- Add an optional `special_characters` flag to `Element.send_keys` to support sending special characters (e.g. emojis) @nathanfallet

## [0.8.0] - 2025-06-01

### Fixed

- Fixed tests so that they can run on Windows (and still run on Linux like before) @nathanfallet
- Remove usage of asyncio subprocess for better compatibility on Windows @nathanfallet
- Added a missing Chrome Canary path for Windows @nathanfallet
- Added a flag to re-enable `--load-extension` (disabled by default in Chrome 136+) @nathanfallet

## [0.7.1] - 2025-05-08

### Changed

- Updated CDP models @jsuarezl

## [0.7.0] - 2025-04-28

### Added

- Added `Tab.screenshot_b64` and `Element.screenshot_b64` methods to return screenshot as base64 string @falmar
- Added `Tab.print_to_pdf` to print the current page to a PDF file @stephanlensky

## [0.6.1] - 2025-04-25

### Fixed

- Fix race condition in `Browser.get` and `Tab.close` which could cause exceptions, especially when running multiple browsers in parallel @stephanlensky

## [0.6.0] - 2025-04-20

### Fixed

- `Browser.get` and `Tab.close` will now wait for their appropiate target events before returning @ccev

### Added

- Added `Tab.save_snapshot` to export the current page to MHTML format.

## [0.5.2] - 2025-04-09

### Fixed

- Fixed type annotation of `Element.children` @stephanlensky

## [0.5.1] - 2025-02-16

### Changed

- Deprecated `zendriver.loop()` function. You should instead use `asyncio` functions directly, for example:

  ```python
  asyncio.run(your_main_method())
  ```

## [0.5.0] - 2025-02-16

### Added

- Add `tab.expect_download` methods to wait for download file @3mora2

## [0.4.3] - 2025-02-11

### Added

- Add logs for Chrome process output on connection failure @stephanlensky

### Changed

- Default and launch changed to use `about:blank` (faster start and less bandwidth) @raycardillo

## [0.4.2] - 2025-02-11

### Fixed

- Multiple Browsers can be created without one affecting the other @raycardillo

## [0.4.1] - 2025-02-09

### Fixed

- Ignore irrelevant `DOM.disable` errors @raycardillo
- Test scripts improved for running on macOS @raycardillo

## [0.4.0] - 2025-02-06

### Added

- Add `tab.expect_request` and `tab.expect_response` methods to wait for a specific request or response @3mora2
- Add `tab.wait_for_ready_state` method for to wait for page to load @3mora2
- Add `tab.remove_handlers` method for removing handlers @khamaileon
- Clean up temporary profiles when `Browser.stop()` is called @barrycarey

## [0.3.1] - 2025-01-28

### Fixed

- Fixed bug in `find`/`find_element_by_text` which caused `ProtocolException` when no results were found @stephanlensky

## [0.3.0] - 2025-01-25

### Fixed

- Added `Tab.set_user_agent()` function for programmatically configuring the user-agent, language, and platform @stephanlensky
- Improved a few type annotations (`Connection.send()` function now returns correctly typed values based on the provided `cdp_obj`) @stephanlensky

## [0.2.3] - 2024-12-14

### Fixed

- Fixed mypy linting errors (attempt 2) @stephanlensky

### Added

- Handle browser process shutdown on 'Failed to connect to browser' @desoul99
- Added configurable browser connection timeout and tries @desoul99

## [0.2.2] - 2024-11-23

### Fixed

- Fix `AttributeError: 'tuple' object has no attribute 'value'` error in `connection.py` when using headless browser, @slimshreydy

## [0.2.1] - 2024-11-23

### Added

- Add automated testing framework! @stephanlensky
  - For now, just a few tests are written, including one to test browserscan.com bot detection
  - In the future, we can expand this test suite further (see [Zendriver#18](https://github.com/stephanlensky/zendriver/issues/18))
- Add return type annotation to `Tab.get_content()` @stephanlensky

### Changed

- Upgraded `websockets` to latest version (`>=14.0`) @yoori @stephanlensky

## [0.2.0] - 2024-11-17

### Changed

- Updated CDP models @stephanlensky

## [0.1.5] - 2024-11-17

### Fixed

- Reverted non-functional fixes for mypy linting errors (oops) @stephanlensky

## [0.1.4] - 2024-11-17

### Fixed

- Fixed a large number of mypy linting errors (should not result in any functional change) @stephanlensky

### Added

- Added `zendriver.__version__` attribute to get current package version at runtime @stephanlensky

## [0.1.3] - 2024-11-12

### Added

- Added support for `DOM.scrollableFlagUpdated` experimental CDP event. @michaellee94

## [0.1.2] - 2024-11-11

### Fixed

- Pinned requirement `websockets<14`, fixing the `AttributeError: 'NoneType' object has no attribute 'closed'` crash which occurs on the latest version of `websockets`. @stephanlensky
- Fixed incorrect `browser.close()` method in examples and documentation -- the correct method is `browser.stop()`. @stephanlensky
- Fixed `atexit` handler to correctly handle async `browser.stop()` method. @stephanlensky

## [0.1.1] - 2024-10-29

### Added

- Support for Python 3.10 and Python 3.11. All versions >=3.10 are now supported. @stephanlensky

## [0.1.0] - 2024-10-20

Initial version, forked from [ultrafunkamsterdam/nodriver@`1bb6003`](https://github.com/ultrafunkamsterdam/nodriver/commit/1bb6003c7f0db4d3ec05fdf3fc8c8e0804260103) with a variety of improvements.

### Fixed

- `Browser.set_all` cookies function now correctly uses provided cookies @ilkecan
- "successfully removed temp profile" message printed on exit is now only shown only when a profile was actually removed. Message is now logged at debug level instead of printed. @mreiden @stephanlensky
- Fix crash on starting browser in headless mode @ilkecan
- Fix `Browser.stop()` method to give the browser instance time to shut down before force killing @stephanlensky
- Many `ruff` lint issues @stephanlensky

### Added

- Support for linting with `ruff` and `mypy`. All `ruff` lints are fixed in the initial release, but many `mypy` issues remain to be fixed at a later date. @stephanlensky
- `py.typed` marker so importing as a library in other packages no longer causes `mypy` errors. @stephanlensky

### Changed

- Project is now built with [`uv`](https://github.com/astral-sh/uv). Automatically install dependencies to a venv with `uv sync`, run commands from the venv with `uv run`, and build the project with `uv build`. See the official [`uv` docs](https://docs.astral.sh/uv/) for more information. @stephanlensky
- Docs migrated from sphinx to [mkdocs-material](https://squidfunk.github.io/mkdocs-material/). @stephanlensky
- `Browser.stop()` is now async (so it must be `await`ed) @stephanlensky

### Removed

- Twitter account creation example @stephanlensky
