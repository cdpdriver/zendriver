import asyncio
import typing

from zendriver import cdp
from zendriver.cdp.fetch import HeaderEntry, RequestStage, RequestPattern
from zendriver.cdp.network import ResourceType
from zendriver.core.connection import Connection


class BaseFetchInterception:
    """
    Base class to wait for a Fetch response matching a URL pattern.
    Use this to collect and decode a paused fetch response, while keeping
    the use block clean and returning its own result.

    :param tab: The Tab instance to monitor.
    :param url_pattern: The URL pattern to match requests and responses.
    :param request_stage: The stage of the fetch request to intercept (e.g., request or response).
    :param resource_type: The type of resource to intercept (e.g., document, script, etc.).
    """

    def __init__(
        self,
        tab: Connection,
        url_pattern: str,
        request_stage: RequestStage,
        resource_type: ResourceType,
    ):
        self.tab = tab
        self.url_pattern = url_pattern
        self.request_stage = request_stage
        self.resource_type = resource_type
        self.response_future: asyncio.Future[cdp.fetch.RequestPaused] = asyncio.Future()

    async def _response_handler(self, event: cdp.fetch.RequestPaused) -> None:
        """
        Internal handler for response events.
        :param event: The response event.
        :type event: cdp.fetch.RequestPaused
        """
        self._remove_response_handler()
        self.response_future.set_result(event)

    def _remove_response_handler(self) -> None:
        """
        Remove the response event handler.
        """
        self.tab.remove_handlers(cdp.fetch.RequestPaused, self._response_handler)

    async def __aenter__(self) -> "BaseFetchInterception":
        """
        Enter the context manager, adding request and response handlers.
        """
        await self._setup()
        return self

    async def __aexit__(self, *args: typing.Any) -> None:
        """
        Exit the context manager, removing request and response handlers.
        """
        await self._teardown()

    async def _setup(self) -> None:
        await self.tab.send(
            cdp.fetch.enable(
                [
                    RequestPattern(
                        url_pattern=self.url_pattern,
                        request_stage=self.request_stage,
                        resource_type=self.resource_type,
                    )
                ]
            )
        )
        self.tab.enabled_domains.append(
            cdp.fetch
        )  # trick to avoid another `fetch.enable` call by _register_handlers
        self.tab.add_handler(cdp.fetch.RequestPaused, self._response_handler)

    async def _teardown(self) -> None:
        self._remove_response_handler()
        await self.tab.send(cdp.fetch.disable())

    async def reset(self) -> None:
        """
        Resets the internal state, allowing the expectation to be reused.
        """
        self.response_future = asyncio.Future()
        await self._teardown()
        await self._setup()

    @property
    async def request(self) -> cdp.network.Request:
        """
        Get the matched request.
        :return: The matched request.
        :rtype: cdp.network.request
        """
        return (await self.response_future).request

    @property
    async def response_body(self) -> tuple[str, bool]:
        """
        Get the body of the matched response.
        :return: The response body.
        :rtype: str
        """
        request_id = (await self.response_future).request_id
        body = await self.tab.send(cdp.fetch.get_response_body(request_id=request_id))
        return body

    async def fail_request(self, error_reason: cdp.network.ErrorReason) -> None:
        request_id = (await self.response_future).request_id
        await self.tab.send(
            cdp.fetch.fail_request(request_id=request_id, error_reason=error_reason)
        )

    async def continue_request(
        self,
        url: typing.Optional[str] = None,
        method: typing.Optional[str] = None,
        post_data: typing.Optional[str] = None,
        headers: typing.Optional[typing.List[HeaderEntry]] = None,
        intercept_response: typing.Optional[bool] = None,
    ) -> None:
        request_id = (await self.response_future).request_id
        await self.tab.send(
            cdp.fetch.continue_request(
                request_id=request_id,
                url=url,
                method=method,
                post_data=post_data,
                headers=headers,
                intercept_response=intercept_response,
            )
        )

    async def fulfill_request(
        self,
        response_code: int,
        response_headers: typing.Optional[typing.List[HeaderEntry]] = None,
        binary_response_headers: typing.Optional[str] = None,
        body: typing.Optional[str] = None,
        response_phrase: typing.Optional[str] = None,
    ) -> None:
        request_id = (await self.response_future).request_id
        await self.tab.send(
            cdp.fetch.fulfill_request(
                request_id=request_id,
                response_code=response_code,
                response_headers=response_headers,
                binary_response_headers=binary_response_headers,
                body=body,
                response_phrase=response_phrase,
            )
        )

    async def continue_response(
        self,
        response_code: typing.Optional[int] = None,
        response_phrase: typing.Optional[str] = None,
        response_headers: typing.Optional[typing.List[HeaderEntry]] = None,
        binary_response_headers: typing.Optional[str] = None,
    ) -> None:
        request_id = (await self.response_future).request_id
        await self.tab.send(
            cdp.fetch.continue_response(
                request_id=request_id,
                response_code=response_code,
                response_phrase=response_phrase,
                response_headers=response_headers,
                binary_response_headers=binary_response_headers,
            )
        )
