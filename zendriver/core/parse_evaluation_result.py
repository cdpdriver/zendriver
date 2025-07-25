import base64
import datetime
import re
import urllib.parse

from typing import Any, Union

SerializedValue = Union[
    None, bool, int, float, str, dict  # the serialized object variants
]

typed_array_constructors = {
    "i8": "b",  # Int8Array
    "ui8": "B",  # Uint8Array
    "ui8c": "B",  # Uint8ClampedArray (same as Uint8Array)
    "i16": "h",
    "ui16": "H",
    "i32": "i",
    "ui32": "I",
    "f32": "f",
    "f64": "d",
    "bi64": "q",
    "bui64": "Q",
}


def base64_to_bytes(base64_str: str) -> bytes:
    return base64.b64decode(base64_str)


def base64_to_typed_array(base64_str: str, kind: str):
    from array import array

    type_code = typed_array_constructors.get(kind)
    if not type_code:
        raise ValueError(f"Unsupported typed array kind: {kind}")
    data = base64_to_bytes(base64_str)
    arr = array(type_code)
    arr.frombytes(data)
    return arr


def parse_evaluation_result_value(
    value: SerializedValue, handles=None, refs=None
) -> Any:
    if refs is None:
        refs = {}
    if handles is None:
        handles = []

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, dict):
        if "ref" in value:
            return refs.get(value["ref"])

        if "v" in value:
            return _parse_special_value(value["v"])

        if "d" in value:
            return _parse_datetime(value["d"])

        if "u" in value:
            return _parse_url(value["u"])

        if "bi" in value:
            return int(value["bi"])

        if "e" in value:
            return _parse_exception(value["e"])

        if "r" in value:
            return _parse_regex(value["r"])

        if "a" in value:
            return _parse_array(value, handles, refs)

        if "o" in value:
            return _parse_object(value, handles, refs)

        if "h" in value:
            return handles[value["h"]]

        if "ta" in value:
            return base64_to_typed_array(value["ta"]["b"], value["ta"]["k"])

    return value


def _parse_special_value(v: str):
    special_values = {
        "undefined": None,
        "null": None,
        "NaN": float("nan"),
        "Infinity": float("inf"),
        "-Infinity": float("-inf"),
        "-0": -0.0,
    }
    return special_values.get(v)


def _parse_datetime(date_str: str):
    return datetime.datetime.fromisoformat(date_str)


def _parse_url(url_str: str):
    return urllib.parse.urlparse(url_str)


def _parse_exception(e: dict):
    exc = Exception(e["m"])
    exc.name = e.get("n", "")  # type: ignore
    exc.stack = e.get("s", "")  # type: ignore
    return exc


def _parse_regex(r: dict):
    return re.compile(r["p"], flags=_regex_flags(r["f"]))


def _parse_array(value: dict, handles, refs):
    arr: list = []
    refs[value["id"]] = arr
    for item in value["a"]:
        arr.append(parse_evaluation_result_value(item, handles, refs))
    return arr


def _parse_object(value: dict, handles, refs):
    obj: dict = {}
    refs[value["id"]] = obj
    for pair in value["o"]:
        key = pair["k"]
        if key == "__proto__":
            continue
        obj[key] = parse_evaluation_result_value(pair["v"], handles, refs)
    return obj


def _regex_flags(flags_str: str) -> int:
    flags = 0
    for ch in flags_str:
        if ch == "i":
            flags |= re.IGNORECASE
        elif ch == "m":
            flags |= re.MULTILINE
        elif ch == "s":
            flags |= re.DOTALL
        # Add more mappings if needed
    return flags
