import logging
import warnings as _warnings
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence


__logger__ = logging.getLogger(__name__)


__all__ = [
    'ContraDict',
    'cdict',
]

from typing import Any


class ContraDict(dict[str, Any]):  # noqa: FURB189
    """
    directly inherited from dict

    accessible by attribute. o.x == o['x']
    This works also for all corner cases.

    native json.dumps and json.loads work with it

    names like "keys", "update", "values" etc won't overwrite the methods,
    but will just be available using dict lookup notation obj['items'] instead of obj.items

    all key names are converted to snake_case
    hyphen's (-), dot's (.) or whitespaces are replaced by underscore (_)

    autocomplete works even if the objects comes from a list

    recursive action. dict assignments will be converted too.
    """

    def __init__(self, *args: Any, silent: bool = False, **kwargs: Any) -> None:
        super().__init__()
        _ = dict(*args, **kwargs)

        # for key, val in dict(*args, **kwargs).items():
        #     _[key] = val
        super().__setattr__('__dict__', self)
        for k, v in _.items():
            _check_key(k, self, boolean=False, silent=silent)
            super().__setitem__(k, _wrap(self.__class__, v))

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, _wrap(self.__class__, value))

    def __setattr__(self, key: str, value: Any) -> None:
        super().__setitem__(key, _wrap(self.__class__, value))

    def __getattribute__(self, attribute: str) -> Any:
        if attribute in self:
            return self[attribute]
        if not _check_key(attribute, self, boolean=True, silent=True):
            return getattr(super(), attribute)

        return object.__getattribute__(self, attribute)


def _wrap(cls: Any, v: Any) -> Any:
    if isinstance(v, _Mapping):
        v = cls(v)
    elif isinstance(v, _Sequence) and not isinstance(
        v,
        (str, bytes, bytearray, set, tuple),
    ):
        v = [_wrap(cls, x) for x in v]

    return v


_warning_names = (
    'items',
    'keys',
    'values',
    'update',
    'clear',
    'copy',
    'fromkeys',
    'get',
    'items',
    'keys',
    'pop',
    'popitem',
    'setdefault',
    'update',
    'values',
    'class',
)

_warning_names_message = """\n\
    While creating a ContraDict object, a key offending key name '{0}' has been found, which might behave unexpected.
    you will only be able to look it up using key, eg. myobject['{0}']. myobject.{0} will not work with that name.
    """


def cdict(*args: Any, **kwargs: Any) -> ContraDict:
    """
    factory function
    """
    return ContraDict(*args, **kwargs)


def _check_key(
    key: str,
    mapping: _Mapping[str, Any],
    *,
    boolean: bool = False,
    silent: bool = False,
) -> str | bool:
    """checks `key` and warns if needed

    :param key:
    :param boolean: return True or False instead of passthrough
    :return:
    """
    e = None
    if not isinstance(key, (str,)):
        if boolean:
            return True
        return key
    if key.lower() in _warning_names or any(_ in key for _ in ('-', '.')):
        if not silent:
            _warnings.warn(_warning_names_message.format(key), stacklevel=1)
        e = True
    if not boolean:
        return key
    return not e
