import zendriver as zd

# The path is never executed, it only has to be set so that Config does not try to
# autodetect a browser binary on machines that do not have one installed.
FAKE_BROWSER_PATH = "/path/to/browser"


def test_lang_is_added_to_browser_args() -> None:
    config = zd.Config(browser_executable_path=FAKE_BROWSER_PATH, lang="de-DE")

    assert "--lang=de-DE" in config()


def test_lang_is_omitted_when_unset() -> None:
    config = zd.Config(browser_executable_path=FAKE_BROWSER_PATH)

    assert not any(arg.startswith("--lang=") for arg in config())


def test_lang_can_be_combined_with_other_browser_args() -> None:
    config = zd.Config(
        browser_executable_path=FAKE_BROWSER_PATH,
        lang="fr-FR",
        browser_args=["--mute-audio"],
    )
    args = config()

    assert "--lang=fr-FR" in args
    assert "--mute-audio" in args


def test_add_argument_still_rejects_lang() -> None:
    """`lang` remains an attribute-only setting, it is not set through add_argument."""
    config = zd.Config(browser_executable_path=FAKE_BROWSER_PATH)

    try:
        config.add_argument("--lang=de-DE")
    except ValueError:
        return
    raise AssertionError("add_argument should reject --lang")
