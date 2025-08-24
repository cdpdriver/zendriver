import asyncio
import re
from typing import Union, Any

from .. import cdp
from .connection import Connection


class BaseRequestExpectation:
    """
    Base class for handling request and response expectations.
    This class provides a context manager to wait for specific network requests and responses
    based on a URL pattern. It sets up handlers for request and response events and provides
    properties to access the request, response, and response body.
    :param tab: The Tab instance to monitor.
    :type tab: Tab
    :param url_pattern: The URL pattern to match requests and responses.
    :type url_pattern: Union[str, re.Pattern[str]]
    """

    def __init__(self, tab: Connection, url_pattern: Union[str, re.Pattern[str]]):
        self.tab = tab
        self.url_pattern = url_pattern
        self.request_future: asyncio.Future[cdp.network.RequestWillBeSent] = (
            asyncio.Future()
        )
        self.response_future: asyncio.Future[cdp.network.ResponseReceived] = (
            asyncio.Future()
        )
        self.loading_finished_future: asyncio.Future[cdp.network.LoadingFinished] = (
            asyncio.Future()
        )
        self.request_id: Union[cdp.network.RequestId, None] = None

    async def _request_handler(self, event: cdp.network.RequestWillBeSent) -> None:
        """
        Internal handler for request events.
        :param event: The request event.
        :type event: cdp.network.RequestWillBeSent
        """
        if re.fullmatch(self.url_pattern, event.request.url):
            self._remove_request_handler()
            self.request_id = event.request_id
            self.request_future.set_result(event)

    async def _response_handler(self, event: cdp.network.ResponseReceived) -> None:
        """
        Internal handler for response events.
        :param event: The response event.
        :type event: cdp.network.ResponseReceived
        """
        if event.request_id == self.request_id:
            self._remove_response_handler()
            self.response_future.set_result(event)

    async def _loading_finished_handler(
        self, event: cdp.network.LoadingFinished
    ) -> None:
        """
        Internal handler for loading finished events.
        :param event: The loading finished event.
        :type event: cdp.network.LoadingFinished
        """
        if event.request_id == self.request_id:
            self._remove_loading_finished_handler()
            self.loading_finished_future.set_result(event)

    def _remove_request_handler(self) -> None:
        """
        Remove the request event handler.
        """
        self.tab.remove_handlers(cdp.network.RequestWillBeSent, self._request_handler)

    def _remove_response_handler(self) -> None:
        """
        Remove the response event handler.
        """
        self.tab.remove_handlers(cdp.network.ResponseReceived, self._response_handler)

    def _remove_loading_finished_handler(self) -> None:
        """
        Remove the loading finished event handler.
        """
        self.tab.remove_handlers(
            cdp.network.LoadingFinished, self._loading_finished_handler
        )

    async def __aenter__(self):  # type: ignore
        """
        Enter the context manager, adding request and response handlers.
        """
        await self._setup()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """
        Exit the context manager, removing request and response handlers.
        """
        self._teardown()

    async def _setup(self) -> None:
        self.tab.add_handler(cdp.network.RequestWillBeSent, self._request_handler)
        self.tab.add_handler(cdp.network.ResponseReceived, self._response_handler)
        self.tab.add_handler(
            cdp.network.LoadingFinished, self._loading_finished_handler
        )

    def _teardown(self) -> None:
        self._remove_request_handler()
        self._remove_response_handler()
        self._remove_loading_finished_handler()

    async def reset(self) -> None:
        """
        Resets the internal state, allowing the expectation to be reused.
        """
        self.request_future = asyncio.Future()
        self.response_future = asyncio.Future()
        self.loading_finished_future = asyncio.Future()
        self.request_id = None
        self._teardown()
        await self._setup()

    @property
    async def request(self) -> cdp.network.Request:
        """
        Get the matched request.
        :return: The matched request.
        :rtype: cdp.network.Request
        """
        return (await self.request_future).request

    @property
    async def response(self) -> cdp.network.Response:
        """
        Get the matched response.
        :return: The matched response.
        :rtype: cdp.network.Response
        """
        return (await self.response_future).response

    @property
    async def response_body(self) -> tuple[str, bool]:
        """
        Get the body of the matched response.
        :return: The response body.
        :rtype: str
        """
        request_id = (await self.response_future).request_id
        await (
            self.loading_finished_future
        )  # Ensure the loading is finished before fetching the body
        body = await self.tab.send(cdp.network.get_response_body(request_id=request_id))
        return body


class RequestExpectation(BaseRequestExpectation):
    """
    Class for handling request expectations.
    This class extends `BaseRequestExpectation` and provides a property to access the matched request.
    :param tab: The Tab instance to monitor.
    :type tab: Tab
    :param url_pattern: The URL pattern to match requests.
    :type url_pattern: Union[str, re.Pattern[str]]
    """

    @property
    async def value(self) -> cdp.network.RequestWillBeSent:
        """
        Get the matched request event.
        :return: The matched request event.
        :rtype: cdp.network.RequestWillBeSent
        """
        return await self.request_future


class ResponseExpectation(BaseRequestExpectation):
    """
    Class for handling response expectations.
    This class extends `BaseRequestExpectation` and provides a property to access the matched response.
    :param tab: The Tab instance to monitor.
    :type tab: Tab
    :param url_pattern: The URL pattern to match responses.
    :type url_pattern: Union[str, re.Pattern[str]]
    """

    @property
    async def value(self) -> cdp.network.ResponseReceived:
        """
        Get the matched response event.
        :return: The matched response event.
        :rtype: cdp.network.ResponseReceived
        """
        return await self.response_future


class DownloadExpectation:
    def __init__(self, tab: Connection):
        self.tab = tab
        self.future: asyncio.Future[cdp.browser.DownloadWillBegin] = asyncio.Future()
        # TODO: Improve
        self.default_behavior = (
            self.tab._download_behavior[0] if self.tab._download_behavior else "default"
        )

    async def _handler(self, event: cdp.browser.DownloadWillBegin) -> None:
        self._remove_handler()
        self.future.set_result(event)

    def _remove_handler(self) -> None:
        self.tab.remove_handlers(cdp.browser.DownloadWillBegin, self._handler)

    async def __aenter__(self) -> "DownloadExpectation":
        """
        Enter the context manager, adding download handler, set download behavior to deny.
        """
        await self.tab.send(
            cdp.browser.set_download_behavior(behavior="deny", events_enabled=True)
        )
        self.tab.add_handler(cdp.browser.DownloadWillBegin, self._handler)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """
        Exit the context manager, removing handler, set download behavior to default.
        """
        await self.tab.send(
            cdp.browser.set_download_behavior(behavior=self.default_behavior)
        )
        self._remove_handler()

    @property
    async def value(self) -> cdp.browser.DownloadWillBegin:
        return await self.future
