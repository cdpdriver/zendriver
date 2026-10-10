from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from tests.docs import import_from_path

# the tutorial code stops the browser when it is done
pytestmark = [pytest.mark.fresh_browser, pytest.mark.external]


async def test_cdp_tutorial_1(
    mocker: MockerFixture, mock_print: Mock, mock_start: Mock
) -> None:
    module = import_from_path("docs/tutorials/tutorial-code/cdp-1.py")

    await module.main()


async def test_cdp_tutorial_2(
    mocker: MockerFixture, mock_print: Mock, mock_start: Mock
) -> None:
    module = import_from_path("docs/tutorials/tutorial-code/cdp-2.py")

    await module.main()

    mock_print.assert_any_call("Console message: log - Button clicked!")
