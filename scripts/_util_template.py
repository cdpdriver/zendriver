import types
from collections.abc import Callable
from typing import Any, Protocol, Self, TypeIs, runtime_checkable


type T_JSON_DICT = dict[str, Any]


@runtime_checkable
class EventType(Protocol):
    @classmethod
    def from_json(cls, json: T_JSON_DICT) -> Self: ...

    @classmethod
    def from_json_optional(cls, json: T_JSON_DICT | None) -> Self | None: ...


_event_types_map: dict[str, type[EventType]] = {}
_event_types: set[type[EventType]] = set()


def event_type[T: type[EventType]](method: str) -> Callable[[T], T]:
    """A decorator that registers a class as an event data parsing class."""

    def decorate(cls: T) -> T:
        _event_types_map[method] = cls
        _event_types.add(cls)
        return cls

    return decorate


def get_event_types() -> dict[str, type[EventType]]:
    return _event_types_map


def is_event_type(type_: type) -> TypeIs[type[EventType]]:
    return (
        type(type_) is type
        and hasattr(type_, '__hash__')
        and hasattr(type_, '__eq__')
        and type_ in _event_types  # keep
    )


def get_event_types_in_domain(domain: types.ModuleType) -> list[type[EventType]]:
    import inspect

    return [et for _, et in inspect.getmembers_static(domain) if is_event_type(et)]


__all__ = [
    'T_JSON_DICT',
    'EventType',
    'event_type',
    'get_event_types',
    'get_event_types_in_domain',
    'is_event_type',
]
