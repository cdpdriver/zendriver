from __future__ import annotations

import asyncio
import collections
import inspect
import itertools
import json
import logging
import sys
import types
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Generator,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
)

import websockets
import websockets.asyncio.client

from .. import cdp
from . import util

if TYPE_CHECKING:
    from zendriver.core.browser import Browser


T = TypeVar("T")

GLOBAL_DELAY = 0.005
MAX_SIZE: int = 2**28
PING_TIMEOUT: int = 900  # 15 minutes

TargetType = Union[cdp.target.TargetInfo, cdp.target.TargetID]

logger = logging.getLogger("uc.connection")


class ProtocolException(Exception):
    def __init__(self, *args: Any):
        self.message = None
        self.code = None
        self.args = args
        if isinstance(args[0], dict):
            self.message = args[0].get("message", None)  # noqa
            self.code = args[0].get("code", None)

        elif hasattr(args[0], "to_json"):

            def serialize(obj: Any, _d: int = 0) -> str:
                res = "\n"
                for k, v in obj.items():
                    space = "\t" * _d
                    if isinstance(v, dict):
                        res += f"{space}{k}: {serialize(v, _d + 1)}\n"
                    else:
                        res += f"{space}{k}: {v}\n"

                return res

            self.message = serialize(args[0].to_json())

        else:
            self.message = "| ".join(str(x) for x in args)

    def __str__(self) -> str:
        return f"{self.message} [code: {self.code}]" if self.code else f"{self.message}"


class SettingClassVarNotAllowedException(PermissionError):
    pass


class Transaction(asyncio.Future[T], Generic[T]):
    def __init__(self, cdp_obj: Generator[dict[str, Any], dict[str, Any], T]):
        """
        :param cdp_obj:
        """
        super().__init__()
        self.__cdp_obj__ = cdp_obj
        self.connection: Connection | None = None
        self.id: int | None = None
        self.session_id: str | None = None

        self.method, *params = next(self.__cdp_obj__).values()
        if params:
            params = params.pop()
        self.params = params

    @property
    def message(self) -> str:
        message = {"method": self.method, "params": self.params, "id": self.id}
        if self.session_id is not None:
            message["sessionId"] = self.session_id
        return json.dumps(message)

    @property
    def has_exception(self) -> bool:
        try:
            if self.exception():
                return True
        except:  # noqa
            return True
        return False

    def __call__(self, **response: dict[str, Any]) -> None:
        """
        parsed the response message and marks the future
        complete

        :param response:
        :return:
        """

        if "error" in response:
            # set exception and bail out
            return self.set_exception(ProtocolException(response["error"]))
        try:
            # try to parse the result according to the py cdp docs.
            self.__cdp_obj__.send(response["result"])
        except StopIteration as e:
            # exception value holds the parsed response
            return self.set_result(e.value)
        raise ProtocolException("could not parse the cdp response:\n%s" % response)

    def __repr__(self) -> str:
        success = False if (self.done() and self.has_exception) else True
        if self.done():
            status = "finished"
        else:
            status = "pending"
        fmt = (
            f"<{self.__class__.__name__}\n\t"
            f"method: {self.method}\n\t"
            f"status: {status}\n\t"
            f"success: {success}>"
        )
        return fmt


class EventTransaction(Transaction[Any]):
    event = None
    value = None

    def __init__(self, event_object: Any):
        asyncio.Future.__init__(self)
        self.set_result(event_object)
        self.event = self.value = self.result()

    def __repr__(self) -> str:
        status = "finished"
        success = False if self.exception() else True
        event_object = self.result()
        fmt = (
            f"{self.__class__.__name__}\n\t"
            f"event: {event_object.__class__.__module__}.{event_object.__class__.__name__}\n\t"
            f"status: {status}\n\t"
            f"success: {success}>"
        )
        return fmt


class CantTouchThis(type):
    def __setattr__(cls, attr: str, value: Any) -> None:
        """
        :meta private:
        """
        if attr == "__annotations__":
            # fix autodoc
            return super().__setattr__(attr, value)
        raise SettingClassVarNotAllowedException(
            "\n".join(
                (
                    "don't set '%s' on the %s class directly, as those are shared with other objects.",
                    "use `my_object.%s = %s`  instead",
                )
            )
            % (attr, cls.__name__, attr, value)
        )


class Connection(metaclass=CantTouchThis):
    websocket: websockets.asyncio.client.ClientConnection | None = None
    _target: cdp.target.TargetInfo | None
    _download_behavior: List[str] | None = None

    def __init__(
        self,
        websocket_url: str,
        target: cdp.target.TargetInfo | None = None,
        _owner: Browser | None = None,
        **kwargs: Any,
    ):
        super().__init__()
        self._target = target
        self._message_ids = itertools.count(1)
        self._owner = _owner
        self.websocket_url: str = websocket_url
        self.websocket = None
        self.mapper: dict[int, Transaction[Any]] = {}
        self.handlers: dict[Any, list[Callable[..., Any]]] = collections.defaultdict(
            list
        )
        self.recv_task = None
        self.enabled_domains: list[Any] = []
        self.manually_enabled_domains: list[Any] = []
        self._last_result: list[Any] = []
        self.listener: Listener | None = None
        self.session_id: str | None = None
        self._session_parent: Connection | None = None
        self._sessions: dict[str, Connection] = {}
        self._inbox: asyncio.Queue[dict[str, Any]] | None = None
        self._attach_lock = asyncio.Lock()
        self.__dict__.update(**kwargs)

    @property
    def target(self) -> cdp.target.TargetInfo | None:
        return self._target

    @target.setter
    def target(self, target: cdp.target.TargetInfo) -> None:
        if not isinstance(target, cdp.target.TargetInfo):
            raise TypeError(
                "target must be set to a '%s' but got '%s"
                % (cdp.target.TargetInfo.__name__, type(target).__name__)
            )
        self._target = target

    @property
    def target_id(self) -> cdp.target.TargetID | None:
        """
        returns the target id of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.target_id
        return None

    @property
    def type_(self) -> str | None:
        """
        returns the type of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.type_
        return None

    @property
    def title(self) -> str | None:
        """
        returns the title of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.title
        return None

    @property
    def url(self) -> str | None:
        """
        returns the url of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.url
        return None

    @property
    def attached(self) -> bool | None:
        """
        returns True if the current target is attached, False otherwise.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.attached
        return None

    @property
    def can_access_opener(self) -> bool | None:
        """
        returns True if the current target can access its opener, False otherwise.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.can_access_opener
        return None

    @property
    def opener_id(self) -> cdp.target.TargetID | None:
        """
        returns the opener id of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.opener_id
        return None

    @property
    def opener_frame_id(self) -> cdp.page.FrameId | None:
        """
        returns the opener frame id of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.opener_frame_id
        return None

    @property
    def browser_context_id(self) -> cdp.browser.BrowserContextID | None:
        """
        returns the browser context id of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.browser_context_id
        return None

    @property
    def subtype(self) -> str | None:
        """
        returns the subtype of the current target.
        if no target is set, it will return None.
        """
        if self.target:
            return self.target.subtype
        return None

    @property
    def closed(self) -> bool:
        return self.websocket is None

    @property
    def _browser_connection(self) -> Connection | None:
        """
        the browser level connection which carries this target's flat session,
        or None if this connection owns its websocket
        """
        if self._owner is None or self.target is None:
            return None
        browser_connection = self._owner.connection
        if browser_connection is None or browser_connection is self:
            return None
        return browser_connection

    def add_handler(
        self,
        event_type_or_domain: Union[type, types.ModuleType],
        handler: Callable[..., Any],
    ) -> None:
        """
        add a handler for given event

        if event_type_or_domain is a module instead of a type, it will find all available events and add
        the handler.

        if you want to receive event updates (network traffic are also 'events') you can add handlers for those events.
        handlers can be regular callback functions or async coroutine functions (and also just lamba's).
        handlers are called with the event, and with the connection as a second argument if they accept one.
        for example, you want to check the network traffic:

        .. code-block::

            page.add_handler(cdp.network.RequestWillBeSent, lambda event: print('network event => %s' % event.request))

        the next time you make network traffic you will see your console print like crazy.

        :param event_type_or_domain:
        :param handler:

        :return:
        :rtype:
        """
        if isinstance(event_type_or_domain, types.ModuleType):
            for event_type in cdp.util.get_event_classes(event_type_or_domain):
                self.handlers[event_type].append(handler)

        else:
            self.handlers[event_type_or_domain].append(handler)

    def remove_handlers(
        self,
        event_type: Optional[type] = None,
        handler: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        remove handlers for given event

        if no event is provided, all handlers will be removed.
        if no handler is provided, all handlers for the event will be removed.

        .. code-block::

                # remove all handlers for all events
                page.remove_handlers()

                # remove all handlers for a specific event
                page.remove_handlers(cdp.network.RequestWillBeSent)

                # remove a specific handler for a specific event
                page.remove_handlers(cdp.network.RequestWillBeSent, handler)
        """

        if handler and not event_type:
            raise ValueError(
                "if handler is provided, event_type should be provided as well"
            )

        if not event_type:
            self.handlers.clear()
            return

        if not handler:
            self.handlers.pop(event_type, None)
            return

        if handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)

    async def aopen(self) -> None:
        """
        opens the websocket connection. should not be called manually by users
        :return:
        """
        browser_connection = self._browser_connection
        if browser_connection is not None:
            await self._attach_session(browser_connection)
        elif self.websocket is None:
            try:
                self.websocket = await websockets.connect(
                    self.websocket_url,
                    ping_timeout=PING_TIMEOUT,
                    max_size=MAX_SIZE,
                )
                self.listener = Listener(self)
            except (Exception,) as e:
                logger.debug("exception during opening of websocket : %s", e)
                if self.listener:
                    self.listener.cancel()
                raise
        if not self.listener or not self.listener.running:
            self.listener = Listener(self)
            logger.debug("\n✅  opened websocket connection to %s", self.websocket_url)

        # when a websocket connection is closed (either by error or on purpose)
        # and reconnected, the registered event listeners (if any), should be
        # registered again, so the browser sends those events
        await self._register_handlers()

    async def _attach_session(self, browser_connection: Connection) -> None:
        async with self._attach_lock:
            if self.session_id is not None:
                return
            if self.target_id is None:
                raise RuntimeError("cannot attach a session without a target")
            await browser_connection.aopen()
            session_id = await browser_connection.send(
                cdp.target.attach_to_target(self.target_id, flatten=True),
                _is_update=True,
            )
            self.session_id = session_id
            self._session_parent = browser_connection
            self._inbox = asyncio.Queue()
            browser_connection._sessions[session_id] = self
            self.websocket = browser_connection.websocket
            self.listener = Listener(self)
            logger.debug(
                "attached to target %s (session %s)", self.target_id, session_id
            )

    def _detach_session(self) -> None:
        """
        forgets the flat session locally. the browser side session is not touched.
        """
        if self._session_parent is not None and self.session_id is not None:
            self._session_parent._sessions.pop(self.session_id, None)
        self.session_id = None
        self._session_parent = None
        self._inbox = None
        self.websocket = None
        if self.listener:
            self.listener.cancel()
        self.enabled_domains.clear()
        self.manually_enabled_domains.clear()
        self.__dict__.pop("_prep_headless_done", None)
        self.__dict__.pop("_prep_expert_done", None)
        self._fail_pending_transactions(
            ProtocolException("target session was detached")
        )

    def _fail_pending_transactions(self, exception: BaseException) -> None:
        for tx in self.mapper.values():
            if not tx.done():
                tx.set_exception(exception)
        self.mapper.clear()

    async def aclose(self) -> None:
        """
        closes the websocket connection. should not be called manually by users.
        """
        if self._session_parent is not None:
            browser_connection = self._session_parent
            session_id = self.session_id
            self._detach_session()
            if session_id is not None and not browser_connection.closed:
                try:
                    await browser_connection.send(
                        cdp.target.detach_from_target(
                            session_id=cdp.target.SessionID(session_id)
                        ),
                        _is_update=True,
                    )
                except ProtocolException:
                    logger.debug("could not detach session %s", session_id)
            logger.debug("\n❌ detached from target %s", self.target_id)
            return
        if self.websocket is not None:
            for session in list(self._sessions.values()):
                session._detach_session()
            if self.listener and self.listener.running:
                self.listener.cancel()
                self.enabled_domains.clear()
                self.manually_enabled_domains.clear()
            await self.websocket.close()
            self.websocket = None
            self._fail_pending_transactions(ProtocolException("connection was closed"))
            logger.debug("\n❌ closed websocket connection to %s", self.websocket_url)

    async def sleep(self, t: Union[int, float] = 0.25) -> None:
        await self.update_target()
        await asyncio.sleep(t)

    def feed_cdp(self, cdp_obj: Generator[dict[str, Any], dict[str, Any], T]) -> None:
        """
        used in specific cases, mostly during cdp.fetch.RequestPaused events,
        in which the browser literally blocks. using feed_cdp you can issue
        a response without a blocking "await".

        note: this method won't cause a response.
        note: this is not an async method, just a regular method!

        :param cdp_obj:
        :return:
        :rtype:
        """
        asyncio.ensure_future(self.send(cdp_obj))

    async def wait(self, t: int | float | None = None) -> None:
        """
        waits until the event listener reports idle (no new events received in certain timespan).
        when `t` is provided, ensures waiting for `t` seconds, no matter what.

        :param t:
        :return:
        :rtype:
        """
        await self.update_target()
        if not self.listener:
            raise ValueError("No listener created yet")

        loop = asyncio.get_running_loop()
        start_time = loop.time()
        try:
            if isinstance(t, (int, float)):
                await asyncio.wait_for(self.listener.idle.wait(), timeout=t)
                while (loop.time() - start_time) < t:
                    await asyncio.sleep(0.1)
            else:
                await self.listener.idle.wait()
        except asyncio.TimeoutError:
            if isinstance(t, (int, float)):
                # explicit time is given, which is now passed
                # so bail out early
                return
        except AttributeError:
            # no listener created yet
            pass

    async def __aenter__(self) -> "Connection":
        """:meta private:"""
        return self

    async def __aexit__(
        self, exc_type: type[BaseException], exc_val: Any, exc_tb: Any
    ) -> None:
        """:meta private:"""
        await self.aclose()
        if exc_type and exc_val:
            raise exc_type(exc_val)

    def __await__(self) -> Any:
        """
        updates targets and wait for event listener to report idle.
        idle is reported when no new events are received for the duration of 1 second
        :return:
        :rtype:
        """
        return self.wait().__await__()

    async def update_target(self) -> None:
        target_info: cdp.target.TargetInfo = await self.send(
            cdp.target.get_target_info(self.target_id), _is_update=True
        )
        self.target = target_info

    async def send(
        self,
        cdp_obj: Generator[dict[str, Any], dict[str, Any], T],
        _is_update: bool = False,
    ) -> T:
        """
        send a protocol command. the commands are made using any of the cdp.<domain>.<method>()'s
        and is used to send custom cdp commands as well.

        :param cdp_obj: the generator object created by a cdp method

        :param _is_update: internal flag
            prevents infinite loop by skipping the registeration of handlers
            when multiple calls to connection.send() are made
        :return:
        """
        await self.aopen()
        if self.websocket is None:
            raise ProtocolException("connection was closed")
        if self._owner:
            browser = self._owner
            if browser.config:
                if browser.config.expert:
                    await self._prepare_expert()
                if browser.config.headless:
                    await self._prepare_headless()
        if not self.listener or not self.listener.running:
            self.listener = Listener(self)

        tx = Transaction(cdp_obj)
        tx.connection = self
        tx.id = self._next_message_id()
        self.mapper.update({tx.id: tx})

        if not _is_update:
            domain_name, _, action = tx.method.partition(".")
            if action == "enable":
                self._update_manual_domain(domain_name, action)
            await self._register_handlers()
            if action == "disable":
                self._update_manual_domain(domain_name, action)
        if self.websocket is None:
            raise ProtocolException("target session was detached")
        tx.session_id = self.session_id
        await self._send_transaction(tx)
        try:
            return await tx
        except ProtocolException as e:
            e.message = e.message or ""
            e.message += f"\ncommand:{tx.method}\nparams:{tx.params}"
            raise e

    #
    async def _register_handlers(self) -> None:
        """
        ensure that for current (event) handlers, the corresponding
        domain is enabled in the protocol.

        """
        # save a copy of current enabled domains in a variable
        # domains will be removed from this variable
        # if it is still needed according to the set handlers
        # so at the end this variable will hold the domains that
        # are not represented by handlers, and can be removed
        enabled_domains = self.enabled_domains.copy()
        for event_type in self.handlers.copy():
            if len(self.handlers[event_type]) == 0:
                self.handlers.pop(event_type)
                continue
            if not isinstance(event_type, type):
                continue
            domain_mod = util.cdp_get_module(event_type.__module__)
            if domain_mod in self.enabled_domains:
                # at this point, the domain is being used by a handler
                # so remove that domain from temp variable 'enabled_domains' if present
                if domain_mod in enabled_domains:
                    enabled_domains.remove(domain_mod)
                continue
            elif (
                domain_mod not in self.enabled_domains
                and domain_mod not in self.manually_enabled_domains
            ):
                if domain_mod in (cdp.target, cdp.storage):
                    # by default enabled
                    continue
                try:
                    # we add this before sending the request, because it will
                    # loop indefinite
                    logger.debug("registered %s", domain_mod)
                    self.enabled_domains.append(domain_mod)

                    await self.send(domain_mod.enable(), _is_update=True)

                except:  # noqa - as broad as possible, we don't want an error before the "actual" request is sent
                    logger.debug("", exc_info=True)
                    try:
                        self.enabled_domains.remove(domain_mod)
                    except:  # noqa
                        logger.debug("NOT GOOD", exc_info=True)
                        continue
        for ed in enabled_domains:
            # we started with a copy of self.enabled_domains and removed a domain from this
            # temp variable when we registered it or saw handlers for it.
            # items still present at this point are unused and need removal
            self.enabled_domains.remove(ed)

    def _update_manual_domain(
        self, domain_name: str, action: Literal["enable", "disable"]
    ) -> None:
        """
        Updates the enabled domain lists for the given domain name

        :param domain_name:
        :param action:
        :return:
        :rtype:
        """
        if action not in ("enable", "disable"):
            return
        try:
            domain_mod = util.cdp_get_module(domain_name.lower())
        except ModuleNotFoundError:
            logger.debug(
                "Could not find module for domain %s",
                domain_name,
            )
            return

        # manual enables/disables always overwrite auto enabled domains
        if domain_mod in self.enabled_domains:
            self.enabled_domains.remove(domain_mod)
        if action == "disable" and domain_mod in self.manually_enabled_domains:
            self.manually_enabled_domains.remove(domain_mod)
        elif action == "enable" and domain_mod not in self.manually_enabled_domains:
            self.manually_enabled_domains.append(domain_mod)

    async def _prepare_headless(self) -> None:
        if getattr(self, "_prep_headless_done", None):
            return
        response = await self._send_oneshot(
            cdp.runtime.evaluate(
                expression="navigator.userAgent",
                user_gesture=True,
                await_promise=True,
                return_by_value=True,
                allow_unsafe_eval_blocked_by_csp=True,
            )
        )
        if response and response[0].value:
            ua = response[0].value
            await self._send_oneshot(
                cdp.network.set_user_agent_override(
                    user_agent=ua.replace("Headless", ""),
                )
            )
        setattr(self, "_prep_headless_done", True)

    async def _prepare_expert(self) -> None:
        if getattr(self, "_prep_expert_done", None):
            return
        if self._owner:
            await self._send_oneshot(
                cdp.page.add_script_to_evaluate_on_new_document(
                    """
                    Element.prototype._attachShadow = Element.prototype.attachShadow;
                    Element.prototype.attachShadow = function () {
                        return this._attachShadow( { mode: "open" } );
                    };
                """
                )
            )

            await self._send_oneshot(cdp.page.enable())
        setattr(self, "_prep_expert_done", True)

    def _next_message_id(self) -> int:
        """
        message ids are shared by all sessions on a websocket, so that a response
        chrome sends without a session id can never be matched to the wrong command
        """
        if self._session_parent is not None:
            return self._session_parent._next_message_id()
        return next(self._message_ids)

    async def _send_transaction(self, tx: Transaction[Any]) -> None:
        if self.websocket is None:
            raise ProtocolException("connection was closed")
        try:
            await self.websocket.send(tx.message)
        except BaseException:
            if tx.id is not None:
                self.mapper.pop(tx.id, None)
            raise

    async def _receive_message(self) -> dict[str, Any] | None:
        """
        returns the next message addressed to this connection, or None when
        the received message was routed to one of the flat sessions instead
        """
        if self._inbox is not None:
            return await self._inbox.get()
        if self.websocket is None:
            raise ValueError("no websocket connection")

        message: dict[str, Any] = json.loads(await self.websocket.recv())
        session_id = message.get("sessionId")
        if session_id is not None:
            session = self._sessions.get(session_id)
            if session is not None and session._inbox is not None:
                session._inbox.put_nowait(message)
            return None

        if message.get("method") == "Target.detachedFromTarget":
            session = self._sessions.get(message["params"]["sessionId"])
            if session is not None:
                session._detach_session()
        return message

    async def _send_oneshot(self, cdp_obj: Any) -> Any:
        if self.websocket is None:
            raise ValueError("no websocket connection")

        tx = Transaction(cdp_obj)
        tx.connection = self
        tx.id = self._next_message_id()
        tx.session_id = self.session_id
        self.mapper.update({tx.id: tx})
        await self._send_transaction(tx)
        try:
            # in try except since if browser connection sends this it reises an exception
            return await tx
        except ProtocolException:
            pass


def _accepts_connection_argument(handler: Callable[..., Any]) -> bool:
    try:
        inspect.signature(handler).bind(None, None)
    except (TypeError, ValueError):
        return False
    return True


class Listener:
    def __init__(self, connection: Connection):
        self.connection = connection
        self.history: collections.deque[Any] = collections.deque()
        self.max_history = 1000
        self.task: asyncio.Future[None] | None = None

        # when in interactive mode, the loop is paused after each return
        # and when the next call is made, it might still have to process some events
        # from the previous call as well.

        # while in "production" the loop keeps running constantly
        # (and so events are continuous processed)

        # therefore we should give it some breathing room in interactive mode
        # and we can tighten that room when in production.

        # /example/demo.py runs ~ 5 seconds faster, which is quite a lot.

        is_interactive = getattr(sys, "ps1", sys.flags.interactive)
        self._time_before_considered_idle = 0.10 if not is_interactive else 0.75
        self.idle = asyncio.Event()
        self.run()

    def run(self) -> None:
        self.task = asyncio.create_task(self.listener_loop())

    @property
    def time_before_considered_idle(self) -> float:
        return self._time_before_considered_idle

    @time_before_considered_idle.setter
    def time_before_considered_idle(self, seconds: Union[int, float]) -> None:
        self._time_before_considered_idle = seconds

    def cancel(self) -> None:
        if self.task and not self.task.cancelled():
            self.task.cancel()

    @property
    def running(self) -> bool:
        if not self.task:
            return False
        if self.task.done():
            return False
        return True

    async def listener_loop(self) -> None:
        while True:
            try:
                message = await asyncio.wait_for(
                    self.connection._receive_message(),
                    self.time_before_considered_idle,
                )
            except asyncio.TimeoutError:
                self.idle.set()
                # breathe
                # await asyncio.sleep(self.time_before_considered_idle / 10)
                continue
            except asyncio.CancelledError:
                logger.debug(
                    "task was cancelled while reading websocket, breaking loop"
                )
                break
            except websockets.exceptions.ConnectionClosed as e:
                # break on connection closed
                logger.debug(
                    "connection listener exception while reading websocket:\n%s", e
                )
                for session in list(self.connection._sessions.values()):
                    session._detach_session()
                self.connection._fail_pending_transactions(e)
                break

            if not self.running:
                # if we have been cancelled or otherwise stopped running
                # break this loop
                break

            if message is None:
                continue

            # since we are at this point, we are not "idle" anymore.
            self.idle.clear()

            if "id" in message:
                # response to our command
                if message["id"] in self.connection.mapper:
                    # get the corresponding Transaction

                    # thanks to zxsleebu for discovering the memory leak
                    # pop to prevent memory leaks
                    tx = self.connection.mapper.pop(message["id"])
                    logger.debug("got answer for %s (message_id:%d)", tx, message["id"])

                    # complete the transaction, which is a Future object
                    # and thus will return to anyone awaiting it.
                    if not tx.done():
                        tx(**message)
            else:
                # probably an event
                try:
                    event = cdp.util.parse_json_event(message)
                except Exception as e:
                    logger.info(
                        "%s: %s  during parsing of json from event : %s"
                        % (type(e).__name__, e.args, message),
                        exc_info=True,
                    )
                    continue
                try:
                    if type(event) in self.connection.handlers:
                        callbacks = self.connection.handlers[type(event)]
                    else:
                        continue
                    if not len(callbacks):
                        continue
                    for callback in callbacks:
                        try:
                            args = (
                                (event, self.connection)
                                if _accepts_connection_argument(callback)
                                else (event,)
                            )
                            if inspect.iscoroutinefunction(callback):
                                asyncio.create_task(callback(*args))
                            else:
                                asyncio.create_task(asyncio.to_thread(callback, *args))
                        except Exception as e:
                            logger.warning(
                                "exception in callback %s for event %s => %s",
                                callback,
                                event.__class__.__name__,
                                e,
                                exc_info=True,
                            )
                            raise
                except asyncio.CancelledError:
                    break
                except Exception:
                    raise
                continue

    def __repr__(self) -> str:
        s_idle = "[idle]" if self.idle.is_set() else "[busy]"
        s_cache_length = f"[cache size: {len(self.history)}]"
        s_running = f"[running: {self.running}]"
        s = f"{self.__class__.__name__} {s_running} {s_idle} {s_cache_length}>"
        return s
