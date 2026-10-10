from enum import Enum, IntEnum
from typing import List, Optional, Tuple, TypedDict, Union

import emoji
import grapheme


class KeyModifiers(IntEnum):
    """Enumeration of keyboard modifiers used in key events.
    For multiple modifiers, use bitwise OR to combine them.

       Example:
        >>> modifiers = KeyModifiers.Alt | KeyModifiers.Shift # Combines Alt and Shift modifiers
    """

    Default = 0
    Alt = 1
    Ctrl = 2
    Meta = 4
    Shift = 8


class SpecialKeys(Enum):
    """Enumeration of special keys with their corresponding names and key codes."""

    SPACE = (" ", 32)  # space key
    ENTER = ("Enter", 13)
    TAB = ("Tab", 9)

    BACKSPACE = ("Backspace", 8)
    ESCAPE = ("Escape", 27)
    DELETE = ("Delete", 46)
    ARROW_LEFT = ("ArrowLeft", 37)
    ARROW_UP = ("ArrowUp", 38)
    ARROW_RIGHT = ("ArrowRight", 39)
    ARROW_DOWN = ("ArrowDown", 40)
    SHIFT = ("Shift", 16)  # internal use only
    ALT = ("Alt", 18)  # internal use only
    CTRL = ("Control", 17)  # internal use only
    META = ("Meta", 91)  # internal use only


class KeyPressEvent(str, Enum):
    """Enumeration of different types of key press events."""

    KEY_DOWN = "keyDown"
    KEY_UP = "keyUp"
    RAW_KEY_DOWN = "rawKeyDown"

    CHAR = "char"
    """Directly sends ASCII character to the element. Cannot send non-ASCII characters and commands (Ctrl+A, etc.)"""
    DOWN_AND_UP = "downAndUp"
    """Way to give both key down and up events in one go for non-ASCII characters, **not standard implementation**"""


class KeyEvents:
    """
    Key events handling class for processing keyboard input and converting to CDP format.

    This class manages keyboard events and converts them into appropriate CDP commands.
    It handles ASCII characters, special keys, and modifier combinations.

    Reference: https://stackoverflow.com/a/79194672
    """

    @staticmethod
    def is_english_alphabet(char: str) -> bool:
        """
        Check if a character is an English alphabet letter (A-Z, a-z).

        Args:
            char: The character to check.

        Returns:
            True if the character is an English alphabet letter, False otherwise.
        """
        if char.isalpha() and char.isascii():
            if len(char) != 1:
                raise ValueError(
                    "Key must be a single ASCII character. If you want to send multiple characters, try using `KeyEvents.from_text` or `KeyEvents.from_mixed_input`."
                )

            return True
        return False

    # Class constants for character mappings
    NUM_SHIFT = ")!@#$%^&*("

    SPECIAL_CHAR_MAP = {
        ";": ("Semicolon", 186),
        "=": ("Equal", 187),
        ",": ("Comma", 188),
        "-": ("Minus", 189),
        ".": ("Period", 190),
        "/": ("Slash", 191),
        "`": ("Backquote", 192),
        "[": ("BracketLeft", 219),
        "\\": ("Backslash", 220),
        "]": ("BracketRight", 221),
        "'": ("Quote", 222),
    }

    SPECIAL_CHAR_SHIFT_MAP = {
        ":": ";",
        "+": "=",
        "<": ",",
        "_": "-",
        ">": ".",
        "?": "/",
        "~": "`",
        "{": "[",
        "|": "\\",
        "}": "]",
        '"': "'",
    }
    SPECIAL_CHAR_REVERSE_MAP = {v: k for k, v in SPECIAL_CHAR_SHIFT_MAP.items()}

    MODIFIER_KEYS = [
        SpecialKeys.SHIFT,
        SpecialKeys.ALT,
        SpecialKeys.CTRL,
        SpecialKeys.META,
    ]

    SPECIAL_KEY_CHAR_MAP = {
        SpecialKeys.SPACE: " ",
        SpecialKeys.ENTER: "\r",
        SpecialKeys.TAB: "\t",
    }

    class Payload(TypedDict):
        type_: str
        modifiers: int
        text: Optional[str]
        key: Optional[str]
        code: Optional[str]
        windows_virtual_key_code: Optional[int]
        native_virtual_key_code: Optional[int]

    def __init__(
        self,
        key: Union[str, SpecialKeys],
        modifiers: Union[KeyModifiers, int] = KeyModifiers.Default,
    ):
        """
        Initialize a KeyEvents instance.

        Args:
            key: The key to be processed (single character string or SpecialKeys enum)
            modifiers: Modifier keys to be applied (can be combined with bitwise OR)
        """

        # modifiers = modifiers
        self.key = key
        self.modifiers = modifiers

        self.code, self.keyCode = (
            self._handle_string_key_lookup(self.key)
            if isinstance(self.key, str)
            else self._handle_special_key_lookup(self.key)
        )

    def conv_to_str(self, specialKey_key: SpecialKeys) -> str:
        if specialKey_key == SpecialKeys.SPACE:
            return " "
        elif specialKey_key == SpecialKeys.ENTER:
            return "\n"
        elif specialKey_key == SpecialKeys.TAB:
            return "\t"
        raise ValueError(
            f"Cannot convert {specialKey_key} to string, only SPACE, ENTER and TAB are supported."
        )

    def _get_key_and_text(
        self, key_press_event: KeyPressEvent, modifiers: Union[KeyModifiers, int]
    ) -> Tuple[str, Optional[str]]:
        """
        Create the appropriate action for this key event.

        Args:
            key_press_event: The type of key press event to generate (Currently supported are `DOWN_AND_UP` and `CHAR`)
            modifiers: Modifier keys to apply

        Returns:
            Action object containing the processed key information

        Raises:
            ValueError: If key is invalid for CHAR event type
        """
        if key_press_event == KeyPressEvent.CHAR:
            if isinstance(self.key, SpecialKeys):
                self.key = self.conv_to_str(self.key)
            return self.key, self.key

        return self._build_action_data(modifiers)

    def _normalise_key(
        self, key: Union[str, SpecialKeys], modifiers: Union[KeyModifiers, int]
    ) -> Tuple[Union[str, SpecialKeys], Union[KeyModifiers, int]]:
        """
        Convert a shifted key to its non-shifted equivalent.

        Args:
            key: The key to convert (may be shifted)
            modifiers: Current modifier keys to apply

        Returns:
            The non-shifted equivalent of the key

        Raises:
            ValueError: If the key is not recognized or supported
        """
        lowercase_key: Optional[str] = None
        if isinstance(key, SpecialKeys):
            return key, modifiers  # all the special keys dont have shifted variants

        if key in self.NUM_SHIFT:
            modifiers |= KeyModifiers.Shift
            lowercase_key = str(self.NUM_SHIFT.index(key))
        elif key in self.SPECIAL_CHAR_SHIFT_MAP:
            modifiers |= KeyModifiers.Shift
            lowercase_key = self.SPECIAL_CHAR_SHIFT_MAP[key]
        elif KeyEvents.is_english_alphabet(key) and key.isupper():
            modifiers |= KeyModifiers.Shift
            lowercase_key = key.lower()
        elif key in "\n\r":
            return SpecialKeys.ENTER, modifiers
        elif key == "\t":
            return SpecialKeys.TAB, modifiers
        elif key == " ":
            return SpecialKeys.SPACE, modifiers

        if (
            modifiers != KeyModifiers.Default | KeyModifiers.Shift
            and lowercase_key is not None
        ):
            raise ValueError(
                f"Key '{key}' is not supported with modifiers {modifiers}."
            )

        if lowercase_key is None:
            return key, modifiers

        modifiers |= KeyModifiers.Shift
        return lowercase_key, modifiers

    def _to_basic_event(
        self,
        key_press_event: KeyPressEvent,
        modifiers: Union[KeyModifiers, int] = KeyModifiers.Default,
    ) -> "KeyEvents.Payload":
        """
        Convert the key event to a basic event format.
        Args:
            key_press_event: The type of key press event to generate
            modifiers: Modifier keys to apply
        Returns:
            A dictionary containing the basic event payload
        """

        key, text = self._get_key_and_text(key_press_event, modifiers)
        if key_press_event == KeyPressEvent.CHAR:
            if text is None:
                raise ValueError(
                    f"Key '{self.key}' is not supported for CHAR event type. Only single ASCII characters are allowed."
                )
            return self.Payload(
                type_=key_press_event.value,
                modifiers=modifiers,
                text=text,
                key=None,
                code=None,
                windows_virtual_key_code=None,
                native_virtual_key_code=None,
            )

        return self.Payload(
            type_=key_press_event.value,
            modifiers=modifiers,
            text=text,
            key=key,
            code=self.code,
            windows_virtual_key_code=self.keyCode,
            native_virtual_key_code=self.keyCode,
        )

    def to_cdp_events(
        self,
        key_press_event: KeyPressEvent,
        override_modifiers: Optional[Union[KeyModifiers, int]] = None,
    ) -> List["KeyEvents.Payload"]:
        """
        Convert the key event to CDP format.

        Args:
            key_press_event: The type of key press event to generate (Currently supported are `DOWN_AND_UP` and `CHAR`)
            override_modifiers: Optional modifiers to override the current ones

        Returns:
            List of dictionaries containing CDP `payload`
        """
        if isinstance(self.key, str):
            if emoji.is_emoji(self.key) or (
                self.key is not None and self.keyCode is None
            ):
                key_press_event = KeyPressEvent.CHAR

        match key_press_event:
            case (
                KeyPressEvent.KEY_DOWN
                | KeyPressEvent.RAW_KEY_DOWN
                | KeyPressEvent.KEY_UP
            ):
                raise NotImplementedError(
                    "Not supported by itself, use CHAR or DOWN_AND_UP instead."
                )

            case KeyPressEvent.CHAR:
                if (
                    not isinstance(self.key, str)
                    and self.key not in self.SPECIAL_KEY_CHAR_MAP.keys()
                ):
                    raise ValueError(
                        f"Key '{self.key}' is not supported for CHAR event type. Only str characters are allowed"
                    )
                return [self._to_basic_event(key_press_event)]

            case KeyPressEvent.DOWN_AND_UP:
                cur_modifier = (
                    self.modifiers if override_modifiers is None else override_modifiers
                )
                self.key, override_modifiers = self._normalise_key(
                    self.key, cur_modifier
                )
                return self.to_down_up_sequence(override_modifiers)

            case _:
                raise ValueError(f"Unsupported key press event type: {key_press_event}")

    def _handle_string_key_lookup(
        self, key: str
    ) -> Tuple[Optional[str], Optional[int]]:
        """Handle string key lookup logic."""

        if KeyEvents.is_english_alphabet(key):
            return f"Key{key.upper()}", ord(key.upper())
        elif key.isdigit() or key in KeyEvents.NUM_SHIFT:
            digit = (
                str(KeyEvents.NUM_SHIFT.index(key))
                if key in KeyEvents.NUM_SHIFT
                else key
            )
            return f"Digit{digit}", ord(digit)
        elif key in "\n\r":
            return SpecialKeys.ENTER.value
        elif key == "\t":
            return SpecialKeys.TAB.value
        elif key == " ":
            return SpecialKeys.SPACE.value
        elif key in KeyEvents.SPECIAL_CHAR_MAP:
            return KeyEvents.SPECIAL_CHAR_MAP[key]
        elif key in KeyEvents.SPECIAL_CHAR_SHIFT_MAP.keys():
            return KeyEvents.SPECIAL_CHAR_MAP[KeyEvents.SPECIAL_CHAR_SHIFT_MAP[key]]

        return None, None  # non english characters

    def _handle_special_key_lookup(self, key: SpecialKeys) -> Tuple[str, int]:
        """Handle special key lookup logic."""
        if key in KeyEvents.MODIFIER_KEYS:
            return f"{key.value[0]}Left", key.value[1]
        return key.value

    def _decompose_modifiers(
        self, modifiers: Union[KeyModifiers, int]
    ) -> List[Tuple[SpecialKeys, KeyModifiers]]:
        """
        Extract individual modifier keys from a modifier bitmask.

        Args:
            modifiers: The modifier bitmask to process

        Returns:
            List of tuples containing (SpecialKey, KeyModifier) pairs
        """
        if modifiers == KeyModifiers.Default:
            return []

        modifier_keys = []
        if modifiers & KeyModifiers.Alt:
            modifier_keys.append((SpecialKeys.ALT, KeyModifiers.Alt))
        if modifiers & KeyModifiers.Ctrl:
            modifier_keys.append((SpecialKeys.CTRL, KeyModifiers.Ctrl))
        if modifiers & KeyModifiers.Meta:
            modifier_keys.append((SpecialKeys.META, KeyModifiers.Meta))
        if modifiers & KeyModifiers.Shift:
            modifier_keys.append((SpecialKeys.SHIFT, KeyModifiers.Shift))

        if not modifier_keys:
            raise ValueError("No valid modifier keys found.")

        return modifier_keys

    def _build_action_data(
        self, modifiers: Union[KeyModifiers, int]
    ) -> Tuple[str, Optional[str]]:
        """
        Build the data needed for a key press action.

        Args:
            key: The key to process
            modifiers: Modifier keys to apply

        Returns:
            Tuple containing (text, key, code, windowsVirtualKeyCode, nativeVirtualKeyCode)
        """

        # Handle printable characters with potential shift modifier
        if isinstance(self.key, str):
            return self._handle_printable_char(self.key, modifiers)

        # Handle modifier keys
        if self.key in KeyEvents.SPECIAL_KEY_CHAR_MAP:
            # Special keys that are not modifiers
            return (
                self.SPECIAL_KEY_CHAR_MAP[self.key],
                self.SPECIAL_KEY_CHAR_MAP[self.key],
            )

        # Handle other special keys
        return self.key.value[0], None

    def _handle_printable_char(
        self, key: str, modifiers: Union[KeyModifiers, int]
    ) -> Tuple[str, str]:
        """Handle printable character with potential shift modifier."""
        if modifiers != KeyModifiers.Shift:
            return key, key

        # Apply shift transformation
        if KeyEvents.is_english_alphabet(key):
            shifted_key = key.upper()
        elif key.isdigit():
            shifted_key = KeyEvents.NUM_SHIFT[int(key)]
        else:
            shifted_key = self.SPECIAL_CHAR_REVERSE_MAP[key]

        return shifted_key, shifted_key

    def to_down_up_sequence(
        self, modifiers: Union[KeyModifiers, int]
    ) -> List["KeyEvents.Payload"]:
        """
        Create a complete key down/up sequence with modifiers.

        This method generates a sequence of key events that properly handles
        modifier keys by sending modifier key down events before the main key,
        and modifier key up events after the main key.

        Args:
            modifiers: Modifier keys to apply

        Returns:
            List of `KeyEvents.Payload` containing the complete key event sequence
        """
        # Validate that all required properties are set
        events: List[KeyEvents.Payload] = []
        modifier_events = [
            (KeyEvents(key), _modifier)
            for key, _modifier in self._decompose_modifiers(modifiers)
        ]
        is_modifier_key = any(key.key == self.key for key, _ in modifier_events)

        # 1: Add modifier key down events
        current_modifiers = 0
        for modifier_key, modifier_flag in modifier_events:
            current_modifiers |= modifier_flag  # done like this since all the keys are not pressed or processed at once
            modifier_payload = modifier_key._to_basic_event(
                KeyPressEvent.KEY_DOWN, current_modifiers
            )
            events.append(modifier_payload)

        # 2: Add main key down (if itself is not a modifier key)
        if not is_modifier_key:
            events.append(
                self._to_basic_event(KeyPressEvent.KEY_DOWN, current_modifiers)
            )

        # 3: Add modifier key up events (in reverse order)
        for modifier_key, modifier_flag in modifier_events:
            current_modifiers &= ~modifier_flag
            # remove the modifier from current modifiers (the same idea)
            modifier_payload = modifier_key._to_basic_event(
                KeyPressEvent.KEY_UP, current_modifiers
            )
            events.append(modifier_payload)

        # 4: Add main key up (if itself is not a modifier key)
        if not is_modifier_key:
            events.append(self._to_basic_event(KeyPressEvent.KEY_UP, current_modifiers))

        return events

    @classmethod
    def from_text(
        cls, text: str, ascii_keypress: KeyPressEvent
    ) -> List["KeyEvents.Payload"]:
        """
        Create KeyEvents payloads from a text string, automatically handling special characters and graphemes.

        Args:
            text: The text to convert to key events
            ascii_keypress: The key press event to use for the ASCII characters (default is DOWN_AND_UP)

        Returns:
            List of KeyEvents.Payload objects ready for CDP
        """

        all_payload: List[KeyEvents.Payload] = []

        for grapheme_char in grapheme.graphemes(text):
            if grapheme_char is None or grapheme_char == "":
                continue

            # Handle special characters
            key_events: KeyEvents
            if grapheme_char in ["\n", "\r"]:
                key_events = cls(SpecialKeys.ENTER)
            elif grapheme_char == "\t":
                key_events = cls(SpecialKeys.TAB)
            elif grapheme_char == " ":
                key_events = cls(SpecialKeys.SPACE)
            else:
                key_events = cls(grapheme_char)

            all_payload.extend(
                key_events.to_cdp_events(
                    KeyPressEvent.CHAR
                    if emoji.is_emoji(grapheme_char)
                    else ascii_keypress
                )
            )

        return all_payload

    @classmethod
    def from_mixed_input(
        cls,
        input_sequence: List[
            Union[str, SpecialKeys, Tuple[Union[str, SpecialKeys], KeyModifiers]]
        ],
        ascii_keypress: KeyPressEvent = KeyPressEvent.DOWN_AND_UP,
    ) -> List["KeyEvents.Payload"]:
        """
        Create KeyEvents payloads from a mixed sequence of strings, special keys, and key+modifier combinations.

        Args:
            input_sequence: List containing:
                - str: Regular text (will be processed character by character)
                - SpecialKeys: Special keys (will use DOWN_AND_UP)
                - Tuple[key, modifiers]: Key with modifiers (will use DOWN_AND_UP)
            - priority_keypress: The key press event to use for the ascii characters (default is DOWN_AND_UP)

        Returns:
            List of KeyEvents.Payload objects ready for CDP

        Example:
            >>> KeyEvents.from_mixed_input([
            ...     "Hello ",
            ...     SpecialKeys.ENTER,
            ...     "World",
            ...     SpecialKeys.ARROW_DOWN,
            ...     ("a", KeyModifiers.Ctrl),  # Ctrl+A
            ...     ("c", KeyModifiers.Ctrl),  # Ctrl+C
            ... ],
            ... ascii_keypress=KeyPressEvent.DOWN_AND_UP)
        """
        all_payload: List[KeyEvents.Payload] = []

        for item in input_sequence:
            if isinstance(item, str):
                # Process string character by character
                all_payload.extend(cls.from_text(item, ascii_keypress))
            elif isinstance(item, SpecialKeys):
                # Process special key
                key_events = cls(item)
                all_payload.extend(key_events.to_cdp_events(KeyPressEvent.DOWN_AND_UP))
            elif isinstance(item, tuple) and len(item) == 2:
                # Process key with modifiers
                key, modifiers = item
                key_events = cls(key, modifiers)
                all_payload.extend(key_events.to_cdp_events(KeyPressEvent.DOWN_AND_UP))
            else:
                raise ValueError(f"Unsupported input type: {type(item)}")

        return all_payload
