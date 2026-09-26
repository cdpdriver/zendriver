from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from tests.docs import import_from_path

# the tutorial code stops the browser when it is done
pytestmark = pytest.mark.fresh_browser


async def test_infinite_scrolling_tutorial_1(
    mocker: MockerFixture, mock_print: Mock, mock_start: Mock
) -> None:
    module = import_from_path("docs/tutorials/tutorial-code/infinite-scrolling-1.py")

    await module.main()

    mock_print.assert_called_once_with([])


async def test_infinite_scrolling_tutorial_2(
    mocker: MockerFixture, mock_print: Mock, mock_start: Mock
) -> None:
    module = import_from_path("docs/tutorials/tutorial-code/infinite-scrolling-2.py")

    await module.main()

    mock_print.assert_has_calls(
        [mocker.call(f"Card {i}") for i in range(1, 11)],
    )


async def test_infinite_scrolling_tutorial_3(
    mocker: MockerFixture, mock_print: Mock, mock_start: Mock
) -> None:
    module = import_from_path("docs/tutorials/tutorial-code/infinite-scrolling-3.py")

    await module.main()

    mock_print.assert_has_calls(
        [
            mocker.call("Loaded new cards. Current count:", 10),
            mocker.call("Loaded new cards. Current count:", 20),
            mocker.call("Loaded new cards. Current count:", 30),
            mocker.call("Lucky card found: Card 27"),
        ]
    )
