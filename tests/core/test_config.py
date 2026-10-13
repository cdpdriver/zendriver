import pathlib

import pytest

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


def get_screen_args(args: list[str]) -> list[str]:
    return [
        arg
        for arg in args
        if arg.startswith(("--screen-info=", "--force-color-profile="))
    ]


def test_screen_is_added_to_headless_browser_args() -> None:
    config = zd.Config(
        browser_executable_path=FAKE_BROWSER_PATH,
        headless=True,
        screen=zd.Screen(1920, 1080),
    )

    assert get_screen_args(config()) == [
        "--screen-info={1920x1080 devicePixelRatio=1 colorDepth=24}"
    ]


def test_screen_sizes_and_insets_are_converted_to_physical_pixels() -> None:
    """Chrome's --screen-info takes physical pixels, the Screen takes CSS pixels."""
    config = zd.Config(
        browser_executable_path=FAKE_BROWSER_PATH,
        headless=True,
        screen=zd.Screen(
            1512,
            982,
            device_pixel_ratio=2,
            color_depth=30,
            work_area_insets=(33, 0, 0, 0),
            wide_gamut=True,
        ),
    )

    assert get_screen_args(config()) == [
        "--screen-info={3024x1964 devicePixelRatio=2 colorDepth=30 workAreaTop=66}",
        "--force-color-profile=display-p3-d65",
    ]


def test_screen_work_area_insets_cover_all_sides() -> None:
    screen = zd.Screen(
        1920, 1080, device_pixel_ratio=1.5, work_area_insets=(10, 20, 30, 40)
    )

    assert screen.browser_args() == [
        "--screen-info={2880x1620 devicePixelRatio=1.5 colorDepth=24"
        " workAreaTop=15 workAreaRight=30 workAreaBottom=45 workAreaLeft=60}"
    ]


def test_screen_hdr_uses_hdr_color_profile() -> None:
    screen = zd.Screen(1920, 1080, wide_gamut=True, hdr=True)

    assert "--force-color-profile=hdr10" in screen.browser_args()


def test_screen_without_wide_gamut_or_hdr_does_not_force_color_profile() -> None:
    screen = zd.Screen(1920, 1080)

    assert not any(
        arg.startswith("--force-color-profile=") for arg in screen.browser_args()
    )


def test_screen_is_ignored_when_not_headless() -> None:
    config = zd.Config(
        browser_executable_path=FAKE_BROWSER_PATH,
        headless=False,
        screen=zd.Screen(1920, 1080, wide_gamut=True),
    )

    assert get_screen_args(config()) == []


def test_screen_is_omitted_when_unset() -> None:
    config = zd.Config(browser_executable_path=FAKE_BROWSER_PATH, headless=True)

    assert get_screen_args(config()) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 0, "height": 1080},
        {"width": 1920, "height": -1},
        {"width": 1920, "height": 1080, "device_pixel_ratio": 0.25},
        {"width": 1920, "height": 1080, "color_depth": 0},
        {"width": 1920, "height": 1080, "work_area_insets": (0, 0)},
        {"width": 1920, "height": 1080, "work_area_insets": (-1, 0, 0, 0)},
        {"width": 1920, "height": 1080, "work_area_insets": (540, 0, 540, 0)},
    ],
)
def test_screen_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        zd.Screen(**kwargs)  # type: ignore[arg-type]
