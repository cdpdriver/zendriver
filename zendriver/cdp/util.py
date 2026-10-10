import types
import typing

T_JSON_DICT = typing.Dict[str, typing.Any]
_event_parsers = dict()


def event_class(method):
    """A decorator that registers a class as an event class."""

    def decorate(cls):
        _event_parsers[method] = cls
        return cls

    return decorate


def parse_json_event(json: T_JSON_DICT) -> typing.Any:
    """Parse a JSON dictionary into a CDP event."""
    return _event_parsers[json["method"]].from_json(json["params"])


def get_event_classes(module: types.ModuleType) -> typing.List[type]:
    """Return the event classes defined in a CDP domain module."""
    return [cls for cls in _event_parsers.values() if cls.__module__ == module.__name__]
