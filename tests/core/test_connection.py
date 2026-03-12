import asyncio
from types import SimpleNamespace
from typing import Any, Generator

import pytest

from zendriver.core.connection import (
    Connection,
    Listener,
    ProtocolException,
    Transaction,
)


def _single_step_command() -> Generator[dict[str, Any], dict[str, Any], Any]:
    result = yield {"method": "Runtime.evaluate", "params": {"expression": "42"}}
    return result


def _parse_mismatch_command() -> Generator[dict[str, Any], dict[str, Any], Any]:
    _ = yield {"method": "Runtime.evaluate", "params": {"expression": "1"}}
    yield {"method": "Runtime.evaluate", "params": {"expression": "2"}}


class _DummyWebsocket:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)


@pytest.mark.asyncio
async def test_transaction_late_response_after_cancel_does_not_raise() -> None:
    tx = Transaction(_single_step_command())
    tx.cancel()

    tx(result={"value": "<!doctype html>"}, id=1)

    assert tx.cancelled()


@pytest.mark.asyncio
async def test_transaction_parse_mismatch_sets_exception_not_raise() -> None:
    tx = Transaction(_parse_mismatch_command())

    tx(result={"value": "ok"}, id=2)

    assert tx.done()
    assert isinstance(tx.exception(), ProtocolException)


@pytest.mark.asyncio
async def test_send_cancellation_removes_tx_from_mapper() -> None:
    connection = Connection("ws://unused")
    connection.websocket = _DummyWebsocket()  # type: ignore[assignment]
    connection.listener = SimpleNamespace(running=True)  # type: ignore[assignment]

    async def no_op() -> None:
        return None

    connection.aopen = no_op  # type: ignore[assignment]
    connection._register_handlers = no_op  # type: ignore[assignment]

    send_task = asyncio.create_task(connection.send(_single_step_command()))
    await asyncio.sleep(0)

    tx_id = next(iter(connection.mapper))
    send_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await send_task

    assert tx_id not in connection.mapper


def test_listener_complete_transaction_handles_exceptions() -> None:
    class ExplodingTransaction:
        def __init__(self) -> None:
            self.captured_exception: Exception | None = None

        def __call__(self, **_: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        def done(self) -> bool:
            return False

        def _set_exception_safely(self, exception: Exception) -> None:
            self.captured_exception = exception

    listener = object.__new__(Listener)
    tx = ExplodingTransaction()

    listener._complete_transaction(tx, {"id": 1, "result": {}}, 1)  # type: ignore[arg-type]

    assert isinstance(tx.captured_exception, RuntimeError)
