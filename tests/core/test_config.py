import pathlib

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


def get_disable_features_args(args: list[str]) -> list[str]:
    return [arg for arg in args if arg.startswith("--disable-features=")]


def test_disable_features_is_passed_once() -> None:
    config = zd.Config(
        browser_executable_path=FAKE_BROWSER_PATH,
        browser_args=["--disable-features=UseOzonePlatform,site-per-process"],
    )

    assert get_disable_features_args(config()) == [
        "--disable-features=IsolateOrigins,DisableLoadExtensionCommandLineSwitch,site-per-process,UseOzonePlatform"
    ]


def test_extensions_enable_unsafe_extension_debugging(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "manifest.json").write_text("{}")
    config = zd.Config(browser_executable_path=FAKE_BROWSER_PATH)

    assert "--enable-unsafe-extension-debugging" not in config()

    config.add_extension(tmp_path)

    assert "--enable-unsafe-extension-debugging" in config()


def test_expert_does_not_disable_web_security() -> None:
    config = zd.Config(browser_executable_path=FAKE_BROWSER_PATH, expert=True)
    args = config()

    assert "--disable-site-isolation-trials" in args
    assert "--disable-web-security" not in args
